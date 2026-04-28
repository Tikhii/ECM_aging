"""
ic_analysis.py
==============
IC analysis for RPT C/40 discharge curves -> (LLI, LAM_PE, LAM_NE) extraction.

Method: paper Mmeka 2025 Eqs. 1, 18-26 quasi-equilibrium forward model +
scipy.optimize.least_squares on V(Q) residuals.
Methodology reference: Dubarry & Anseán 2022, Front. Energy Res. 10:1023555.

This is an independent Python implementation, not a translation of `alawa`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.optimize import brentq, least_squares
from scipy.signal import savgol_filter

from libquiv_aging.cell_factory import (
    _derive_C0_NE,
    _derive_C0_PE,
    _derive_Q0_SEI_NE,
    _extract_value,
    _project_root,
)
from libquiv_aging.lookup_tables import HalfCellThermo, open_circuit_voltage


T_REF_K: float = 298.15


@dataclass
class ICAnalysisResult:
    LLI_Ah: float
    LAM_PE_Ah: float
    LAM_NE_Ah: float
    LLI_std: float
    LAM_PE_std: float
    LAM_NE_std: float
    rmse_V: float
    n_points: int
    converged: bool
    iterations: int
    V_model: np.ndarray
    dQdV_obs: np.ndarray
    dQdV_model: np.ndarray
    Q_grid: np.ndarray


def _load_ic_artifacts(material_spec_path: str | Path,
                       params_spec_path: str | Path) -> dict:
    """Load and derive everything synthesize_V_ocv needs from the two specs.

    Returns a dict with C0_PE_Ah, C0_NE_Ah, Q0_SEI_NE_Ah, X0_PE, X0_NE,
    C_nominal_Ah, anode_thermo, cathode_thermo. Done once per analyze_ic call
    so the optimizer's residual function doesn't re-load on every iteration.
    """
    root = _project_root()
    material_spec_path = Path(material_spec_path)
    params_spec_path = Path(params_spec_path)
    if not material_spec_path.is_absolute():
        material_spec_path = root / material_spec_path
    if not params_spec_path.is_absolute():
        params_spec_path = root / params_spec_path

    with open(material_spec_path) as f:
        material_spec = json.load(f)
    with open(params_spec_path) as f:
        params_spec = json.load(f)

    C0_PE_As = _derive_C0_PE(material_spec, params_spec)
    C0_NE_As = _derive_C0_NE(C0_PE_As, material_spec)
    Q0_SEI_NE_As = _derive_Q0_SEI_NE(C0_PE_As, material_spec)

    anode_thermo = HalfCellThermo.from_dat_file(
        str(root / material_spec["anode_thermo_dat"])
    )
    cathode_thermo = HalfCellThermo.from_dat_file(
        str(root / material_spec["cathode_thermo_dat"])
    )

    return {
        "C0_PE_As": C0_PE_As,
        "C0_NE_As": C0_NE_As,
        "Q0_SEI_NE_As": Q0_SEI_NE_As,
        "C0_PE_Ah": C0_PE_As / 3600.0,
        "C0_NE_Ah": C0_NE_As / 3600.0,
        "Q0_SEI_NE_Ah": Q0_SEI_NE_As / 3600.0,
        "X0_PE": _extract_value(material_spec["X0_PE"], "X0_PE"),
        "X0_NE": _extract_value(material_spec["X0_NE"], "X0_NE"),
        "C_nominal_Ah": _extract_value(
            material_spec["C_nominal_Ah"], "C_nominal_Ah"
        ),
        "V_max": _extract_value(material_spec["V_max"], "V_max"),
        "V_min": _extract_value(material_spec["V_min"], "V_min"),
        "anode_thermo": anode_thermo,
        "cathode_thermo": cathode_thermo,
    }


def _V_at_internal_dQ(
    dQ_As: float,
    Q_PE_init_As: float,
    Q_NE_init_As: float,
    C_PE_aged_As: float,
    C_NE_aged_As: float,
    anode_thermo: HalfCellThermo,
    cathode_thermo: HalfCellThermo,
    T_K: float,
) -> float:
    """Cell V at charge offset dQ from the (Q_PE_init, Q_NE_init) reference.

    dQ > 0 corresponds to charging (Q_PE decreases, Q_NE increases).
    Returns +inf when X falls outside [0, 1] so brentq can detect
    infeasible regimes.
    """
    X_PE = (Q_PE_init_As - dQ_As) / C_PE_aged_As
    X_NE = (Q_NE_init_As + dQ_As) / C_NE_aged_As
    if X_PE < 0.0 or X_PE > 1.0 or X_NE < 0.0 or X_NE > 1.0:
        return float("inf")
    V0, *_ = open_circuit_voltage(X_NE, X_PE, T_K, anode_thermo, cathode_thermo)
    return float(np.atleast_1d(V0)[0])


def _bracket_dQ_for_voltage(
    V_target: float,
    Q_PE_init_As: float,
    Q_NE_init_As: float,
    C_PE_aged_As: float,
    C_NE_aged_As: float,
    anode_thermo: HalfCellThermo,
    cathode_thermo: HalfCellThermo,
    T_K: float,
    n_probe: int = 41,
) -> tuple[float, float] | None:
    """Sample the feasible dQ window and return a sign-changing bracket
    (lo, hi) for V_at(dQ) - V_target, or None if no bracket exists.

    Feasible dQ is bounded by X_PE in [0,1] and X_NE in [0,1]:
      dQ_min = max(Q_PE_init - C_PE_aged, -Q_NE_init)
      dQ_max = min(Q_PE_init, C_NE_aged - Q_NE_init)
    """
    dQ_lo_phys = max(Q_PE_init_As - C_PE_aged_As, -Q_NE_init_As)
    dQ_hi_phys = min(Q_PE_init_As, C_NE_aged_As - Q_NE_init_As)
    if dQ_hi_phys - dQ_lo_phys <= 0.0:
        return None
    eps = 1e-4 * (dQ_hi_phys - dQ_lo_phys)
    grid = np.linspace(dQ_lo_phys + eps, dQ_hi_phys - eps, n_probe)
    f = np.array([
        _V_at_internal_dQ(
            float(dq), Q_PE_init_As, Q_NE_init_As,
            C_PE_aged_As, C_NE_aged_As,
            anode_thermo, cathode_thermo, T_K,
        ) - V_target
        for dq in grid
    ])
    finite = np.isfinite(f)
    if finite.sum() < 2:
        return None
    idx = np.where(finite)[0]
    f_finite = f[idx]
    sign_change = np.where(np.sign(f_finite[:-1]) * np.sign(f_finite[1:]) < 0)[0]
    if len(sign_change) == 0:
        return None
    k = sign_change[0]
    return float(grid[idx[k]]), float(grid[idx[k + 1]])


def _synthesize_V_ocv_inner(
    Q_obs_Ah: np.ndarray,
    LAM_PE_Ah: float,
    LAM_NE_Ah: float,
    LLI_Ah: float,
    *,
    C0_PE_As: float,
    C0_NE_As: float,
    Q0_SEI_NE_As: float,
    X0_PE: float,
    X0_NE: float,
    V_max: float,
    V_min: float,
    anode_thermo: HalfCellThermo,
    cathode_thermo: HalfCellThermo,
    T_K: float = T_REF_K,
) -> np.ndarray:
    """Vectorized forward model with preloaded artifacts; see synthesize_V_ocv
    for the full algorithm decision and equation references."""
    Q_obs_Ah = np.asarray(Q_obs_Ah, dtype=float)
    N = Q_obs_Ah.size

    # Step 1: aged half-cell capacities (LAM enters denominator of Eq. 25/26
    # via C(t) = C^0 - Q^{LAM}; LAM does NOT enter X^0 numerator).
    C_PE_aged_As = C0_PE_As - LAM_PE_Ah * 3600.0
    C_NE_aged_As = C0_NE_As - LAM_NE_Ah * 3600.0
    if C_PE_aged_As <= 0.0 or C_NE_aged_As <= 0.0:
        return np.full(N, np.inf)

    # Step 2: reference electrode charges. spec X0 defines the dQ-axis
    # integration constant; SEI + LLI both consume Q_NE per paper Eq. 22.
    Q_PE_init_As = X0_PE * C_PE_aged_As
    Q_NE_init_As = X0_NE * C_NE_aged_As - (Q0_SEI_NE_As + LLI_Ah * 3600.0)

    # Step 3: dual brentq for dQ at V_min and V_max (matches FIT-1's
    # _calibrate_soc_bounds). Cannot assume dQ at V_min == 0 because spec
    # X0 is just an axis reference, not necessarily exactly at V_min.
    def v_at(dq: float) -> float:
        return _V_at_internal_dQ(
            dq, Q_PE_init_As, Q_NE_init_As,
            C_PE_aged_As, C_NE_aged_As,
            anode_thermo, cathode_thermo, T_K,
        )

    br_lo = _bracket_dQ_for_voltage(
        V_min, Q_PE_init_As, Q_NE_init_As,
        C_PE_aged_As, C_NE_aged_As,
        anode_thermo, cathode_thermo, T_K,
    )
    br_hi = _bracket_dQ_for_voltage(
        V_max, Q_PE_init_As, Q_NE_init_As,
        C_PE_aged_As, C_NE_aged_As,
        anode_thermo, cathode_thermo, T_K,
    )
    if br_lo is None or br_hi is None:
        return np.full(N, np.inf)
    try:
        dQ_at_Vmin_As = brentq(
            lambda dq: v_at(dq) - V_min, br_lo[0], br_lo[1],
            xtol=1e-6, maxiter=200,
        )
        dQ_at_Vmax_As = brentq(
            lambda dq: v_at(dq) - V_max, br_hi[0], br_hi[1],
            xtol=1e-6, maxiter=200,
        )
    except (ValueError, RuntimeError):
        return np.full(N, np.inf)

    # Step 4: vectorize. Q_obs convention matches RPT C/40 raw CSV:
    # Q_obs[0] = 0 at V_max, Q_obs grows monotonically to C_aged at V_min.
    # During discharge, internal dQ decreases from dQ_at_Vmax to dQ_at_Vmin.
    dQ_internal_As = dQ_at_Vmax_As - Q_obs_Ah * 3600.0
    Q_PE_arr = Q_PE_init_As - dQ_internal_As
    Q_NE_arr = Q_NE_init_As + dQ_internal_As
    X_PE_arr = Q_PE_arr / C_PE_aged_As
    X_NE_arr = Q_NE_arr / C_NE_aged_As

    if (np.any(X_PE_arr < 0.0) or np.any(X_PE_arr > 1.0)
            or np.any(X_NE_arr < 0.0) or np.any(X_NE_arr > 1.0)):
        return np.full(N, np.inf)

    V_cell, *_ = open_circuit_voltage(
        X_NE_arr, X_PE_arr, T_K, anode_thermo, cathode_thermo,
    )
    return np.asarray(V_cell, dtype=float)


def synthesize_V_ocv(
    Q_obs_Ah: np.ndarray,
    LAM_PE_Ah: float,
    LAM_NE_Ah: float,
    LLI_Ah: float,
    *,
    material_spec_path: str | Path,
    params_spec_path: str | Path,
) -> np.ndarray:
    """Quasi-equilibrium V(Q) forward model for an aged-cell C/40 discharge.

    Algorithm decision (web-chat ground truth, revised after subphase 2
    self-test exposed an X^0-reference inconsistency in the original
    paper-faithful Eq. 21/22 form):

      The implementation reuses scripts/fit_electrode_balance.py's V_cell
      framework (_derive_fresh_cell_params + _V_at_dQ + brentq calibration)
      because that path is the SPEC- and FIT-1-validated reference for how
      this codebase composes spec X0 + half-cell .dat into V_cell. The IC
      analysis differs only in (a) injecting LAM/LLI into aged caps and
      Q_NE_at_Vmin and (b) anchoring the V_max endpoint via brentq once
      per forward eval.

    X^0 convention clarification:
      - paper Mmeka 2025 Table I uses X^0_PE = 0.0 / X^0_NE ~ 0.85 at the
        SOC=1 (fully delithiated cathode) reference. Numerically different
        from the spec.
      - libquiv-aging spec X0_PE = 0.95 / X0_NE = 0.01 use the V_min-state
        stoichiometry (half-cell .dat domain endpoint, fully lithiated
        cathode / fully delithiated graphite at the discharge cutoff).
      Both conventions are physically valid; we use the spec convention
      throughout because that is what the half-cell .dat tables are
      anchored to and what FIT-1 already validated. cell_model.py uses
      the same convention internally (verified subphase 2 self-test:
      cell.init(SOC=0) returns X_PE = 0.917, X_NE = 0.013, matching spec
      X0 within the SOC-calibration brentq tolerance).

    Forward model (three steps, ~10 ms per eval target):

      Step 1: aged half-cell capacities
        C_PE_aged = C0_PE - LAM_PE                 (Eq. 25 denominator)
        C_NE_aged = C0_NE - LAM_NE                 (Eq. 26 denominator)
        LAM does NOT enter X^0 numerator.

      Step 2: V_min-state electrode charges
        Q_PE_at_Vmin = X0_PE * C_PE_aged
        Q_NE_at_Vmin = X0_NE * C_NE_aged - (Q_SEI^0_fresh + LLI)
        (paper Eq. 22 LLI accumulation; Q_PE^{LLI,0} = 0 by paper assumption.)

      Step 3: brentq anchor V_max + vectorize
        dQ = signed charge offset from V_min ref; +dQ = charging.
        V_at(dQ) = V_PE^0((Q_PE_at_Vmin - dQ) / C_PE_aged)
                 - V_NE^0((Q_NE_at_Vmin + dQ) / C_NE_aged)
        dQ_at_Vmax = brentq(V_at(dQ) - V_max, 0, C_PE_aged)
        dQ_internal[k] = dQ_at_Vmax - Q_obs[k]
        X_PE_arr = (Q_PE_at_Vmin - dQ_internal) / C_PE_aged
        X_NE_arr = (Q_NE_at_Vmin + dQ_internal) / C_NE_aged
        V_cell[k] = V_PE^0(X_PE_arr[k]) - V_NE^0(X_NE_arr[k])

    Q_obs convention (matches RPT C/40 raw CSV, no preprocessing required):
      Q_obs[0] = 0 at V_max (cell at top-of-charge, start of discharge),
      Q_obs[-1] = C_aged_observed at V_min (end of discharge cutoff).
      Optimizer fits this directly without coordinate translation.

    X-domain handling: any sample with X_PE or X_NE outside [0, 1] forces
    the entire returned array to +inf; same for brentq failure (V_max
    unreachable within feasible dQ window). HalfCellThermo.interp_dH_dS
    silently clamps inputs at the lookup level (subphase 0 finding 3), so
    explicit rejection here is necessary to keep the optimizer honest.

    Parameters
    ----------
    Q_obs_Ah : np.ndarray
        Cumulative discharge from V_max in Ah, monotone non-decreasing,
        starting at 0.
    LAM_PE_Ah, LAM_NE_Ah, LLI_Ah : float
        Aged-state degradation modes in Ah. All non-negative.
    material_spec_path, params_spec_path : path-like
        Spec files; resolved relative to the project root if not absolute.

    Returns
    -------
    V_cell : np.ndarray
        Cell OCV at each Q_obs sample (V), or +inf entries when the
        (LAM_PE, LAM_NE, LLI) input falls outside the .dat alawa regime.
    """
    art = _load_ic_artifacts(material_spec_path, params_spec_path)
    return _synthesize_V_ocv_inner(
        Q_obs_Ah, LAM_PE_Ah, LAM_NE_Ah, LLI_Ah,
        C0_PE_As=art["C0_PE_As"],
        C0_NE_As=art["C0_NE_As"],
        Q0_SEI_NE_As=art["Q0_SEI_NE_As"],
        X0_PE=art["X0_PE"],
        X0_NE=art["X0_NE"],
        V_max=art["V_max"],
        V_min=art["V_min"],
        anode_thermo=art["anode_thermo"],
        cathode_thermo=art["cathode_thermo"],
    )


def _fresh_state_model_capacity_Ah(art: dict) -> float:
    """Compute the model's fresh-state (LLI=LAM_PE=LAM_NE=0) C/40 quasi-equilibrium
    capacity in Ah via dual brentq for V_min and V_max.

    Different from spec C_nominal (datasheet C/2 measurement, includes hysteresis
    and IR drop). For heuristic initial-guess purposes, the model-domain capacity
    is the correct baseline because the optimizer fits in the model domain.

    Falls back to spec C_nominal if either bracket fails (artifacts-layer
    inconsistency that should not happen in a well-formed spec).
    """
    C_PE_As = art["C0_PE_As"]
    C_NE_As = art["C0_NE_As"]
    Q_PE_init_As = art["X0_PE"] * C_PE_As
    Q_NE_init_As = art["X0_NE"] * C_NE_As - art["Q0_SEI_NE_As"]
    br_lo = _bracket_dQ_for_voltage(
        art["V_min"], Q_PE_init_As, Q_NE_init_As, C_PE_As, C_NE_As,
        art["anode_thermo"], art["cathode_thermo"], T_REF_K,
    )
    br_hi = _bracket_dQ_for_voltage(
        art["V_max"], Q_PE_init_As, Q_NE_init_As, C_PE_As, C_NE_As,
        art["anode_thermo"], art["cathode_thermo"], T_REF_K,
    )
    if br_lo is None or br_hi is None:
        return float(art["C_nominal_Ah"])
    v_at = lambda dq: _V_at_internal_dQ(  # noqa: E731
        dq, Q_PE_init_As, Q_NE_init_As, C_PE_As, C_NE_As,
        art["anode_thermo"], art["cathode_thermo"], T_REF_K,
    )
    try:
        dQ_lo = brentq(lambda dq: v_at(dq) - art["V_min"], br_lo[0], br_lo[1],
                       xtol=1e-6, maxiter=200)
        dQ_hi = brentq(lambda dq: v_at(dq) - art["V_max"], br_hi[0], br_hi[1],
                       xtol=1e-6, maxiter=200)
    except (ValueError, RuntimeError):
        return float(art["C_nominal_Ah"])
    return float((dQ_hi - dQ_lo) / 3600.0)


def heuristic_initial_guess(
    Q_obs_Ah: np.ndarray,
    V_obs_V: np.ndarray,
    *,
    material_spec_path: str | Path | None = None,
    params_spec_path: str | Path | None = None,
    artifacts: dict | None = None,
) -> dict:
    """Coarse 0.4 LLI / 0.3 LAM_PE / 0.3 LAM_NE budget split of the observed
    capacity loss vs the model's fresh-state C/40 capacity. Returns
    {'LLI_Ah', 'LAM_PE_Ah', 'LAM_NE_Ah'}.

    Capacity baseline (subphase 2 第二次修订): uses the alawa-domain
    fresh-state capacity from one fresh forward sweep, NOT the spec
    C_nominal datasheet value. Mixing datasheet C/2 capacity with model-domain
    C/40 fits drives a 3-5% systematic offset that masks light-aging
    capacity loss.

    For very-light aging (capacity_loss < 0.01 Ah) a 1% nominal
    perturbation is injected so the optimizer Jacobian is non-degenerate
    at the bound; the optimizer then settles back to bounds + ICA-W002
    if the data really is fresh.

    Refinements via graphite stage 2<->3 peak shift (LLI) and 1<->2 peak
    height (LAM_NE) are optional; the global V(Q) optimizer refines from
    here. See Dubarry & Ansean 2022 §peak conventions.
    """
    if artifacts is None:
        if material_spec_path is None or params_spec_path is None:
            raise ValueError(
                "heuristic_initial_guess requires either artifacts dict or "
                "both material_spec_path and params_spec_path"
            )
        artifacts = _load_ic_artifacts(material_spec_path, params_spec_path)

    Q_obs = np.asarray(Q_obs_Ah, dtype=float)
    if Q_obs[0] > Q_obs[-1]:
        Q_obs = Q_obs[::-1]
    Q_obs_max = float(Q_obs.max())

    C_fresh_model = _fresh_state_model_capacity_Ah(artifacts)
    capacity_loss = max(0.0, C_fresh_model - Q_obs_max)

    if capacity_loss < 0.01:
        capacity_loss = 0.01

    return {
        "LLI_Ah": 0.4 * capacity_loss,
        "LAM_PE_Ah": 0.3 * capacity_loss,
        "LAM_NE_Ah": 0.3 * capacity_loss,
    }


def _validate_inputs(Q_obs_Ah: np.ndarray, V_obs_V: np.ndarray) -> None:
    """ICA-E001 caller-side validation. Raises ValueError on contract breach."""
    if Q_obs_Ah.ndim != 1 or V_obs_V.ndim != 1:
        raise ValueError("Q_obs_Ah and V_obs_V must be 1-D arrays")
    if Q_obs_Ah.shape != V_obs_V.shape:
        raise ValueError(
            f"Q_obs_Ah and V_obs_V length mismatch: "
            f"{Q_obs_Ah.shape} vs {V_obs_V.shape}"
        )
    if len(Q_obs_Ah) < 50:
        raise ValueError(
            f"n_points={len(Q_obs_Ah)} < 50 (ICA-E001 minimum sample count)"
        )
    q_range = float(Q_obs_Ah.max() - Q_obs_Ah.min())
    if q_range < 1.5:
        raise ValueError(
            f"Q range {q_range:.3f} Ah < 1.5 Ah "
            f"(ICA-E001 minimum span)"
        )


def _prepare_grid(
    Q_obs_Ah: np.ndarray, V_obs_V: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Auto-flip descending Q, deduplicate, return strictly ascending grid."""
    Q = np.asarray(Q_obs_Ah, dtype=float)
    V = np.asarray(V_obs_V, dtype=float)
    if Q[0] > Q[-1]:
        Q = Q[::-1]
        V = V[::-1]
    order = np.argsort(Q, kind="mergesort")
    Q = Q[order]
    V = V[order]
    Q_unique, idx = np.unique(Q, return_index=True)
    V_unique = V[idx]
    if not np.all(np.diff(Q_unique) > 0):
        raise ValueError("Q grid not strictly monotone after deduplication")
    return Q_unique, V_unique


def _smooth_voltage(
    V: np.ndarray, *, window_frac: float, polyorder: int,
) -> np.ndarray:
    """Savitzky-Golay smoothing on V(Q). Window forced odd, >=5, > polyorder."""
    n = len(V)
    raw = int(window_frac * n)
    window = max(5, polyorder + 2 if (polyorder + 2) % 2 == 1 else polyorder + 3)
    candidate = (raw // 2) * 2 + 1 if raw >= 5 else window
    window = max(window, candidate)
    if window > n:
        window = n if n % 2 == 1 else n - 1
    if window <= polyorder:
        return V.copy()
    return savgol_filter(V, window_length=window, polyorder=polyorder)


def _central_dQdV(Q: np.ndarray, V: np.ndarray) -> np.ndarray:
    """Central-difference dQ/dV diagnostic. Q and V must be ascending in Q."""
    dV = np.gradient(V, Q)
    with np.errstate(divide="ignore", invalid="ignore"):
        dqdv = np.where(np.abs(dV) > 1e-12, 1.0 / dV, np.nan)
    return dqdv


def analyze_ic(
    Q_obs_Ah: np.ndarray,
    V_obs_V: np.ndarray,
    *,
    material_spec_path: str | Path,
    params_spec_path: str | Path,
    smoothing_window_frac: float = 0.05,
    smoothing_polyorder: int = 3,
    bounds: Optional[dict] = None,
    initial_guess: Optional[dict] = None,
    method: str = "trf",
    verbose: bool = False,
) -> ICAnalysisResult:
    """Extract (LLI, LAM_PE, LAM_NE) from an aged-cell C/40 discharge curve.

    Pipeline:
      1. Validate input contract (n>=50, Q range>=1.5 Ah; ICA-E001).
      2. Auto-flip descending Q; deduplicate; assert strict monotonicity.
      3. Smooth V(Q) with Savitzky-Golay on V (NOT on dQ/dV).
      4. Heuristic initial guess unless caller provides one.
      5. scipy.optimize.least_squares(method=trf, bounds=...) on V residuals.
      6. Hessian-based covariance: Sigma = (J^T J)^{-1} * SSE / (N-3).
      7. Diagnostic dQ/dV for both observed (smoothed) and model curves.

    Bounds default to [0, 0, 0] - [0.3*C0_PE, 0.3*C0_NE, 0.3*C_nominal] in Ah,
    matching SPEC. Caller may override via the `bounds` dict (keys
    LAM_PE_Ah / LAM_NE_Ah / LLI_Ah, values are (low, high) tuples).
    """
    Q_obs_arr = np.asarray(Q_obs_Ah, dtype=float)
    V_obs_arr = np.asarray(V_obs_V, dtype=float)
    _validate_inputs(Q_obs_arr, V_obs_arr)

    Q_grid, V_grid = _prepare_grid(Q_obs_arr, V_obs_arr)
    V_smoothed = _smooth_voltage(
        V_grid,
        window_frac=smoothing_window_frac,
        polyorder=smoothing_polyorder,
    )

    art = _load_ic_artifacts(material_spec_path, params_spec_path)
    C0_PE_Ah = art["C0_PE_Ah"]
    C0_NE_Ah = art["C0_NE_Ah"]
    C_nominal_Ah = art["C_nominal_Ah"]

    if initial_guess is None:
        initial_guess = heuristic_initial_guess(
            Q_grid, V_smoothed, artifacts=art,
        )

    if bounds is None:
        bounds_lo = [0.0, 0.0, 0.0]
        bounds_hi = [
            0.3 * C0_PE_Ah,
            0.3 * C0_NE_Ah,
            0.3 * C_nominal_Ah,
        ]
    else:
        bounds_lo = [
            bounds["LAM_PE_Ah"][0],
            bounds["LAM_NE_Ah"][0],
            bounds["LLI_Ah"][0],
        ]
        bounds_hi = [
            bounds["LAM_PE_Ah"][1],
            bounds["LAM_NE_Ah"][1],
            bounds["LLI_Ah"][1],
        ]

    x0 = [
        float(np.clip(initial_guess["LAM_PE_Ah"], bounds_lo[0], bounds_hi[0])),
        float(np.clip(initial_guess["LAM_NE_Ah"], bounds_lo[1], bounds_hi[1])),
        float(np.clip(initial_guess["LLI_Ah"], bounds_lo[2], bounds_hi[2])),
    ]

    inner_kwargs = dict(
        C0_PE_As=art["C0_PE_As"],
        C0_NE_As=art["C0_NE_As"],
        Q0_SEI_NE_As=art["Q0_SEI_NE_As"],
        X0_PE=art["X0_PE"],
        X0_NE=art["X0_NE"],
        V_max=art["V_max"],
        V_min=art["V_min"],
        anode_thermo=art["anode_thermo"],
        cathode_thermo=art["cathode_thermo"],
    )

    def residual(theta: np.ndarray) -> np.ndarray:
        LAM_PE, LAM_NE, LLI = float(theta[0]), float(theta[1]), float(theta[2])
        V_model = _synthesize_V_ocv_inner(
            Q_grid, LAM_PE, LAM_NE, LLI, **inner_kwargs
        )
        return V_model - V_smoothed

    result = least_squares(
        residual, x0=x0, bounds=(bounds_lo, bounds_hi),
        method=method, verbose=2 if verbose else 0,
    )

    converged = bool(result.status > 0)

    LAM_PE_hat, LAM_NE_hat, LLI_hat = (
        float(result.x[0]), float(result.x[1]), float(result.x[2])
    )
    V_model_at_best = _synthesize_V_ocv_inner(
        Q_grid, LAM_PE_hat, LAM_NE_hat, LLI_hat, **inner_kwargs
    )
    residuals = V_model_at_best - V_smoothed
    n = len(V_grid)
    sse = float(np.sum(residuals ** 2))
    rmse_V = float(np.sqrt(sse / n)) if n > 0 else float("nan")

    J = result.jac
    dof = max(n - 3, 1)
    sigma2 = sse / dof
    try:
        cov = sigma2 * np.linalg.inv(J.T @ J)
        stds = np.sqrt(np.clip(np.diag(cov), 0.0, None))
        if not np.all(np.isfinite(stds)):
            stds = np.array([np.nan, np.nan, np.nan])
    except np.linalg.LinAlgError:
        stds = np.array([np.nan, np.nan, np.nan])

    dqdv_obs = _central_dQdV(Q_grid, V_smoothed)
    dqdv_model = _central_dQdV(Q_grid, V_model_at_best)

    return ICAnalysisResult(
        LLI_Ah=LLI_hat,
        LAM_PE_Ah=LAM_PE_hat,
        LAM_NE_Ah=LAM_NE_hat,
        LLI_std=float(stds[2]),
        LAM_PE_std=float(stds[0]),
        LAM_NE_std=float(stds[1]),
        rmse_V=rmse_V,
        n_points=n,
        converged=converged,
        iterations=int(result.nfev),
        V_model=V_model_at_best,
        dQdV_obs=dqdv_obs,
        dQdV_model=dqdv_model,
        Q_grid=Q_grid,
    )
