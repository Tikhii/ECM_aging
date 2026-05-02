#!/usr/bin/env python3
"""
FIT-4 DM aging fit CLI: cell-dir aggregated RPT -> stage_a/b/c result JSON.

Implements the contract in ``docs/SPEC_dm_aging.md`` §2 (data contract) +
§2.3 (debug snapshot) + §5 (sub-fits sequencing). Wraps the four public
APIs of ``libquiv_aging.dm_aging_fit``:

  - aggregate_rpt_records(cell_dir, stage)
  - fit_calendar_aging(records)
  - fit_cycle_aging(records, calendar_result)
  - fit_knee_location(records, calendar_result, cycle_result)

Output layout (``<out>/``):
  - fit4a_calendar_result.json      # FIT4ACalendarResult
  - fit4b_cycle_result.json         # FIT4BCycleResult (含 cap_loss_self_consistency)
  - fit4c_knee_result.json          # FIT4CKneeResult
  - _debug/<error_code>_<UTC_ts>.json   (E-code; W-code 仅 --debug-on-warning)
  - _intermediate/rpt_records_<stage>.json   (--save-intermediate 时)
  - fit4{a,b,c}_*_diagnostic.png    (--no-png 关闭时跳过)

Exit codes (per docs/error_codes_registry.json::script_behavior.exit_code):
  0   pass
  34  FIT4A-E005   |  37  FIT4A-W001   |  38  FIT4A-W002
  35  FIT4A-E006   |
  36  FIT4A-E007   |
  43  FIT4B-E004   |  47  FIT4B-W001   |  48  FIT4B-W002
  44  FIT4B-E005   |
  45  FIT4B-E006   |
  46  FIT4B-E007   |
  52  FIT4C-E003   |  55  FIT4C-W001   |  56  FIT4C-W002
  53  FIT4C-E004   |
  54  FIT4C-E005   |

Multi-stage --stage all: 任一 stage E-code -> 后续 stage 跳过, exit_code 取
最先 fail 的 E-code; 若全 stage PASS/W-only, 取所有 stage W-code 的 max。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libquiv_aging.dm_aging_fit import (
    FIT4ACalendarResult,
    FIT4BCycleResult,
    FIT4CKneeResult,
    RPTRecord,
    aggregate_rpt_records,
    fit_calendar_aging,
    fit_cycle_aging,
    fit_knee_location,
)
from libquiv_aging.fitting import PreflightError, get_git_commit_hash


LIBQUIV_AGING_VERSION = "0.7.0"

_RESULT_FILENAMES = {
    "calendar": "fit4a_calendar_result.json",
    "cycle":    "fit4b_cycle_result.json",
    "knee":     "fit4c_knee_result.json",
}

_PNG_FILENAMES = {
    "calendar": "fit4a_calendar_diagnostic.png",
    "cycle":    "fit4b_cycle_diagnostic.png",
    "knee":     "fit4c_knee_diagnostic.png",
}

# (W001 exit, W002 exit) per stage
_W_EXIT_BY_STAGE = {
    "calendar": (37, 38),
    "cycle":    (47, 48),
    "knee":     (55, 56),
}


# ============================================================================
# Run context (mutable state for debug snapshot on PreflightError)
# ============================================================================

class _RunCtx:
    """Tracks current stage / records / x0 so the PreflightError handler can
    populate the debug snapshot's input_summary / initial_guess fields.
    """
    def __init__(self) -> None:
        self.stage: str | None = None
        self.records: list[RPTRecord] | None = None
        self.initial_guess: dict | None = None
        self.cell_dir: Path | None = None


# ============================================================================
# Debug snapshot (SPEC §2.3 schema)
# ============================================================================

def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rpt_records_brief(records: list[RPTRecord] | None) -> list[dict]:
    if records is None:
        return []
    return [
        {
            "rpt_index": r.rpt_index,
            "EFC": r.EFC,
            "time_s": r.time_s,
            "T_storage_K": r.T_storage_K,
            "LLI_Ah": r.LLI_Ah,
            "LAM_PE_Ah": r.LAM_PE_Ah,
            "LAM_NE_Ah": r.LAM_NE_Ah,
            "cap_loss_Ah": r.cap_loss_Ah,
        }
        for r in records
    ]


def _build_cli_metadata(cell_dir: Path | None) -> dict:
    return {
        "cell_dir": str(cell_dir) if cell_dir is not None else None,
        "git_commit": get_git_commit_hash(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "libquiv_aging_version": LIBQUIV_AGING_VERSION,
        "algorithm": "scripts/fit_dm_aging.py CLI; "
                     "libquiv_aging.dm_aging_fit (scipy least_squares trf "
                     "+ Hessian covariance + S3 forward-sim)",
    }


def _write_debug_snapshot(error: PreflightError, out_dir: Path,
                          ctx: _RunCtx) -> Path:
    """Write SPEC §2.3 debug snapshot to <out>/_debug/<code>_<ts>.json.

    convergence_history fallback = [] (子阶段 2 module 当前不暴露 optimizer
    迭代轨迹给 CLI; 见 docs/SPEC_dm_aging.md §2.3 "若 optimizer 未启动则空").
    """
    debug_dir = out_dir / "_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    snap_path = debug_dir / f"{error.code}_{_utc_ts()}.json"
    payload = {
        "error_code": error.code,
        "error_message": error.message,
        "stage": ctx.stage,
        "input_summary": {
            "cell_dir": str(ctx.cell_dir) if ctx.cell_dir is not None else None,
            "n_rpt": len(ctx.records) if ctx.records is not None else 0,
            "rpt_records_brief": _rpt_records_brief(ctx.records),
        },
        "initial_guess": ctx.initial_guess or {},
        "convergence_history": [],
        "metadata": _build_cli_metadata(ctx.cell_dir),
    }
    _json_dump(payload, snap_path)
    return snap_path


# ============================================================================
# JSON I/O (NaN-safe, dataclass round-trip)
# ============================================================================

def _json_default(obj):
    """JSON encoder fallback: NaN/Inf -> string, Path -> str."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def _json_dump(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False,
                  default=_json_default, allow_nan=False)
        f.write("\n")


def _replace_nan_strings(value):
    """Reverse mapping of _json_default: 'NaN'/'Infinity' -> float."""
    if isinstance(value, str):
        if value == "NaN":
            return float("nan")
        if value == "Infinity":
            return float("inf")
        if value == "-Infinity":
            return float("-inf")
        return value
    if isinstance(value, list):
        return [_replace_nan_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _replace_nan_strings(v) for k, v in value.items()}
    return value


def _write_stage_json(result, path: Path) -> None:
    payload = asdict(result)
    _json_dump(payload, path)


def _load_stage_json(stage: str, out_dir: Path, dataclass_cls):
    """Load fit4a/b/c JSON and reconstruct dataclass.

    All 4 result dataclasses have flat top-level fields (floats + dicts +
    list[str]); nested fit_quality / cap_loss_self_consistency / metadata
    stay as plain dicts. dataclass(**payload) suffices.
    """
    path = out_dir / _RESULT_FILENAMES[stage]
    if not path.is_file():
        return None
    with open(path) as f:
        payload = json.load(f)
    payload = _replace_nan_strings(payload)
    return dataclass_cls(**payload)


# ============================================================================
# Intermediate (--save-intermediate)
# ============================================================================

def _maybe_save_intermediate(records: list[RPTRecord], args, stage: str) -> None:
    if not args.save_intermediate:
        return
    target = args.out / "_intermediate" / f"rpt_records_{stage}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(r) for r in records]
    _json_dump({"stage": stage, "n": len(records), "records": payload}, target)


# ============================================================================
# Diagnostic PNGs (lazy matplotlib + try/except)
# ============================================================================

def _safe_plot_calendar(records: list[RPTRecord],
                        result: FIT4ACalendarResult,
                        out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        efc = np.array([r.EFC for r in records])
        lli = np.array([r.LLI_Ah for r in records])
        lam_pe = np.array([r.LAM_PE_Ah for r in records])
        lam_ne = np.array([r.LAM_NE_Ah for r in records])

        fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.0))
        axes[0].plot(efc, lli, "ko", label="obs")
        axes[0].set_xlabel("EFC")
        axes[0].set_ylabel("LLI (Ah)")
        axes[0].set_title(
            f"FIT-4a LLI(EFC), R²={result.fit_quality.get('r2_LLI', float('nan')):.4f}"
        )
        axes[0].grid(alpha=0.3)
        axes[0].legend(fontsize=8)

        axes[1].plot(efc, lam_pe, "ro", label="LAM_PE obs")
        axes[1].plot(efc, lam_ne, "g^", label="LAM_NE obs")
        axes[1].set_xlabel("EFC")
        axes[1].set_ylabel("LAM (Ah)")
        axes[1].set_title("FIT-4a LAM_PE / LAM_NE")
        axes[1].grid(alpha=0.3)
        axes[1].legend(fontsize=8)

        axes[2].axis("off")
        fq = result.fit_quality
        txt = (
            f"k_SEI_cal   = {result.k_SEI_cal:.4e}\n"
            f"k_LAM_PE_cal= {result.k_LAM_PE_cal:.4e}\n"
            f"gamma_PE    = {result.gamma_PE:.4f}\n"
            f"R_SEI       = {result.R_SEI:.4f}\n"
            f"E_a_SEI     = {result.E_a_SEI:.1f} J/mol\n\n"
            f"R²: LLI={fq.get('r2_LLI'):.4f} / LAM_PE={fq.get('r2_LAM_PE'):.4f}"
            f" / LAM_NE={fq.get('r2_LAM_NE'):.4f}\n"
            f"RMSE: LLI={fq.get('rmse_LLI_Ah'):.4f} / LAM_PE="
            f"{fq.get('rmse_LAM_PE_Ah'):.4f} / LAM_NE={fq.get('rmse_LAM_NE_Ah'):.4f} Ah\n"
            f"pass_overall: {fq.get('pass_overall')}\n"
            f"marginal:     {fq.get('marginal_quality')}\n"
            f"bounds_hit:   {fq.get('bounds_hit') or 'none'}\n"
        )
        axes[2].text(0.0, 1.0, txt, family="monospace", va="top", fontsize=9)
        fig.suptitle("FIT-4a calendar aging diagnostic", fontsize=11)
        fig.tight_layout()
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_dir / _PNG_FILENAMES["calendar"], dpi=120,
                    bbox_inches="tight")
        plt.close(fig)
    except Exception as exc:
        print(f"[WARN] FIT-4a PNG diagnostic failed: {exc}", file=sys.stderr)


def _safe_plot_cycle(records: list[RPTRecord],
                     result: FIT4BCycleResult,
                     out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        efc = np.array([r.EFC for r in records])
        lli = np.array([r.LLI_Ah for r in records])
        lam_pe = np.array([r.LAM_PE_Ah for r in records])
        lam_ne = np.array([r.LAM_NE_Ah for r in records])
        cap = np.array([r.cap_loss_Ah if r.cap_loss_Ah is not None else float("nan")
                        for r in records])

        fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.0))
        axes[0].plot(efc, lli, "ko", label="LLI obs")
        axes[0].plot(efc, lam_pe, "rs", label="LAM_PE")
        axes[0].plot(efc, lam_ne, "g^", label="LAM_NE")
        axes[0].set_xlabel("EFC")
        axes[0].set_ylabel("DMs (Ah)")
        axes[0].set_title("FIT-4b DMs vs EFC")
        axes[0].grid(alpha=0.3)
        axes[0].legend(fontsize=8)

        s3 = result.cap_loss_self_consistency or {}
        cap_model = s3.get("cap_loss_model_Ah") or []
        axes[1].plot(efc, cap, "ko", label="cap_loss obs (RPT C/40)")
        if cap_model and len(cap_model) == len(efc):
            axes[1].plot(efc, cap_model, "r-", label="cap_loss model (forward)")
        axes[1].set_xlabel("EFC")
        axes[1].set_ylabel("cap_loss (Ah)")
        axes[1].set_title(
            f"S3 self-consistency  rel_err_max="
            f"{s3.get('rel_error_max', float('nan')):.4f}"
        )
        axes[1].grid(alpha=0.3)
        axes[1].legend(fontsize=8)

        axes[2].axis("off")
        fq = result.fit_quality
        txt = (
            f"k_SEI_cyc   = {result.k_SEI_cyc:.4e}\n"
            f"k_LAM_PE_cyc= {result.k_LAM_PE_cyc:.4e}\n"
            f"k_LAM_NE_cyc= {result.k_LAM_NE_cyc:.4e}\n\n"
            f"R²: LLI={fq.get('r2_LLI'):.4f} / LAM_PE={fq.get('r2_LAM_PE'):.4f}"
            f" / LAM_NE={fq.get('r2_LAM_NE'):.4f}\n"
            f"RMSE LLI/LAM_PE/LAM_NE = "
            f"{fq.get('rmse_LLI_Ah'):.4f}/{fq.get('rmse_LAM_PE_Ah'):.4f}/"
            f"{fq.get('rmse_LAM_NE_Ah'):.4f} Ah\n\n"
            f"S3 pass:     {s3.get('pass')}\n"
            f"S3 marginal: {s3.get('marginal')}\n"
            f"bounds_hit:  {fq.get('bounds_hit') or 'none'}\n"
        )
        axes[2].text(0.0, 1.0, txt, family="monospace", va="top", fontsize=9)
        fig.suptitle("FIT-4b cycle aging diagnostic (含 S3 N3 落点)", fontsize=11)
        fig.tight_layout()
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_dir / _PNG_FILENAMES["cycle"], dpi=120,
                    bbox_inches="tight")
        plt.close(fig)
    except Exception as exc:
        print(f"[WARN] FIT-4b PNG diagnostic failed: {exc}", file=sys.stderr)


def _safe_plot_knee(records: list[RPTRecord],
                    result: FIT4CKneeResult,
                    out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        efc = np.array([r.EFC for r in records])
        cap = np.array([r.cap_loss_Ah if r.cap_loss_Ah is not None else float("nan")
                        for r in records])

        fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0))
        axes[0].plot(efc, cap, "ko", label="cap_loss obs")
        if not math.isnan(result.knee_efc_predicted):
            axes[0].axvline(result.knee_efc_predicted, color="r", linestyle="--",
                            label=f"knee EFC = {result.knee_efc_predicted:.0f}")
        axes[0].set_xlabel("EFC")
        axes[0].set_ylabel("cap_loss (Ah)")
        axes[0].set_title("FIT-4c knee location")
        axes[0].grid(alpha=0.3)
        axes[0].legend(fontsize=8)

        axes[1].axis("off")
        fq = result.fit_quality
        txt = (
            f"k_LP        = {result.k_LP:.4e} A\n"
            f"k_LP_std    = {result.k_LP_std:.4e}\n"
            f"knee_EFC    = {result.knee_efc_predicted}\n\n"
            f"R²:    {fq.get('r2_cap_loss'):.4f}\n"
            f"RMSE:  {fq.get('rmse_cap_loss_Ah'):.4f} Ah\n"
            f"pass_overall: {fq.get('pass_overall')}\n"
            f"marginal:     {fq.get('marginal_quality')}\n"
            f"bounds_hit:   {fq.get('bounds_hit') or 'none'}\n"
        )
        axes[1].text(0.0, 1.0, txt, family="monospace", va="top", fontsize=9)
        fig.suptitle("FIT-4c knee location diagnostic", fontsize=11)
        fig.tight_layout()
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_dir / _PNG_FILENAMES["knee"], dpi=120,
                    bbox_inches="tight")
        plt.close(fig)
    except Exception as exc:
        print(f"[WARN] FIT-4c PNG diagnostic failed: {exc}", file=sys.stderr)


# ============================================================================
# Warning -> exit code classification
# ============================================================================

def _classify_warnings(warnings: list[str], stage: str) -> int:
    """Map W-code presence in warnings list -> exit code.

    Returns max(W001 exit, W002 exit) if both fire, else single, else 0.
    """
    w001_exit, w002_exit = _W_EXIT_BY_STAGE[stage]
    has_w001 = any("W001" in w for w in warnings)
    has_w002 = any("W002" in w for w in warnings)
    if has_w002:
        return w002_exit
    if has_w001:
        return w001_exit
    return 0


# ============================================================================
# Main flow
# ============================================================================

def run(args, ctx: _RunCtx) -> int:
    """Dispatch by --stage. Multi-stage 'all' chains calendar->cycle->knee."""
    args.out.mkdir(parents=True, exist_ok=True)
    ctx.cell_dir = args.cell_dir

    final_exit = 0

    # ---- FIT-4a (calendar) -----------------------------------------------
    if args.stage in ("calendar", "all"):
        ctx.stage = "calendar"
        ctx.records = aggregate_rpt_records(args.cell_dir, "calendar")
        _maybe_save_intermediate(ctx.records, args, "calendar")
        cal = fit_calendar_aging(ctx.records)
        _write_stage_json(cal, args.out / _RESULT_FILENAMES["calendar"])
        if not args.no_png:
            _safe_plot_calendar(ctx.records, cal, args.out)
        if cal.warnings:
            for w in cal.warnings:
                print(f"[FIT4A] {w}", file=sys.stderr)
            if args.debug_on_warning:
                _emit_warn_debug(cal.warnings, args.out, ctx)
        stage_exit = _classify_warnings(cal.warnings, "calendar")
        final_exit = max(final_exit, stage_exit)
        print(f"[FIT4A] PASS  k_SEI_cal={cal.k_SEI_cal:.4e}  "
              f"R_SEI={cal.R_SEI:.3f}  pass_overall={cal.fit_quality.get('pass_overall')}")

    # ---- FIT-4b (cycle pre-knee) ----------------------------------------
    if args.stage in ("cycle", "all"):
        ctx.stage = "cycle"
        cal = _load_stage_json("calendar", args.out, FIT4ACalendarResult)
        if cal is None:
            # autoload failure -> reuse FIT4B-E004 path (calendar_result=None)
            raise PreflightError(
                "FIT4B-E004",
                f"前置 stage_a 缺失: {args.out / _RESULT_FILENAMES['calendar']} "
                f"未找到. 先跑 --stage calendar 或 --stage all.",
                exit_code=43,
            )
        ctx.records = aggregate_rpt_records(args.cell_dir, "cycle")
        _maybe_save_intermediate(ctx.records, args, "cycle")
        cyc = fit_cycle_aging(ctx.records, cal)
        _write_stage_json(cyc, args.out / _RESULT_FILENAMES["cycle"])
        if not args.no_png:
            _safe_plot_cycle(ctx.records, cyc, args.out)
        if cyc.warnings:
            for w in cyc.warnings:
                print(f"[FIT4B] {w}", file=sys.stderr)
            if args.debug_on_warning:
                _emit_warn_debug(cyc.warnings, args.out, ctx)
        stage_exit = _classify_warnings(cyc.warnings, "cycle")
        final_exit = max(final_exit, stage_exit)
        s3 = cyc.cap_loss_self_consistency or {}
        print(f"[FIT4B] PASS  k_SEI_cyc={cyc.k_SEI_cyc:.4e}  "
              f"S3 pass={s3.get('pass')}  rel_err_max="
              f"{s3.get('rel_error_max', float('nan')):.4f}")

    # ---- FIT-4c (knee) --------------------------------------------------
    if args.stage in ("knee", "all"):
        ctx.stage = "knee"
        cal = _load_stage_json("calendar", args.out, FIT4ACalendarResult)
        cyc = _load_stage_json("cycle", args.out, FIT4BCycleResult)
        if cal is None or cyc is None:
            raise PreflightError(
                "FIT4C-E003",
                f"前置 stage_a/b 缺失: cal={cal is not None}, cyc={cyc is not None}. "
                f"先跑 --stage cycle 或 --stage all.",
                exit_code=52,
            )
        ctx.records = aggregate_rpt_records(args.cell_dir, "knee")
        _maybe_save_intermediate(ctx.records, args, "knee")
        knee = fit_knee_location(ctx.records, cal, cyc)
        _write_stage_json(knee, args.out / _RESULT_FILENAMES["knee"])
        if not args.no_png:
            _safe_plot_knee(ctx.records, knee, args.out)
        if knee.warnings:
            for w in knee.warnings:
                print(f"[FIT4C] {w}", file=sys.stderr)
            if args.debug_on_warning:
                _emit_warn_debug(knee.warnings, args.out, ctx)
        stage_exit = _classify_warnings(knee.warnings, "knee")
        final_exit = max(final_exit, stage_exit)
        print(f"[FIT4C] PASS  k_LP={knee.k_LP:.4e} +/- {knee.k_LP_std:.4e}  "
              f"knee_EFC={knee.knee_efc_predicted}")

    return final_exit


def _emit_warn_debug(warnings: list[str], out_dir: Path, ctx: _RunCtx) -> None:
    """--debug-on-warning: 给每条 W-code 落一个 _debug snapshot."""
    for w in warnings:
        # 提取 code (e.g. "FIT4A-W001: ..." or "FIT4A-W002: bounds_hit=...")
        for code_prefix in ("FIT4A-W001", "FIT4A-W002",
                            "FIT4B-W001", "FIT4B-W002",
                            "FIT4C-W001", "FIT4C-W002"):
            if w.startswith(code_prefix):
                synth = PreflightError(code_prefix, w, exit_code=0)
                _write_debug_snapshot(synth, out_dir, ctx)
                break


# ============================================================================
# CLI entrypoint
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "FIT-4 DM aging fit (calendar/cycle/knee) per "
            "docs/SPEC_dm_aging.md. Wraps libquiv_aging.dm_aging_fit "
            "public APIs."
        )
    )
    parser.add_argument(
        "--cell-dir", type=Path, required=True,
        help="Cell-level raw data root: <cell-dir>/RPT_<NN>/ic_output.json "
             "+ cell_*_rpt.csv (per SPEC §2.1)."
    )
    parser.add_argument(
        "--out", type=Path, required=True,
        help="Output dir for fit4{a,b,c}_*_result.json + _debug/ "
             "+ (optional) PNG diagnostics."
    )
    parser.add_argument(
        "--stage", choices=["calendar", "cycle", "knee", "all"],
        default="all",
        help="Single stage or 'all' (auto-loads prior stage result JSON). "
             "R2 sequencing enforced by FIT4B-E004 / FIT4C-E003."
    )
    parser.add_argument(
        "--debug-on-warning", action="store_true",
        help="W-code also writes _debug snapshot (default: only E-code)."
    )
    parser.add_argument(
        "--save-intermediate", action="store_true",
        help="Dump aggregated rpt_records_<stage>.json to <out>/_intermediate/."
    )
    parser.add_argument(
        "--no-png", action="store_true",
        help="Skip diagnostic PNGs (CI / air-gapped / matplotlib-less)."
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Verbose optimizer log to stderr."
    )
    args = parser.parse_args()

    ctx = _RunCtx()
    try:
        return run(args, ctx)
    except PreflightError as e:
        snap_path = _write_debug_snapshot(e, args.out, ctx)
        print(f"[{e.code}] {e.message}", file=sys.stderr)
        print(f"  debug snapshot: {snap_path}", file=sys.stderr)
        print(f"  see docs/07_offline_runbook.md {e.code}", file=sys.stderr)
        return e.exit_code
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
