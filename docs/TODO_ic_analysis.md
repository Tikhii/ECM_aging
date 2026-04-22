# TODO: IC Analysis for RPT → (LLI, LAM_PE, LAM_NE) Extraction

**Status**: Spec frozen 2026-04-22. Ready for implementation.
**Assignee**: Claude Code (local execution on libquiv-aging repo).
**Blocks**: FIT-4a (calendar aging), FIT-4b (cycle preknee). Both need 
(LLI_Ah, LAM_PE_Ah, LAM_NE_Ah) per RPT as their primary constraints.

---

## Purpose

Automate degradation-mode extraction from RPT C/40 discharge curves, for use in 
FIT-4a (calendar) and FIT-4b (cycle-preknee) aging parameter fits.

## Context

- RPT protocol: `docs/PARAMETER_SOP.md §二` step (3), C/40 V_cell curve.
- Physics: paper Mmeka 2025 Eqs. 1, 18–26 (electrode balance, lithium stoichiometry).
- Methodology reference: Dubarry & Anseán 2022, Front. Energy Res. 10:1023555.
- Underlying framework: `alawa` (Dubarry et al., HNEI, MATLAB, paper Ref 47). 
  This task produces an **independent Python implementation**, not a translation. 
  Consulting `alawa` source is optional background reading and not required.

---

## Step 0: Codebase Reconnaissance (do this first)

Before writing any new code, inspect the existing repo to identify reusable pieces:

```bash
# 1. Does EquivCircuitCell already have an OCV-only / quasi-equilibrium path?
grep -rn "V_cell" libquiv_aging/cell_model.py
grep -rn "def.*V_cell\|def.*OCV" libquiv_aging/

# 2. Is there an existing aging-state → Q_PE^0, Q_NE^0 initialization?
grep -rn "Q_PE_0\|Q_NE_0\|aging.*init\|init.*SOC" libquiv_aging/

# 3. HalfCellThermo interpolator — what's its interface?
grep -n "class HalfCellThermo\|def interp" libquiv_aging/lookup_tables.py

# 4. Are there existing tests that exercise OCV-only discharge?
grep -rn "C/40\|C_40\|quasi.*equilibrium\|OCV.*discharge" tests/
```

**Report findings briefly** before writing new code. Then decide:
- If `EquivCircuitCell` has usable OCV-only path → reuse it.
- If not → implement `synthesize_V_ocv` as an independent function in 
  `libquiv_aging/ic_analysis.py` following paper Eqs. 1, 18–26 + 25, 26 
  algebraically (no ODE integration needed at C/40 limit).

---

## Deliverables

1. **Library module**: `libquiv_aging/ic_analysis.py`
2. **CLI script**: `scripts/fit_ic_to_dms.py`
3. **Tests**: `tests/test_ic_analysis.py` (≥5 test cases)
4. **Doc update**: `PARAMETER_SOP.md` — new `§SOP-4.5` + `§SOP-5` script table row 
   (already in PARAMETER_SOP.md §SOP-4.5 and §SOP-5; do not duplicate)
5. **Doc update**: `PARAMETER_SOP.md §3.2` — add `ic_analysis_fit_quality` 
   and `ic_analysis_timestamp` columns to RPT CSV schema 
   (already in PARAMETER_SOP.md §3.2; do not duplicate)

Note: items 4 and 5 above were committed as part of the 2026-04-22 documentation 
PR, **before** this implementation begins. Do not re-edit those files during 
implementation unless something was missed.

---

## Algorithm Design (fixed — do not renegotiate without escalating to web chat)

### Forward model

C/40 is treated as **quasi-equilibrium**: no RC dynamics, no I·R drop. 
For each $Q_\text{cell}$ grid point, compute algebraically per paper:

1. $Q_\text{PE}(Q_\text{cell}) = Q_\text{PE}^0 + Q_\text{cell}$ (Eq. 18 integrated)
2. $Q_\text{NE}(Q_\text{cell}) = Q_\text{NE}^0 - Q_\text{cell}$ (Eq. 19 integrated, discharge convention)
3. $X_\text{PE} = Q_\text{PE} / (C_\text{PE}^0 - \mathrm{LAM}_\text{PE})$ (Eq. 25)
4. $X_\text{NE} = Q_\text{NE} / (C_\text{NE}^0 - \mathrm{LAM}_\text{NE})$ (Eq. 26)
5. $V_\text{cell} = V_\text{PE}^0(X_\text{PE}) - V_\text{NE}^0(X_\text{NE})$ (Eq. 1 at $I=0$)

Initial conditions for aged cell:
- $Q_\text{PE}^0 = X_\text{PE}^0 (C_\text{PE}^0 - \mathrm{LAM}_\text{PE})$ (Eq. 21, with $Q_\text{PE}^{\text{LLI},0} = 0$)
- $Q_\text{NE}^0 = X_\text{NE,aged}^0 (C_\text{NE}^0 - \mathrm{LAM}_\text{NE})$
  where $X_\text{NE,aged}^0$ accounts for LLI; derivation follows paper Eq. 55–56 
  logic applied to the aged state.

### Objective

$$
\mathcal{L}(\vec\theta) = \sum_i \bigl[V_\text{cell}^\text{obs}(Q_i) - V_\text{cell}^\text{model}(Q_i; \vec\theta)\bigr]^2
$$

$\vec\theta = (\mathrm{LAM}_\text{PE}, \mathrm{LAM}_\text{NE}, \mathrm{LLI})$, all in Ah.
**Do not fit on dQ/dV**: noise amplification and smoothing-coupling make it worse 
than V(Q). dQ/dV is **diagnostic-only**.

### Initial guess heuristic

1. Total capacity loss: $\Delta C = C^0 - C_\text{obs}$. Distribute to the three DMs 
   by (0.4 · LLI, 0.3 · LAM_PE, 0.3 · LAM_NE) as crude starting split.
2. Graphite stage 2↔3 peak position shift → refine LLI estimate.
3. Graphite stage 1↔2 peak height ratio → refine LAM_NE.
4. LAM_PE = total loss − LLI − LAM_NE (from step 1 budget).

Exact SOC-window thresholds for peak detection: let the implementation look them 
up from Dubarry & Anseán 2022 or Devie & Dubarry 2016 and document choice in 
docstring. Heuristic does not need to be tight — global V(Q) optimizer will refine.

### Optimizer

`scipy.optimize.least_squares(method='trf', bounds=...)`, returns residuals + Jacobian. 
Covariance: $\Sigma \approx (J^T J)^{-1} \hat\sigma^2$ where 
$\hat\sigma^2 = \text{SSE} / (N - 3)$.

### Bounds

- LLI: [0, 0.3 · C_nominal]
- LAM_PE: [0, 0.3 · C_PE_0]
- LAM_NE: [0, 0.3 · C_NE_0]

---

## Module API (`libquiv_aging/ic_analysis.py`)

```python
from dataclasses import dataclass
import numpy as np
from typing import Callable, Optional

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
    V_model: np.ndarray
    dQdV_obs: np.ndarray
    dQdV_model: np.ndarray
    Q_grid: np.ndarray


def analyze_ic(
    Q_obs_Ah: np.ndarray,
    V_obs_V: np.ndarray,
    *,
    cell_factory: Callable,
    smoothing_window_frac: float = 0.05,
    smoothing_polyorder: int = 3,
    bounds: Optional[dict] = None,
    initial_guess: Optional[dict] = None,
    method: str = 'trf',
    verbose: bool = False,
) -> ICAnalysisResult:
    """Extract (LLI, LAM_PE, LAM_NE) from aged cell C/40 discharge curve.

    Pipeline:
      1. Regularize (Q, V) onto uniform Q grid via linear interpolation
      2. Smooth V(Q) with Savitzky-Golay
      3. Compute heuristic initial guess via `heuristic_initial_guess`
      4. scipy.optimize.least_squares on V(Q) residuals
      5. Hessian-based covariance
      6. Compute diagnostic dQ/dV for observed and model

    Raises:
      ValueError if n_points < 50 or Q range < 50% of expected C_nominal.
    """
    ...


def synthesize_V_ocv(
    Q_cell_Ah: np.ndarray,
    LAM_PE_Ah: float,
    LAM_NE_Ah: float,
    LLI_Ah: float,
    *,
    cell_factory: Callable,
) -> np.ndarray:
    """Quasi-equilibrium forward model per paper Eqs. 1, 18–26 at I=0 limit.

    If EquivCircuitCell already exposes an OCV-only method (confirm in Step 0),
    wrap it. Otherwise implement the algebraic chain here.
    """
    ...


def heuristic_initial_guess(
    Q_obs_Ah: np.ndarray,
    V_obs_V: np.ndarray,
    *,
    cell_factory: Callable,
) -> dict:
    """Returns {'LLI_Ah', 'LAM_PE_Ah', 'LAM_NE_Ah'} starting point for optimizer.

    Uses total capacity loss + graphite stage-peak features. Does not need to be
    tight — global optimizer refines. See Dubarry & Anseán 2022 for peak-feature
    conventions.
    """
    ...
```

---

## CLI Script (`scripts/fit_ic_to_dms.py`)

```bash
python scripts/fit_ic_to_dms.py \
    --aged-data experiments/EXP-E/cell_E1_RPT03_C40.csv \
    --cell-type panasonic_ncr18650b \
    --output experiments/EXP-E/cell_E1_RPT03_dms.json \
    --plot experiments/EXP-E/cell_E1_RPT03_dms.png   # optional
```

**Input CSV schema**: required columns `Q_Ah`, `V_cell_V`. Optional: 
`time_s`, `I_A`. Auto-detect and flip if Q is descending.

**Output JSON schema**:
```json
{
  "LLI_Ah": 0.123,
  "LAM_PE_Ah": 0.045,
  "LAM_NE_Ah": 0.031,
  "LLI_std_Ah": 0.008,
  "LAM_PE_std_Ah": 0.006,
  "LAM_NE_std_Ah": 0.005,
  "fit_quality": {
    "rmse_V": 0.0085,
    "n_points": 1024,
    "converged": true,
    "iterations": 43
  },
  "metadata": {
    "input_file": "...",
    "cell_type": "panasonic_ncr18650b",
    "timestamp": "2026-04-22T12:34:56Z",
    "libquiv_aging_version": "...",
    "algorithm": "scipy.optimize.least_squares, trf method"
  }
}
```

**Diagnostic PNG** (2×2 layout):
- (0,0): V(Q) observed + model + residual
- (0,1): dQ/dV observed + model (smoothed)
- (1,0): bar chart of (LLI, LAM_PE, LAM_NE) with 1σ error bars
- (1,1): text summary (RMSE, convergence, iterations, metadata)

---

## Acceptance Tests (`tests/test_ic_analysis.py`)

**T1 Fresh-cell roundtrip**: synthesize V(Q) with (0,0,0), invert, recover < 0.005 Ah each.

**T2 Synthetic self-consistency**: for ground-truth triplets 
`{(0.05,0.02,0.01), (0.10,0.05,0.03), (0.15,0.08,0.05), (0.20,0.10,0.08), (0.25,0.15,0.10)}`, 
synthesize V(Q) + N(0, 2 mV) noise, invert, assert each recovered DM within 2σ of truth.

**T3 Hessian covariance sanity**: for T2 cases, assert 
`LLI_std < 0.02`, `LAM_PE_std < 0.02`, `LAM_NE_std < 0.02`. Any failure → 
investigate identifiability and report in test output.

**T4 Conservation check**: recovered `LLI + LAM_PE + LAM_NE` ≈ capacity loss 
within 10% (accounts for LR-coupling via paper Eq. 53).

**T5 Input validation**: reject CSV with <50 points; reject CSV with Q range 
<1.5 Ah; accept ascending-Q or descending-Q input (auto-flip).

---

## Implementation Notes

**Performance target**: <2 s per RPT on standard laptop. C/40 forward model is 
algebraic, no ODE solve. Vectorize over Q array via numpy.

**Numerical subtleties**:
- Q grid strictly monotone. Deduplicate + resort input before use.
- Savitzky-Golay window: `max(5, (int(smoothing_window_frac * n) // 2) * 2 + 1)`.
- Model interpolated onto observed Q grid, not vice versa. Aged Q range < fresh Q range.
- V_PE_0(X) HalfCellThermo has bounded X domain ([0.162, 0.95] for NCA). If 
  optimizer drives X_PE out of bounds, return `np.inf` residual — no silent 
  extrapolation.
- Savitzky-Golay is applied to V(Q) **before** differentiation. Do not 
  differentiate first then smooth.

**Dependencies**: numpy, scipy ≥ 1.10, pandas, matplotlib (plot-only). 
All present in existing `libquiv-aging` conda env.

---

## Out of Scope for v1 (do not implement)

- Multi-RPT joint / temporal-smoothing fits (v2)
- Temperature-corrected inversion (depends on future T(model) extension)
- MCMC / ensemble UQ (v2 if needed)
- Automatic detection of non-alawa regime (extreme LAM where peaks merge)
- CEI / LLI_PE (paper assumes zero; we follow)
- Charge-curve IC analysis (discharge-only in v1; CV tail messes up NCA/G on charge)

---

## Documentation Updates (handled in 2026-04-22 documentation PR, not here)

SOP entries, §SOP-4.5 section, §SOP-5 script table row, and §3.2 CSV column 
additions are all done in the 2026-04-22 documentation PR (methodological 
rationale: 2026-04-22 web-chat discussion Q1–Q6). **Do not re-edit these 
during the implementation PR.** Module docstring should still cite Dubarry & 
Anseán 2022 as the methodological reference.

`PARAMETERS.json::fit_steps`: **no change required** — IC analysis produces 
intermediate data for FIT-4a/b, not new parameters.
