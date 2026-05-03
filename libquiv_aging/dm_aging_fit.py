"""
dm_aging_fit.py
================
FIT-4 老化参数全栈拟合 (DM = Degradation Mechanism).

实现 docs/SPEC_dm_aging.md 描述的 FIT-4a (calendar) / FIT-4b (cycle pre-knee)
/ FIT-4c (knee) 三阶段拟合, 严格按 R2 顺序: 4a → 4b → 4c.

公共 API (各 stage 独立函数, 顶层入口由 scripts/fit_dm_aging.py 串联):

- ``aggregate_rpt_records(cell_dir, stage)``     : 从 cell-dir 聚合 RPT 元数据
- ``fit_calendar_aging(records, bounds=None)``  : FIT-4a, 5 free params
- ``fit_cycle_aging(records, fit4a, bounds)``   : FIT-4b, 3 free params + S3
- ``fit_knee_location(records, fit4a, fit4b, ...)``: FIT-4c, 1 free param k_LP

错误码 (16 条 status=draft @ docs/error_codes_registry.json, since_version=0.7.0):

- FIT4A-E005..W002 / FIT4B-E004..W002 / FIT4C-E003..W002
- E (refuse) raise PreflightError; W (warn) 写入 result.warnings 不阻塞

SSoT 复用:

- aging_kinetics.py — paper Eqs. 36/39/40/41/43-46 速率律 (不重写)
- cell_model.EquivCircuitCell — paper Eqs. 1-30 cell DAE forward (不重写)
- cell_factory.create_cell_from_specs — cell 构造 (不重写)
- fitting.PreflightError / RunArtifactWriter / get_git_commit_hash / hash_file
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import copy
import hashlib
import json
import warnings

import numpy as np
from scipy.optimize import least_squares, minimize_scalar

from libquiv_aging.aging_kinetics import (
    AgingModel,
    LAMParameters,
    PlatingParameters,
    ResistanceAgingParameters,
    SEIParameters,
)
from libquiv_aging.cell_model import EquivCircuitCell
from libquiv_aging.fitting import (
    PreflightError,
    compute_r_squared,
    compute_rmse,
    get_git_commit_hash,
    hash_file,
)


# ============================================================================
# 1. Constants — bounds (SPEC §3.5) + thresholds (SPEC §4)
# ============================================================================

# (lower, upper, x0) per parameter; x0 是 paper_value_NCA_G 起步, bounds 跨 2-3 数量级
_DEFAULT_BOUNDS_FIT4A: dict[str, tuple[float, float, float]] = {
    "k_SEI_cal":   (1e-4, 1.0, 4.2e-2),         # A²·s; paper Table I.b 纠正后值
    "k_LAM_PE_cal": (1e-12, 1e-7, 1.15e-11),    # A
    "gamma_PE":    (0.0, 30.0, 3.18),           # 1/V
    "E_a_SEI":     (40000.0, 80000.0, 55500.0), # J/mol
}
# R_SEI 退出 FIT-4a fittable params (ADR-0016): calendar I=0 模式 J 列恒 0,
# J^TJ 奇异. 来源 = cell.aging.resistance_aging.R_SEI (param_specs literature_default 0.66
# 或 EXP-E IR 脉冲实测覆盖).

_DEFAULT_BOUNDS_FIT4B: dict[str, tuple[float, float, float]] = {
    "k_SEI_cyc":   (1e-4, 1.0, 0.470),          # F = A·s/V
    "k_LAM_PE_cyc": (1e-12, 1e-6, 2.73e-3),     # 无因次 (paper Table I.b)
    "k_LAM_NE_cyc": (1e-14, 1e-8, 3.87e-4),     # 无因次
}

_DEFAULT_BOUNDS_FIT4C: dict[str, tuple[float, float, float]] = {
    "k_LP":        (1e-12, 1e-6, 2.33e-4),      # A
}

# fit_quality 阈值 (SPEC §4)
_R2_PASS = 0.99
_R2_MARGINAL_LOW = 0.95
_RMSE_PASS_AH = 0.02
_RMSE_MARGINAL_HIGH_AH = 0.05

# S3 阈值 (SPEC §3.4 / §8.2)
_S3_PASS = 0.05
_S3_MARGINAL_HIGH = 0.10

# Bounds-hit 边距判据 (SPEC §3.5 "1% 量级" — 起步 0.001 严格)
_BOUNDS_HIT_MARGIN = 1e-3

# ≥30% bad RPT 阈值 (SPEC §3.4 S1)
_BAD_RPT_FRACTION_THRESHOLD = 0.30

# Std weighting epsilon floor (避免 std=0 致除零)
_STD_FLOOR_AH = 1e-6


# ============================================================================
# 2. Dataclasses (SPEC §2.2 schema)
# ============================================================================

@dataclass
class RPTRecord:
    """单个 RPT 点的元数据 + IC 反演输出 + 直接测量 cap_loss.

    fields per SPEC §2.1 + §2.2 输入契约. provenance 路径供 _debug 落盘.
    """
    rpt_index: int
    EFC: float
    time_s: float
    T_storage_K: float
    SOC_storage: float | None
    LLI_Ah: float
    LAM_PE_Ah: float
    LAM_NE_Ah: float
    LLI_std_Ah: float
    LAM_PE_std_Ah: float
    LAM_NE_std_Ah: float
    cap_loss_Ah: float | None
    ica_converged: bool
    ica_marginal: bool
    ica_bounds_hit: list[str]
    phase: str | None  # "calendar" | "cycle" | None
    source_paths: dict


@dataclass
class FIT4ACalendarResult:
    """FIT-4a stage_a_calendar.json schema.

    R_SEI 不在此 dataclass: 退出 FIT-4a fittable params (ADR-0016); 来源
    cell.aging.resistance_aging.R_SEI (param_specs literature_default).
    """
    k_SEI_cal: float
    k_LAM_PE_cal: float
    gamma_PE: float
    E_a_SEI: float
    rate_constants_std: dict
    fit_quality: dict
    warnings: list[str]
    metadata: dict


@dataclass
class FIT4BCycleResult:
    """FIT-4b stage_b_cycle.json schema. cap_loss_self_consistency 是 N3 落点."""
    k_SEI_cyc: float
    k_LAM_PE_cyc: float
    k_LAM_NE_cyc: float
    rate_constants_std: dict
    fit_quality: dict
    cap_loss_self_consistency: dict
    warnings: list[str]
    metadata: dict


@dataclass
class FIT4CKneeResult:
    """FIT-4c stage_c_knee.json schema."""
    k_LP: float
    k_LP_std: float
    knee_efc_predicted: float
    fit_quality: dict
    warnings: list[str]
    metadata: dict


# ============================================================================
# 3. RPT 聚合与质量信号 helpers
# ============================================================================

def aggregate_rpt_records(cell_dir: Path, stage: str) -> list[RPTRecord]:
    """从 ``<cell-dir>/RPT_<NN>/ic_output.json`` + ``<cell-dir>/cell_<id>_rpt.csv`` 聚合.

    SPEC §2.1 输入契约 + §3.4 S1 子步骤. 内存返回 ``list[RPTRecord]``, 不落盘.

    Parameters
    ----------
    cell_dir : Path
        含 ``RPT_<NN>/ic_output.json`` 子目录与 ``cell_*_rpt.csv`` 元数据 CSV 的目录.
    stage : str
        "calendar" | "cycle" | "knee" — 决定必填字段 (calendar 需 SOC_storage, cycle/knee 需 cap_loss_Ah).

    Returns
    -------
    list[RPTRecord]
        按 rpt_index 升序排序.

    Raises
    ------
    PreflightError
        FIT4A-E005 / FIT4B-E004 / FIT4C-E003 — 输入契约违规
        (RPT_<NN> 数量 < 3 / CSV 缺列 / 类型错误).
    """
    cell_dir = Path(cell_dir)
    if not cell_dir.is_dir():
        raise PreflightError(
            _stage_input_code(stage),
            f"cell-dir 不是目录: {cell_dir}",
            exit_code=_stage_input_exit(stage),
        )

    # 扫 RPT_<NN> 子目录
    rpt_dirs = sorted(
        d for d in cell_dir.iterdir()
        if d.is_dir() and d.name.startswith("RPT_")
    )
    if len(rpt_dirs) < 3:
        raise PreflightError(
            _stage_input_code(stage),
            f"RPT_<NN> 子目录数量 {len(rpt_dirs)} < 3 (SPEC §2.1 最小数据契约).",
            exit_code=_stage_input_exit(stage),
        )

    # 找 cell_<id>_rpt.csv
    csv_candidates = list(cell_dir.glob("cell_*_rpt.csv"))
    if len(csv_candidates) != 1:
        raise PreflightError(
            _stage_input_code(stage),
            f"cell_<id>_rpt.csv 应有且仅有 1 份, 实际找到 {len(csv_candidates)} 份.",
            exit_code=_stage_input_exit(stage),
        )
    rpt_csv_path = csv_candidates[0]

    # 解析 CSV (无 pandas 依赖, 用 stdlib csv)
    import csv
    with open(rpt_csv_path) as f:
        rows = list(csv.DictReader(f))
    required_cols = {"rpt_index", "EFC", "time_s", "T_storage_K"}
    if stage == "calendar":
        required_cols.add("SOC_storage")
    if stage in ("cycle", "knee"):
        required_cols.add("cap_loss_Ah")
    if rows:
        missing = required_cols - set(rows[0].keys())
        if missing:
            raise PreflightError(
                _stage_input_code(stage),
                f"cell_<id>_rpt.csv 缺必填列 {sorted(missing)} (stage={stage}).",
                exit_code=_stage_input_exit(stage),
            )

    csv_by_index: dict[int, dict] = {}
    for row in rows:
        try:
            csv_by_index[int(row["rpt_index"])] = row
        except (KeyError, ValueError) as exc:
            raise PreflightError(
                _stage_input_code(stage),
                f"cell_<id>_rpt.csv rpt_index 列类型错误: {exc}",
                exit_code=_stage_input_exit(stage),
            )

    records: list[RPTRecord] = []
    for rpt_dir in rpt_dirs:
        try:
            rpt_idx = int(rpt_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue  # RPT_xx 解析失败的目录跳过, 不视为 fatal
        ic_path = rpt_dir / "ic_output.json"
        if not ic_path.is_file():
            continue
        with open(ic_path) as f:
            ic = json.load(f)
        meta_row = csv_by_index.get(rpt_idx)
        if meta_row is None:
            raise PreflightError(
                _stage_input_code(stage),
                f"RPT_{rpt_idx:02d}/ic_output.json 存在, 但 cell_*_rpt.csv 中无对应 rpt_index={rpt_idx} 行.",
                exit_code=_stage_input_exit(stage),
            )
        fq = ic.get("fit_quality", {})
        records.append(RPTRecord(
            rpt_index=rpt_idx,
            EFC=float(meta_row["EFC"]),
            time_s=float(meta_row["time_s"]),
            T_storage_K=float(meta_row["T_storage_K"]),
            SOC_storage=(float(meta_row["SOC_storage"])
                        if meta_row.get("SOC_storage") not in (None, "") else None),
            LLI_Ah=float(ic["LLI_Ah"]),
            LAM_PE_Ah=float(ic["LAM_PE_Ah"]),
            LAM_NE_Ah=float(ic["LAM_NE_Ah"]),
            LLI_std_Ah=float(ic["LLI_std_Ah"]),
            LAM_PE_std_Ah=float(ic["LAM_PE_std_Ah"]),
            LAM_NE_std_Ah=float(ic["LAM_NE_std_Ah"]),
            cap_loss_Ah=(float(meta_row["cap_loss_Ah"])
                         if meta_row.get("cap_loss_Ah") not in (None, "") else None),
            ica_converged=bool(fq.get("converged", True)),
            ica_marginal=bool(fq.get("marginal_quality", False)),
            ica_bounds_hit=list(fq.get("bounds_hit", [])),
            phase=meta_row.get("phase") or None,
            source_paths={
                "ic_output_json": str(ic_path),
                "cell_rpt_csv": str(rpt_csv_path),
            },
        ))
    records.sort(key=lambda r: r.rpt_index)
    if len(records) < 3:
        raise PreflightError(
            _stage_input_code(stage),
            f"成功聚合的 RPT 记录 {len(records)} < 3.",
            exit_code=_stage_input_exit(stage),
        )
    return records


def _stage_input_code(stage: str) -> str:
    return {"calendar": "FIT4A-E005", "cycle": "FIT4B-E004", "knee": "FIT4C-E003"}[stage]


def _stage_input_exit(stage: str) -> int:
    return {"calendar": 34, "cycle": 43, "knee": 52}[stage]


def _count_upstream_bad_quality(records: list[RPTRecord]) -> float:
    """返回上游 IC 反演不可靠 (bounds_hit 命中或 unconverged) 的 RPT 比例.

    SPEC §3.4 "若 ≥ 30% 的 RPT 命中 bounds_hit 或 converged=False, 抛 FIT4*-E005/E004/E003".
    marginal_quality=True 不计入 (它走 warn 写 warnings 字段不影响权重).
    """
    if not records:
        return 0.0
    bad = sum(
        1 for r in records
        if (not r.ica_converged) or len(r.ica_bounds_hit) > 0
    )
    return bad / len(records)


def _compute_weights(records: list[RPTRecord], field_name: str) -> np.ndarray:
    """返回 1/std² 数组, 1e-6 Ah floor 防除零.

    SPEC §3.4: ``weight_i = 1 / std_i²``; bounds_hit/unconverged RPT 不直接排除, 通过倒数加权.
    """
    stds = np.array(
        [getattr(r, field_name) for r in records],
        dtype=float,
    )
    floored = np.maximum(stds, _STD_FLOOR_AH)
    return 1.0 / (floored ** 2)


# ============================================================================
# 4. Forward simulation helpers
# ============================================================================

def _build_cell_prototype() -> EquivCircuitCell:
    """Build a fresh NCR18650B cell prototype.

    SPEC §3.1 "Forward 通用框架 EquivCircuitCell" + "FIT-4 只调老化 rate constants,
    不动 cell 模型". 当前 release 仅支持 NCR18650B (cell_factory.create_panasonic_ncr18650b);
    cell_type 派发由 子阶段 3 CLI 实装.
    """
    from libquiv_aging.panasonic_ncr18650b import create_panasonic_ncr18650b
    return create_panasonic_ncr18650b()


def _inject_calendar_params(cell: EquivCircuitCell, theta: dict) -> None:
    """把 FIT-4a free params 注入 cell.aging (calendar 段, k_cyc=0).

    Parameters
    ----------
    theta : dict
        含 k_SEI_cal, k_LAM_PE_cal, gamma_PE, E_a_SEI (4 free params; R_SEI
        退出 FIT-4a fittable, ADR-0016).

    Notes
    -----
    cell.aging.resistance_aging.R_SEI 不在此处注入: 来源 param_specs
    literature_default (cell_factory 加载时已 frozen) 或用户在 cell_factory
    load 后通过 EXP-E IR 实测覆盖.
    """
    cell.aging.sei.k_cal = float(theta["k_SEI_cal"])
    cell.aging.sei.k_cyc = 0.0  # calendar: cycle 项关闭
    cell.aging.sei.Ea = float(theta["E_a_SEI"])
    cell.aging.lam_pe.k_cal = float(theta["k_LAM_PE_cal"])
    cell.aging.lam_pe.k_cyc = 0.0
    cell.aging.lam_pe.gamma = float(theta["gamma_PE"])
    # plating + LAM_NE 在 calendar 阶段不激活
    cell.aging.plating.k_LP = 0.0
    cell.aging.lam_ne.k_cal = 0.0
    cell.aging.lam_ne.k_cyc = 0.0


def _inject_cycle_params(
    cell: EquivCircuitCell,
    theta: dict,
    calendar_result: FIT4ACalendarResult,
) -> None:
    """把 FIT-4b free params + frozen 4a 参数 + k_LP=0 注入 cell.aging.

    R2 强制: 4a 的 4 个参数 frozen, k_LP 强制 0.

    Notes
    -----
    cell.aging.resistance_aging.R_SEI 不重新注入 (R_SEI 退出 FIT-4a
    fittable, ADR-0016); 来源 cell_factory 加载时的 literature_default,
    保持 cell.aging.resistance_aging.R_SEI 跨 stage 不变.
    """
    # 4a frozen (R_SEI 不在 frozen list, 见 ADR-0016)
    cell.aging.sei.k_cal = calendar_result.k_SEI_cal
    cell.aging.sei.Ea = calendar_result.E_a_SEI
    cell.aging.lam_pe.k_cal = calendar_result.k_LAM_PE_cal
    cell.aging.lam_pe.gamma = calendar_result.gamma_PE
    # 4b free
    cell.aging.sei.k_cyc = float(theta["k_SEI_cyc"])
    cell.aging.lam_pe.k_cyc = float(theta["k_LAM_PE_cyc"])
    cell.aging.lam_ne.k_cal = 0.0  # paper NCA/Graphite cell 假设
    cell.aging.lam_ne.k_cyc = float(theta["k_LAM_NE_cyc"])
    # k_LP 强制 0 (R2 第二条)
    cell.aging.plating.k_LP = 0.0


def _inject_knee_params(
    cell: EquivCircuitCell,
    k_LP: float,
    calendar_result: FIT4ACalendarResult,
    cycle_result: FIT4BCycleResult,
) -> None:
    """注入完整的 4a + 4b frozen 参数, 仅 k_LP 自由.

    Notes
    -----
    cell.aging.resistance_aging.R_SEI 不重新注入 (R_SEI 退出 FIT-4a
    fittable, ADR-0016); 来源 cell_factory 加载时的 literature_default.
    """
    cell.aging.sei.k_cal = calendar_result.k_SEI_cal
    cell.aging.sei.Ea = calendar_result.E_a_SEI
    cell.aging.lam_pe.k_cal = calendar_result.k_LAM_PE_cal
    cell.aging.lam_pe.gamma = calendar_result.gamma_PE
    cell.aging.sei.k_cyc = cycle_result.k_SEI_cyc
    cell.aging.lam_pe.k_cyc = cycle_result.k_LAM_PE_cyc
    cell.aging.lam_ne.k_cal = 0.0
    cell.aging.lam_ne.k_cyc = cycle_result.k_LAM_NE_cyc
    cell.aging.plating.k_LP = float(k_LP)


def _forward_sim_calendar(
    theta: dict,
    records: list[RPTRecord],
) -> dict[str, np.ndarray]:
    """FIT-4a forward: cell.init(SOC_storage) + cell.CC(I=0, dt) 累积到每个 RPT.

    所有 RPT 假设同 cell 单元 (相同 SOC_storage / T_storage), 按 time_s 单调递增累积积分.
    若 SOC_storage 因 RPT 而变化 (多段 calendar 协议), 在 SOC 切换边界做 init 重置 + 状态续接.

    Returns
    -------
    dict
        keys: "LLI_Ah", "LAM_PE_Ah", "LAM_NE_Ah", "cap_loss_Ah" — 各 N 维 array.
    """
    cell = _build_cell_prototype()
    _inject_calendar_params(cell, theta)
    # 取首条 RPT 的 SOC_storage / T 作初始化
    soc0 = records[0].SOC_storage if records[0].SOC_storage is not None else 0.5
    cell.T_ambient = float(records[0].T_storage_K)
    cell.init(soc0)
    cap_BoL_Ah = cell.C / 3600.0

    LLI = np.zeros(len(records))
    LAM_PE = np.zeros(len(records))
    LAM_NE = np.zeros(len(records))
    cap_loss = np.zeros(len(records))

    t_prev = 0.0
    for i, r in enumerate(records):
        delta_t = r.time_s - t_prev
        if delta_t < 0:
            raise ValueError(
                f"RPT_{r.rpt_index} time_s={r.time_s} 早于前一 RPT, 输入未按时间单调."
            )
        # SOC 切换 (多 SOC calendar 协议) 时手动调整: 当前简化处理 — 假设单 SOC 协议
        # FIXME(subphase 3+): 多 SOC_storage 段需要在切换边界做正确状态续接
        if delta_t > 0:
            cell.T_ambient = float(r.T_storage_K)
            cell.CC(I=0.0, duration_s=float(delta_t))
        LLI[i] = cell.aging_Q_LLI_NE / 3600.0
        LAM_PE[i] = cell.aging_Q_LAM_PE / 3600.0
        LAM_NE[i] = cell.aging_Q_LAM_NE / 3600.0
        cap_loss[i] = cap_BoL_Ah - cell.C / 3600.0
        t_prev = r.time_s
    return {"LLI_Ah": LLI, "LAM_PE_Ah": LAM_PE, "LAM_NE_Ah": LAM_NE, "cap_loss_Ah": cap_loss}


def _drive_cycles_to_efc(
    cell: EquivCircuitCell,
    target_efc: float,
    c_rate: float = 1.0,
) -> None:
    """驱动 cell 至 target_efc (cumulative equivalent full cycles).

    协议: 1C CC discharge 至 V_min → 1C CC charge 至 V_max → 重复. 每完成
    一次完整 DCH+CHG 视作 EFC += 1. cell.t / aging_Q_* / C 由 cell 内部 ODE 自动累积.
    """
    C_nominal_Ah = cell.aging_C0_PE / 3600.0  # 近似 nominal capacity
    I_1C = c_rate * C_nominal_Ah  # [A], 正号 = 放电 (cell.CC 约定)
    # 单 cycle 估上限 ~ 2/c_rate hours 加上 CV 容差; 用 4× 量级的 duration 保险, 配合 break_criterion
    duration_per_phase_s = 4.0 * 3600.0 / max(c_rate, 1e-3)

    # 估算需要多少 cycle 才到 target_efc; cell._aging_calibrate_SOC 在每段后更新 cell.C
    # 用循环 + 实时 EFC 累积 (cell.Q 是外部累积电荷; EFC = total_throughput / C_nom)
    # 简化: 每完成一次 DCH 计 +0.5 EFC, 完成一次 CHG 也计 +0.5 EFC
    efc_so_far = 0.0
    safety_max_cycles = int(np.ceil(target_efc * 2.5)) + 2
    for _ in range(safety_max_cycles):
        if efc_so_far >= target_efc:
            break
        # DCH from current SOC down to V_min
        cell.CC(I=I_1C, duration_s=duration_per_phase_s, break_criterion=f"V < {cell.aging_V_min}")
        efc_so_far += 0.5
        if efc_so_far >= target_efc:
            break
        # CHG back up to V_max
        cell.CC(I=-I_1C, duration_s=duration_per_phase_s, break_criterion=f"V > {cell.aging_V_max}")
        efc_so_far += 0.5


def _forward_sim_cycle(
    theta: dict,
    records: list[RPTRecord],
    calendar_result: FIT4ACalendarResult,
) -> dict[str, np.ndarray]:
    """FIT-4b forward: 1C CC cycling 至每个 RPT EFC, 读 cell.aging_Q_*.

    Returns
    -------
    dict — keys: "LLI_Ah", "LAM_PE_Ah", "LAM_NE_Ah", "cap_loss_Ah" (forward-sim 模型预测)
    """
    cell = _build_cell_prototype()
    _inject_cycle_params(cell, theta, calendar_result)
    cell.T_ambient = float(records[0].T_storage_K)
    cell.init(0.5)  # 中间 SOC 起步, 后续由 cycling 协议覆盖 [V_min, V_max] 全程
    cap_BoL_Ah = cell.C / 3600.0

    LLI = np.zeros(len(records))
    LAM_PE = np.zeros(len(records))
    LAM_NE = np.zeros(len(records))
    cap_loss = np.zeros(len(records))

    efc_prev = 0.0
    for i, r in enumerate(records):
        delta_efc = r.EFC - efc_prev
        if delta_efc < 0:
            raise ValueError(
                f"RPT_{r.rpt_index} EFC={r.EFC} 小于前一 RPT, 输入未按 EFC 单调."
            )
        if delta_efc > 0:
            _drive_cycles_to_efc(cell, target_efc=delta_efc)
        LLI[i] = cell.aging_Q_LLI_NE / 3600.0
        LAM_PE[i] = cell.aging_Q_LAM_PE / 3600.0
        LAM_NE[i] = cell.aging_Q_LAM_NE / 3600.0
        cap_loss[i] = cap_BoL_Ah - cell.C / 3600.0
        efc_prev = r.EFC
    return {"LLI_Ah": LLI, "LAM_PE_Ah": LAM_PE, "LAM_NE_Ah": LAM_NE, "cap_loss_Ah": cap_loss}


def _forward_sim_knee(
    k_LP: float,
    records: list[RPTRecord],
    calendar_result: FIT4ACalendarResult,
    cycle_result: FIT4BCycleResult,
) -> np.ndarray:
    """FIT-4c forward: 完整 4a + 4b + k_LP 候选 → 1C cycle 至各 RPT EFC → cap_loss(EFC).

    Returns
    -------
    np.ndarray — cap_loss_Ah 模型预测序列, shape (N,)
    """
    cell = _build_cell_prototype()
    _inject_knee_params(cell, k_LP, calendar_result, cycle_result)
    cell.T_ambient = float(records[0].T_storage_K)
    cell.init(0.5)
    cap_BoL_Ah = cell.C / 3600.0
    cap_loss = np.zeros(len(records))

    efc_prev = 0.0
    for i, r in enumerate(records):
        delta_efc = r.EFC - efc_prev
        if delta_efc > 0:
            _drive_cycles_to_efc(cell, target_efc=delta_efc)
        cap_loss[i] = cap_BoL_Ah - cell.C / 3600.0
        efc_prev = r.EFC
    return cap_loss


# ============================================================================
# 5. Cost functions (residual stacking with std weighting)
# ============================================================================

def _stack_residuals(
    obs: dict[str, np.ndarray],
    model: dict[str, np.ndarray],
    weights: dict[str, np.ndarray],
) -> np.ndarray:
    """Stack 3*N 残差 (LLI / LAM_PE / LAM_NE), 按 sqrt(weight) 倒数加权."""
    parts = []
    for fld in ("LLI_Ah", "LAM_PE_Ah", "LAM_NE_Ah"):
        sw = np.sqrt(weights[fld])
        parts.append(sw * (obs[fld] - model[fld]))
    return np.concatenate(parts)


def _cost_fn_calendar(x: np.ndarray, *, records, weights, param_names) -> np.ndarray:
    theta = dict(zip(param_names, x))
    obs = {
        "LLI_Ah": np.array([r.LLI_Ah for r in records]),
        "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]),
        "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]),
    }
    model = _forward_sim_calendar(theta, records)
    return _stack_residuals(obs, model, weights)


def _cost_fn_cycle(
    x: np.ndarray, *, records, weights, param_names, calendar_result,
) -> np.ndarray:
    theta = dict(zip(param_names, x))
    obs = {
        "LLI_Ah": np.array([r.LLI_Ah for r in records]),
        "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in records]),
        "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in records]),
    }
    model = _forward_sim_cycle(theta, records, calendar_result)
    return _stack_residuals(obs, model, weights)


def _cost_fn_knee(
    k_LP: float, *, records, calendar_result, cycle_result,
) -> float:
    """1D scalar cost: SSE on cap_loss(EFC) (FIT-4c minimize_scalar)."""
    obs = np.array([r.cap_loss_Ah for r in records], dtype=float)
    model = _forward_sim_knee(float(k_LP), records, calendar_result, cycle_result)
    return float(np.sum((obs - model) ** 2))


# ============================================================================
# 6. Optimizer wrappers
# ============================================================================

def _run_least_squares(
    cost_fn: Callable,
    x0: np.ndarray,
    bounds: tuple[np.ndarray, np.ndarray],
    kwargs: dict,
):
    """scipy least_squares (trf, bounds) wrapper.

    Returns
    -------
    scipy.optimize.OptimizeResult
        含 .x, .jac, .fun (residuals), .status, .active_mask, .success.
    """
    return least_squares(
        cost_fn, x0,
        bounds=bounds,
        method="trf",
        kwargs=kwargs,
        max_nfev=200,
        ftol=1e-8, xtol=1e-8, gtol=1e-8,
    )


def _run_minimize_scalar(
    cost_fn: Callable,
    bounds: tuple[float, float],
    kwargs: dict,
):
    """scipy minimize_scalar (bounded) wrapper for FIT-4c k_LP.

    Returns
    -------
    OptimizeResult — 含 .x, .fun, .success.
    """
    def wrapped(k_LP):
        return cost_fn(k_LP, **kwargs)
    return minimize_scalar(wrapped, bounds=bounds, method="bounded",
                           options={"xatol": 1e-10, "maxiter": 100})


# ============================================================================
# 7. Diagnostic helpers (covariance, bounds_hit, fit_quality, S3)
# ============================================================================

def _estimate_covariance_nvar(
    jac: np.ndarray,
    residuals: np.ndarray,
    n_free: int,
    param_names: list[str],
) -> dict[str, float]:
    """N-var Hessian-based covariance: cov = sigma² * (J^T J)^-1.

    LinAlgError → 全 NaN dict (SPEC §3.2 fallback). N - n_free <= 0 时同样 fallback.
    """
    n_data = len(residuals)
    dof = n_data - n_free
    if dof <= 0:
        return {p: float("nan") for p in param_names}
    sse = float(np.sum(residuals ** 2))
    sigma_sq = sse / dof
    try:
        JTJ = jac.T @ jac
        cov = sigma_sq * np.linalg.inv(JTJ)
    except np.linalg.LinAlgError:
        warnings.warn("Hessian inv 失败, 不确定度 fallback NaN")
        return {p: float("nan") for p in param_names}
    diag = np.diag(cov)
    if np.any(diag < 0) or not np.all(np.isfinite(diag)):
        return {p: float("nan") for p in param_names}
    return {p: float(np.sqrt(d)) for p, d in zip(param_names, diag)}


def _estimate_kLP_std(
    cost_fn: Callable,
    k_LP_opt: float,
    kwargs: dict,
    h: float = 1e-9,
) -> float:
    """1D numerical Hessian for FIT-4c. (d²cost/dk²)^-1 * sigma².

    SPEC §3.2 fallback: 非有限时 NaN.
    """
    try:
        f0 = cost_fn(k_LP_opt, **kwargs)
        f_plus = cost_fn(k_LP_opt + h, **kwargs)
        f_minus = cost_fn(k_LP_opt - h, **kwargs)
    except Exception:
        return float("nan")
    d2 = (f_plus - 2 * f0 + f_minus) / (h ** 2)
    if d2 <= 0 or not np.isfinite(d2):
        return float("nan")
    n_records = max(int(kwargs.get("_n_records", 1)), 2)
    sigma_sq = f0 / max(n_records - 1, 1)
    var = sigma_sq / (d2 / 2.0)
    if var < 0 or not np.isfinite(var):
        return float("nan")
    return float(np.sqrt(var))


def _check_bounds_hit(
    x_opt: np.ndarray,
    bounds: tuple[np.ndarray, np.ndarray],
    param_names: list[str],
    active_mask: np.ndarray | None = None,
) -> list[str]:
    """SPEC §3.5: bounds_hit (距 bound 边界 1‰ 量级 — log/linear 两态判)."""
    hits: list[str] = []
    lb, ub = bounds
    for i, p in enumerate(param_names):
        if active_mask is not None and i < len(active_mask) and active_mask[i] != 0:
            hits.append(p)
            continue
        x = x_opt[i]
        # 跨度 > 100x 视作 log-scale 参数
        if ub[i] > 0 and lb[i] > 0 and ub[i] / lb[i] > 100.0:
            log_span = np.log10(ub[i] / lb[i])
            margin = _BOUNDS_HIT_MARGIN * log_span
            if (np.log10(x / lb[i]) < margin) or (np.log10(ub[i] / x) < margin):
                hits.append(p)
        else:
            span = ub[i] - lb[i]
            margin = _BOUNDS_HIT_MARGIN * span
            if (x - lb[i] < margin) or (ub[i] - x < margin):
                hits.append(p)
    return hits


def _compute_fit_quality(
    obs: dict[str, np.ndarray],
    model: dict[str, np.ndarray],
    n_free: int,
) -> dict:
    """SPEC §4: R² / RMSE per (LLI, LAM_PE, LAM_NE) 独立; pass_overall = 三者都 PASS.

    marginal_quality = 任一在 marginal 区间.
    """
    out: dict = {"n_rpt": len(obs["LLI_Ah"]), "n_free_params": n_free}
    pass_count = 0
    marginal_count = 0
    for fld_short, fld_full in (("LLI", "LLI_Ah"), ("LAM_PE", "LAM_PE_Ah"), ("LAM_NE", "LAM_NE_Ah")):
        residuals = obs[fld_full] - model[fld_full]
        rmse = compute_rmse(residuals)
        r2 = compute_r_squared(model[fld_full], obs[fld_full])
        out[f"rmse_{fld_short}_Ah"] = rmse
        out[f"r2_{fld_short}"] = r2
        is_pass = (r2 > _R2_PASS) and (rmse < _RMSE_PASS_AH)
        is_fail = (r2 < _R2_MARGINAL_LOW) or (rmse > _RMSE_MARGINAL_HIGH_AH)
        if is_pass:
            pass_count += 1
        elif not is_fail:
            marginal_count += 1
    out["pass_overall"] = (pass_count == 3)
    out["marginal_quality"] = (not out["pass_overall"]) and (marginal_count > 0 or pass_count > 0)
    return out


def _compute_fit_quality_cap_loss(
    obs: np.ndarray,
    model: np.ndarray,
    n_free: int,
) -> dict:
    """FIT-4c: 单一 cap_loss(EFC) R²/RMSE. 用于 FIT4C-E005 / W001 判定."""
    residuals = obs - model
    rmse = compute_rmse(residuals)
    r2 = compute_r_squared(model, obs)
    is_pass = (r2 > _R2_PASS) and (rmse < _RMSE_PASS_AH)
    is_fail = (r2 < _R2_MARGINAL_LOW) or (rmse > _RMSE_MARGINAL_HIGH_AH)
    return {
        "rmse_cap_loss_Ah": rmse,
        "r2_cap_loss": r2,
        "n_rpt": len(obs),
        "n_free_params": n_free,
        "pass_overall": is_pass,
        "marginal_quality": (not is_pass) and (not is_fail),
    }


def _check_s3_self_consistency(
    records: list[RPTRecord],
    calendar_result: FIT4ACalendarResult,
    cycle_result: FIT4BCycleResult,
) -> dict:
    """SPEC §3.4 / §8.2: forward-sim cap_loss_model vs cap_loss_obs.

    cap_loss_model 取自 _forward_sim_cycle 的 ``cap_loss_Ah`` 序列 (EquivCircuitCell forward
    跨完整 EFC 时间轴 → cap_BoL - cell.C/3600).

    NOTE: docs/error_codes_registry.json::FIT4B-E007 trigger 文本写的是 "|sum(LLI+LAM_PE+LAM_NE)
    - cap_loss_obs|", 与 SPEC §3.4 / §8.2 的 forward-sim 表述不一致。本实装按 SPEC 算法契约
    走 forward-sim (sum_DMs 检查会因 N3 非线性恒不满足, 不构成有意义的 self-consistency 检查).
    discrepancy 已登记到子阶段 2 报告供下个事实层修订周期处理.
    """
    theta_b = {
        "k_SEI_cyc": cycle_result.k_SEI_cyc,
        "k_LAM_PE_cyc": cycle_result.k_LAM_PE_cyc,
        "k_LAM_NE_cyc": cycle_result.k_LAM_NE_cyc,
    }
    model = _forward_sim_cycle(theta_b, records, calendar_result)
    cap_loss_model = model["cap_loss_Ah"]
    obs = np.array([r.cap_loss_Ah for r in records], dtype=float)
    if np.any(np.isnan(obs)):
        raise PreflightError(
            "FIT4B-E004",
            "S3 cap_loss_self_consistency 需要 cap_loss_Ah 列, 存在 NaN 值.",
            exit_code=43,
        )
    abs_err = np.abs(cap_loss_model - obs)
    rel_err = abs_err / np.maximum(np.abs(obs), 1e-9)
    rel_max = float(np.max(rel_err))
    return {
        "rel_error_max": rel_max,
        "pass": rel_max < _S3_PASS,
        "marginal": _S3_PASS <= rel_max <= _S3_MARGINAL_HIGH,
        "rpt_indices_compared": [int(r.rpt_index) for r in records],
        "cap_loss_model_Ah": [float(v) for v in cap_loss_model],
        "cap_loss_obs_Ah": [float(v) for v in obs],
    }


# ============================================================================
# 8. Metadata helpers
# ============================================================================

def _libquiv_aging_version() -> str:
    try:
        from libquiv_aging import __version__  # type: ignore
        return str(__version__)
    except Exception:
        return "unknown"


def _input_hash_for_records(records: list[RPTRecord]) -> str:
    """SHA256 short hash of source paths + rpt_index + key fields (provenance fingerprint)."""
    h = hashlib.sha256()
    for r in sorted(records, key=lambda x: x.rpt_index):
        payload = (
            f"{r.rpt_index}|{r.EFC}|{r.time_s}|{r.T_storage_K}|"
            f"{r.LLI_Ah}|{r.LAM_PE_Ah}|{r.LAM_NE_Ah}|"
            f"{r.source_paths.get('ic_output_json', '')}"
        )
        h.update(payload.encode("utf-8"))
    return h.hexdigest()[:12]


def _build_metadata(records: list[RPTRecord], algorithm: str) -> dict:
    return {
        "input_hash": _input_hash_for_records(records),
        "git_commit": get_git_commit_hash(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "libquiv_aging_version": _libquiv_aging_version(),
        "algorithm": algorithm,
    }


# ============================================================================
# 9. Public API: fit_calendar_aging  (FIT-4a)
# ============================================================================

def fit_calendar_aging(
    rpt_records: list[RPTRecord],
    bounds: dict | None = None,
) -> FIT4ACalendarResult:
    """FIT-4a — calendar aging 拟合 (4 free params).

    Free: k_SEI_cal, k_LAM_PE_cal, gamma_PE, E_a_SEI (SPEC §3.1, ADR-0016).
    Frozen: cell_factory + Tier I/II/III + R_NE_0 (R4) + R_SEI (来源
    cell.aging.resistance_aging.R_SEI, param_specs literature_default).

    Raises
    ------
    PreflightError
        FIT4A-E005 (输入契约 / ≥30% bad upstream),
        FIT4A-E006 (不收敛 / Hessian 非有限),
        FIT4A-E007 (收敛但 fit_quality FAIL).

    Returns
    -------
    FIT4ACalendarResult
        含 5 个 free param + std + fit_quality + warnings (FIT4A-W001 marginal,
        FIT4A-W002 bounds_hit) + metadata.
    """
    # ---- Preflight: FIT4A-E005 ------------------------------------------
    if len(rpt_records) < 3:
        raise PreflightError("FIT4A-E005",
            f"RPT 数量 {len(rpt_records)} < 3 (SPEC §2.1).", exit_code=34)
    bad_frac = _count_upstream_bad_quality(rpt_records)
    if bad_frac >= _BAD_RPT_FRACTION_THRESHOLD:
        raise PreflightError("FIT4A-E005",
            f"上游 IC 反演 bad RPT 比例 {bad_frac:.2%} >= 30% (bounds_hit + unconverged).",
            exit_code=34)

    # ---- 准备 bounds / x0 / weights -------------------------------------
    bnd = bounds or _DEFAULT_BOUNDS_FIT4A
    param_names = list(bnd.keys())
    lb = np.array([bnd[p][0] for p in param_names], dtype=float)
    ub = np.array([bnd[p][1] for p in param_names], dtype=float)
    x0 = np.array([bnd[p][2] for p in param_names], dtype=float)
    weights = {
        "LLI_Ah":   _compute_weights(rpt_records, "LLI_std_Ah"),
        "LAM_PE_Ah": _compute_weights(rpt_records, "LAM_PE_std_Ah"),
        "LAM_NE_Ah": _compute_weights(rpt_records, "LAM_NE_std_Ah"),
    }

    # ---- 拟合 ------------------------------------------------------------
    try:
        result = _run_least_squares(
            _cost_fn_calendar, x0, (lb, ub),
            kwargs={"records": rpt_records, "weights": weights, "param_names": param_names},
        )
    except Exception as exc:
        raise PreflightError("FIT4A-E006",
            f"least_squares 抛异常: {type(exc).__name__}: {exc}", exit_code=35) from exc

    if not result.success or result.status <= 0:
        raise PreflightError("FIT4A-E006",
            f"least_squares 未收敛: status={result.status}, message={result.message}",
            exit_code=35)

    # ---- 协方差 ----------------------------------------------------------
    std_dict = _estimate_covariance_nvar(
        result.jac, result.fun, n_free=len(param_names), param_names=param_names,
    )
    if any(not np.isfinite(v) for v in std_dict.values()):
        raise PreflightError("FIT4A-E006",
            f"Hessian 协方差非有限 (LinAlgError 或 dof≤0): std={std_dict}",
            exit_code=35)

    # ---- fit_quality -----------------------------------------------------
    theta = dict(zip(param_names, result.x))
    model_final = _forward_sim_calendar(theta, rpt_records)
    obs = {
        "LLI_Ah": np.array([r.LLI_Ah for r in rpt_records]),
        "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in rpt_records]),
        "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in rpt_records]),
    }
    fq = _compute_fit_quality(obs, model_final, n_free=len(param_names))

    bounds_hit = _check_bounds_hit(result.x, (lb, ub), param_names,
                                    active_mask=getattr(result, "active_mask", None))
    fq["bounds_hit"] = bounds_hit

    # ---- E007 / W001 / W002 判 -----------------------------------------
    warnings_list: list[str] = []
    if (not fq["pass_overall"]) and (not fq["marginal_quality"]):
        # FAIL: R² < 0.95 or RMSE > 0.05 — 拒绝
        raise PreflightError("FIT4A-E007",
            f"fit_quality FAIL: R²={[fq[f'r2_{k}'] for k in ['LLI','LAM_PE','LAM_NE']]}, "
            f"RMSE={[fq[f'rmse_{k}_Ah'] for k in ['LLI','LAM_PE','LAM_NE']]}",
            exit_code=36)
    if fq["marginal_quality"]:
        warnings_list.append("FIT4A-W001: fit_quality 在 marginal 区间")
    if bounds_hit:
        warnings_list.append(f"FIT4A-W002: bounds_hit={bounds_hit}")

    # ICA marginal RPT 上游信号传递到 warnings
    ica_marginal_count = sum(1 for r in rpt_records if r.ica_marginal)
    if ica_marginal_count > 0:
        warnings_list.append(
            f"upstream ICA: {ica_marginal_count}/{len(rpt_records)} RPT marginal_quality=True"
        )

    return FIT4ACalendarResult(
        k_SEI_cal=float(result.x[param_names.index("k_SEI_cal")]),
        k_LAM_PE_cal=float(result.x[param_names.index("k_LAM_PE_cal")]),
        gamma_PE=float(result.x[param_names.index("gamma_PE")]),
        E_a_SEI=float(result.x[param_names.index("E_a_SEI")]),
        rate_constants_std=std_dict,
        fit_quality=fq,
        warnings=warnings_list,
        metadata=_build_metadata(rpt_records,
            algorithm="scipy.optimize.least_squares (trf, bounds) + Hessian covariance"),
    )


# ============================================================================
# 10. Public API: fit_cycle_aging  (FIT-4b, with S3)
# ============================================================================

def fit_cycle_aging(
    rpt_records: list[RPTRecord],
    calendar_result: FIT4ACalendarResult,
    bounds: dict | None = None,
) -> FIT4BCycleResult:
    """FIT-4b — cycle pre-knee 拟合 (3 free params + S3 cap_loss self-consistency).

    Free: k_SEI_cyc, k_LAM_PE_cyc, k_LAM_NE_cyc.
    Frozen: 4a 全部输出 + Tier I/II/III + k_LP=0 (R2 强制).

    Raises
    ------
    PreflightError
        FIT4B-E004, E005, E006, E007.
    """
    # ---- Preflight: FIT4B-E004 ------------------------------------------
    if calendar_result is None:
        raise PreflightError("FIT4B-E004",
            "calendar_result 为 None (R2 顺序: 必须先跑完 FIT-4a).", exit_code=43)
    if not calendar_result.fit_quality.get("pass_overall", False) and \
       not calendar_result.fit_quality.get("marginal_quality", False):
        raise PreflightError("FIT4B-E004",
            f"calendar_result.fit_quality FAIL: pass_overall=False, marginal_quality=False; "
            f"不能进入 FIT-4b.", exit_code=43)
    if len(rpt_records) < 3:
        raise PreflightError("FIT4B-E004",
            f"RPT 数量 {len(rpt_records)} < 3.", exit_code=43)
    bad_frac = _count_upstream_bad_quality(rpt_records)
    if bad_frac >= _BAD_RPT_FRACTION_THRESHOLD:
        raise PreflightError("FIT4B-E004",
            f"上游 IC 反演 bad RPT 比例 {bad_frac:.2%} >= 30%.", exit_code=43)
    # cap_loss_Ah 是 S3 必需输入
    if any(r.cap_loss_Ah is None for r in rpt_records):
        raise PreflightError("FIT4B-E004",
            "FIT-4b 需要 cell_<id>_rpt.csv::cap_loss_Ah 列 (S3 N3 落点).",
            exit_code=43)

    # ---- 准备 bounds / x0 / weights -------------------------------------
    bnd = bounds or _DEFAULT_BOUNDS_FIT4B
    param_names = list(bnd.keys())
    lb = np.array([bnd[p][0] for p in param_names], dtype=float)
    ub = np.array([bnd[p][1] for p in param_names], dtype=float)
    x0 = np.array([bnd[p][2] for p in param_names], dtype=float)
    weights = {
        "LLI_Ah":   _compute_weights(rpt_records, "LLI_std_Ah"),
        "LAM_PE_Ah": _compute_weights(rpt_records, "LAM_PE_std_Ah"),
        "LAM_NE_Ah": _compute_weights(rpt_records, "LAM_NE_std_Ah"),
    }

    # ---- 拟合 ------------------------------------------------------------
    try:
        result = _run_least_squares(
            _cost_fn_cycle, x0, (lb, ub),
            kwargs={
                "records": rpt_records, "weights": weights, "param_names": param_names,
                "calendar_result": calendar_result,
            },
        )
    except Exception as exc:
        raise PreflightError("FIT4B-E005",
            f"least_squares 抛异常: {type(exc).__name__}: {exc}", exit_code=44) from exc

    if not result.success or result.status <= 0:
        raise PreflightError("FIT4B-E005",
            f"least_squares 未收敛: status={result.status}, message={result.message}",
            exit_code=44)

    std_dict = _estimate_covariance_nvar(
        result.jac, result.fun, n_free=len(param_names), param_names=param_names,
    )
    if any(not np.isfinite(v) for v in std_dict.values()):
        raise PreflightError("FIT4B-E005",
            f"Hessian 协方差非有限: std={std_dict}", exit_code=44)

    theta = dict(zip(param_names, result.x))
    model_final = _forward_sim_cycle(theta, rpt_records, calendar_result)
    obs = {
        "LLI_Ah": np.array([r.LLI_Ah for r in rpt_records]),
        "LAM_PE_Ah": np.array([r.LAM_PE_Ah for r in rpt_records]),
        "LAM_NE_Ah": np.array([r.LAM_NE_Ah for r in rpt_records]),
    }
    fq = _compute_fit_quality(obs, model_final, n_free=len(param_names))
    bounds_hit = _check_bounds_hit(result.x, (lb, ub), param_names,
                                    active_mask=getattr(result, "active_mask", None))
    fq["bounds_hit"] = bounds_hit

    if (not fq["pass_overall"]) and (not fq["marginal_quality"]):
        raise PreflightError("FIT4B-E006",
            f"fit_quality FAIL: R²={[fq[f'r2_{k}'] for k in ['LLI','LAM_PE','LAM_NE']]}, "
            f"RMSE={[fq[f'rmse_{k}_Ah'] for k in ['LLI','LAM_PE','LAM_NE']]}",
            exit_code=45)

    # ---- 构造 partial result 用于 S3 (cycle 参数已 frozen) -------------
    partial = FIT4BCycleResult(
        k_SEI_cyc=float(result.x[param_names.index("k_SEI_cyc")]),
        k_LAM_PE_cyc=float(result.x[param_names.index("k_LAM_PE_cyc")]),
        k_LAM_NE_cyc=float(result.x[param_names.index("k_LAM_NE_cyc")]),
        rate_constants_std=std_dict,
        fit_quality=fq,
        cap_loss_self_consistency={},
        warnings=[],
        metadata={},
    )
    s3 = _check_s3_self_consistency(rpt_records, calendar_result, partial)

    # ---- E007: S3 FAIL --------------------------------------------------
    if s3["rel_error_max"] > _S3_MARGINAL_HIGH:
        raise PreflightError("FIT4B-E007",
            f"S3 cap_loss_self_consistency FAIL (N3 落点): "
            f"rel_error_max={s3['rel_error_max']:.4f} > {_S3_MARGINAL_HIGH}",
            exit_code=46)

    # ---- W001 / W002 ----------------------------------------------------
    warnings_list: list[str] = []
    s3_marginal = s3["marginal"]
    if fq["marginal_quality"] or s3_marginal:
        msg = "FIT4B-W001:"
        if fq["marginal_quality"]:
            msg += " fit_quality marginal;"
        if s3_marginal:
            msg += f" S3 marginal (rel_error_max={s3['rel_error_max']:.4f});"
        warnings_list.append(msg)
    if bounds_hit:
        warnings_list.append(f"FIT4B-W002: bounds_hit={bounds_hit}")
    ica_marginal_count = sum(1 for r in rpt_records if r.ica_marginal)
    if ica_marginal_count > 0:
        warnings_list.append(
            f"upstream ICA: {ica_marginal_count}/{len(rpt_records)} RPT marginal_quality=True"
        )

    return FIT4BCycleResult(
        k_SEI_cyc=partial.k_SEI_cyc,
        k_LAM_PE_cyc=partial.k_LAM_PE_cyc,
        k_LAM_NE_cyc=partial.k_LAM_NE_cyc,
        rate_constants_std=std_dict,
        fit_quality=fq,
        cap_loss_self_consistency=s3,
        warnings=warnings_list,
        metadata=_build_metadata(rpt_records,
            algorithm="scipy.optimize.least_squares (trf, bounds) + Hessian covariance + S3 forward-sim"),
    )


# ============================================================================
# 11. Public API: fit_knee_location  (FIT-4c, k_LP only)
# ============================================================================

def fit_knee_location(
    rpt_records: list[RPTRecord],
    calendar_result: FIT4ACalendarResult,
    cycle_result: FIT4BCycleResult,
    bounds: dict | None = None,
) -> FIT4CKneeResult:
    """FIT-4c — knee location 拟合 (1 free param k_LP, 1D minimize_scalar).

    Free: k_LP (paper Eq. 39 plating exchange current density 相关).
    Frozen: 4a + 4b 全部输出.

    Raises
    ------
    PreflightError
        FIT4C-E003, E004, E005.
    """
    # ---- Preflight: FIT4C-E003 ------------------------------------------
    if calendar_result is None or cycle_result is None:
        raise PreflightError("FIT4C-E003",
            "calendar_result / cycle_result 为 None (R2 顺序: 必须先跑完 4a + 4b).",
            exit_code=52)
    if len(rpt_records) < 3:
        raise PreflightError("FIT4C-E003",
            f"RPT 数量 {len(rpt_records)} < 3.", exit_code=52)
    if any(r.cap_loss_Ah is None for r in rpt_records):
        raise PreflightError("FIT4C-E003",
            "FIT-4c 需要 cap_loss_Ah 列.", exit_code=52)
    # N3 前置门: 若 cycle_result.cap_loss_self_consistency.pass=False 且 marginal=False, refuse
    s3 = cycle_result.cap_loss_self_consistency or {}
    if s3.get("rel_error_max", 0.0) > _S3_MARGINAL_HIGH:
        raise PreflightError("FIT4C-E003",
            f"cycle_result S3 FAIL (rel_error_max={s3.get('rel_error_max'):.4f}); "
            f"不允许在 N3 violation 下做 knee fit.", exit_code=52)
    bad_frac = _count_upstream_bad_quality(rpt_records)
    if bad_frac >= _BAD_RPT_FRACTION_THRESHOLD:
        raise PreflightError("FIT4C-E003",
            f"上游 IC 反演 bad RPT 比例 {bad_frac:.2%} >= 30%.", exit_code=52)

    # ---- 准备 bounds ----------------------------------------------------
    bnd = bounds or _DEFAULT_BOUNDS_FIT4C
    param_names = ["k_LP"]
    lb = bnd["k_LP"][0]
    ub = bnd["k_LP"][1]

    # ---- 拟合 ------------------------------------------------------------
    kwargs = {
        "records": rpt_records,
        "calendar_result": calendar_result,
        "cycle_result": cycle_result,
    }
    try:
        result = _run_minimize_scalar(_cost_fn_knee, (lb, ub), kwargs=kwargs)
    except Exception as exc:
        raise PreflightError("FIT4C-E004",
            f"minimize_scalar 抛异常: {type(exc).__name__}: {exc}",
            exit_code=53) from exc

    if not result.success:
        raise PreflightError("FIT4C-E004",
            f"minimize_scalar 未收敛: message={getattr(result, 'message', 'unknown')}",
            exit_code=53)

    k_LP_opt = float(result.x)
    k_LP_std = _estimate_kLP_std(_cost_fn_knee, k_LP_opt,
                                  kwargs={**kwargs, "_n_records": len(rpt_records)})
    if not np.isfinite(k_LP_std):
        raise PreflightError("FIT4C-E004",
            f"k_LP_std 非有限 (1D Hessian fallback NaN).", exit_code=53)

    # ---- fit_quality (cap_loss(EFC)) ------------------------------------
    obs = np.array([r.cap_loss_Ah for r in rpt_records], dtype=float)
    model = _forward_sim_knee(k_LP_opt, rpt_records, calendar_result, cycle_result)
    fq = _compute_fit_quality_cap_loss(obs, model, n_free=1)
    bounds_hit = _check_bounds_hit(np.array([k_LP_opt]),
        (np.array([lb]), np.array([ub])), param_names, active_mask=None)
    fq["bounds_hit"] = bounds_hit

    if (not fq["pass_overall"]) and (not fq["marginal_quality"]):
        raise PreflightError("FIT4C-E005",
            f"fit_quality FAIL (cap_loss(EFC)): R²={fq['r2_cap_loss']:.4f}, "
            f"RMSE={fq['rmse_cap_loss_Ah']:.4f} Ah", exit_code=54)

    # ---- knee_efc_predicted: 二阶导极值 (forward 求 cap_loss(EFC) 拐点) -
    # 简化: 在 [min(EFC), 2 * max(EFC)] 网格上取 cap_loss 二阶差分极值
    knee_efc = _predict_knee_efc(k_LP_opt, calendar_result, cycle_result, rpt_records)

    warnings_list: list[str] = []
    if fq["marginal_quality"]:
        warnings_list.append("FIT4C-W001: fit_quality 在 marginal 区间")
    if bounds_hit:
        warnings_list.append(f"FIT4C-W002: k_LP bounds_hit (反复触发 = §S2 升级触发条件)")
    ica_marginal_count = sum(1 for r in rpt_records if r.ica_marginal)
    if ica_marginal_count > 0:
        warnings_list.append(
            f"upstream ICA: {ica_marginal_count}/{len(rpt_records)} RPT marginal_quality=True"
        )

    return FIT4CKneeResult(
        k_LP=k_LP_opt,
        k_LP_std=k_LP_std,
        knee_efc_predicted=float(knee_efc),
        fit_quality=fq,
        warnings=warnings_list,
        metadata=_build_metadata(rpt_records,
            algorithm="scipy.optimize.minimize_scalar (bounded) + 1D numerical Hessian"),
    )


def _predict_knee_efc(
    k_LP: float,
    calendar_result: FIT4ACalendarResult,
    cycle_result: FIT4BCycleResult,
    records: list[RPTRecord],
) -> float:
    """在 [0, 2*max_EFC] 网格上 forward-sim cap_loss(EFC), 取二阶差分最大点作 knee 预测.

    若网格内无明显二阶导极值 (单调减速 → 加速过渡不显著), 返回 NaN.
    """
    max_efc = max(r.EFC for r in records) * 2.0
    n_grid = 30
    efc_grid = np.linspace(max_efc * 0.05, max_efc, n_grid)
    # 临时 records 序列模拟均匀 EFC 网格 forward
    proto_records = [
        RPTRecord(
            rpt_index=i, EFC=float(efc), time_s=0.0,
            T_storage_K=records[0].T_storage_K, SOC_storage=None,
            LLI_Ah=0.0, LAM_PE_Ah=0.0, LAM_NE_Ah=0.0,
            LLI_std_Ah=1.0, LAM_PE_std_Ah=1.0, LAM_NE_std_Ah=1.0,
            cap_loss_Ah=0.0, ica_converged=True, ica_marginal=False, ica_bounds_hit=[],
            phase=None, source_paths={},
        )
        for i, efc in enumerate(efc_grid)
    ]
    try:
        cap_loss_grid = _forward_sim_knee(k_LP, proto_records, calendar_result, cycle_result)
    except Exception:
        return float("nan")
    if len(cap_loss_grid) < 5:
        return float("nan")
    # 二阶差分
    d2 = np.diff(cap_loss_grid, n=2)
    if not np.any(d2 > 0):
        return float("nan")
    knee_idx = int(np.argmax(d2)) + 1  # +1: d2[i] 对齐 efc_grid[i+1]
    return float(efc_grid[knee_idx])
