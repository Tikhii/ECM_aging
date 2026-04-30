# 0007. X^0 reference convention (paper SOC=1 vs spec V_min) — per-context choice

Date: 2026-04-28
Status: accepted

## Context

The Mmeka 2025 paper defines the half-cell stoichiometry anchor `X^0` (initial state-of-charge in the negative electrode) at SOC = 1 — the fully-charged terminal. The project's spec files (`material_specs/<cell>.json::X0_NE`, `X0_PE`) document `X^0` as the value at the V_min terminal — the discharged end. The two conventions disagree by exactly one full-cell capacity sweep.

Both conventions are internally consistent within their respective domains. The mismatch became operationally relevant during the v0.5.2 IC analysis subphase 2 self-test: forward-model evaluation at the V_max end produced X_NE values consistent with SOC = 1 paper convention, while the spec-loaded `X0_NE` was a V_min reference. Without an explicit reconciliation, calls to `synthesize_V_ocv` either silently used the wrong anchor or required ad-hoc shifts that obscured intent.

The frozen SPEC_ic_analysis.md had carried an "X^0 convention clarification" placeholder (added in v0.4.2 during SPEC promotion), pending IC analysis landing for resolution.

## Decision

Both conventions coexist; the choice is per-context and explicitly documented at each call site:

- **Spec field semantics**: `material_specs/<cell>.json::X0_NE / X0_PE` are V_min-referenced. Spec is the canonical static record (loaded at cell construction).
- **Paper-equation evaluation**: where the paper's equations explicitly anchor at SOC = 1, the conversion to V_min reference is performed inline at the call site. The conversion is a simple shift by total stoichiometry sweep, computable from the cell's nominal capacity.
- **Forward-model `synthesize_V_ocv`**: takes raw `(X_NE, X_PE)` as inputs without imposing a convention; the caller (e.g., IC analysis optimizer) is responsible for supplying values consistent with whichever reference frame it uses.
- **Docstring discipline**: every function that internally fixes a convention states it in its docstring. `libquiv_aging/ic_analysis.py::synthesize_V_ocv` and the dual-brentq helpers carry explicit notes.

The two-convention coexistence is a deliberate design — not a defect to be unified — because forcing a single convention would either:
- Rewrite paper-equation references in code (loses traceability to paper text), or
- Renormalize all spec values to SOC=1 (silently breaks compatibility with existing spec files and FIT-1 outputs).

## Alternatives

- **Force SOC=1 reference globally** (rewrite spec files) — rejected. Breaks v0.3.0 compatibility shim and forces a re-fit of every previously-fitted cell.
- **Force V_min reference globally** (rewrite paper-equation translations in code) — rejected. Loses one-to-one mapping between paper equation text and code implementation, harms maintainability when the paper is the primary reference.
- **Wrap both in a convention-tagged dataclass** (e.g., `Stoichiometry(value=0.05, ref=Reference.V_MIN)`) — explored, deferred. The wrapper would propagate through call chains and add boilerplate without preventing convention errors at call sites that actually do mixed-convention arithmetic. Docstring discipline is the lighter alternative until a real bug demands stricter typing.

## Consequences

Positive:
- Paper-equation code stays one-to-one mappable to paper text.
- Existing spec files remain valid without migration.
- Convention errors are detectable: an X_NE value that drifts outside `[0, 1]` after applying a wrong-direction shift triggers the alawa-edge fail-fast path (see ADR-0008) and produces an explicit error rather than a silent miscompute.

Negative:
- New contributors must read docstrings before passing X_NE/X_PE between functions. The convention is not enforced by types.
- Future paper updates that change the reference convention would require a sweep through call sites — the ad-hoc shift is not isolated in one place.

## References

- `libquiv_aging/ic_analysis.py::synthesize_V_ocv` docstring
- `material_specs/<cell>.json::X0_NE / X0_PE` field documentation
- `docs/SPEC_ic_analysis.md` (frozen SPEC carries the convention clarification)
- `docs/legacy/MIGRATION_NOTES.md` §20.8 (convention difference noted as v0.4.2 SPEC-promotion placeholder, cleared at v0.5.2 IC analysis landing)
- Mmeka, Dubarry, Bessler 2025, J. Electrochem. Soc. 172:080538, electrode-balance equations
