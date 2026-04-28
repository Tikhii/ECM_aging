#!/usr/bin/env python3
"""
SOP-4.5 IC analysis CLI: RPT C/40 -> (LLI, LAM_PE, LAM_NE) extraction.

Input: aged-cell C/40 discharge CSV + cell_type identifier.
Output: JSON with LLI/LAM_PE/LAM_NE + std + fit_quality + metadata; optional
2x2 diagnostic PNG.

Quality gating per SPEC_ic_analysis.md + ICA-E001/E002/E003 + ICA-W001/W002:
  exit 0   -> pass (RMSE < 15 mV, R^2 >= 0.999, no bound hit)
  exit 100 -> ICA-E001 (input contract: missing column / n<50 / Q range<1.5)
  exit 101 -> ICA-E002 (optimizer non-convergence / non-finite covariance)
  exit 102 -> ICA-E003 (RMSE > 20 mV or R^2 < 0.99)
  exit 103 -> ICA-W001 (marginal: 15-20 mV or 0.99 <= R^2 < 0.999)
  exit 104 -> ICA-W002 (parameter touched search bound, < 1% bound width)

The output JSON is RPT-level provenance, not a spec write-back: LLI/LAM are
RPT-derived data (per SOP §3.2), aggregated downstream into cell_XX_rpt.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libquiv_aging.fitting import (
    PreflightError,
    get_git_commit_hash,
    hash_file,
)
from libquiv_aging.ic_analysis import _load_ic_artifacts, analyze_ic


LIBQUIV_AGING_VERSION = "1.0.0"
ALGORITHM_LABEL = (
    "scipy.optimize.least_squares (trf, bounds=[0,0,0]-[0.3*C0_PE,"
    " 0.3*C0_NE, 0.3*C_nominal] Ah); Hessian covariance (J^T J)^{-1}"
    " * SSE/(N-3); paper Mmeka 2025 quasi-equilibrium V(Q) forward model."
)

RMSE_FAIL_V = 0.020
RMSE_MARGINAL_V = 0.015
R2_FAIL = 0.99
R2_MARGINAL = 0.999
BOUND_PROXIMITY_FRAC = 0.01


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Cannot find project root (no pyproject.toml).")


def _resolve_specs(cell_type: str) -> tuple[Path, Path]:
    root = _project_root()
    material_path = root / "material_specs" / f"{cell_type}.material.json"
    params_path = (
        root / "param_specs" / f"{cell_type}__mmeka2025.params.json"
    )
    if not material_path.exists():
        raise PreflightError(
            "ICA-E001",
            f"material spec 不存在: {material_path}",
            exit_code=100,
        )
    if not params_path.exists():
        raise PreflightError(
            "ICA-E001",
            f"params spec 不存在: {params_path}",
            exit_code=100,
        )
    return material_path, params_path


def _load_aged_csv(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not csv_path.exists():
        raise PreflightError(
            "ICA-E001", f"CSV 文件不存在: {csv_path}", exit_code=100,
        )
    df = pd.read_csv(csv_path)
    missing = [c for c in ("Q_Ah", "V_cell_V") if c not in df.columns]
    if missing:
        raise PreflightError(
            "ICA-E001",
            f"CSV 缺必填列: {missing}; 现有列: {list(df.columns)}",
            exit_code=100,
        )
    Q = df["Q_Ah"].to_numpy(dtype=float)
    V = df["V_cell_V"].to_numpy(dtype=float)
    if len(Q) < 50:
        raise PreflightError(
            "ICA-E001",
            f"CSV 行数不足: {len(Q)} < 50",
            exit_code=100,
        )
    q_range = float(Q.max() - Q.min())
    if q_range < 1.5:
        raise PreflightError(
            "ICA-E001",
            f"Q range 不足: {q_range:.3f} Ah < 1.5 Ah",
            exit_code=100,
        )
    return Q, V


def _check_bounds_hit(
    LLI_Ah: float, LAM_PE_Ah: float, LAM_NE_Ah: float,
    C0_PE_Ah: float, C0_NE_Ah: float, C_nominal_Ah: float,
) -> list[str]:
    """Per SPEC §1.2 ICA-W002: a parameter is bound-hit when its distance to
    either bound is < 1% of the bound width.
    """
    triplets = [
        ("LLI", LLI_Ah, 0.0, 0.3 * C_nominal_Ah),
        ("LAM_PE", LAM_PE_Ah, 0.0, 0.3 * C0_PE_Ah),
        ("LAM_NE", LAM_NE_Ah, 0.0, 0.3 * C0_NE_Ah),
    ]
    flags: list[str] = []
    for name, value, lo, hi in triplets:
        width = hi - lo
        if width <= 0.0:
            continue
        prox = BOUND_PROXIMITY_FRAC * width
        if abs(value - lo) < prox:
            flags.append(f"{name}_lo")
        elif abs(value - hi) < prox:
            flags.append(f"{name}_hi")
    return flags


def _r_squared(V_model: np.ndarray, V_obs: np.ndarray) -> float:
    ss_res = float(np.sum((V_obs - V_model) ** 2))
    ss_tot = float(np.sum((V_obs - np.mean(V_obs)) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


def _validate_optimizer_result(result, stds: tuple[float, float, float]) -> None:
    if not result.converged:
        raise PreflightError(
            "ICA-E002",
            "scipy.optimize.least_squares 未收敛 (status<=0)",
            exit_code=101,
        )
    if not all(np.isfinite(stds)):
        raise PreflightError(
            "ICA-E002",
            f"Hessian 反演返回非有限 std: {stds}",
            exit_code=101,
        )


def _build_output_payload(
    *,
    result, V_obs_aligned: np.ndarray,
    rmse_V: float, r_squared: float,
    is_marginal: bool, bounds_hit: list[str],
    csv_path: Path, cell_type: str,
) -> dict:
    return {
        "LLI_Ah": result.LLI_Ah,
        "LAM_PE_Ah": result.LAM_PE_Ah,
        "LAM_NE_Ah": result.LAM_NE_Ah,
        "LLI_std_Ah": result.LLI_std,
        "LAM_PE_std_Ah": result.LAM_PE_std,
        "LAM_NE_std_Ah": result.LAM_NE_std,
        "fit_quality": {
            "rmse_V": rmse_V,
            "r_squared": r_squared,
            "n_points": result.n_points,
            "converged": result.converged,
            "marginal_quality": is_marginal,
            "bounds_hit": bounds_hit,
        },
        "metadata": {
            "input_file": str(csv_path),
            "cell_type": cell_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "libquiv_aging_version": LIBQUIV_AGING_VERSION,
            "git_commit": get_git_commit_hash(),
            "input_file_hash": "sha256:" + hash_file(csv_path),
            "algorithm": ALGORITHM_LABEL,
        },
    }


def _plot_diagnostic(
    result, V_obs_aligned: np.ndarray, output_path: Path, payload: dict,
) -> None:
    """2x2: V(Q)+model+residual / dQ/dV / DM bar / text summary.

    matplotlib is imported lazily so the core CLI stays plot-free.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(11, 8.5))
    gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.28)

    # (0,0) V(Q) observed + model + residual subplot
    ax_v = fig.add_subplot(gs[0, 0])
    ax_v.plot(result.Q_grid, V_obs_aligned, "k.", markersize=3, label="obs (smoothed)")
    ax_v.plot(result.Q_grid, result.V_model, "r-", linewidth=1.0, label="model")
    ax_v.set_xlabel("Q (Ah)")
    ax_v.set_ylabel("V (V)")
    ax_v.set_title("V(Q): observed vs model")
    ax_v.legend(loc="best", fontsize=8)
    ax_v.grid(alpha=0.3)

    # residual inset
    ax_res = ax_v.inset_axes([0.55, 0.55, 0.4, 0.4])
    ax_res.plot(
        result.Q_grid, (result.V_model - V_obs_aligned) * 1000.0,
        "b-", linewidth=0.8,
    )
    ax_res.axhline(0.0, color="k", linewidth=0.5)
    ax_res.set_title("residual (mV)", fontsize=8)
    ax_res.tick_params(labelsize=7)
    ax_res.grid(alpha=0.3)

    # (0,1) dQ/dV
    ax_dq = fig.add_subplot(gs[0, 1])
    ax_dq.plot(result.Q_grid, result.dQdV_obs, "k-", linewidth=0.8, label="obs")
    ax_dq.plot(result.Q_grid, result.dQdV_model, "r-", linewidth=0.8, label="model")
    ax_dq.set_xlabel("Q (Ah)")
    ax_dq.set_ylabel("dQ/dV (Ah/V)")
    ax_dq.set_title("dQ/dV (diagnostic only, fit on V(Q))")
    ax_dq.legend(loc="best", fontsize=8)
    ax_dq.grid(alpha=0.3)

    # (1,0) DM bar with 1 sigma error bars
    ax_bar = fig.add_subplot(gs[1, 0])
    labels = ["LLI", "LAM_PE", "LAM_NE"]
    values = [result.LLI_Ah, result.LAM_PE_Ah, result.LAM_NE_Ah]
    errs = [result.LLI_std, result.LAM_PE_std, result.LAM_NE_std]
    ax_bar.bar(labels, values, yerr=errs, capsize=6, color=["#3a6fb0", "#b03a3a", "#3aa03a"])
    ax_bar.set_ylabel("Ah")
    ax_bar.set_title("Degradation modes (1 sigma error bar)")
    ax_bar.grid(alpha=0.3, axis="y")
    for i, (v, e) in enumerate(zip(values, errs)):
        ax_bar.text(i, v + e + 0.002, f"{v:.4f}\n+/-{e:.4f}",
                    ha="center", va="bottom", fontsize=8)

    # (1,1) text summary
    ax_txt = fig.add_subplot(gs[1, 1])
    ax_txt.axis("off")
    fq = payload["fit_quality"]
    md = payload["metadata"]
    txt = (
        f"cell_type: {md['cell_type']}\n"
        f"input: {Path(md['input_file']).name}\n"
        f"timestamp: {md['timestamp']}\n"
        f"git: {md['git_commit'][:12]}\n"
        f"hash: {md['input_file_hash']}\n\n"
        f"RMSE: {fq['rmse_V']*1000:.2f} mV\n"
        f"R^2:  {fq['r_squared']:.5f}\n"
        f"n:    {fq['n_points']}\n"
        f"converged: {fq['converged']}\n"
        f"marginal:  {fq['marginal_quality']}\n"
        f"bounds_hit: {fq['bounds_hit'] or 'none'}\n"
    )
    ax_txt.text(0.0, 1.0, txt, family="monospace", va="top", fontsize=9)

    fig.suptitle(
        f"IC analysis: LLI={result.LLI_Ah:.4f} / LAM_PE={result.LAM_PE_Ah:.4f}"
        f" / LAM_NE={result.LAM_NE_Ah:.4f} Ah",
        fontsize=11,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "SOP-4.5 IC analysis: aged C/40 discharge -> "
            "(LLI, LAM_PE, LAM_NE) JSON."
        )
    )
    parser.add_argument("--aged-data", type=Path, required=True,
                        help="RPT C/40 CSV, columns: Q_Ah, V_cell_V.")
    parser.add_argument("--cell-type", type=str, required=True,
                        help="Cell type id; resolves to material_specs/<id>"
                             ".material.json + param_specs/<id>__mmeka2025"
                             ".params.json.")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output JSON path.")
    parser.add_argument("--plot", type=Path, default=None,
                        help="Optional 2x2 diagnostic PNG path.")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose optimizer log to stderr.")
    args = parser.parse_args()

    try:
        return run(args)
    except PreflightError as e:
        print(f"[{e.code}] {e.message}", file=sys.stderr)
        return e.exit_code


def run(args) -> int:
    material_path, params_path = _resolve_specs(args.cell_type)
    Q_obs, V_obs = _load_aged_csv(args.aged_data)

    art = _load_ic_artifacts(material_path, params_path)
    C0_PE_Ah = art["C0_PE_Ah"]
    C0_NE_Ah = art["C0_NE_Ah"]
    C_nominal_Ah = art["C_nominal_Ah"]

    try:
        result = analyze_ic(
            Q_obs, V_obs,
            material_spec_path=material_path,
            params_spec_path=params_path,
            verbose=args.verbose,
        )
    except ValueError as e:
        raise PreflightError("ICA-E001", str(e), exit_code=100) from e
    except RuntimeError as e:
        raise PreflightError("ICA-E002", str(e), exit_code=101) from e

    stds = (result.LAM_PE_std, result.LAM_NE_std, result.LLI_std)
    _validate_optimizer_result(result, stds)

    # analyze_ic returns Q_grid/V_model on the post-deduped grid; we use the
    # smoothed model V vs the model V for residual gating, matching the
    # internal optimizer objective. R^2 is computed against the smoothed obs
    # implicit in result.V_model - residuals (which equals V_smoothed at
    # optimizer convergence). To keep things consistent we recover V_obs
    # aligned to result.Q_grid via interpolation.
    V_obs_aligned = np.interp(result.Q_grid, *_align_with_grid(Q_obs, V_obs))
    rmse_V = result.rmse_V
    r_squared = _r_squared(result.V_model, V_obs_aligned)

    fail_reasons: list[str] = []
    if rmse_V > RMSE_FAIL_V:
        fail_reasons.append(
            f"RMSE={rmse_V*1000:.2f} mV > {RMSE_FAIL_V*1000:.0f} mV"
        )
    if r_squared < R2_FAIL:
        fail_reasons.append(f"R^2={r_squared:.4f} < {R2_FAIL}")
    if fail_reasons:
        raise PreflightError(
            "ICA-E003",
            "; ".join(fail_reasons)
            + ". 检查: 1) 是否真为 C/40 (IR 未消除); 2) graphite stage"
              " features 是否清晰; 3) CSV 单位。",
            exit_code=102,
        )

    is_marginal = (rmse_V > RMSE_MARGINAL_V) or (r_squared < R2_MARGINAL)
    bounds_hit = _check_bounds_hit(
        result.LLI_Ah, result.LAM_PE_Ah, result.LAM_NE_Ah,
        C0_PE_Ah, C0_NE_Ah, C_nominal_Ah,
    )

    payload = _build_output_payload(
        result=result,
        V_obs_aligned=V_obs_aligned,
        rmse_V=rmse_V,
        r_squared=r_squared,
        is_marginal=is_marginal,
        bounds_hit=bounds_hit,
        csv_path=args.aged_data,
        cell_type=args.cell_type,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(payload, f, indent=2)

    if args.plot is not None:
        _plot_diagnostic(result, V_obs_aligned, args.plot, payload)

    print(
        f"[ICA] LLI={result.LLI_Ah:.4f}+/-{result.LLI_std:.4f} Ah, "
        f"LAM_PE={result.LAM_PE_Ah:.4f}+/-{result.LAM_PE_std:.4f} Ah, "
        f"LAM_NE={result.LAM_NE_Ah:.4f}+/-{result.LAM_NE_std:.4f} Ah, "
        f"RMSE={rmse_V*1000:.2f} mV, R^2={r_squared:.5f}, n={result.n_points}"
    )

    if bounds_hit:
        print(
            f"[ICA-W002] 参数命中 search bound: {bounds_hit} "
            f"(<{BOUND_PROXIMITY_FRAC*100:.0f}% bound width). "
            f"详见 docs/07_offline_runbook.md ICA-W002.",
            file=sys.stderr,
        )
        return 104
    if is_marginal:
        print(
            f"[ICA-W001] 拟合质量 marginal (RMSE={rmse_V*1000:.2f} mV, "
            f"R^2={r_squared:.5f}). FIT-4a/b 应放宽该 RPT 数据点权重。",
            file=sys.stderr,
        )
        return 103
    return 0


def _align_with_grid(Q: np.ndarray, V: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sort+dedupe (Q, V) for np.interp consistency with analyze_ic._prepare_grid.

    analyze_ic auto-flips descending Q internally, so result.Q_grid is always
    ascending; we mirror that here so np.interp does not silently misbehave.
    """
    Q = np.asarray(Q, dtype=float)
    V = np.asarray(V, dtype=float)
    if Q[0] > Q[-1]:
        Q = Q[::-1]
        V = V[::-1]
    order = np.argsort(Q, kind="mergesort")
    Q = Q[order]
    V = V[order]
    Q_unique, idx = np.unique(Q, return_index=True)
    return Q_unique, V[idx]


if __name__ == "__main__":
    sys.exit(main())
