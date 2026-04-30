# 0005. R7 dual-spec architecture (material_specs + param_specs) for cell-type creation

Date: 2026-04-25
Status: accepted

## Context

Through v0.2.x the only cell type was Panasonic NCR18650B, defined as a hardcoded Python factory module `panasonic_ncr18650b.py`. The v0.3.0 task scope was: add a second cell type (LFP/graphite) without copy-pasting a second hardcoded factory.

A naive duplication approach (`lfp_graphite.py` mirroring `panasonic_ncr18650b.py`) would have:

- Embedded parameters in Python source, violating R1's "edit JSON first" — every parameter change requires a code edit.
- Locked the parameter schema to the Python class structure — adding a new field forces every cell-type module to update.
- Made parameter modification version-controlled at code-release granularity rather than data-release granularity.

The cell-type problem is a test case for whether the SSoT architecture (ADR-0001) extends from "parameter values" to "cell instantiation".

## Decision

**Dual-spec architecture**: a cell instance is defined by a pair of spec files.

- **Material spec** (`material_specs/<cell>.json`) — physical-intrinsic quantities. Half-cell OCV file paths, electrode-balance parameters, stoichiometry ranges. Schema is stable across cell types (same fields, different values).
- **Param spec** (`param_specs/<cell>__<mechanism>.json`) — phenomenological quantities. Aging rate constants, resistance partition factors, initial degradation states. Schema is **versioned by mechanism model** — current schema is `params_mmeka2025.schema.v1.json`. Future mechanism upgrades (resistance degradation, dynamic plating) produce new schema versions; old versions are retained as academic history.

A cell is loaded via `create_cell_from_specs(material_path, params_path)`. The loader performs schema validation, derived-quantity computation (`C0_PE`, `C0_NE`, `Q0_SEI_NE` from FIT-0 correction factors), mechanism-version routing (`libquiv_aging/model_versions/<version>.py`), and resistance-closure construction.

**Dispatch by mechanism version** rather than cell type: `libquiv_aging/model_versions/mmeka2025.py` assembles the AgingModel. Future mechanism additions add a sibling module + a corresponding schema version, without modifying the loader or any existing spec file.

**`panasonic_ncr18650b.py` retained as compatibility shim**: the module now calls `create_cell_from_specs` internally and points at bundled spec files. This preserves the external API `create_panasonic_ncr18650b()` and all 22 existing tests. It is the only allowed hardcoded-factory form, and only as an example convenience entry.

**R7 ordering**:

```
material_specs/ + param_specs/  (fact layer)
  → libquiv_aging/model_versions/  (only when current mechanism doesn't fit; rare)
  → FIT-X scripts auto-write spec  (fitted-status fields are not hand-edited)
  → tests + examples for the cell type  (derived layer)
```

R7 explicitly forbids creating new `*_cell.py` hardcoded factories outside the bundled compatibility shim, and forbids hand-editing `status=fitted` fields in spec files (those are written exclusively by FIT-X scripts).

## Alternatives

- **Single-spec format** (one JSON per cell holding both material and param data) — rejected. Material schema is stable; param schema versions with mechanism. Mixing them would force schema migration on every mechanism upgrade for every cell type.
- **Class-per-cell-type Python factories** — rejected. The original problem.
- **Parameter inheritance** (LFP inherits NCA, overrides specific fields) — rejected. Inheritance encodes a lineage assumption that doesn't hold (LFP and NCA are not in a parent-child relationship), and it complicates schema validation.

## Consequences

Positive:
- New cell types: drop in two JSON files; no Python code change.
- Mechanism upgrades: add one Python module + one schema version; existing cell specs unaffected.
- Fitting outputs (FIT-1 LR/OFS, FIT-2 C1/C2, etc.) write back to spec files with provenance — the fitted record IS the spec, no parallel "fit results" registry.
- Compatibility shim approach lets the test suite and existing entry points migrate gradually.

Negative:
- Two-spec lookup increases cognitive load when debugging — "where is parameter X" requires checking material spec, param spec, and possibly mechanism module code.
- The `material/param` boundary criterion ("does it need schema versioning?") is a judgment call for some fields. Misclassification is recoverable (move the field, bump a schema version) but produces churn.
- The loader is now a critical-path component: a bug in `create_cell_from_specs` affects all cell types simultaneously.

## References

- `material_specs/`, `param_specs/`, `schemas/`
- `libquiv_aging/cell_factory.py`
- `libquiv_aging/model_versions/mmeka2025.py`
- `libquiv_aging/panasonic_ncr18650b.py` (compatibility shim)
- `docs/CLAUDE.md` R7 rule text
- `docs/legacy/MIGRATION_NOTES.md` §十四
- Tag: `release/v0.3.0`
