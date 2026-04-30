# 0009. Path B algebraic forward (vectorized lookup_tables) for IC analysis, over Path A (EquivCircuitCell)

Date: 2026-04-28
Status: accepted

## Context

The frozen `docs/SPEC_ic_analysis.md` contract requires `synthesize_V_ocv(...)` to evaluate an open-circuit-voltage forward model fast enough to satisfy `<2 s/RPT` total wall-clock — including the inner optimizer's many forward evaluations.

Subphase 0 reconnaissance (the empirical-driven SPEC-implementation start, see ADR-0003 R5 spirit) examined two implementation paths:

**Path A — reuse `EquivCircuitCell.open_circuit_voltage_cell()`**:
- Returns the cell-terminal V at a single SOC point.
- Internally calls `_aging_calibrate_SOC`, which performs 2× brentq per call.
- Scanning N points across the Q grid → 2N brentq solves per forward evaluation.
- Measured: seconds per forward, blowing through the SPEC budget.

**Path B — call `lookup_tables.open_circuit_voltage(X_NE, X_PE, T, ...)` directly**:
- Vectorized primitive that accepts numpy arrays and returns `(V0, dS_NE, dS_PE, V0_PE, V0_NE)`.
- Internal `interp_dH_dS` is plain linear interpolation over LUT data.
- No brentq inside the forward path.
- Measured: ~3.9 ms per evaluation including spec re-load (see ADR-0008).

A separate finding: `HalfCellThermo.interp_dH_dS(X)` silent-clamps X∈[0,1] rather than returning `inf`. Path B requires explicit X-domain checking by the caller — the boundary handling is a caller responsibility, not an interface defect.

## Decision

**Path B is the implementation path** for IC analysis forward evaluation. Specifically:

- `libquiv_aging/ic_analysis.py::synthesize_V_ocv` uses `lookup_tables.open_circuit_voltage` directly.
- The caller (IC optimizer + dual-brentq inversion) explicitly checks X_NE, X_PE domain validity before invocation; out-of-domain conditions return `inf` residual to the optimizer (see ADR-0008 bracket-helper behavior).
- Module-level helpers `_derive_C0_PE`, `_derive_C0_NE`, `_derive_Q0_SEI_NE` are reused as-is from existing code (signatures match SPEC); A·s → Ah unit conversion (`/3600`) is performed at the call site.

**The decision rests on a hard constraint, not a stylistic preference**: Path A's `init()` brentq makes the SPEC performance budget unreachable. This is recorded explicitly because earlier task-package framing described Path B as "decoupling that's more suitable for pure-forward computation" — the actual reason is harder.

**A related architectural choice**: IC analysis output (`(LLI, LAM_PE, LAM_NE)` per RPT) does **not** write back to spec files. Instead, each RPT produces an independent JSON artifact for downstream FIT-4a/4b consumption. This is recorded here as context for why Path B's clean-decoupling pays off (no spec-writeback machinery on the IC side), but the no-writeback decision itself is documented in `CHANGELOG.md` and `docs/SPEC_ic_analysis.md §3` rather than as a separate ADR — IC analysis has no slot in the FIT-X numbering system (SOP-4.5 is FIT-4 input preparation, not an independent FIT step), so the "spec writeback only via FIT-X" R7 spirit is preserved.

## Alternatives

- **Path A with caching** (memoize `_aging_calibrate_SOC` outputs) — rejected. Cache keys would have to include the entire degradation-state vector; cache hit rate during optimization would be ~0.
- **Path A with a "fast-mode" flag** that skips brentq-based calibration — rejected. Adds branch logic in `EquivCircuitCell` that exists solely for IC analysis, polluting the cell model with fitting-script concerns.
- **A new third primitive** (custom vectorized OCV that bypasses both Path A and Path B) — rejected. `lookup_tables.open_circuit_voltage` is already the right primitive; reinventing it would duplicate maintenance burden.

## Consequences

Positive:
- IC analysis meets the `<2 s/RPT` SPEC target with margin (measured ~3.9 ms/eval × typical optimizer iterations).
- `EquivCircuitCell` remains uncomplicated by IC-analysis-specific shortcuts.
- The "caller checks X domain" responsibility is straightforward (one bounds check per call) and aligns with the bracket-helper (ADR-0008) which already needs sign-change scan over the physical domain.

Negative:
- The X-domain check is duplicated between `synthesize_V_ocv` and the bracket helper — two places to keep aligned if a future change tightens the domain.
- New maintainers may be surprised that IC analysis bypasses `EquivCircuitCell.open_circuit_voltage_cell`. Module docstring + ADR cross-reference mitigates.

## References

- `libquiv_aging/ic_analysis.py::synthesize_V_ocv`
- `libquiv_aging/lookup_tables.py::open_circuit_voltage`
- `libquiv_aging/cell_model.py::EquivCircuitCell.open_circuit_voltage_cell` (Path A, not used)
- `docs/SPEC_ic_analysis.md` (performance target, no-writeback contract)
- `docs/legacy/MIGRATION_NOTES.md` §20.2 (Step 0 reconnaissance findings)
- `docs/legacy/MIGRATION_NOTES.md` §20.3.3 (no-writeback decision)
- ADR-0008 (dual brentq + bracket helper, the inversion side that consumes Path B's forward)
