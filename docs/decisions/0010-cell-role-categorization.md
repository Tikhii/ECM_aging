# 0010. cell_role categorization — reference cell vs sentinel cell

Date: 2026-04-29
Status: accepted

## Context

External-SOP (EXTERNAL_SOP v1.0 → v1.4) review surfaced ambiguity in the historical PARAMETER_SOP §二.5 hygiene clauses. Items 3 and 4 conflated two distinct experimental roles:

- The phrase "全新参考 cell 在标定箱存放" was self-contradictory. A "fresh reference" cell that is then aged in a calibration chamber is no longer fresh. The original intent — provide a baseline for instrument drift and aging-rate cross-check — was not captured by the literal wording.
- The "sentinel" role (replicate cells dedicated to detecting unexpected divergence) was implicit, not labeled, and not distinguished from the reference role.

The two roles serve different scientific purposes and have different cell-count and condition requirements. Without explicit naming, external experimental teams reading the SOP could not tell which role their cells should fill, leading to under-provisioned protocols.

## Decision

Two distinct cell roles, named and defined:

**Reference cell**:
- Purpose: baseline for measurement-instrument drift, secondary calibration anchor.
- Condition: **least-aged with known aging condition** (not "fresh"). The cell sees the mildest aging condition in the protocol set, providing a low-aging-rate floor against which other cells' degradation can be compared.
- Count: ≥ 1.

**Sentinel cell**:
- Purpose: detect unexpected divergence in protocol execution (chamber failure, calibration drift, sample-prep variability).
- Condition: **replicates of the mildest aging condition** in the protocol set, run in parallel with the main aging matrix.
- Count: ≥ 2 (replication is the core of the sentinel function).

The two roles are complementary, not conflicting. A sentinel cell's mildest-condition replication often co-locates with reference duty (the same cell can serve both roles), but the protocol must enumerate both roles separately so that staffing and chamber slots are correctly provisioned.

## Alternatives

- **Single "control cell" role** (collapsing reference + sentinel into one) — rejected. The two roles diverge on count requirement (1 vs ≥2) and on primary diagnostic question (instrument drift vs protocol variance). Collapsing would force teams to over-specify or under-specify.
- **Add more roles** (e.g., "fresh sample for half-cell extraction" as a third role) — rejected as out-of-scope. Half-cell extraction is documented under EXP-B1/B2; mixing it into the aging-protocol cell-role taxonomy would conflate experimental layers.

## Consequences

Positive:
- External-SOP language can be unambiguous about which cells fill which role.
- Protocol planning (chamber-slot allocation, replicate count) becomes mechanical.
- Future cell-role additions can be made with clear precedent (define purpose / condition / count).

Negative:
- A team reading older protocols (predating this clarification) may need to retrospectively classify their existing cells. The classification is usually obvious from the experimental log but adds a step.
- The "co-location" pattern (one cell serves both roles) needs explicit documentation per protocol; otherwise role overlap can be mistaken for under-provisioning.

## References

- `docs/PARAMETER_SOP.md §二.5` (hygiene rewrite — current canonical text)
- `docs/legacy/MIGRATION_NOTES.md` §二十一.2.3 (role disambiguation rationale)
- Commit `fcc3a83` (PARAMETER_SOP §二.5 rewrite, EXP-D derived quantities `compute_via=planned`)
- External SOP v1.0 → v1.4 review (vault, not in git)
