# 0004. R6 error code chain (registry → runbook → scripts) with independent fact-layer registry

Date: 2026-04-23
Status: accepted

## Context

The 2026-04-23 batch introduced an air-gapped offline workflow with explicit error-code-driven recovery procedures. This required a new artifact class: error codes with `trigger / consequence / cross_refs / script_behavior / immediate_action / followup / escalation` fields, consumed by both fitting scripts and field operators reading the offline runbook.

Two questions had to be answered:

1. Where does the fact layer live — folded into `PARAMETERS.json`, or in a separate document?
2. What is the modification ordering rule — analogous to R1 but for error codes?

## Decision

**Independent fact-layer document**: `docs/error_codes_registry.json`. Not folded into PARAMETERS.json. Schema-validated against `docs/error_codes.schema.json`.

The independence rationale is semantic purity: PARAMETERS.json answers "what parameters exist, where do they come from"; the registry answers "what can go wrong, how is it intercepted, when does it escalate". The two have completely different change cadences and consumer sets — folding them would create coupling (R1 and R6 modification orderings would interfere) without a corresponding benefit.

**R6 modification ordering**:

```
docs/error_codes_registry.json  (fact layer)
   →  docs/07_offline_runbook.md  (derived layer)
   →  scripts/  (consumer raise sites and exit codes)
```

**Number-reuse prohibition**: error code numbers, once issued, are never reused. Deprecated entries are marked `status=deprecated` with `deprecated_note` pointing to the replacement code. This mirrors R1's fact-layer-first principle but with the additional constraint that error codes are protocol-level identifiers (consumed by field-side operators, logged into release artifacts) and renumbering would silently invalidate old logs.

**Layering with the runbook**: the 11-field schema (trigger, consequence, cross_refs, script_behavior, etc.) lives in the registry; the runbook restates these fields in human-readable form per error code. When the two disagree, the registry wins (same as PARAMETERS.json wins over MD).

**Layering with the consultation protocol**: `docs/08_consultation_protocol.md §4` defines an observation-note template for escalating to online consultation; the registry's `escalation` field interlocks with that template. Either side modifying requires synchronization.

## Alternatives

- **Fold error codes into PARAMETERS.json under a `error_codes` key** — rejected. Different change cadence (parameters change at FIT cadence; errors at incident cadence), different consumers (model code vs field operators), different schemas (parameter triplets vs 11-field error definitions). Folding would create coupling without compression.
- **Allow number reuse for deprecated codes** — rejected. Old logs would silently re-resolve to new meanings. Deprecation with frozen numbers is the only safe path.
- **Skip the runbook entirely and have scripts emit error documentation directly** — rejected. The runbook is read offline by field operators without script source access; it must exist as a standalone derived document.

## Consequences

Positive:
- R1 and R6 evolve independently. A new parameter does not force an error-code review and vice versa.
- Number-reuse prohibition makes log forensics tractable across release versions.
- The 11-field schema is enforced (via `docs/error_codes.schema.json`), catching ill-specified error codes before they enter the registry.

Negative:
- Two fact-layer JSONs to maintain. New contributors must learn the boundary.
- Cross-doc invariants (registry ↔ runbook ↔ consultation-protocol template) need vigilance — R6 enforces the registry → runbook leg; the consultation-protocol leg is currently informal.
- Deprecated entries accumulate over time; periodic review is needed to ensure `deprecated_note` references stay valid.

## References

- `docs/error_codes_registry.json`
- `docs/error_codes.schema.json`
- `docs/07_offline_runbook.md`
- `docs/08_consultation_protocol.md §4`
- `docs/CLAUDE.md` R6 rule text
- `docs/legacy/MIGRATION_NOTES.md` §十 (offline workflow architectural decisions, including independent-registry rationale lines 140-144)
- Tag: `docs/v0.2.0-offline-workflow`
