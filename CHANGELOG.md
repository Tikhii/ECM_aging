# Changelog

All notable changes are summarized here. Architectural rationale lives in `docs/decisions/` (ADR-NNNN). For frozen historical detail, see `docs/legacy/MIGRATION_NOTES.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

- Engineering archive cleanup: 15 ADRs extracted into `docs/decisions/`, MIGRATION_NOTES frozen under `docs/legacy/`, repo-root `CLAUDE.md` introduced as collaboration philosophy entry, `docs/CLAUDE.md` trimmed to engineering operations manual (R1-R8 preserved verbatim).

## [docs/v0.5.3-ext-sop-feedback] — 2026-04-30

- Retroactive task-package wrap for the external-SOP-feedback batch (commits 86def27, dadb15c, 7be3ffd, fcc3a83, 9af79e9). MIGRATION_NOTES §二十一 documents the meta-lessons from the 5-commit batch; no other file changes.
- See ADR-0010 (cell role categorization), ADR-0011 (RPT bidirectional data contract), ADR-0012 (EXP-B4 splits fallback structure).

## [docs/v0.5.3-ic-methodology-review] — 2026-04-29

- IC-analysis methodology review patch: `docs/UPGRADE_LITERATURE/ic_analysis_methodology_review.md` (555 lines) places v0.5.2 IC analysis in the Birkl 2017 / Dubarry & Anseán 2022 / Mmeka 2025 lineage; 7-item self-audit; upgrade paths flagged for v0.6+ (Marinescu phantom-IR correction) and v0.7+ (Lin & Khoo N/P reparameterization).
- `critical_review_findings::N3` derived-layer sync — see ADR-0013.

## [release/v0.5.2-ic-analysis] — 2026-04-28

- IC analysis full implementation: `libquiv_aging/ic_analysis.py` + `scripts/fit_ic_to_dms.py` + `tests/test_ic_analysis.py` (22 cases) + ICA-scope error codes (E001/E002/E003/W001/W002).
- See ADR-0007 (x_NE0 reference convention), ADR-0008 (dual-brentq inversion), ADR-0009 (Path B algebraic forward), ADR-0013 (Fig. 6c sum(DMs) ≠ cap_loss handling).

## [docs/v0.5.1-deprecate-exp-c] — 2026-04-27

- Derived-layer semantic-radiation fix: EXP-C deprecated for FIT-2; PARAMETERS.json (3 fields), SPEC_ic_analysis Status, PARAMETER_SOP §3.1/§3.3, README directory tree all synced.

## [release/v0.5.0-fit2] — 2026-04-26

- FIT-2 RC relaxation fitting: `scripts/fit_rc_transient.py` + `libquiv_aging/relaxation_fitting.py` (dispatch pattern); FIT2-Exxx/W001 error codes.
- `CRITICAL_REVIEW.md` C7 (RC topology limitation for long relaxation) + `docs/UPGRADE_LITERATURE/fractional_order_RC.md` upgrade entry.
- See ADR-0014 (tau→R dual-candidate mapping with RSS selection), ADR-0015 (relaxation-models dispatch pattern).

## [docs/v0.4.2-spec-promotion] — 2026-04-25

- `docs/TODO_ic_analysis.md` promoted to `docs/SPEC_ic_analysis.md` with synchronized references and interface contract.

## [docs/v0.4.1-readme-sync] — 2026-04-25

- R8 introduced: README/QUICKSTART sync becomes a release-task subphase rather than an afterthought.
- See ADR-0006 (R8 README/QUICKSTART/external-object sync).

## [release/v0.4.0-fit1] — 2026-04-25

- FIT-1 electrode-balance fitting script lands: `scripts/fit_electrode_balance.py` + `libquiv_aging/fitting.py` infrastructure; FIT1-Exxx/W001 error codes.

## [docs/v0.3.1-env-e002] — 2026-04-25

- ENV-E002 error code formalized (pip install failure on internal mirror): registry + runbook + offline-bundle-guide cross-refs synced per R6.

## [release/v0.3.0-cell-factory] — 2026-04-25

- Cell-type abstraction layer: `schemas/`, `material_specs/`, `param_specs/` directories; `panasonic_ncr18650b.py` refactored to a compatibility shim; `create_cell_from_specs` becomes the unified multi-cell-type entry.
- See ADR-0005 (R7 dual-spec cell-type architecture).

## [docs/v0.2.4-scope-tightening] — 2026-04-23

- First application of Occam's-razor scope tightening: 08 consultation protocol scope statement, IDENT-Wxxx marked draft, 09 offline bundle guide pruned.

## [docs/v0.2.3-offline-pip-mirror] — 2026-04-23

- Offline workflow lands: internal pip mirror single-track; `docs/09_offline_bundle_guide.md` + `build_requirements.sh` / `install_offline.sh` / `verify_install.sh`.

## [docs/v0.2.2-meta-lessons] — 2026-04-23

- 2026-04-23 meta-lessons institutionalized in `docs/CLAUDE.md`: 术语约定, 破坏性命令清单, Claude Code 协作规范 added; R5 verification step extended to forbid auto `git add` / `commit` / `tag`.

## [docs/v0.2.1-env-frozen-locked] — 2026-04-23

- `environment-frozen.yml` entered git history (commit 4770178); ENV-E001 prerequisite satisfied, TODO markers cleared in registry and runbook.

## [docs/v0.2.0-offline-workflow] — 2026-04-23

- R6 introduced: error-code registry + offline runbook + consultation protocol triad lands (`docs/error_codes_registry.json` + `07_offline_runbook.md` + `08_consultation_protocol.md`).
- See ADR-0004 (R6 error-code chain).

## [pre-tag baseline] — 2026-04-20 / 2026-04-21

- 2026-04-20: initial scaffold; PARAMETERS.json established as the single source of truth; R_SEI corrected to FIT-4a (per paper). See ADR-0001 (three-document SSoT), ADR-0002 (paper errata precedence).
- 2026-04-21: R5 added (document-consistency protocol) — triggered by the FIT-3 missing-section incident. See ADR-0003 (R5 four-step protocol).
