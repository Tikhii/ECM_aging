# 0012. EXP-B4 splits with preferred / fallback / fallback_warning structure

Date: 2026-04-29
Status: accepted

## Context

EXP-B4 is the GITT scan that produces the 2D resistance lookup tables (`R_NE_LUT`, `R_PE_LUT`). The protocol historically described `splits` as a single-string field encoding the chemistry-specific NE/PE resistance partition assumption. This worked when a chemistry's preferred split was unambiguous, but external-SOP review (v1.4) surfaced two issues:

1. Real-world experimental teams sometimes cannot execute the preferred split (instrument limitations, sample geometry constraints) and must fall back to a less-precise alternative. The single-string field had no slot for "fallback option" — teams either deviated silently or escalated as a question.
2. The accuracy degradation of the fallback was not documented at the data-contract level. Downstream FIT-2/3 consumers had no way to know whether their inputs were preferred-split or fallback-split outputs.

The fix had to enrich the data contract without breaking existing consumers and to document the precision trade-off explicitly.

## Decision

`PARAMETERS.json::experiments::EXP-B4::splits` is restructured from a single string to an object with three keys:

- `preferred` — chemistry-specific preferred split protocol.
- `fallback` — alternative protocol when preferred is not executable.
- `fallback_warning` — explicit precision-degradation note (10–20% accuracy loss expected when fallback is used).

A new field `ne_pe_split_ratio_default` records the chemistry-default partition ratio:
- NCA-G / NMC-G: 0.6 / 0.4
- LFP / G: 0.5 / 0.5

When neither preferred nor fallback can be executed, the chemistry-default ratio applies — sufficient for the model to run but with the precision trade-off downstream FIT consumers can detect.

**Fact-layer first** (R1): the `splits` object lives in PARAMETERS.json. Derived layers (PARAMETER_SOP §二, narrative docs) reference it but do not redefine.

## Alternatives

- **Two separate fields** (`splits_preferred` and `splits_fallback`) — rejected. Two fields decouple the relationship; the `fallback_warning` cannot easily attach to either. A single object groups the related data.
- **Keep single string, add separate `splits_fallback_warning` field** — rejected. Same decoupling problem; multiple top-level fields encoding one concept.
- **Drop the fallback option entirely; require preferred or escalate** — rejected. Real experimental teams hit instrument constraints; refusing to document the fallback path forces silent deviation, which is worse.

## Consequences

Positive:
- External teams have an explicit fallback path with precision expectations stated upfront.
- Downstream FIT-2/3 consumers can detect whether inputs were preferred or fallback (by checking which split produced the LUT), and can apply confidence weighting.
- The `ne_pe_split_ratio_default` is a chemistry-level fact that no longer needs to be hunted down in narrative docs.

Negative:
- Schema migration: existing consumers reading `splits` as a string break under the new object shape. The change was made at v0.5.3 commit `7be3ffd`; consumers were updated in the same commit. Future external schema readers must use the post-7be3ffd shape.
- The 10–20% precision band is a rule of thumb, not a derived bound. Future instrumentation studies might tighten or widen it; the field is a string warning, not a quantitative tolerance, by design (precision is dataset-dependent and overly-precise warnings would mislead).

## References

- `PARAMETERS.json::experiments::EXP-B4::splits`
- `PARAMETERS.json::experiments::EXP-B4::ne_pe_split_ratio_default`
- `docs/PARAMETER_SOP.md §二` (real-source declaration prelude — protocol params live in PARAMETERS.json)
- `docs/legacy/MIGRATION_NOTES.md` §二十一.2.2
- Commit `7be3ffd`
