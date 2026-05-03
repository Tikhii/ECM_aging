# 0017. forward-sim 性能问题登记 (实装移 v0.8)

Date: 2026-05-02
Status: proposed

## Context

子阶段 4 实证 `_forward_sim_cycle` 性能基线:
- 单 forward 调用 ~28s @ EFC=20 (含 `_drive_cycles_to_efc` 1C ODE 循环)
- `least_squares` max_nfev=200 → 单 cycle 或 knee fit 30-60 min
- CI 不可承受, 阻塞 4 个测试:
  - `tests/test_dm_aging.py::TestT2_RoundTripSynthetic` cycle (行 423-431)
  - `tests/test_dm_aging.py::TestT2_RoundTripSynthetic` knee
  - `tests/test_dm_aging.py::TestT4_PaperFig6c` (行 632-639)
  - 子阶段 4 §1.3 长尾 #2 阻塞 N3 升级落点 "已设计但未实证"

paper Mmeka 2025 Fig.6c 端到端验证 (T4) 是 N3 升级的关键证据. 性能不足
导致此验证留 v0.8.

用户裁定 2 (子阶段 4 review 后): forward-sim 性能优化留 v0.8 release, 子阶段
6 仅 ADR 设计登记, 不实施.

## Decision

v0.7.0 release 内 forward-sim 性能不足以支持 T2 cycle/knee + T4 端到端测试.

解决方案设计与实装移到 v0.8 release, 候选方案在 v0.8 内实证决定.

v0.7.0 release 内保留 4 个 xfail 测试 (T2 cycle round-trip + T2 knee
round-trip + T4 paper Fig.6c) 作为问题锚点.

v0.8 实装时本 ADR status 升级 accepted + 同步 dates.

## Alternatives

1. 保持现状, 接受 30-60 min/fit — CI 不可承受, 阻塞测试矩阵 T2/T4. 拒绝.
2. 直接放弃 round-trip 测试覆盖 — 失去 SPEC §C3 全局收敛性证据 + N3 升级
   阻塞. 拒绝.

## Consequences

正面:
- v0.7.0 release 收尾不被性能优化阻塞
- xfail 测试作为锚点在 CI 内显式可见, 防止 v0.8 忘记落地
- v0.7.0 测试覆盖仍包含 T1 forward-only / T3 degenerate / T5 错误码 (26 fast
  PASSED)

负面:
- 4 个 xfail 测试在 v0.7.0 release 内未实证, T2 round-trip / T4 paper Fig.6c
  保留 xfail
- N3 升级落点维持 "已设计但未实证" (synthetic 自证), 留 v0.8 升级 (见
  ADR-0018)
- v0.8 设计与实装是后续 release 工作量, 现 ADR 不预设方案选择

## References

- 子阶段 4 §1.3 长尾 #2 (vault/v0.7.0-fit4/fit4_subphase_4.md)
- 子阶段 5 PARAMETERS.json::FIT-4b::known_limitations_v0_7_0[0]
- `tests/test_dm_aging.py` 行 423-431 (T2 cycle xfail) + 632-639 (T4 xfail)
- `libquiv_aging/dm_aging_fit.py::_forward_sim_cycle` + `_drive_cycles_to_efc`
  (子阶段 2 frozen)
- 用户裁定 2 (子阶段 4 review 2026-05-01)
