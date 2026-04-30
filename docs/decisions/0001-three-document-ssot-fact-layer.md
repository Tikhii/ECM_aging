# 0001. Three-document SSoT (PARAMETERS.json + PARAMETER_SOP + CRITICAL_REVIEW) as fact-layer authority

Date: 2026-04-20
Status: accepted

## Context

Early in the project, parameter information was scattered across multiple narrative markdown documents. A concrete consequence: `R_SEI` was incorrectly attributed to a cycle-aging fitting step, while the paper (Mmeka 2025) explicitly identifies it as a calendar-aging parameter. The narrative drift was undetectable because no single document was authoritative — every document partially described parameters, and nothing forced consistency.

This forced a structural decision: where does the truth live, and how is it kept consistent across many derived layers (narrative docs, code comments, error code definitions, fitting scripts, README descriptions)?

## Decision

Three documents constitute the engineering single source of truth (SSoT). When any other source (narrative MD, code comment, README) conflicts with these, the SSoT wins:

1. **`docs/PARAMETERS.json`** — fact layer. All parameter metadata: values, units, sources, code locations, fit-step provenance, `paper_errata` field, `critical_review_findings` index. Machine-readable.
2. **`docs/PARAMETER_SOP.md`** — process layer. Standard operating procedures for the seven experiments (EXP-A through EXP-G) and seven fit steps (FIT-0 through FIT-4c). Human-readable but structurally aligned with PARAMETERS.json.
3. **`docs/CRITICAL_REVIEW.md`** — diagnostic layer. Paper errata, scope-of-validity cards, simplifying-assumption ledger, upgrade paths.

R1 (parameter-modification ordering: PARAMETERS.json → code → MD) operationalizes the SSoT relationship: every parameter change must originate in the fact layer.

`docs/error_codes_registry.json` was later carved out as a parallel fact-layer document for error codes (see ADR-0004). The two-fact-document pattern is intentional — different change cadences and different consumer sets justify keeping them separate rather than folded.

## Alternatives

- **Single monolithic markdown SSoT** — rejected. Markdown lacks schema enforcement; the original drift problem stemmed precisely from "everything is narrative".
- **Code-as-SSoT (Python dataclasses with docstrings)** — rejected. Would couple parameter authority to release cadence and force code edits for non-implementation parameter changes (units, source citations, errata flags).
- **External database (e.g., SQLite)** — rejected. Overkill for ~40 parameters; incompatible with git-based diff/review workflow.

## Consequences

Positive:
- Conflict resolution rule is unambiguous: when two sources disagree, look up which layer is which, prefer fact layer.
- New parameters cannot quietly enter the project — they must land in PARAMETERS.json first, which forces the sources/units/provenance fields to be filled.
- Cross-document consistency (R5) and cross-fact-document boundaries (R6) become tractable rules because the layering exists.

Negative:
- PARAMETERS.json grew complex (deferred_extensions, critical_review_findings, paper_errata, scope_of_validity sub-trees). Schema-of-schemas drift is a future risk.
- Editing requires discipline: editing only the narrative MD without updating JSON is a frequent slip-up that R1 specifically addresses.

## References

- `docs/PARAMETERS.json` (file itself)
- `docs/CLAUDE.md` § "工程单一事实来源 (SSoT)"
- `docs/CLAUDE.md` R1 rule text
- Original incident: `R_SEI` mis-routing (predates MIGRATION_NOTES.md; documented retrospectively in `docs/legacy/MIGRATION_NOTES.md` §一 / §二)
