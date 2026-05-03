# 0019. FIT4B-E007 + FIT4B-W001 trigger 字符串 sum-based → forward-sim 修订

Date: 2026-05-02
Status: accepted

## Context

子阶段 1 注册 FIT4B-E007 + FIT4B-W001 时, trigger 字符串采用 sum-based 表述:
- `FIT4B-E007`: `|sum(LLI + LAM_PE + LAM_NE) - cap_loss_observed| / cap_loss_observed > 10%`
- `FIT4B-W001` (c) 子条款: `S3 子步骤 5% < |sum_DMs - cap_loss|/cap_loss ≤ 10%`

子阶段 2 实装 `_check_s3_self_consistency` 时按 SPEC §3.4 / §8.2 选择
forward-sim 路径 (paper Fig.6c N3 caveat: sum=0.25, cap_loss=0.11, 比率
2.27, 简单 sum 严重失配, 物理上不正确).

`libquiv_aging/dm_aging_fit.py` 行 813-816 注释已报告此不一致, 留子阶段 6
ADR 修订.

子阶段 6 plan execute 第一步实证 (2026-05-02):
- `docs/error_codes_registry.json::codes::FIT4B-E007::trigger`: sum-based
- `docs/error_codes_registry.json::codes::FIT4B-W001::trigger` (含 c 子条款): sum-based
- `docs/07_offline_runbook.md` 行 1107-1146 (FIT4B-E007 + W001 段): sum-based
  (与 registry 一致)
- `docs/SPEC_dm_aging.md §3.4` 行 234: forward-sim
  (`rel_error_max = max_i |cap_loss_model_i - cap_loss_obs_i| / cap_loss_obs_i`)
- `libquiv_aging/dm_aging_fit.py::_check_s3_self_consistency`: forward-sim

结论: registry + runbook 一致 sum-based, 但与 SPEC + 实装一致 forward-sim
不一致. 修订方向对齐 SPEC §3.4 + 实装 (forward-sim).

## Decision

**`docs/error_codes_registry.json` 修订**:
- `FIT4B-E007.trigger`: 改为
  `FIT-4b 主拟合已通过 (FIT4B-E006 未触发), 但 SPEC_dm_aging §3.4 子步骤 S3 的容量自洽性检查中 forward-sim 预测 cap_loss(t_RPT) 与观测 cap_loss_obs 相对误差 > 10% (rel_error_max > 0.10, 任一 RPT 点违反阈值即触发).`
- `FIT4B-W001.trigger` (c) 子条款: 改为
  `(c) S3 子步骤 5% < forward-sim 预测 cap_loss(t_RPT) 与观测 cap_loss_obs 相对误差 ≤ 10% (0.05 < rel_error_max ≤ 0.10).`
- (a)/(b) 子条款不变 (R²/RMSE 与 forward-sim 表述无关)

**`docs/07_offline_runbook.md` 修订**:
- 行 1107-1145 FIT4B-E007 段: 触发条件文本同步 forward-sim
- 行 1141-1168 FIT4B-W001 段 (c) 子条款: 同步 forward-sim
- 物理/方法学后果段 (paper Fig.6c sum=0.25 ratio=2.27 物理依据) 维持, 仅修
  trigger 文本

**SPEC §3.4 + dm_aging_fit.py 不动** — 已对齐 forward-sim, 是修订基准.

## Alternatives

1. 保持 sum-based trigger, 实装路径自行其是 — 违反 R6 (registry → runbook →
  scripts 一致性). 拒绝.
2. 反向修实装 (回到 sum-based) — paper N3 caveat 已明确 sum 不正确 (Fig.6c
  ratio 2.27), 物理上不可接受. 拒绝.
3. 仅修 E007, 不修 W001 (c) — 实证显示 W001 (c) 同样含 sum-based 文本, 与
  E007 同根因, 一并修保持一致性. 拒绝.

## Consequences

正面:
- registry / runbook / SPEC / 实装四者 trigger 表述一致 (forward-sim)
- R6 链条收口
- 用户读 runbook 时理解的 trigger 与脚本实际行为一致

负面:
- runbook FIT4B-E007 段 paper Fig.6c sum 数字 (0.25 / 0.11 / 2.27) 仍保留
  作为 N3 物理依据展示 — 这是历史依据, 不是 trigger 阈值, 文本需调整避免
  混淆 (放在 "物理/方法学后果" 段, trigger 段仅说 forward-sim rel_error)
- registry schema 内 since_version 字段不动 (仍 0.7.0); trigger 字符串修订
  本身不构成 code 编号变更

## References

- `libquiv_aging/dm_aging_fit.py` 行 813-816 注释 (子阶段 2 报告 trigger 不一致)
- `docs/SPEC_dm_aging.md §3.4` 行 230-240 (forward-sim S3 表述, 修订基准)
- `docs/SPEC_dm_aging.md §8.2` (N3 物理依据, 不动)
- `docs/CRITICAL_REVIEW.md §N3 sum DMs ≠ cap_loss` (paper Fig.6c 物理依据)
- ADR-0013 (Fig. 6c sum(DMs) ≠ cap_loss handling, paper N3 起源)
- 子阶段 6 plan execute 实证记录 (vault/v0.7.0-fit4/fit4_subphase_6.md §5)
