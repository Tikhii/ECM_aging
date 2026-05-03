# 0020. 旧 FIT-4 错误码 (FIT4A-E001..E004 / FIT4B-E001..E003 / FIT4C-E001..E002) deprecate

Date: 2026-05-02
Status: accepted

## Context

`docs/error_codes_registry.json` 内 9 条旧 FIT-4 错误码:
- FIT4A-E001 / E002 / E003 / E004 (4 条)
- FIT4B-E001 / E002 / E003 (3 条)
- FIT4C-E001 / E002 (2 条)

全部 status=active, since_version=0.1.0 (paper 发表前的 0.1.0 前置条件检查
设计). v0.7.0 release 子阶段 1 注册 16 条新错误码 (FIT4*-E005..W002) 后,
旧 9 条在 dm_aging_fit.py 实装中**无 raise 站点** (子阶段 5 §3 + 子阶段 6
plan execute 实证).

子阶段 5 报告 §3 (D2) 显式登记此事实, 决议子阶段 6 ADR 处置. 选项:
- (a) 补回 raise 路径 (维持 active)
- (b) deprecate (status: active → deprecated, 无 raise 路径)

## Decision

**9 条旧错误码 status: active → deprecated**:
- 各 entry 加 `deprecated_note` 字段, 指向 v0.7.0 替代码:
  - FIT4A-E001..E004 → "v0.7.0 替代为 FIT4A-E005..W002, 见 ADR-0020"
  - FIT4B-E001..E003 → "v0.7.0 替代为 FIT4B-E004..W002, 见 ADR-0020"
  - FIT4C-E001..E002 → "v0.7.0 替代为 FIT4C-E003..W002, 见 ADR-0020"
- runbook §A 总表 status 字段同步
- runbook 内各 deprecated code 段 (主体段落) 维持文本不删, 加 "已 deprecate
  自 v0.7.0, 见 ADR-0020" 注释

**`docs/PARAMETERS.json::FIT-4a/4b/4c::error_codes` 数组中 9 条旧 codes 引用
保留**:
- audit trail 用途 — 用户读历史 PARAMETERS.json 时仍可看到这 9 条 code 在
  v0.7.0-fit4 阶段的引用关系
- registry 单一事实层 status=deprecated 已显式声明
- 不做物理删除, 避免破坏 R6 "编号一经发放不复用" 原则

**用户读 PARAMETERS.json 时的引用契约**:
- error_codes 数组是 codes list (历史登记 + 当前引用), 非 status 字段
- 实际 status 信息 cross-ref `docs/error_codes_registry.json` 单一事实层

## Alternatives

1. 补回 raise 路径 (维持 active) — 膨胀 fit_calendar_aging / fit_cycle_aging
   / fit_knee_location 的 preflight gate, 违反 SPEC §3.1 简洁原则; 旧 codes
   语义已被新 codes (E005-W002) 完全等价覆盖, 重复登记无信息增益. 拒绝.
2. 直接删除 entry (硬移除) — 违反 R6 "编号一经发放不复用" 原则, 历史一致性
   破坏. 拒绝.

## Consequences

正面:
- registry status 反映实装现状 (无 raise 路径 = deprecated)
- R6 链条 (registry → runbook → scripts) 收口
- 旧 codes 历史登记保留, audit trail 完整
- v0.7.0 SPEC §3.1 简洁性维持, fit_calendar_aging preflight 不膨胀

负面:
- registry / runbook 9 条段保留但状态变化, 文档体量不减反增 (新增
  deprecated_note 字段)
- 用户从 PARAMETERS.json 读到 error_codes 引用旧 codes 时, 必须 cross-ref
  registry 才能知 deprecated 状态 — 由 ADR-0020 Decision 段 "用户读
  PARAMETERS.json 时的引用契约" 明确

## References

- 子阶段 5 报告 §3.3 旧 error_codes 状态登记表
  (vault/v0.7.0-fit4/fit4_subphase_5.md)
- 子阶段 5 报告 §3 D2 (旧 codes 状态实证)
- `docs/error_codes_registry.json` schema (子阶段 1)
- `docs/07_offline_runbook.md` §A 总表
- ADR-0004 (R6 error code chain registry → runbook → scripts)
- 子阶段 6 plan execute 实证 (dm_aging_fit.py grep 旧 codes 无 raise 站点)
