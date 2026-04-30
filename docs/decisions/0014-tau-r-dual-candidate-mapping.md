# 0014. tau→R dual candidate mapping with amplitude RSS selection (FIT-2)

Date: 2026-04-26
Status: accepted

## Context

FIT-2 fits the RC relaxation behavior using a two-exponential model, returning fitted time constants `(tau1, tau2)`. In the equivalent-circuit topology, each tau is associated with one of two electrodes (NE or PE) — tau1 anchors to either R_NE or R_PE depending on which electrode has the shorter RC time constant for the cell at hand. The mapping is not knowable a priori from `(tau1, tau2)` alone.

Letting users manually specify the mapping direction was rejected as an option from the outset: under R7's spirit, parameters and parameter assignments must be data-and-LUT-driven, not human judgment calls. Manual mapping would turn C1 / C2 into vehicles for unintended hand-tuning.

The fitter therefore must auto-select the mapping with a defensible decision rule, and must signal the user when the selection is marginal so downstream consumers can apply appropriate weighting.

## Decision

For each FIT-2 fit, compute both candidate mappings:

- **candidate_A**: `tau1 ↔ R_NE`, `tau2 ↔ R_PE`
- **candidate_B**: `tau1 ↔ R_PE`, `tau2 ↔ R_NE`

For each candidate, derive the expected amplitudes `(A1, A2)` from the LUT-queried `(R_NE, R_PE)` values and compare to the fitted amplitudes via residual sum of squares (RSS). The candidate with the lower RSS is `chosen`; the other is `alternate`.

**Marginality warning**: when `|RSS_chosen - RSS_alternate| / max(RSS_chosen, RSS_alternate) < 10%`, raise `FIT2-W001` (mapping_marginal=true). The threshold is empirical — fits below 10% RSS gap are not statistically distinguishable given typical measurement noise.

The `mapping_marginal` flag is persisted in the spec's `relaxation_metadata` (a sub-object on C1 / C2 entries; see `additionalProperties: true` in the schema). Downstream FIT-3 / FIT-4 should detect `mapping_marginal=true` and reduce the C1 / C2 weight in their objective functions.

## Alternatives

- **Always pick candidate_A** (no auto-selection) — rejected. Half of cells will have wrong mapping; FIT-3/4 consumers receive systematically biased C1 / C2 values.
- **Manual user mapping flag** — rejected as discussed above.
- **Hard-fail (raise error) on marginal cases instead of warning** — rejected. Marginal mapping is still useful information for downstream consumers; a hard-fail would force re-collection or mock-data substitution, which is more disruptive than a warning + downstream weighting.
- **Use a third statistic** (e.g., AIC / BIC) — rejected. RSS is dimensionally direct (amplitudes have units), interpretable, and readily compared against measurement noise. AIC/BIC add complexity without changing the decision in the marginal regime.

## Consequences

Positive:
- C1 / C2 spec entries include enough diagnostic metadata (`relaxation_metadata.mapping_marginal`) for downstream consumers to weigh appropriately.
- The fitter's behavior is fully data-driven — no human knob exposes itself to inadvertent hand-tuning.
- The 10% threshold is documented and adjustable if measurement noise levels change.

Negative:
- The RSS comparison adds work proportional to forward-model evaluations × 2; for FIT-2 the cost is negligible but worth flagging if the pattern is replicated for higher-dimensional fits.
- The marginal-warning threshold requires periodic re-validation — if measurement noise tightens significantly, 10% may become too lax.

## References

- `libquiv_aging/relaxation_fitting.py`
- `scripts/fit_rc_transient.py`
- `docs/error_codes_registry.json::FIT2-W001`
- `schemas/params_mmeka2025.schema.v1.json` (`additionalProperties: true` on `value_with_provenance`)
- `docs/legacy/MIGRATION_NOTES.md` §十八.2.3
- Tag: `release/v0.5.0`
