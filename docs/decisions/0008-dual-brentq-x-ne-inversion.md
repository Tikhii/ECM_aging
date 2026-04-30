# 0008. Dual brentq for X_NE inversion (V_min + V_max) with bracket-helper for fail-fast at alawa edge

Date: 2026-04-28
Status: accepted

## Context

IC analysis (`libquiv_aging/ic_analysis.py`) inverts a forward voltage model to find the X_NE corresponding to a target voltage. The first implementation in subphase 2 of the v0.5.2 task used a single `brentq` call anchored at V_max, on the implicit assumption that `dQ = 0` corresponds to V_min.

Self-test exposed the assumption: the spec's `X0_NE` combined with the paper Eq. 22 SEI subtraction term produced an X_NE ≈ -0.008 at the V_min end — a non-physical negative stoichiometry. `brentq` cannot bracket through this region; the assumption "dQ = 0 ↔ V_min" is wrong in the presence of aging.

A second issue: the IC analysis optimizer pushes (LAM_PE, LAM_NE, LLI) toward alawa-regime boundaries during optimization. At those boundaries, the bracket window for `brentq` may have `f(a) * f(b) > 0`, causing brentq to raise a hard error rather than the expected fail-fast `inf` residual signal.

The fix had to be more than a single-bracket adjustment — it had to handle aging-shifted endpoints AND optimizer-driven edge-condition robustness.

## Decision

**Dual brentq**: invert at V_min and V_max independently, in two `brentq` calls. This pattern is borrowed from `scripts/fit_electrode_balance.py::_calibrate_soc_bounds`, the FIT-1 fresh-cell SOC-calibration routine. The two routines now share the same dual-brentq shape, but the IC analysis case adds an extra robustness layer (next item).

**Bracket-helper `_bracket_dQ_for_voltage(target_V)`**: 41-point sampling over the physically-feasible dQ domain to find the first sign-change pair, which is then handed to `brentq` as a clean bracket. This avoids `brentq`'s `f(a) * f(b) > 0` failure mode by explicitly establishing the bracket exists before invoking the solver. When no sign-change pair is found in the 41-point sweep (i.e., the target voltage is outside the achievable range under the current degradation hypothesis), the routine returns `inf` residual immediately — the fail-fast signal the optimizer needs.

**Fresh-state-model-capacity helper** (added in subphase 2 v2): `_fresh_state_model_capacity_Ah(art)` factored out the same dual-brentq + bracket pattern for `heuristic_initial_guess`'s fresh-cell capacity estimate. This avoids relying on an externally-supplied guess.

**Performance**: measured ~3.9 ms per evaluation (including spec re-load). Below the SPEC `<10 ms/eval` threshold.

## Alternatives

- **Single brentq with aging-aware bracket** — explored. Aging shifts the bracket endpoints in a state-dependent way; constructing a single correct bracket requires knowing the aging hypothesis a priori, which is precisely what IC analysis is solving for. Circular.
- **Newton iteration with damping** (avoiding brentq entirely) — rejected. Newton needs a derivative; the forward model's piecewise-linear interpolation makes derivatives non-smooth at lookup-table knots, requiring fallback machinery that ends up more complex than dual brentq + bracket.
- **Reuse FIT-1 `_calibrate_soc_bounds` directly** (no IC-specific bracket helper) — rejected. FIT-1 calibrates fresh cells once; brackets are well-conditioned. IC analysis evaluates many times per optimization step at potentially edge-pushing points; bracket-helper failsafe is needed.

## Consequences

Positive:
- IC analysis is robust under optimizer-driven edge probing — aging-regime boundaries produce explicit `inf` residual rather than solver crashes.
- Pattern alignment with FIT-1 (dual brentq) reduces conceptual surface area when reading either routine.
- The bracket-helper is reusable: applied to the fresh-state capacity estimate inside `heuristic_initial_guess` in the v2 follow-up.

Negative:
- Two brentq calls per evaluation is ~2× the cost of a (working) single call. The 3.9 ms result is comfortable but the constant doubles.
- 41-point sampling is a magic number; chosen empirically to cover the domain without excessive cost. A future refinement might adapt sampling density.

## References

- `libquiv_aging/ic_analysis.py::_bracket_dQ_for_voltage`
- `libquiv_aging/ic_analysis.py::_fresh_state_model_capacity_Ah` (subphase-2 v2 abstraction)
- `scripts/fit_electrode_balance.py::_calibrate_soc_bounds` (parallel pattern in FIT-1)
- `docs/legacy/MIGRATION_NOTES.md` §20.3.1 (single → dual brentq + bracket-helper rationale)
- `docs/SPEC_ic_analysis.md` (frozen SPEC, performance target <10 ms/eval)
