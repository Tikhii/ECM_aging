# 0015. Dispatch pattern for relaxation models (FIT-2 future-proofing)

Date: 2026-04-26
Status: accepted

## Context

FIT-2 v0.5.0 introduces a two-exponential relaxation model. CRITICAL_REVIEW.md C7 identifies an upgrade direction: long-relaxation behavior (~minutes) is poorly captured by two-exponential RC and would benefit from fractional-order / Mittag-Leffler / DRT (Distribution of Relaxation Times) models. `docs/UPGRADE_LITERATURE/fractional_order_RC.md` documents the specific candidate models and required reading.

Two implementation choices for v0.5.0:

- **Hardcode `two_exponential` in the CLI and fit functions** — simplest now, but every future model upgrade requires rewriting the CLI flag handling, fit loop, and spec writeback paths. Each upgrade introduces regression risk.
- **Introduce a dispatch table** — small upfront cost (a dict + a getter), but new models register as new entries without touching the CLI or writeback machinery.

This is a textbook over-design risk: building extension points for models that may never land. The decision rests on whether the upgrade direction is a near-term, identified path or a hypothetical future.

## Decision

Introduce a dispatch table `RELAXATION_MODELS` keyed by model name. v0.5.0 ships with one registered entry: `two_exponential`. The CLI `--relaxation-model` flag is a dispatch-table key with `two_exponential` as default.

Future model additions (fractional-order, Mittag-Leffler, DRT, etc.) register a new entry by:

1. Implementing the fit function with the same signature contract.
2. Adding a `RELAXATION_MODELS["<name>"] = <fit_fn>` line.
3. No change to CLI argument parsing, no change to spec writeback (`fitting.py::write_back_to_spec` is model-agnostic), no change to error codes (FIT2-Exxx scope covers all relaxation models in this registry).

This is **Occam's Razor reverse-applied**: when an upgrade direction is concretely identified (UPGRADE_LITERATURE entry exists with citations), and the upgrade is near-term (C7 finding active), proactive abstraction is justified — the alternative is paying the upgrade cost in regression risk later. The judgment is conservative when applied incorrectly (one extra dict lookup per fit run, ~zero cost) and pays back significantly when an upgrade lands (CLI / writeback paths untouched).

## Alternatives

- **Hardcode `two_exponential`** — rejected per the reasoning above. The C7 upgrade direction is identified, not hypothetical; the cost of refactoring later exceeds the cost of dispatch now.
- **Plugin discovery (entry points, file-system scanning)** — rejected. The four-or-five-model future registry doesn't justify discovery machinery; an explicit dict is more readable and debuggable.
- **Subclass-based polymorphism** (`class RelaxationModel; class TwoExponential(RelaxationModel)`) — rejected. Subclasses for what would be 4-5 model families is heavier than a function dispatch; no shared state is held across calls.

## Consequences

Positive:
- C7 upgrade path is structurally ready: the upgrade work becomes "implement and register", not "implement, refactor CLI, refactor writeback, retest all paths".
- Dispatch entry is a single line, easily grep-able when surveying available models.
- `additionalProperties: true` on `value_with_provenance` (see ADR-0014) is the spec-side counterpart: the dispatch handles the code side; the schema accommodates per-model metadata.

Negative:
- A reader new to the codebase encounters indirection — `RELAXATION_MODELS["two_exponential"]` instead of a direct call. Documented in the module docstring, but still a small cognitive cost.
- If the C7 upgrade direction turns out wrong (e.g., DRT becomes the consensus and fractional-order is abandoned), the dispatch was justified retrospectively only if C7-flagged models ever land. As of v0.5.0 the answer is "yes, at least one upgrade is near-term planned"; if that planning lapses the dispatch becomes infrastructure-without-customers.

## References

- `libquiv_aging/relaxation_fitting.py::RELAXATION_MODELS`
- `scripts/fit_rc_transient.py` CLI `--relaxation-model` flag
- `docs/UPGRADE_LITERATURE/fractional_order_RC.md`
- `docs/CRITICAL_REVIEW.md` C7 finding
- `docs/legacy/MIGRATION_NOTES.md` §十八.2.2
- ADR-0014 (paired tau→R mapping decision; same FIT-2 batch)
- Tag: `release/v0.5.0`
