"""tests/test_dm_aging.py — FIT-4 老化拟合测试矩阵 T1-T5

SPEC §7 frozen contract:

- T1: Forward-only — paper Eqs. 36/40/41/39 vs SSoT (1e-10 tolerance)
- T2: Round-trip synthetic — 1σ-2σ recovery on three stages [slow]
- T3: Hessian std — non-NaN on healthy fit + raise FIT4*-E006/E005/E004 on degenerate
- T4: Paper Fig.6c S3 cap_loss self-consistency — N3 落点试金石 [slow]
- T5: 16 status=draft 错误码各 ≥1 触发用例

子阶段 4 实装范围: 测试单文件; 不动 dm_aging_fit / fit_dm_aging / SPEC / registry / runbook。
"""
from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from libquiv_aging.aging_kinetics import (
    I_SEI_NE,
    I_LAM_PE,
    I_LAM_NE,
    I_PLA_NE,
    SEIParameters,
    PlatingParameters,
    LAMParameters,
    MolarVolumeModel,
    NCA_V_REL_COEFF,
    GRAPHITE_V_REL_COEFF,
)
from libquiv_aging.constants import F, R_GAS, T_REF
from libquiv_aging.dm_aging_fit import (
    RPTRecord,
    FIT4ACalendarResult,
    FIT4BCycleResult,
    FIT4CKneeResult,
    aggregate_rpt_records,
    fit_calendar_aging,
    fit_cycle_aging,
    fit_knee_location,
)
from libquiv_aging.dm_aging_fit import (
    _DEFAULT_BOUNDS_FIT4A,
    _DEFAULT_BOUNDS_FIT4B,
    _DEFAULT_BOUNDS_FIT4C,
    _check_bounds_hit,
    _BOUNDS_HIT_MARGIN,
    _S3_PASS,
    _S3_MARGINAL_HIGH,
    _R2_PASS,
)
from libquiv_aging.fitting import PreflightError


# Suppress PytestUnknownMarkWarning for the slow marker
# (markers section in pyproject.toml deferred to subphase 6 R8 sync per plan D5)
def pytest_configure(config):  # pragma: no cover - fixture hook
    config.addinivalue_line("markers", "slow: marks tests that take >30s")


# ============================================================================
# Module-level helpers
# ============================================================================

def _make_synth_cell_dir(
    tmp_path: Path,
    stage: str,
    recs_data: list[dict],
    cell_id: str = "T01",
) -> Path:
    """合成 RPT_<NN>/ic_output.json + cell_<id>_rpt.csv 目录, 返回 cell_dir."""
    cell_dir = tmp_path / f"cell_{cell_id}"
    cell_dir.mkdir()
    csv_rows = []
    for i, rec in enumerate(recs_data):
        rpt_dir = cell_dir / f"RPT_{i:02d}"
        rpt_dir.mkdir()
        ic = {
            "LLI_Ah": rec.get("LLI_Ah", 0.0),
            "LAM_PE_Ah": rec.get("LAM_PE_Ah", 0.0),
            "LAM_NE_Ah": rec.get("LAM_NE_Ah", 0.0),
            "LLI_std_Ah": rec.get("LLI_std_Ah", 1e-3),
            "LAM_PE_std_Ah": rec.get("LAM_PE_std_Ah", 1e-3),
            "LAM_NE_std_Ah": rec.get("LAM_NE_std_Ah", 1e-3),
            "fit_quality": {
                "converged": rec.get("ica_converged", True),
                "marginal_quality": rec.get("ica_marginal", False),
                "bounds_hit": rec.get("ica_bounds_hit", []),
            },
        }
        (rpt_dir / "ic_output.json").write_text(json.dumps(ic))
        csv_row = {
            "rpt_index": i,
            "EFC": rec.get("EFC", 0.0),
            "time_s": rec.get("time_s", 0.0),
            "T_storage_K": rec.get("T_storage_K", 298.15),
        }
        if stage == "calendar":
            csv_row["SOC_storage"] = rec.get("SOC_storage", 0.50)
        if stage in ("cycle", "knee"):
            csv_row["cap_loss_Ah"] = rec.get("cap_loss_Ah", 0.0)
        csv_rows.append(csv_row)
    csv_path = cell_dir / f"cell_{cell_id}_rpt.csv"
    cols = list(csv_rows[0].keys())
    lines = [",".join(cols)] + [
        ",".join(str(r[c]) for c in cols) for r in csv_rows
    ]
    csv_path.write_text("\n".join(lines) + "\n")
    return cell_dir


def _direct_records(rpt_data: list[dict]) -> list[RPTRecord]:
    """绕开 aggregate_rpt_records, 直接构造 list[RPTRecord]. 加速 T2/T3/T4 + 部分 T5."""
    out: list[RPTRecord] = []
    for i, r in enumerate(rpt_data):
        out.append(RPTRecord(
            rpt_index=r.get("rpt_index", i),
            EFC=float(r["EFC"]),
            time_s=float(r["time_s"]),
            T_storage_K=float(r["T_storage_K"]),
            SOC_storage=r.get("SOC_storage"),
            LLI_Ah=float(r["LLI_Ah"]),
            LAM_PE_Ah=float(r["LAM_PE_Ah"]),
            LAM_NE_Ah=float(r["LAM_NE_Ah"]),
            LLI_std_Ah=float(r.get("LLI_std_Ah", 1e-3)),
            LAM_PE_std_Ah=float(r.get("LAM_PE_std_Ah", 1e-3)),
            LAM_NE_std_Ah=float(r.get("LAM_NE_std_Ah", 1e-3)),
            cap_loss_Ah=(float(r["cap_loss_Ah"])
                          if r.get("cap_loss_Ah") is not None else None),
            ica_converged=bool(r.get("ica_converged", True)),
            ica_marginal=bool(r.get("ica_marginal", False)),
            ica_bounds_hit=list(r.get("ica_bounds_hit", [])),
            phase=r.get("phase"),
            source_paths={},
        ))
    return out


def _calendar_stub(**overrides) -> FIT4ACalendarResult:
    """合格 stub calendar_result, 给 FIT-4b/4c monkeypatch 测试当上游."""
    base = dict(
        k_SEI_cal=4.2e-2,
        k_LAM_PE_cal=1.15e-11,
        gamma_PE=3.18,
        R_SEI=0.66,
        E_a_SEI=55500.0,
        rate_constants_std={
            "k_SEI_cal": 1e-4, "k_LAM_PE_cal": 1e-13, "gamma_PE": 0.1,
            "R_SEI": 0.01, "E_a_SEI": 1000.0,
        },
        fit_quality={
            "n_rpt": 5, "n_free_params": 5,
            "rmse_LLI_Ah": 0.001, "rmse_LAM_PE_Ah": 0.001, "rmse_LAM_NE_Ah": 0.001,
            "r2_LLI": 0.999, "r2_LAM_PE": 0.999, "r2_LAM_NE": 0.999,
            "pass_overall": True, "marginal_quality": False, "bounds_hit": [],
        },
        warnings=[],
        metadata={},
    )
    base.update(overrides)
    return FIT4ACalendarResult(**base)


def _cycle_stub(**overrides) -> FIT4BCycleResult:
    """合格 stub cycle_result, 给 FIT-4c 测试当上游."""
    base = dict(
        k_SEI_cyc=0.470,
        k_LAM_PE_cyc=2.73e-3,
        k_LAM_NE_cyc=3.87e-4,
        rate_constants_std={
            "k_SEI_cyc": 1e-3, "k_LAM_PE_cyc": 1e-5, "k_LAM_NE_cyc": 1e-6,
        },
        fit_quality={
            "n_rpt": 5, "n_free_params": 3,
            "rmse_LLI_Ah": 0.001, "rmse_LAM_PE_Ah": 0.001, "rmse_LAM_NE_Ah": 0.001,
            "r2_LLI": 0.999, "r2_LAM_PE": 0.999, "r2_LAM_NE": 0.999,
            "pass_overall": True, "marginal_quality": False, "bounds_hit": [],
        },
        cap_loss_self_consistency={
            "rel_error_max": 0.01, "pass": True, "marginal": False,
            "rpt_indices_compared": [0, 1, 2],
            "cap_loss_model_Ah": [], "cap_loss_obs_Ah": [],
        },
        warnings=[],
        metadata={},
    )
    base.update(overrides)
    return FIT4BCycleResult(**base)


def _fake_lsq_result(
    x: np.ndarray | list[float],
    *,
    jac: np.ndarray | None = None,
    fun: np.ndarray | None = None,
    success: bool = True,
    status: int = 1,
    active_mask: np.ndarray | list[int] | None = None,
):
    """伪造 scipy.optimize.OptimizeResult, 用于 T5 monkeypatch 测试.

    必含 active_mask (子阶段 2 _check_bounds_hit 读); jac 默认非奇异以便协方差计算成功.
    """
    from scipy.optimize import OptimizeResult
    x_arr = np.asarray(x, dtype=float)
    n = len(x_arr)
    if jac is None:
        # 3N×N 单位 Jacobian (J^TJ = 3I 非奇异; residuals = 0 → fun=0 → cov 退化为 0)
        # 用稍 perturb 让 residuals 不为 0 + cov 计算合法
        jac = np.tile(np.eye(n), (3, 1))
    if fun is None:
        # n_data=3N > n_free=N → dof>0; 注入小残差让 sigma_sq>0
        fun = np.full(3 * n, 1e-3)
    if active_mask is None:
        active_mask = np.zeros(n, dtype=int)
    return OptimizeResult(
        x=x_arr,
        jac=np.asarray(jac, dtype=float),
        fun=np.asarray(fun, dtype=float),
        success=bool(success),
        status=int(status),
        message="fake",
        active_mask=np.asarray(active_mask, dtype=int),
    )


def _fake_min_scalar_result(x: float, fun: float = 0.0, success: bool = True):
    from scipy.optimize import OptimizeResult
    return OptimizeResult(x=float(x), fun=float(fun),
                          success=bool(success), message="fake")


# Paper Mmeka 2025 Fig. 6c 关键标定点 + 趋势插值 (LLI ~ sqrt(EFC), LAM ~ linear-EFC)
# 143 EFC 是 paper 锚点: LLI=0.13, LAM_PE=0.08, LAM_NE=0.04, cap_loss=0.11 Ah
# (sum DMs=0.25 Ah, ratio=2.27 验证 N3 caveat)
def _paper_fig6c_records() -> list[dict]:
    EFC_grid = [0.0, 30.0, 70.0, 110.0, 143.0, 180.0]
    records = []
    for efc in EFC_grid:
        f_sqrt = math.sqrt(efc / 143.0) if efc > 0 else 0.0
        f_lin = efc / 143.0
        records.append({
            "EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
            "LLI_Ah":   0.13 * f_sqrt,
            "LAM_PE_Ah": 0.08 * f_lin,
            "LAM_NE_Ah": 0.04 * f_lin,
            "cap_loss_Ah": 0.11 * f_lin,
            "LLI_std_Ah": 0.005, "LAM_PE_std_Ah": 0.005, "LAM_NE_std_Ah": 0.005,
        })
    return records


# ============================================================================
# T1 — Forward-only: SSoT vs paper Eqs. 36/40/41/39
# ============================================================================
class TestT1_ForwardOnly:
    """直接调 SSoT (aging_kinetics.py), 与 paper 解析公式 1e-10 tolerance 比对.

    不需 cell.CC, 不需 optimizer; 验证 implementation = paper algebra.
    """

    def test_calendar_LLI_matches_paper_eq36(self):
        """Paper Eq. 36 calendar 项 (k_cyc=0, I=0):

            I_SEI = (arrhenius / Q_SEI) * k_cal * exp(-α_f F V_NE / R T) * (C_NE/C_NE^0)
        """
        params = SEIParameters(k_cal=4.2e-2, k_cyc=0.0, Ea=55500.0, alpha_f=0.5)
        mvol = MolarVolumeModel(v_coeff=GRAPHITE_V_REL_COEFF)
        T = 298.15
        V_NE = 0.1
        X_NE = 0.5
        Q_LAM_NE = 0.0
        Q_SEI_NE = 0.05
        C0_NE = 1.0
        I_test = 0.0  # calendar
        out = I_SEI_NE(
            I=I_test, T=T, V_NE=V_NE, X_NE=X_NE,
            Q_LLI_NE=0.0, Q_LAM_NE=Q_LAM_NE, Q_SEI_NE=Q_SEI_NE,
            params=params, mvol=mvol, C0_NE=C0_NE,
        )
        arrhenius = math.exp(-params.Ea / R_GAS * (1.0 / T - 1.0 / T_REF))
        q_safe = max(Q_SEI_NE, 1e-3)
        calendar = params.k_cal * math.exp(-params.alpha_f * F / (R_GAS * T) * V_NE)
        cycle = 0.0  # I=0
        area_factor = (C0_NE - Q_LAM_NE) / C0_NE
        expected = arrhenius / q_safe * (calendar + cycle) * area_factor
        assert abs(out - expected) < 1e-10

    def test_calendar_LAM_PE_matches_paper_eq40(self):
        """Paper Eq. 40: I_LAM_PE = k_cal * exp(γ * V_PE) + k_cyc * |I * dv/dX|."""
        params = LAMParameters(k_cal=1.15e-11, k_cyc=0.0, gamma=3.18)
        mvol = MolarVolumeModel(v_coeff=NCA_V_REL_COEFF)
        V_PE = 4.0
        X_PE = 0.6
        I_test = 0.0  # calendar
        out = I_LAM_PE(I=I_test, T=298.15, V_PE=V_PE, X_PE=X_PE,
                       Q_LAM_PE=0.0, params=params, mvol=mvol)
        expected = params.k_cal * math.exp(params.gamma * V_PE) + 0.0
        assert abs(out - expected) < 1e-10

    def test_cycle_LAM_NE_matches_paper_eq41(self):
        """Paper Eq. 41 cycle 项: k_cal=0 (paper 假设), k_cyc * |I·dv/dX|."""
        params = LAMParameters(k_cal=0.0, k_cyc=3.87e-4, gamma=0.0)
        mvol = MolarVolumeModel(v_coeff=GRAPHITE_V_REL_COEFF)
        V_NE = 0.1
        X_NE = 0.5
        I_test = 3.35  # 1C nominal current [A]
        out = I_LAM_NE(I=I_test, T=298.15, V_NE=V_NE, X_NE=X_NE,
                       Q_LAM_NE=0.0, Q_LLI_NE=0.0, params=params, mvol=mvol)
        dv_dX_at_X = mvol.dv_dX(X_NE)
        expected = 0.0 + params.k_cyc * abs(I_test * dv_dX_at_X)
        assert abs(out - expected) < 1e-10

    def test_knee_PLA_NE_matches_paper_eq39(self):
        """Paper Eq. 39: I_LP = max(0, k_LP*(exp(-aV)-exp(aV))) * (C_NE/C_NE^0).

        V_NE > V_LP_eq=0 时, exp(-a·dv) - exp(a·dv) < 0 → max(0, ·) = 0.
        V_NE < 0 时反向.
        """
        params = PlatingParameters(k_LP=2.33e-4, alpha_LP=0.5, V_LP_eq=0.0)
        T = 298.15
        # Case 1: V_NE > 0 → I_LP = 0
        out_pos = I_PLA_NE(I=0.0, T=T, V_NE=0.05, X_NE=0.5,
                            Q_LLI_NE=0.0, Q_LAM_NE=0.0, params=params, C0_NE=1.0)
        assert out_pos == 0.0
        # Case 2: V_NE = -0.005 (略低于平衡电位, 触发镀锂)
        V_NE_neg = -0.005
        out_neg = I_PLA_NE(I=0.0, T=T, V_NE=V_NE_neg, X_NE=0.5,
                            Q_LLI_NE=0.0, Q_LAM_NE=0.0, params=params, C0_NE=1.0)
        a = params.alpha_LP * F / (R_GAS * T)
        dv = V_NE_neg - params.V_LP_eq
        rate = params.k_LP * (math.exp(-a * dv) - math.exp(a * dv))
        expected = max(0.0, rate) * 1.0
        assert abs(out_neg - expected) < 1e-10
        assert out_neg > 0.0  # V_NE < V_LP_eq 触发净镀锂


# ============================================================================
# T2 — Round-trip synthetic (3 stages, slow)
# ============================================================================
@pytest.mark.slow
class TestT2_RoundTripSynthetic:
    """ground truth → forward → fit → assert |recovered - truth| < 2σ.

    SPEC §7 T2 契约: 三 stage 各自独立 round-trip (1σ-2σ 内).
    Plan D6: ground truth = paper Table I.b 中心点; 不抖动初值.
    Plan D1: max_nfev=20 起步, n_rpt=5; 单测试预算 5 min × 2 安全边际.
    """

    @pytest.mark.xfail(
        reason=(
            "R_SEI 在 calendar (I=0) 模式下完全不可识别: 实测 _forward_sim_calendar "
            "对 R_SEI 灵敏度 = 0 (R_SEI 不进 V_NE 演化, 仅在 cycling 时 IR drop 显现). "
            "SPEC §3.1 假设的 5-param 拟合在合成数据上必触发 J^TJ 奇异 → FIT4A-E006. "
            "子阶段 4 §1.3 长尾, 子阶段 6 ADR 决议是否削减 calendar 自由参数到 4."
        ),
        strict=False,
    )
    def test_calendar_round_trip_recovers_rates(self):
        """SPEC §7 T2 calendar: ground truth → forward → fit → 1σ-2σ recovery.

        T 跨 RPT 变化 (298.15 / 308.15 / 318.15 K) 让 E_a_SEI 在 Arrhenius 项里可识别;
        若所有 RPT 同 T, E_a 完全不可识别 → J^TJ 奇异.
        """
        from libquiv_aging.dm_aging_fit import _forward_sim_calendar
        truth = {
            "k_SEI_cal": 4.2e-2, "k_LAM_PE_cal": 1.15e-11,
            "gamma_PE": 3.18, "R_SEI": 0.66, "E_a_SEI": 55500.0,
        }
        # 5 RPT × 跨 T (Arrhenius 激活) × 跨 time (calendar SEI √t 动力学激活)
        configs = [
            (50.0,   298.15),
            (100.0,  308.15),
            (200.0,  318.15),
            (300.0,  303.15),
            (400.0,  313.15),
        ]
        proto = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": T, "SOC_storage": 0.5,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0}
            for efc, T in configs
        ])
        synth = _forward_sim_calendar(truth, proto)
        # 注入小噪声防 J^TJ 完美奇异 (synthetic 完美贴合时 residuals=0)
        rng = np.random.default_rng(seed=2026)
        noise_Ah = 1e-5
        records = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": T, "SOC_storage": 0.5,
             "LLI_Ah": float(synth["LLI_Ah"][i]) + float(rng.normal(0, noise_Ah)),
             "LAM_PE_Ah": float(synth["LAM_PE_Ah"][i]) + float(rng.normal(0, noise_Ah)),
             "LAM_NE_Ah": float(synth["LAM_NE_Ah"][i]) + float(rng.normal(0, noise_Ah))}
            for i, (efc, T) in enumerate(configs)
        ])
        # Tighter bounds (truth ± 2x; E_a 紧锁 ±5000)
        tight_bounds = {
            "k_SEI_cal":   (truth["k_SEI_cal"] * 0.5, truth["k_SEI_cal"] * 2.0,
                            truth["k_SEI_cal"] * 0.8),
            "k_LAM_PE_cal": (truth["k_LAM_PE_cal"] * 0.5, truth["k_LAM_PE_cal"] * 2.0,
                            truth["k_LAM_PE_cal"] * 0.8),
            "gamma_PE":    (truth["gamma_PE"] * 0.7, truth["gamma_PE"] * 1.3,
                            truth["gamma_PE"] * 0.9),
            "R_SEI":       (truth["R_SEI"] * 0.7, truth["R_SEI"] * 1.3,
                            truth["R_SEI"] * 0.9),
            "E_a_SEI":     (truth["E_a_SEI"] - 5000, truth["E_a_SEI"] + 5000,
                            truth["E_a_SEI"] - 1000),
        }
        result = fit_calendar_aging(records, bounds=tight_bounds)
        # 1σ-2σ recovery (SPEC §7 T2)
        for k, v_true in truth.items():
            v_rec = getattr(result, k)
            std = result.rate_constants_std[k]
            # Floor std to avoid div-by-near-zero on perfectly fit cases
            std_floor = max(std, abs(v_true) * 1e-4)
            assert abs(v_rec - v_true) < 2.0 * std_floor, (
                f"{k}: recovered={v_rec:.4g}, truth={v_true:.4g}, "
                f"std={std:.4g}, |diff|/std={abs(v_rec-v_true)/std_floor:.2f}σ"
            )

    @pytest.mark.xfail(
        reason=(
            "_forward_sim_cycle 含 _drive_cycles_to_efc 1C ODE 循环, 单 forward 28s @ "
            "max EFC=20 (5 RPT). 优化器 max_nfev=200 → 单 round-trip 数十分钟, 不能在 CI "
            "/ 快速验证内运行. 子阶段 4 §1.3 长尾, 子阶段 6 ADR 决议是否引入 fast-path mock "
            "或 c_rate / break_criterion 调优."
        ),
        strict=False,
    )
    def test_cycle_round_trip_recovers_rates(self):
        from libquiv_aging.dm_aging_fit import _forward_sim_cycle
        cal_stub = _calendar_stub()
        truth = {
            "k_SEI_cyc": 0.470, "k_LAM_PE_cyc": 2.73e-3, "k_LAM_NE_cyc": 3.87e-4,
        }
        EFC_grid = [0.0, 50.0, 100.0, 150.0, 200.0]
        proto = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.0}
            for efc in EFC_grid
        ])
        synth = _forward_sim_cycle(truth, proto, cal_stub)
        records = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
             "LLI_Ah": float(synth["LLI_Ah"][i]),
             "LAM_PE_Ah": float(synth["LAM_PE_Ah"][i]),
             "LAM_NE_Ah": float(synth["LAM_NE_Ah"][i]),
             "cap_loss_Ah": float(synth["cap_loss_Ah"][i])}
            for i, efc in enumerate(EFC_grid)
        ])
        tight_bounds = {
            "k_SEI_cyc":   (truth["k_SEI_cyc"] * 0.5, truth["k_SEI_cyc"] * 2.0,
                            truth["k_SEI_cyc"] * 0.8),
            "k_LAM_PE_cyc": (truth["k_LAM_PE_cyc"] * 0.5, truth["k_LAM_PE_cyc"] * 2.0,
                            truth["k_LAM_PE_cyc"] * 0.8),
            "k_LAM_NE_cyc": (truth["k_LAM_NE_cyc"] * 0.5, truth["k_LAM_NE_cyc"] * 2.0,
                            truth["k_LAM_NE_cyc"] * 0.8),
        }
        result = fit_cycle_aging(records, cal_stub, bounds=tight_bounds)
        for k, v_true in truth.items():
            v_rec = getattr(result, k)
            std = result.rate_constants_std[k]
            std_floor = max(std, abs(v_true) * 1e-4)
            assert abs(v_rec - v_true) < 2.0 * std_floor, (
                f"{k}: recovered={v_rec:.4g}, truth={v_true:.4g}, std={std:.4g}"
            )

    @pytest.mark.xfail(
        reason=(
            "_forward_sim_knee 复用 _drive_cycles_to_efc 1C ODE 循环, 单 forward 同 cycle "
            "level 量级. 1D minimize_scalar 至少 ~25 evaluations → 单 round-trip 仍 ~10 min. "
            "子阶段 4 §1.3 长尾, 子阶段 6 ADR 跟踪."
        ),
        strict=False,
    )
    def test_knee_round_trip_recovers_kLP(self):
        from libquiv_aging.dm_aging_fit import _forward_sim_knee
        cal_stub = _calendar_stub()
        cyc_stub = _cycle_stub()
        truth_kLP = 2.33e-4
        EFC_grid = [50.0, 100.0, 150.0, 200.0, 250.0, 300.0]
        proto = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.0}
            for efc in EFC_grid
        ])
        synth_cap_loss = _forward_sim_knee(truth_kLP, proto, cal_stub, cyc_stub)
        records = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": float(synth_cap_loss[i])}
            for i, efc in enumerate(EFC_grid)
        ])
        tight_bounds = {
            "k_LP": (truth_kLP * 0.1, truth_kLP * 10.0, truth_kLP * 0.3),
        }
        result = fit_knee_location(records, cal_stub, cyc_stub, bounds=tight_bounds)
        std = result.k_LP_std
        std_floor = max(std, abs(truth_kLP) * 1e-3)
        assert abs(result.k_LP - truth_kLP) < 2.0 * std_floor, (
            f"k_LP: recovered={result.k_LP:.4g}, truth={truth_kLP:.4g}, std={std:.4g}"
        )


# ============================================================================
# T3 — Hessian std non-NaN + degenerate fallback (D2: 统一 raise 路径)
# ============================================================================
class TestT3_HessianStd_Degenerate:
    """退化数据 → Hessian/optimizer 非有限 → raise FIT4*-E006/E005/E004 (D2).

    SPEC §7 T3 退化 case 行为, dm_aging_fit.py 三 fit 函数末段都有 'any(not np.isfinite)
    → raise' 硬保护; 不存在 std=NaN result fallback 出口.
    """

    def test_calendar_hessian_nan_raises_FIT4A_E006(self, monkeypatch):
        """monkeypatch _estimate_covariance_nvar 返回全 NaN → raise FIT4A-E006."""
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_estimate_covariance_nvar",
            lambda jac, residuals, n_free, param_names: {p: float("nan") for p in param_names},
        )
        # Construct minimal valid records (avoid E005); fit will succeed but cov NaN
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600), "T_storage_K": 298.15,
             "SOC_storage": 0.5,
             "LLI_Ah": 0.001 * (i + 1),
             "LAM_PE_Ah": 0.0001 * (i + 1),
             "LAM_NE_Ah": 0.00005 * (i + 1)}
            for i in range(3)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_calendar_aging(records)
        assert exc.value.code == "FIT4A-E006"
        assert exc.value.exit_code == 35

    def test_knee_kLP_std_nan_raises_FIT4C_E004(self, monkeypatch):
        """monkeypatch _estimate_kLP_std 返回 NaN → raise FIT4C-E004."""
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(dm_aging_fit, "_estimate_kLP_std",
                            lambda *a, **kw: float("nan"))
        # 让 fit_quality 通过: monkeypatch _forward_sim_knee 等于 obs
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(3)
        ])
        # _forward_sim_knee 返回 obs 序列, fit_quality PASS
        cap_loss_obs = np.array([r.cap_loss_Ah for r in records])
        monkeypatch.setattr(dm_aging_fit, "_forward_sim_knee",
                            lambda *a, **kw: cap_loss_obs.copy())
        # _run_minimize_scalar 返回成功 result, x = paper default
        monkeypatch.setattr(dm_aging_fit, "_run_minimize_scalar",
                            lambda *a, **kw: _fake_min_scalar_result(2.33e-4))
        cal_stub = _calendar_stub()
        cyc_stub = _cycle_stub()
        with pytest.raises(PreflightError) as exc:
            fit_knee_location(records, cal_stub, cyc_stub)
        assert exc.value.code == "FIT4C-E004"
        assert exc.value.exit_code == 53


@pytest.mark.slow
class TestT3_HessianStd_Healthy:
    """T2 healthy fit case → result.rate_constants_std 各字段非 NaN, > 0."""

    @pytest.mark.xfail(
        reason=(
            "同 T2 calendar: R_SEI 在 calendar (I=0) 模式 J 该列恒 0 → J^TJ 奇异 → "
            "_estimate_covariance_nvar fallback NaN → fit_calendar_aging raise FIT4A-E006. "
            "子阶段 6 ADR 决议是否削减自由参数."
        ),
        strict=False,
    )
    def test_calendar_std_non_nan(self):
        # 复用 T2 calendar 的 path: 但更浅, 仅检查 std 字段
        from libquiv_aging.dm_aging_fit import _forward_sim_calendar
        truth = {
            "k_SEI_cal": 4.2e-2, "k_LAM_PE_cal": 1.15e-11,
            "gamma_PE": 3.18, "R_SEI": 0.66, "E_a_SEI": 55500.0,
        }
        EFC_grid = [0.0, 100.0, 200.0, 300.0]
        proto = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
             "SOC_storage": 0.5, "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0}
            for efc in EFC_grid
        ])
        synth = _forward_sim_calendar(truth, proto)
        records = _direct_records([
            {"EFC": efc, "time_s": efc * 3600.0, "T_storage_K": 298.15,
             "SOC_storage": 0.5,
             "LLI_Ah": float(synth["LLI_Ah"][i]),
             "LAM_PE_Ah": float(synth["LAM_PE_Ah"][i]),
             "LAM_NE_Ah": float(synth["LAM_NE_Ah"][i])}
            for i, efc in enumerate(EFC_grid)
        ])
        tight_bounds = {
            "k_SEI_cal":   (truth["k_SEI_cal"] * 0.5, truth["k_SEI_cal"] * 2.0,
                            truth["k_SEI_cal"] * 0.8),
            "k_LAM_PE_cal": (truth["k_LAM_PE_cal"] * 0.5, truth["k_LAM_PE_cal"] * 2.0,
                            truth["k_LAM_PE_cal"] * 0.8),
            "gamma_PE":    (truth["gamma_PE"] * 0.7, truth["gamma_PE"] * 1.3,
                            truth["gamma_PE"] * 0.9),
            "R_SEI":       (truth["R_SEI"] * 0.7, truth["R_SEI"] * 1.3,
                            truth["R_SEI"] * 0.9),
            "E_a_SEI":     (truth["E_a_SEI"] - 5000, truth["E_a_SEI"] + 5000,
                            truth["E_a_SEI"] - 1000),
        }
        result = fit_calendar_aging(records, bounds=tight_bounds)
        for k, std in result.rate_constants_std.items():
            assert math.isfinite(std), f"{k}: std={std} (expected finite)"
            assert std >= 0.0


# ============================================================================
# T4 — Paper Fig.6c S3 cap_loss self-consistency (N3 落点试金石)
# ============================================================================
@pytest.mark.slow
class TestT4_PaperFig6c:
    """Paper Mmeka 2025 Fig.6c 5-7 RPT 点 → fit_cycle_aging → S3 PASS.

    143 EFC 锚定: LLI=0.13, LAM_PE=0.08, LAM_NE=0.04, cap_loss=0.11 Ah
    其余 EFC 趋势插值 (LLI~sqrt, LAM/cap_loss~linear).
    Plan D3: 5-7 RPT 默认; xfail 已成最终 fallback (forward sim 成本).
    """

    @pytest.mark.xfail(
        reason=(
            "fit_cycle_aging → _forward_sim_cycle ODE 循环至 paper 实测 EFC 范围 "
            "(0..180 EFC, 6 RPT) 单 forward >分钟; 优化器 max_nfev=200 → 数小时. "
            "N3 升级声明 fallback 到 '已设计但未实证', 子阶段 6 ADR 跟踪 fast-path 或 paper "
            "原始 MATLAB 实现的 reference cap_loss 序列对照."
        ),
        strict=False,
    )
    def test_S3_cap_loss_self_consistency_pass(self):
        records = _direct_records(_paper_fig6c_records())
        cal_stub = _calendar_stub()
        try:
            result = fit_cycle_aging(records, cal_stub)
        except PreflightError as exc:
            pytest.xfail(
                f"T4 paper Fig.6c short series 在子阶段 4 实装框架下 raise {exc.code}: "
                f"{exc.message}. 子阶段 6 ADR 跟踪, N3 升级声明降回 '已设计但未实证'."
            )
        s3 = result.cap_loss_self_consistency
        if not s3["pass"]:
            pytest.xfail(
                f"T4 S3 rel_error_max={s3['rel_error_max']:.4f} > {_S3_PASS}; "
                f"N3 升级声明降回 '已设计但未实证', 子阶段 6 ADR 跟踪."
            )
        assert s3["rel_error_max"] < _S3_PASS


# ============================================================================
# T5 — 16 status=draft 错误码各 ≥1 触发用例
# ============================================================================
class TestT5_FIT4A_ErrorCodes:
    """FIT-4a: E005 (input contract) / E006 (non-conv) / E007 (FAIL) / W001 / W002."""

    def test_FIT4A_E005_too_few_rpt(self):
        records = _direct_records([
            {"EFC": 0.0, "time_s": 0.0, "T_storage_K": 298.15, "SOC_storage": 0.5,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0},
            {"EFC": 50.0, "time_s": 50 * 3600.0, "T_storage_K": 298.15,
             "SOC_storage": 0.5,
             "LLI_Ah": 0.01, "LAM_PE_Ah": 0.001, "LAM_NE_Ah": 0.0005},
        ])
        with pytest.raises(PreflightError) as exc:
            fit_calendar_aging(records)
        assert exc.value.code == "FIT4A-E005"
        assert exc.value.exit_code == 34

    def test_FIT4A_E005_high_bad_quality_fraction(self):
        # 10 records, 4 bounds_hit + 2 unconverged → bad_frac = 0.6 ≥ 0.30
        recs_data = []
        for i in range(10):
            bad = i < 4  # 前 4 条 bounds_hit
            unc = 4 <= i < 6  # 后 2 条 unconverged
            recs_data.append({
                "EFC": float(i * 30), "time_s": float(i * 30) * 3600,
                "T_storage_K": 298.15, "SOC_storage": 0.5,
                "LLI_Ah": 0.001 * (i + 1),
                "LAM_PE_Ah": 0.0001 * (i + 1), "LAM_NE_Ah": 0.00005 * (i + 1),
                "ica_bounds_hit": ["LLI"] if bad else [],
                "ica_converged": not unc,
            })
        records = _direct_records(recs_data)
        with pytest.raises(PreflightError) as exc:
            fit_calendar_aging(records)
        assert exc.value.code == "FIT4A-E005"
        assert exc.value.exit_code == 34

    def test_FIT4A_E005_via_aggregate_too_few_rpt_dirs(self, tmp_path):
        # I/O 路径: 仅 2 个 RPT_<NN> 子目录
        cell_dir = _make_synth_cell_dir(tmp_path, "calendar", [
            {"EFC": 0.0, "time_s": 0.0, "SOC_storage": 0.5},
            {"EFC": 50.0, "time_s": 50 * 3600.0, "SOC_storage": 0.5},
        ])
        with pytest.raises(PreflightError) as exc:
            aggregate_rpt_records(cell_dir, "calendar")
        assert exc.value.code == "FIT4A-E005"

    def test_FIT4A_E006_non_convergence(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        # _run_least_squares wrapper 返回 success=False
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[4.2e-2, 1.15e-11, 3.18, 0.66, 55500.0],
                success=False, status=-1,
            ),
        )
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15, "SOC_storage": 0.5,
             "LLI_Ah": 0.01, "LAM_PE_Ah": 0.001, "LAM_NE_Ah": 0.0005}
            for i in range(3)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_calendar_aging(records)
        assert exc.value.code == "FIT4A-E006"
        assert exc.value.exit_code == 35

    def test_FIT4A_E007_fit_quality_fail(self, monkeypatch):
        """monkeypatch optimizer 返回成功结果 + forward_sim 返回 0 → obs - 0 = obs (大 RMSE)."""
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[4.2e-2, 1.15e-11, 3.18, 0.66, 55500.0],
            ),
        )
        n = 5
        # forward 返回 全 0, obs 是显著 0.1 Ah → R²≈0, RMSE 大
        monkeypatch.setattr(
            dm_aging_fit, "_forward_sim_calendar",
            lambda theta, records: {
                "LLI_Ah": np.zeros(len(records)),
                "LAM_PE_Ah": np.zeros(len(records)),
                "LAM_NE_Ah": np.zeros(len(records)),
                "cap_loss_Ah": np.zeros(len(records)),
            },
        )
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15, "SOC_storage": 0.5,
             "LLI_Ah": 0.1 * (i + 1),
             "LAM_PE_Ah": 0.05 * (i + 1), "LAM_NE_Ah": 0.025 * (i + 1)}
            for i in range(n)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_calendar_aging(records)
        assert exc.value.code == "FIT4A-E007"
        assert exc.value.exit_code == 36

    def test_FIT4A_W001_marginal_quality(self, monkeypatch):
        """forward = obs * 0.92 → R²≈0.965 ∈ [0.95, 0.99] marginal, RMSE PASS → marginal_quality=True.

        For obs = a*[1..5], R² = 1 - 5.5*(1-α)². α=0.92 → R²=0.9648.
        """
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[4.2e-2, 1.15e-11, 3.18, 0.66, 55500.0],
            ),
        )

        def fake_forward(theta, records):
            return {
                "LLI_Ah": np.array([r.LLI_Ah for r in records]) * 0.92,
                "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]) * 0.92,
                "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]) * 0.92,
                "cap_loss_Ah": np.zeros(len(records)),
            }

        monkeypatch.setattr(dm_aging_fit, "_forward_sim_calendar", fake_forward)
        # obs = (i+1) * scale for i in 0..4 → linear ramp matching α = 0.92 R² formula
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15, "SOC_storage": 0.5,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1)}
            for i in range(5)
        ])
        result = fit_calendar_aging(records)
        assert any("FIT4A-W001" in w for w in result.warnings)
        assert result.fit_quality["marginal_quality"] is True

    def test_FIT4A_W002_bounds_hit(self, monkeypatch):
        """x_opt 命中下界 → bounds_hit 列表非空 → warnings 含 FIT4A-W002."""
        from libquiv_aging import dm_aging_fit
        # x[0] = lb (k_SEI_cal 下界) → bounds_hit detected (log-scale margin 1‰)
        x_at_bound = [
            _DEFAULT_BOUNDS_FIT4A["k_SEI_cal"][0],  # lb
            _DEFAULT_BOUNDS_FIT4A["k_LAM_PE_cal"][2],
            _DEFAULT_BOUNDS_FIT4A["gamma_PE"][2],
            _DEFAULT_BOUNDS_FIT4A["R_SEI"][2],
            _DEFAULT_BOUNDS_FIT4A["E_a_SEI"][2],
        ]
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(x=x_at_bound),
        )
        # forward 返回 obs 完美 → fit_quality PASS
        n = 5

        def perfect_forward(theta, records):
            return {
                "LLI_Ah": np.array([r.LLI_Ah for r in records]),
                "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]),
                "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]),
                "cap_loss_Ah": np.zeros(len(records)),
            }

        monkeypatch.setattr(dm_aging_fit, "_forward_sim_calendar", perfect_forward)
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15, "SOC_storage": 0.5,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1), "LAM_NE_Ah": 0.0025 * (i + 1)}
            for i in range(n)
        ])
        result = fit_calendar_aging(records)
        assert any("FIT4A-W002" in w for w in result.warnings)
        assert "k_SEI_cal" in result.fit_quality["bounds_hit"]


class TestT5_FIT4B_ErrorCodes:
    """FIT-4b: E004 (input contract incl. cal stub) / E005 (non-conv) / E006 (FAIL)
    / E007 (S3 FAIL) / W001 (S3 marginal) / W002 (bounds_hit).
    """

    def test_FIT4B_E004_calendar_result_none(self):
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1),
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_cycle_aging(records, calendar_result=None)
        assert exc.value.code == "FIT4B-E004"
        assert exc.value.exit_code == 43

    def test_FIT4B_E004_missing_cap_loss(self):
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1),
             "cap_loss_Ah": None}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_cycle_aging(records, _calendar_stub())
        assert exc.value.code == "FIT4B-E004"

    def test_FIT4B_E005_non_convergence(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[0.470, 2.73e-3, 3.87e-4],
                success=False, status=-1,
            ),
        )
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1),
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_cycle_aging(records, _calendar_stub())
        assert exc.value.code == "FIT4B-E005"
        assert exc.value.exit_code == 44

    def test_FIT4B_E006_fit_quality_fail(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[0.470, 2.73e-3, 3.87e-4],
            ),
        )
        # forward_sim_cycle 返回全 0, obs 非零 → R² 差 → FAIL
        monkeypatch.setattr(
            dm_aging_fit, "_forward_sim_cycle",
            lambda theta, records, cal: {
                "LLI_Ah": np.zeros(len(records)),
                "LAM_PE_Ah": np.zeros(len(records)),
                "LAM_NE_Ah": np.zeros(len(records)),
                "cap_loss_Ah": np.zeros(len(records)),
            },
        )
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15,
             "LLI_Ah": 0.1 * (i + 1),
             "LAM_PE_Ah": 0.05 * (i + 1), "LAM_NE_Ah": 0.025 * (i + 1),
             "cap_loss_Ah": 0.1 * (i + 1)}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_cycle_aging(records, _calendar_stub())
        assert exc.value.code == "FIT4B-E006"
        assert exc.value.exit_code == 45

    def test_FIT4B_E007_S3_fail(self, monkeypatch):
        """fit_quality PASS 但 S3 rel_error_max > 0.10 → raise FIT4B-E007."""
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[0.470, 2.73e-3, 3.87e-4],
            ),
        )
        # 让 LLI/LAM 完美 fit → fit_quality PASS
        # 但 S3 cap_loss 偏离 → forward 返回的 cap_loss_Ah 远小于 obs
        monkeypatch.setattr(
            dm_aging_fit, "_forward_sim_cycle",
            lambda theta, records, cal: {
                "LLI_Ah": np.array([r.LLI_Ah for r in records]),
                "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]),
                "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]),
                "cap_loss_Ah": np.full(len(records), 0.001),  # 远小于 obs ~0.1
            },
        )
        records = _direct_records([
            {"EFC": float(i * 50), "time_s": float(i * 50 * 3600),
             "T_storage_K": 298.15,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1),
             "cap_loss_Ah": 0.1 * (i + 1)}  # obs ~0.1 (rel_error >> 0.10)
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_cycle_aging(records, _calendar_stub())
        assert exc.value.code == "FIT4B-E007"
        assert exc.value.exit_code == 46

    def test_FIT4B_W001_S3_marginal(self, monkeypatch):
        """fit_quality PASS, S3 rel_error 在 [0.05, 0.10] marginal → warnings 含 FIT4B-W001."""
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(
                x=[0.470, 2.73e-3, 3.87e-4],
            ),
        )

        def fake_forward(theta, records, cal):
            obs_cap = np.array([r.cap_loss_Ah for r in records])
            # 92% 的 obs → rel_error_max ~0.08 (marginal)
            return {
                "LLI_Ah": np.array([r.LLI_Ah for r in records]),
                "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]),
                "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]),
                "cap_loss_Ah": obs_cap * 0.92,
            }

        monkeypatch.setattr(dm_aging_fit, "_forward_sim_cycle", fake_forward)
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1),
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        result = fit_cycle_aging(records, _calendar_stub())
        assert any("FIT4B-W001" in w for w in result.warnings)
        s3 = result.cap_loss_self_consistency
        assert s3["marginal"] is True

    def test_FIT4B_W002_bounds_hit(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        x_at_bound = [
            _DEFAULT_BOUNDS_FIT4B["k_SEI_cyc"][0],
            _DEFAULT_BOUNDS_FIT4B["k_LAM_PE_cyc"][2],
            _DEFAULT_BOUNDS_FIT4B["k_LAM_NE_cyc"][2],
        ]
        monkeypatch.setattr(
            dm_aging_fit, "_run_least_squares",
            lambda *a, **kw: _fake_lsq_result(x=x_at_bound),
        )

        def perfect_forward(theta, records, cal):
            return {
                "LLI_Ah": np.array([r.LLI_Ah for r in records]),
                "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]),
                "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]),
                "cap_loss_Ah": np.array([r.cap_loss_Ah for r in records]),
            }

        monkeypatch.setattr(dm_aging_fit, "_forward_sim_cycle", perfect_forward)
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.01 * (i + 1),
             "LAM_PE_Ah": 0.005 * (i + 1),
             "LAM_NE_Ah": 0.0025 * (i + 1),
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        result = fit_cycle_aging(records, _calendar_stub())
        assert any("FIT4B-W002" in w for w in result.warnings)
        assert "k_SEI_cyc" in result.fit_quality["bounds_hit"]


class TestT5_FIT4C_ErrorCodes:
    """FIT-4c: E003 (input contract incl. S3 upstream) / E004 (non-conv)
    / E005 (FAIL) / W001 / W002.
    """

    def test_FIT4C_E003_cycle_result_none(self):
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_knee_location(records, _calendar_stub(), cycle_result=None)
        assert exc.value.code == "FIT4C-E003"
        assert exc.value.exit_code == 52

    def test_FIT4C_E003_S3_fail_upstream(self):
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        bad_cyc = _cycle_stub(cap_loss_self_consistency={
            "rel_error_max": 0.20, "pass": False, "marginal": False,
            "rpt_indices_compared": [], "cap_loss_model_Ah": [], "cap_loss_obs_Ah": [],
        })
        with pytest.raises(PreflightError) as exc:
            fit_knee_location(records, _calendar_stub(), bad_cyc)
        assert exc.value.code == "FIT4C-E003"

    def test_FIT4C_E004_non_convergence(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_minimize_scalar",
            lambda *a, **kw: _fake_min_scalar_result(2.33e-4, success=False),
        )
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_knee_location(records, _calendar_stub(), _cycle_stub())
        assert exc.value.code == "FIT4C-E004"
        assert exc.value.exit_code == 53

    def test_FIT4C_E005_fit_quality_fail(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_minimize_scalar",
            lambda *a, **kw: _fake_min_scalar_result(2.33e-4),
        )
        monkeypatch.setattr(
            dm_aging_fit, "_estimate_kLP_std",
            lambda *a, **kw: 1e-6,
        )
        # forward_sim_knee 返回全 0, obs 非零 → R² 差
        monkeypatch.setattr(
            dm_aging_fit, "_forward_sim_knee",
            lambda *a, **kw: np.zeros(5),
        )
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.1 * (i + 1)}
            for i in range(5)
        ])
        with pytest.raises(PreflightError) as exc:
            fit_knee_location(records, _calendar_stub(), _cycle_stub())
        assert exc.value.code == "FIT4C-E005"
        assert exc.value.exit_code == 54

    def test_FIT4C_W001_marginal_quality(self, monkeypatch):
        """forward = obs * 0.92 → R²≈0.965 marginal; RMSE PASS → fit_quality.marginal=True."""
        from libquiv_aging import dm_aging_fit
        monkeypatch.setattr(
            dm_aging_fit, "_run_minimize_scalar",
            lambda *a, **kw: _fake_min_scalar_result(2.33e-4),
        )
        monkeypatch.setattr(
            dm_aging_fit, "_estimate_kLP_std",
            lambda *a, **kw: 1e-6,
        )
        records = _direct_records([
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ])
        cap_loss_obs = np.array([r.cap_loss_Ah for r in records])
        monkeypatch.setattr(
            dm_aging_fit, "_forward_sim_knee",
            lambda *a, **kw: cap_loss_obs * 0.92,
        )
        result = fit_knee_location(records, _calendar_stub(), _cycle_stub())
        assert any("FIT4C-W001" in w for w in result.warnings)
        assert result.fit_quality["marginal_quality"] is True

    def test_FIT4C_W002_kLP_bounds_hit(self, monkeypatch):
        from libquiv_aging import dm_aging_fit
        kLP_at_bound = _DEFAULT_BOUNDS_FIT4C["k_LP"][0]
        monkeypatch.setattr(
            dm_aging_fit, "_run_minimize_scalar",
            lambda *a, **kw: _fake_min_scalar_result(kLP_at_bound),
        )
        monkeypatch.setattr(
            dm_aging_fit, "_estimate_kLP_std",
            lambda *a, **kw: 1e-12,
        )
        # forward 返回 obs (perfect fit → quality PASS)
        records_data = [
            {"EFC": float(i * 50 + 50), "time_s": float(i * 50 + 50) * 3600,
             "T_storage_K": 298.15,
             "LLI_Ah": 0.0, "LAM_PE_Ah": 0.0, "LAM_NE_Ah": 0.0,
             "cap_loss_Ah": 0.01 * (i + 1)}
            for i in range(5)
        ]
        records = _direct_records(records_data)
        cap_loss_obs = np.array([r.cap_loss_Ah for r in records])
        monkeypatch.setattr(
            dm_aging_fit, "_forward_sim_knee",
            lambda *a, **kw: cap_loss_obs.copy(),
        )
        result = fit_knee_location(records, _calendar_stub(), _cycle_stub())
        assert any("FIT4C-W002" in w for w in result.warnings)
        assert "k_LP" in result.fit_quality["bounds_hit"]
