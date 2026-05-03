# Changelog

All notable changes are summarized here. Architectural rationale lives in `docs/decisions/` (ADR-NNNN). For frozen historical detail, see `docs/legacy/MIGRATION_NOTES.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

- (空)

## [release/v0.7.0-fit4] — 2026-05-02

### Added
- FIT-4 老化参数拟合框架 `libquiv_aging.dm_aging_fit`:
  - 4 公共 API: `aggregate_rpt_records`, `fit_calendar_aging`, `fit_cycle_aging`, `fit_knee_location`
  - 4 dataclass: `RPTRecord`, `FIT4ACalendarResult`, `FIT4BCycleResult`, `FIT4CKneeResult`
  - 16 条新错误码 (FIT4A-E005..W002 / FIT4B-E004..W002 / FIT4C-E003..W002), status=active (ADR-0018)
- CLI: `scripts/fit_dm_aging.py --stage {a,b,c,all}`
- SPEC: `docs/SPEC_dm_aging.md` (frozen 2026-05-01, ADR-0016 修订 2026-05-02)
- 测试: `tests/test_dm_aging.py` (26 fast + 2 slow targeted (T2 calendar + T3 healthy 解 xfail, ADR-0016) + 3 xfail (T2 cycle/knee + T4, 留 v0.8); T1 forward-only / T2 calendar / T3 healthy / T5 错误码 全 PASS)
- R8 派生层: `README.md` / `QUICKSTART.md` / `docs/CLAUDE.md` 同步 v0.7.0-fit4 公共 API

### Changed
- ADR-0016: R_SEI 退出 FIT-4a calendar fittable params (5-param → 4-param)
  - `docs/SPEC_dm_aging.md` §1 新增第 7 条; §3.1 free params 5 → 4; §3.3 R3 段; §3.5 删 R_SEI bounds 行; frontmatter 新增 Revision history
  - `libquiv_aging/dm_aging_fit.py`: `_DEFAULT_BOUNDS_FIT4A` (4 keys); `_inject_calendar_params` 不再注入 R_SEI; `_inject_cycle_params` / `_inject_knee_params` 不再从 calendar_result.R_SEI 重注入; `FIT4ACalendarResult` 4 字段; result 实例化同步
  - `docs/PARAMETERS.json::FIT-4a::fits` 4 keys; `critical_constraint` / `known_limitations_v0_7_0` 同步
  - `tests/test_dm_aging.py` T2 calendar + T3 healthy std xfail 解除 (4-param J^TJ 非奇异)
- ADR-0018: 16 条新错误码 status: draft → active (raise path validation 已实证, 与 N3 model behavior validation 拆分)
- ADR-0019: FIT4B-E007 + FIT4B-W001(c) registry trigger sum-based → forward-sim
- ADR-0020: 9 条旧 FIT-4 codes (FIT4A-E001..E004 / FIT4B-E001..E003 / FIT4C-E001..E002) status: active → deprecated, deprecated_note 指向 v0.7.0 新 codes

### Breaking changes
- `FIT4ACalendarResult.R_SEI: float` 字段移除 (5-param → 4-param). v0.7.0 是 release/v0.7.0-fit4 first release 含此 dataclass, 无外部消费者依赖. 见 ADR-0016.

### Deferred to v0.8
- ADR-0017: forward-sim 性能优化路径 (实装移 v0.8); 4 个 xfail (T2 cycle round-trip / T2 knee round-trip / T4 paper Mmeka 2025 Fig.6c) 保留为问题锚点
- N3 升级落点 "已设计但未实证" 维持; v0.8 跑通 T4 后升级 "已实证 (paper Fig.6c)" (ADR-0018)

### References
- ADRs: 0016 / 0017 / 0018 / 0019 / 0020
- 跨子阶段 1-6 工作量: vault/v0.7.0-fit4/fit4_subphase_{0..6}.md
- 跨子阶段 1-6 工作量与长尾移交 v0.8 总结: vault/v0.7.0-fit4/fit4_subphase_6.md §13

## [Pre-v0.7.0 archive cleanup]

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
