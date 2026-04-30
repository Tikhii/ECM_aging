# 0006. R8 README/QUICKSTART/CLAUDE.md sync triggers (with member extension to LICENSE/NOTICE/pyproject.toml)

Date: 2026-04-25
Status: accepted

## Context

Through v0.4.0, the project's outward-facing surfaces — `README.md` and `QUICKSTART.md` — had not been updated since v0.1. They claimed "5 modules" (actual: 8+), "15 tests" (actual: 69), missing `schemas/`, `material_specs/`, `param_specs/`, `scripts/` from the directory tree, and missing six docs (06-09 + MIGRATION_NOTES + error_codes_*) from the navigation table. The dual-spec architecture (v0.3.0) and FIT script series (v0.4.0) were entirely absent.

R1-R7 covered model correctness (R1, R2, R3, R4) and internal document self-consistency (R5, R6, R7). None addressed "outward project consistency" — README is a presentation surface, it doesn't affect whether the model runs correctly, so task-driven workflows had been ignoring it.

This is a workflow-category gap, not a single-file oversight. The fix had to institute "outward consistency" as a first-class category alongside the existing rules.

## Decision

**R8 trigger conditions**: before tagging any `release/vX.Y.0`, README.md is reviewed. If the release introduced any of the four trigger categories, README updates are a mandatory release-task subphase, equal in priority to code/doc/error-code changes:

1. New public API (exported function / class / CLI script)
2. New directory structure (top-level addition like `schemas/`, `material_specs/`)
3. New workflow entry (new tag-naming convention, new air-gapped procedure)
4. New concept (cell type, mechanism version routing, dual-spec architecture)

**QUICKSTART.md** follows the same rule (it is the executable-summary form of README).

**`docs/vX.Y.Z` patches** do not require README updates by default, unless the patch specifically fixes functionality described in README.

**R8 vs R5 boundary**: R5 governs internal-document consistency (PARAMETERS.json ↔ code ↔ MD); R8 governs project-outward consistency (README/QUICKSTART ↔ actual functionality). They are complementary, not overlapping. R8 fills the workflow-category gap that R5 alone could not address.

**Member extension** (added retroactively in v0.4.3): R8 covers additional outward-facing artifacts beyond README/QUICKSTART, each with independent triggers:

- **`LICENSE` / `NOTICE`** — triggered by license changes, attribution changes, copyright-year transitions, or upstream license-chain shifts (upstream license upgrade, paper/dataset license change).
- **`pyproject.toml` `description` field** — triggered by project-positioning changes (e.g., "Python port" → "Python implementation with extensions") or key-citation shifts (primary paper DOI, upstream attribution).

These members are not reviewed every release; their independent triggers govern. When a trigger fires, sync priority is equal to README/QUICKSTART.

`CONTRIBUTING.md` is a candidate member, deferred until the project first accepts external contributions.

## Alternatives

- **Generalize an existing rule** to cover outward consistency — rejected. R5's domain (internal-document mutual consistency) is structurally different from R8's (presentation-vs-functionality consistency). Forcing one rule to cover both would dilute both.
- **Run a CI check** that scrapes README claims and compares to repository state — explored, deferred. README's natural-language assertions ("the model has X feature") are hard to mechanically verify; trigger-based human review is more reliable for now.
- **No outward-consistency rule** (rely on individual contributor vigilance) — rejected by the original incident: vigilance had failed for three releases (v0.2 → v0.4) without correction.

## Consequences

Positive:
- README/QUICKSTART now lag releases by at most one tag.
- Member extension (LICENSE/NOTICE/pyproject) closes adjacent outward-facing surfaces under the same governance umbrella, without requiring a new R-rule per artifact.
- Trigger-based discipline scales: when a future surface (e.g., `CONTRIBUTING.md`) becomes relevant, it is added as an R8 member with its own trigger, not a new rule.

Negative:
- Trigger interpretation is subjective at the margin (does a refactor that exposes a private helper count as "new public API"?). Borderline cases default to "yes, sync README" — friction beats drift.
- The grep pattern used to verify R8 compliance ("filename appears in README") is incomplete: the v0.5.0 R8 audit found `relaxation_fitting.py` was mentioned once but missing from the directory tree section. A future R8 governance patch should extend the verify pattern to "directory-tree position + filename appears" double-check (recorded as deferred enhancement; see `docs/legacy/MIGRATION_NOTES.md` §20.4.2 / §20.7.4).

## References

- `README.md`, `QUICKSTART.md`, `LICENSE`, `NOTICE`, `pyproject.toml`
- `docs/CLAUDE.md` R8 rule text (canonical, including member-extension paragraph)
- `docs/legacy/MIGRATION_NOTES.md` §十六 (R8 birth and four trigger categories)
- `docs/legacy/MIGRATION_NOTES.md` §十六 trailing v0.4.3 status note (member extension for LICENSE/NOTICE/pyproject.toml)
- `docs/legacy/MIGRATION_NOTES.md` §20.4.2, §20.7.4 (R8 grep pattern weakness, deferred)
- Tag: `docs/v0.4.1`
