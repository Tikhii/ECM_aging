# 0011. RPT bidirectional data contract (C/40 + IR both directions) with DATA-E004/E005

Date: 2026-04-29
Status: accepted

## Context

`scripts/fit_ic_to_dms.py` (IC analysis CLI, v0.5.2) reads RPT C/40 data and computes incremental capacity (IC) curves to extract degradation modes (LLI, LAM_PE, LAM_NE). The IC method is most informative when both charge-direction and discharge-direction curves are available — the two directions reveal stage-feature asymmetries that single-direction data cannot resolve.

External-SOP review (v1.4) discovered that:

- The script implicitly expected charge-direction data (line 5, line 290 in `fit_ic_to_dms.py` reference charge-direction conventions).
- The internal data-delivery protocol (`PARAMETERS.json::experiments::EXP-E`) did NOT require both directions.
- The mismatch was an undocumented hidden assumption between the consumer (IC analysis script) and the producer (experimental delivery).

Without explicit fact-layer specification, an external team delivering single-direction RPT data would (silently) provide insufficient input for the script's actual capability — the script would either fail with a confusing error or, worse, produce results from incomplete data.

## Decision

**Fact layer first** (per ADR-0001 / R1):

- `PARAMETERS.json::experiments::EXP-E::CRITICAL` adds three mandatory clauses requiring bidirectional delivery for: C/5 cycling, IR pulse measurements, and C/40 RPT.
- `docs/error_codes_registry.json` adds **DATA-E004** (single-direction IR pulse) and **DATA-E005** (missing direction file in C/40 set). Both are field-detectable at data-ingestion time, so failures surface before the optimizer is invoked.

**Derived layer follows**:

- `docs/PARAMETER_SOP.md §3.2` updates the RPT-CSV format table to show both-direction columns.
- `docs/07_offline_runbook.md` adds DATA-E004/E005 entries with diagnostic procedures.

**Script-side dual-direction consumption is deferred** (recorded as deferred extension): `fit_ic_to_dms.py` continues to read discharge-direction only in v0.5.2. Trigger conditions for picking up the deferred work:
- First batch of real RPT data delivered under the new contract, OR
- Drafting a SPEC for dual-direction support that doesn't depend on real data delivery (mock fixture sufficient).

The deferred work is safe because DATA-E005 catches missing-direction conditions at ingestion — experimental teams have been notified to deliver both directions; the script ignoring the charge direction does not corrupt current discharge-only correctness.

## Alternatives

- **Update the script to consume both directions immediately, before fact-layer formalization** — rejected. Violates R1 (fact layer first) and would have produced a script with no specification anchor; future maintainers would have no record of why dual-direction support exists.
- **Document the discharge-only assumption in the script docstring without changing the data contract** — rejected. Externalizes a hidden assumption rather than fixing it; the next external SOP review would re-encounter the same problem.
- **Skip DATA-E004 and rely on DATA-E005 alone** — rejected. IR pulses and C/40 sweeps fail in different ways, and the diagnostic "this IR pulse only has one direction" is distinct from "this RPT folder is missing a direction-tagged file".

## Consequences

Positive:
- Hidden assumption is now explicit at the fact layer; cannot drift away unnoticed.
- DATA-E004/E005 give experimental teams clear actionable error messages, reducing back-and-forth in delivery iterations.
- Deferred script update is intentional and recorded with trigger conditions, not abandoned.

Negative:
- Existing single-direction historical data (pre-contract) requires retroactive direction-tagging to be ingestible — a one-time migration burden for teams with archives.
- The deferred dual-direction script consumption means current IC analysis cannot use the additional information from the charge direction even if delivered. Until script update lands, the contract is "deliver both" but use is "discharge only".

## References

- `PARAMETERS.json::experiments::EXP-E::CRITICAL`
- `docs/error_codes_registry.json::DATA-E004`, `DATA-E005`
- `docs/PARAMETER_SOP.md §3.2`
- `docs/07_offline_runbook.md` DATA-E004/E005 entries
- `scripts/fit_ic_to_dms.py` (current discharge-only consumer)
- `docs/legacy/MIGRATION_NOTES.md` §二十一.2.1, §二十一.4.1 (deferred dual-direction trigger conditions)
- Commit `dadb15c`
