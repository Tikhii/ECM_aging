#!/usr/bin/env python3
"""
FIT-2: RC 弛豫电容 C1, C2 的拟合。
对应 PARAMETER_SOP.md §三.2 FIT-2。

输入: 材料 spec + 参数 spec + EXP-B4 GITT 弛豫 CSV
输出: 拟合后的 C1, C2 写回参数 spec, 加 runs/{run_id}/ 工件

CLI 用法见 --help 或 PARAMETER_SOP.md §三.2。

升级路径: --relaxation-model 当前仅 'two_exponential'。
docs/UPGRADE_LITERATURE/fractional_order_RC.md 描述未来分数阶 RC 升级动机。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libquiv_aging.fitting import (
    PreflightError,
    RunArtifactWriter,
    find_params_schema,
    get_git_commit_hash,
    hash_file,
    make_value_with_provenance,
    preflight_csv,
    preflight_material_spec,
    write_back_to_spec,
)
from libquiv_aging.lookup_tables import ResistanceLUTs
from libquiv_aging.relaxation_fitting import get_relaxation_model


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Cannot find project root (no pyproject.toml).")


def _load_params_spec(spec_path: Path) -> dict:
    import json
    with open(spec_path) as f:
        return json.load(f)


def _stoichiometry_from_soc(
    soc: float,
    X0_PE: float, X0_NE: float,
    dX_PE: float, dX_NE: float,
    LR: float, OFS: float,
) -> tuple[float, float]:
    """Map SOC ∈ [0, 1] to fresh-cell electrode stoichiometries (X_PE, X_NE).

    Inverse of the FIT-1 forward model at SOC=0 / SOC=1 endpoints, linear
    interpolation between (consistent with V_cell_model_array's SOC→dQ map
    when V_min/V_max bounds are given). For RC fitting we only need X at
    one SOC (the pulse SOC), so a linear approximation is adequate; LUT
    interpolation is locally smooth.
    """
    X_PE = X0_PE - soc * dX_PE * (1.0 - OFS / 100.0)
    X_NE = X0_NE + soc * dX_NE * LR
    X_PE = float(np.clip(X_PE, 1e-6, 1.0 - 1e-6))
    X_NE = float(np.clip(X_NE, 1e-6, 1.0 - 1e-6))
    return X_PE, X_NE


def _tau_to_R_mapping(
    tau1: float, tau2: float,
    A1: float, A2: float,
    R_NE: float, R_PE: float,
    I_pre: float,
) -> tuple[dict, dict, str]:
    """Map (tau1, tau2) to (C1, C2) via two candidates and pick by amplitude RMSE.

    Two candidates:
      A) tau1 ↔ NE (R1=R_NE), tau2 ↔ PE (R2=R_PE):
         C1 = tau1 / R_NE, C2 = tau2 / R_PE
         Expected amplitudes: A1 ≈ -I_pre * R_NE, A2 ≈ -I_pre * R_PE
      B) tau2 ↔ NE (R1=R_NE), tau1 ↔ PE (R2=R_PE):
         C1 = tau2 / R_NE, C2 = tau1 / R_PE
         Expected amplitudes: A2 ≈ -I_pre * R_NE, A1 ≈ -I_pre * R_PE

    Selection criterion: amplitude residual sum-of-squares
      RSS_A = (A_assigned_to_NE - (-I*R_NE))^2 + (A_assigned_to_PE - (-I*R_PE))^2

    Returns (chosen_candidate, alternate_candidate, mapping_label).
    Each candidate dict has keys: C1, C2, R_NE, R_PE, expected_A_NE,
    expected_A_PE, observed_A_NE, observed_A_PE, amplitude_rss, label.
    """
    expected_A_NE = -I_pre * R_NE
    expected_A_PE = -I_pre * R_PE

    cand_A = {
        "label": "A: tau1->NE, tau2->PE",
        "C1": tau1 / R_NE,
        "C2": tau2 / R_PE,
        "R_NE": R_NE,
        "R_PE": R_PE,
        "expected_A_NE": expected_A_NE,
        "expected_A_PE": expected_A_PE,
        "observed_A_NE": A1,
        "observed_A_PE": A2,
        "amplitude_rss": float(
            (A1 - expected_A_NE) ** 2 + (A2 - expected_A_PE) ** 2
        ),
    }
    cand_B = {
        "label": "B: tau2->NE, tau1->PE",
        "C1": tau2 / R_NE,
        "C2": tau1 / R_PE,
        "R_NE": R_NE,
        "R_PE": R_PE,
        "expected_A_NE": expected_A_NE,
        "expected_A_PE": expected_A_PE,
        "observed_A_NE": A2,
        "observed_A_PE": A1,
        "amplitude_rss": float(
            (A2 - expected_A_NE) ** 2 + (A1 - expected_A_PE) ** 2
        ),
    }

    if cand_A["amplitude_rss"] <= cand_B["amplitude_rss"]:
        return cand_A, cand_B, cand_A["label"]
    return cand_B, cand_A, cand_B["label"]


def main():
    parser = argparse.ArgumentParser(
        description="FIT-2: RC 弛豫电容 C1, C2 的拟合。"
    )
    parser.add_argument("--material-spec", type=Path, required=True,
                        help="材料 spec JSON 文件路径")
    parser.add_argument("--params-spec", type=Path, required=True,
                        help="参数 spec JSON 文件路径")
    parser.add_argument("--exp-b4-csv", type=Path, default=None,
                        help="EXP-B4 GITT 弛豫 CSV (除 --dry-run 外必填)")
    parser.add_argument("--relaxation-model", type=str, default="two_exponential",
                        choices=["two_exponential"],
                        help="弛豫模型 (升级路径预留, 当前仅 'two_exponential')")
    parser.add_argument("--preflight-only", action="store_true",
                        help="仅做前置检查不拟合")
    parser.add_argument("--dry-run", action="store_true",
                        help="用合成数据反演, 验证脚本逻辑")
    parser.add_argument("--require-pending", action="store_true",
                        help="严格模式: C1/C2 必须为 pending_fit 才执行")
    parser.add_argument("--temperature", type=float, default=298.15,
                        help="弛豫数据采集时的参考温度 (K), 仅写入 metadata")
    args = parser.parse_args()

    try:
        if args.dry_run:
            return run_dry_run(args)
        else:
            if args.exp_b4_csv is None and not args.preflight_only:
                print("[FIT-2] --exp-b4-csv 为必填参数 (除 --dry-run 或 "
                      "--preflight-only 模式外)。", file=sys.stderr)
                return 1
            return run_real(args)
    except PreflightError as e:
        print(f"[{e.code}] {e.message}", file=sys.stderr)
        return e.exit_code


def run_real(args) -> int:
    material_spec = preflight_material_spec(
        args.material_spec,
        required_fields=["dX_PE_alawa", "dX_NE_alawa", "X0_PE", "X0_NE",
                         "LR", "OFS", "C_nominal_Ah"],
    )

    params_spec = _load_params_spec(args.params_spec)

    if args.preflight_only and args.exp_b4_csv is None:
        print("[FIT-2] preflight 通过, --preflight-only 模式退出。")
        return 0

    df = preflight_csv(
        args.exp_b4_csv,
        required_columns=["time_s", "voltage_V", "current_pre_step_A",
                          "soc_at_step", "t_step_s"],
        min_rows=10,
    )

    df = df.sort_values("time_s").reset_index(drop=True)
    t_step_s = float(df["t_step_s"].iloc[0])
    if not np.allclose(df["t_step_s"].values, t_step_s):
        raise PreflightError(
            "FIT2-E001",
            "t_step_s 列在所有行中必须一致 (单脉冲弛豫)",
            exit_code=90,
        )
    soc_at_step = float(df["soc_at_step"].iloc[0])
    if not np.allclose(df["soc_at_step"].values, soc_at_step):
        raise PreflightError(
            "FIT2-E001",
            "soc_at_step 列在所有行中必须一致 (单脉冲弛豫)",
            exit_code=90,
        )
    I_pre = float(df["current_pre_step_A"].iloc[0])
    if not np.allclose(df["current_pre_step_A"].values, I_pre):
        raise PreflightError(
            "FIT2-E001",
            "current_pre_step_A 列在所有行中必须一致 (单脉冲弛豫)",
            exit_code=90,
        )

    t_rel = df["time_s"].values - t_step_s
    if t_rel[0] < -1e-6:
        raise PreflightError(
            "FIT2-E001",
            f"弛豫数据不应包含脉冲终止前的样本: t_rel[0]={t_rel[0]:.3f}s",
            exit_code=90,
        )
    t_rel = np.maximum(t_rel, 0.0)
    v = df["voltage_V"].values

    C1_status = params_spec["C1"]["status"]
    C2_status = params_spec["C2"]["status"]
    if C1_status == "fitted" or C2_status == "fitted":
        if args.require_pending:
            print("[FIT-2] C1 或 C2 已 fitted。--require-pending 模式拒绝覆盖。",
                  file=sys.stderr)
            return 1
        else:
            print(f"[WARN] C1 (status={C1_status}) 或 C2 (status={C2_status}) "
                  f"已 fitted, 本次将覆盖。", file=sys.stderr)

    if args.preflight_only:
        print("[FIT-2] preflight 通过, --preflight-only 模式退出。")
        return 0

    project_root = _project_root()
    luts = ResistanceLUTs.from_mat_file(
        str(project_root / params_spec["resistance_mat"])
    )

    fit_fn = get_relaxation_model(args.relaxation_model)
    try:
        fit_result = fit_fn(t_rel, v)
    except RuntimeError as e:
        raise PreflightError("FIT2-E002", str(e), 91) from e

    rmse = fit_result["rmse"]
    r_squared = fit_result["r_squared"]

    RMSE_FAIL = 0.005   # 5 mV
    RMSE_MARGINAL = 0.001  # 1 mV
    R2_FAIL = 0.95

    if rmse > RMSE_FAIL or r_squared < R2_FAIL:
        raise PreflightError(
            "FIT2-E003",
            f"RMSE={rmse*1000:.2f}mV (>{RMSE_FAIL*1000:.0f}mV) 或 "
            f"R²={r_squared:.4f} (<{R2_FAIL}). 残差呈系统性时考虑 C7 升级路径。",
            exit_code=92,
        )

    is_marginal = (RMSE_MARGINAL <= rmse <= RMSE_FAIL)

    X0_PE = material_spec["X0_PE"]["value"]
    X0_NE = material_spec["X0_NE"]["value"]
    dX_PE = material_spec["dX_PE_alawa"]["value"]
    dX_NE = material_spec["dX_NE_alawa"]["value"]
    LR = material_spec["LR"]["value"]
    OFS = material_spec["OFS"]["value"]
    C_nominal = material_spec["C_nominal_Ah"]["value"]

    X_PE, X_NE = _stoichiometry_from_soc(
        soc_at_step, X0_PE, X0_NE, dX_PE, dX_NE, LR, OFS,
    )
    C_rate = I_pre / C_nominal
    R_NE = float(luts.interp_RNE(C_rate, X_NE))
    R_PE = float(luts.interp_RPE(C_rate, X_PE))

    chosen, alternate, mapping_label = _tau_to_R_mapping(
        fit_result["tau1"], fit_result["tau2"],
        fit_result["A1"], fit_result["A2"],
        R_NE, R_PE, I_pre,
    )

    rss_chosen = chosen["amplitude_rss"]
    rss_alt = alternate["amplitude_rss"]
    mapping_marginal = False
    if rss_chosen > 0 and rss_alt > 0:
        ratio = abs(rss_chosen - rss_alt) / max(rss_chosen, rss_alt)
        mapping_marginal = ratio < 0.10

    is_marginal = is_marginal or mapping_marginal

    sigma_tau1 = fit_result["sigma_tau1"]
    sigma_tau2 = fit_result["sigma_tau2"]
    if mapping_label.startswith("A"):
        sigma_C1 = abs(sigma_tau1 / R_NE) if np.isfinite(sigma_tau1) else float("nan")
        sigma_C2 = abs(sigma_tau2 / R_PE) if np.isfinite(sigma_tau2) else float("nan")
    else:
        sigma_C1 = abs(sigma_tau2 / R_NE) if np.isfinite(sigma_tau2) else float("nan")
        sigma_C2 = abs(sigma_tau1 / R_PE) if np.isfinite(sigma_tau1) else float("nan")

    now_iso = datetime.now(timezone.utc).isoformat()
    git_hash = get_git_commit_hash()
    csv_hash = hash_file(args.exp_b4_csv)

    relaxation_metadata = {
        "model": args.relaxation_model,
        "T_ref_K": args.temperature,
        "soc_at_step": soc_at_step,
        "I_pre_A": I_pre,
        "C_rate": C_rate,
        "X_NE": X_NE,
        "X_PE": X_PE,
        "R_NE_LUT": R_NE,
        "R_PE_LUT": R_PE,
        "tau1_s": fit_result["tau1"],
        "tau2_s": fit_result["tau2"],
        "A1_V": fit_result["A1"],
        "A2_V": fit_result["A2"],
        "V_inf_V": fit_result["V_inf"],
        "mapping": mapping_label,
        "alternate_mapping": alternate["label"],
        "alternate_C1": alternate["C1"],
        "alternate_C2": alternate["C2"],
        "amplitude_rss_chosen": rss_chosen,
        "amplitude_rss_alternate": rss_alt,
        "mapping_marginal": mapping_marginal,
    }

    fit_source = f"{args.exp_b4_csv.name}@{csv_hash}"
    C1_provenance = make_value_with_provenance(
        value=round(chosen["C1"], 6), status="fitted",
        fit_step="FIT-2",
        fit_source=fit_source,
        fit_script_version=git_hash,
        fit_r_squared=round(r_squared, 6),
        uncertainty=round(sigma_C1, 6) if np.isfinite(sigma_C1) else None,
        last_modified_at=now_iso,
    )
    C1_provenance["relaxation_metadata"] = relaxation_metadata
    C2_provenance = make_value_with_provenance(
        value=round(chosen["C2"], 6), status="fitted",
        fit_step="FIT-2",
        fit_source=fit_source,
        fit_script_version=git_hash,
        fit_r_squared=round(r_squared, 6),
        uncertainty=round(sigma_C2, 6) if np.isfinite(sigma_C2) else None,
        last_modified_at=now_iso,
    )
    C2_provenance["relaxation_metadata"] = relaxation_metadata

    schema_path = find_params_schema(
        args.params_spec, "params_mmeka2025.schema.v1.json"
    )
    write_back_to_spec(
        args.params_spec, schema_path,
        updates={"C1": C1_provenance, "C2": C2_provenance},
    )

    cell_type = material_spec["cell_type"]
    writer = RunArtifactWriter("fit2", cell_type)
    spec_hash_material = hash_file(args.material_spec)
    spec_hash_params = hash_file(args.params_spec)
    writer.write_config(
        cli_args=vars(args),
        spec_hashes={"material": spec_hash_material, "params": spec_hash_params},
        csv_hash=csv_hash,
    )

    warnings_list = []
    if is_marginal:
        if rmse >= RMSE_MARGINAL and rmse <= RMSE_FAIL:
            warnings_list.append(
                f"[FIT2-W001] RMSE={rmse*1000:.2f}mV 在 marginal 区间 [1, 5] mV"
            )
        if mapping_marginal:
            warnings_list.append(
                f"[FIT2-W001] tau-to-R 映射两候选幅值 RSS 差异 < 10%, "
                f"chosen={mapping_label!r}"
            )

    writer.write_report_md({
        "timestamp": now_iso,
        "cell_type": cell_type,
        "fit_step": "FIT-2",
        "material_spec": str(args.material_spec),
        "exp_csv": str(args.exp_b4_csv),
        "parameters": {
            "C1": {"value": chosen["C1"], "uncertainty": sigma_C1},
            "C2": {"value": chosen["C2"], "uncertainty": sigma_C2},
        },
        "rmse": rmse,
        "r_squared": r_squared,
        "verdict": "marginal" if is_marginal else "pass",
        "converged": True,
        "n_iterations": None,
        "optimizer_message": "scipy.optimize.curve_fit converged",
        "warnings": warnings_list,
    })
    writer.write_diagnostic_json({
        "tau1": fit_result["tau1"], "tau2": fit_result["tau2"],
        "A1": fit_result["A1"], "A2": fit_result["A2"],
        "V_inf": fit_result["V_inf"],
        "sigma_tau1": fit_result["sigma_tau1"],
        "sigma_tau2": fit_result["sigma_tau2"],
        "R_NE": R_NE, "R_PE": R_PE,
        "C_rate": C_rate, "X_NE": X_NE, "X_PE": X_PE,
        "soc_at_step": soc_at_step, "I_pre": I_pre, "T_ref_K": args.temperature,
        "C1_chosen": chosen["C1"], "C2_chosen": chosen["C2"],
        "C1_alternate": alternate["C1"], "C2_alternate": alternate["C2"],
        "mapping": mapping_label, "alternate_mapping": alternate["label"],
        "amplitude_rss_chosen": rss_chosen,
        "amplitude_rss_alternate": rss_alt,
        "rmse": rmse, "r_squared": r_squared,
        "n_data": len(t_rel),
        "t_rel": t_rel.tolist(), "v_observed": v.tolist(),
    })

    sigma_C1_str = f"{sigma_C1:.4f}" if np.isfinite(sigma_C1) else "N/A"
    sigma_C2_str = f"{sigma_C2:.4f}" if np.isfinite(sigma_C2) else "N/A"
    print(f"[FIT-2] 完成。C1={chosen['C1']:.4f}±{sigma_C1_str} F, "
          f"C2={chosen['C2']:.4f}±{sigma_C2_str} F, "
          f"RMSE={rmse*1000:.2f}mV, R²={r_squared:.5f}, mapping={mapping_label}")
    print(f"[FIT-2] Artifacts: {writer.run_dir}")

    if is_marginal:
        for w in warnings_list:
            print(w, file=sys.stderr)
        return 93
    return 0


def run_dry_run(args) -> int:
    """Use synthetic relaxation data to verify script logic."""
    material_spec = preflight_material_spec(
        args.material_spec,
        required_fields=["dX_PE_alawa", "dX_NE_alawa", "X0_PE", "X0_NE",
                         "LR", "OFS", "C_nominal_Ah"],
    )
    params_spec = _load_params_spec(args.params_spec)

    project_root = _project_root()
    luts = ResistanceLUTs.from_mat_file(
        str(project_root / params_spec["resistance_mat"])
    )

    soc = 0.5
    I_pre = 1.0
    C_nominal = material_spec["C_nominal_Ah"]["value"]
    X_PE, X_NE = _stoichiometry_from_soc(
        soc,
        material_spec["X0_PE"]["value"], material_spec["X0_NE"]["value"],
        material_spec["dX_PE_alawa"]["value"], material_spec["dX_NE_alawa"]["value"],
        material_spec["LR"]["value"], material_spec["OFS"]["value"],
    )
    C_rate = I_pre / C_nominal
    R_NE = float(luts.interp_RNE(C_rate, X_NE))
    R_PE = float(luts.interp_RPE(C_rate, X_PE))

    C1_true = 950.0
    C2_true = 3500.0
    tau1_true = R_NE * C1_true
    tau2_true = R_PE * C2_true
    if tau2_true < tau1_true:
        tau1_true, tau2_true = tau2_true, tau1_true

    V_inf = 3.6
    A1 = -I_pre * R_NE
    A2 = -I_pre * R_PE
    rng = np.random.default_rng(42)
    t = np.linspace(0, max(5 * tau2_true, 100.0), 500)
    v_true = V_inf + A1 * np.exp(-t / tau1_true) + A2 * np.exp(-t / tau2_true)
    v_noisy = v_true + rng.normal(0, 1e-4, size=len(t))

    fit_fn = get_relaxation_model(args.relaxation_model)
    fit_result = fit_fn(t, v_noisy)

    chosen, alternate, mapping_label = _tau_to_R_mapping(
        fit_result["tau1"], fit_result["tau2"],
        fit_result["A1"], fit_result["A2"],
        R_NE, R_PE, I_pre,
    )

    C1_err = abs(chosen["C1"] - C1_true) / C1_true
    C2_err = abs(chosen["C2"] - C2_true) / C2_true

    print(f"[FIT-2 dry-run] 真值: C1={C1_true}, C2={C2_true}")
    print(f"[FIT-2 dry-run] 拟合: C1={chosen['C1']:.4f}, C2={chosen['C2']:.4f}")
    print(f"[FIT-2 dry-run] 相对误差: C1={C1_err:.6f}, C2={C2_err:.6f}")
    print(f"[FIT-2 dry-run] tau1={fit_result['tau1']:.4f}s, "
          f"tau2={fit_result['tau2']:.4f}s, "
          f"RMSE={fit_result['rmse']*1000:.4f}mV, "
          f"R²={fit_result['r_squared']:.6f}")
    print(f"[FIT-2 dry-run] mapping={mapping_label}")

    tol = 0.02
    ok = True
    if C1_err > tol:
        print(f"[FAIL] C1 相对误差 {C1_err:.6f} > {tol}", file=sys.stderr)
        ok = False
    if C2_err > tol:
        print(f"[FAIL] C2 相对误差 {C2_err:.6f} > {tol}", file=sys.stderr)
        ok = False

    if ok:
        print("[FIT-2 dry-run] PASS: 反演精度满足要求。")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
