# Architectural Decision Records

Flat, append-only record of architectural decisions for libquiv-aging. Each ADR is self-contained — readable without external context. Numbering is zero-padded, four digits, never reused. Status updates are atomic via supersession (new ADR pointing back), not in-place edits.

For collaboration philosophy, see repo-root `CLAUDE.md`.
For engineering disciplines (R1-R8) and routing, see `docs/CLAUDE.md`.
For frozen historical archive, see `docs/legacy/MIGRATION_NOTES.md`.

## Index

- [ADR-0001: Three-document SSoT fact layer](0001-three-document-ssot-fact-layer.md) — PARAMETERS.json + PARAMETER_SOP.md + CRITICAL_REVIEW.md as authoritative trio (R1 anchor).
- [ADR-0002: Paper errata precedence](0002-paper-errata-precedence.md) — published-paper values may be wrong; corrections live in `paper_errata` and override the paper.
- [ADR-0003: R5 four-step protocol](0003-r5-four-step-protocol.md) — scan / confirm / edit / verify for any structural cross-doc change.
- [ADR-0004: R6 error-code chain](0004-r6-error-code-chain.md) — registry → runbook → scripts ordering; numbers never reused.
- [ADR-0005: R7 dual-spec cell-type architecture](0005-r7-dual-spec-cell-type-architecture.md) — material_specs/ + param_specs/ split; no per-cell hardcoded factories.
- [ADR-0006: R8 README/QUICKSTART/external-object sync](0006-r8-readme-quickstart-sync.md) — release-tagged sync for README, QUICKSTART, LICENSE, NOTICE, pyproject description.
- [ADR-0007: x_NE0 reference convention](0007-x0-reference-convention.md) — `x_NE0` as fresh-cell reference stoichiometry feeding IC analysis inversion.
- [ADR-0008: Dual-brentq x_NE inversion](0008-dual-brentq-x-ne-inversion.md) — two-stage bracketed root finding for stoichiometric inversion in IC analysis.
- [ADR-0009: Path-B algebraic forward for IC analysis](0009-path-b-algebraic-forward-for-ic-analysis.md) — closed-form forward model preferred over ODE re-integration for IC reconstruction.
- [ADR-0010: Cell role categorization](0010-cell-role-categorization.md) — reference / sentinel / aging-cohort role taxonomy clarified in EXP and SOP.
- [ADR-0011: RPT bidirectional data contract](0011-rpt-bidirectional-data-contract.md) — both charge and discharge directions required for C/40 + IR; DATA-E004/E005.
- [ADR-0012: EXP-B4 splits preferred/fallback structure](0012-exp-b4-splits-fallback-warning.md) — chemistry split protocol with explicit fallback path and precision-loss warning.
- [ADR-0013: Fig. 6c sum(DMs) vs cap_loss handling](0013-fig-6c-sum-dms-vs-cap-loss.md) — T4 redesigned as cap_loss self-consistency, not sum conservation; nonlinearity is real.
- [ADR-0014: tau→R dual-candidate mapping with RSS selection](0014-tau-r-dual-candidate-mapping.md) — auto-select tau↔electrode mapping; FIT2-W001 marginal warning.
- [ADR-0015: Relaxation models dispatch pattern](0015-relaxation-models-dispatch-pattern.md) — `RELAXATION_MODELS` registry preps fractional-order/Mittag-Leffler/DRT upgrade path.

## Template

See `_template.md` when drafting a new ADR.
