# 0018. 16 条 v0.7.0 错误码 status=draft → active 升级 + N3 状态升级路径

Date: 2026-05-02
Status: accepted

## Context

子阶段 1 注册 16 条 v0.7.0 错误码 (`docs/error_codes_registry.json`):
- FIT4A-E005 / E006 / E007 / W001 / W002 (5 条)
- FIT4B-E004 / E005 / E006 / E007 / W001 / W002 (6 条)
- FIT4C-E003 / E004 / E005 / W001 / W002 (5 条)

全部 status=draft, since_version=0.7.0.

子阶段 4 测试矩阵 `tests/test_dm_aging.py::TestT5_*` 已对 16 条各设 ≥1 触发
用例, 全部 PASS (子阶段 4 §3 实测).

争议: N3 整体未端到端验证 (paper Fig.6c 留 v0.8, 见 ADR-0017), 但 16 条
entry 自身 raise 路径已测试覆盖. status 是否可从 draft 升级到 active?

## Decision

**升级 16 条 status: draft → active**, 论证如下:

拆分两个独立维度:
- **Model behavior validation** (N3 落点): 模型整体物理输出是否在 paper
  Fig.6c 数据上端到端验证 — 当前 "已设计但未实证", 留 v0.8 升级
- **Error code raise path validation**: 16 条 entry 的 trigger / consequence /
  raise 站点是否在测试矩阵 T5 实证覆盖 — 当前 100% 覆盖 (子阶段 4 §3)

`docs/error_codes_registry.json::codes::*::status` 字段语义按子阶段 1
注册 SPEC = raise path validation 状态, 不反映底层模型物理验证.

因此 16 条 entry status: draft → active 升级合规, 即使 N3 未端到端验证.

**N3 状态升级路径**:
- 当前 v0.7.0: "已设计但未实证" (synthetic round-trip 自证 + 错误码触发
  覆盖)
- v0.8 (forward-sim 性能优化, ADR-0017 实装) 后跑通 T4 paper Fig.6c S3:
  升级到 "已实证 (paper Mmeka 2025 Fig.6c)"
- 中间态 v0.7.x patch (若有): 不强制升级, 保持 v0.7.0 措辞

**升级范围明确** (R1 / R6 一致性):
- 仅修 `docs/error_codes_registry.json::codes::FIT4*::status` 字段 (事实层
  升级)
- `docs/PARAMETERS.json::FIT-4a/4b/4c::error_codes` 数组中的 16 条新引用
  **不动** (子阶段 5 已添加, 是 codes list 不是 status 字段; status 由
  registry 单一事实层提供)
- runbook §A 总表同步 status 字段

## Alternatives

1. 16 条 status 保持 draft 直到 N3 端到端验证 — 维持 raise path validation
   与 model behavior validation 同 status, 但混淆两个独立维度. 拒绝.
2. 16 条 status active + N3 一并升级到 "已实证" — 虚假声明物理验证完成,
   违反子阶段 5 用户硬约束 (PARAMETERS.json::status 不允许写
   "validated"/"fitted_paper" 措辞). 拒绝.

## Consequences

正面:
- 16 条错误码 status 反映其 raise path validation 真实状态 (active)
- N3 model behavior 状态独立维度保持诚实 (待 v0.8 升级)
- registry 单一事实层语义清晰

负面:
- 用户若误读 status=active 为 "16 条已经过 paper 数据全验证", 会有 false
  confidence. 由 ADR-0018 段 + CHANGELOG "Deferred to v0.8" 段双重声明缓解
- v0.7.0 + v0.8 之间 status 字段含义连续性需说明 — 本 ADR References 段提供
  锚点

## References

- 子阶段 1 registry 起草 SPEC (vault/v0.7.0-fit4/fit4_subphase_1.md)
- 子阶段 4 §3 16 条 trigger 测试矩阵 T5 (vault/v0.7.0-fit4/fit4_subphase_4.md)
- 子阶段 5 PARAMETERS.json::FIT-4a/4b/4c::error_codes (子阶段 5 报告 §3 一致性
  核对表, vault/v0.7.0-fit4/fit4_subphase_5.md)
- `docs/error_codes_registry.json` schema (子阶段 1)
- `docs/CRITICAL_REVIEW.md §N3 sum DMs ≠ cap_loss`
- ADR-0017 (forward-sim 性能, v0.8 实装锚点)
- ADR-0013 (Fig. 6c sum(DMs) ≠ cap_loss handling, paper N3 起源)
