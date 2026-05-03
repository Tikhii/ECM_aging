# 0016. R_SEI 退出 FIT-4a calendar fittable params

Date: 2026-05-02
Status: accepted

## Context

SPEC `docs/SPEC_dm_aging.md` frozen 2026-05-01 (子阶段 1 of release/v0.7.0-fit4) 时
将 `R_SEI` 列入 FIT-4a 5 个 calendar 自由参数:
`{k_SEI_cal, k_LAM_PE_cal, gamma_PE, R_SEI, E_a_SEI}`.

子阶段 4 实装测试 `tests/test_dm_aging.py::TestT2_RoundTripSynthetic` 后发现
T2 calendar round-trip xfail, 根因经子阶段 4 §1.3 长尾 #1 + 子阶段 5
PARAMETERS.json::FIT-4a::known_limitations_v0_7_0[0] 实证确认:

- `_forward_sim_calendar` 在 calendar (I=0 storage) 模式下只调
  `cell.CC(I=0.0, duration_s=...)`, R_SEI 项消零 (无电流 → 无 IR drop)
- R_SEI 在 J 矩阵的列恒 0, J^TJ 奇异, Hessian 不可逆
- 触发 `FIT4A-E006` (Hessian 非有限)
- 物理上, paper Mmeka 2025 §Calendar degradation p.12 实际 R_SEI 路径是从
  EXP-E RPT IR 脉冲直接测量 (非从 LLI 序列反推)

子阶段 5 PARAMETERS.json::FIT-4a::known_limitations_v0_7_0[0] 已登记此误归类
待修, 用户裁定 1 (子阶段 4 review 后) 决议子阶段 6 ADR 实施.

## Decision

FIT-4a 自由参数从 5 降到 4:
`{k_SEI_cal, k_LAM_PE_cal, gamma_PE, E_a_SEI}` (E_a_SEI 在单温度数据时
fixed_to_default, SPEC §3.1 已有约定, 不变).

R_SEI 来源: `cell.aging.resistance_aging.R_SEI` 从 `param_specs/*.params.json`
加载 (literature_default 0.66, 见 `param_specs/panasonic_ncr18650b__mmeka2025.params.json::R_SEI`).
现场用户若有 EXP-E IR 脉冲实测数据, 在 `cell_factory.create_cell_from_specs`
load 后修改 `cell.aging.resistance_aging.R_SEI` 字段即可覆盖默认值.

`fit_calendar_aging` 不再注入 R_SEI; cell.aging.resistance_aging.R_SEI 在
cell_factory 加载时已 frozen 0.66, 直接读即可 (避免双重事实层, R1).

涉及修订:
- `docs/SPEC_dm_aging.md`: §1 新增第 7 条; §3.1 free params 5 → 4; §3.5 删
  R_SEI bounds 行; §3.3 R3 段 R_SEI 表述; frontmatter 加 Revision history 子节
- `libquiv_aging/dm_aging_fit.py`: `_DEFAULT_BOUNDS_FIT4A` (行 69) /
  `FIT4ACalendarResult` dataclass (行 138) / `_inject_calendar_params` (行 374) /
  `_inject_cycle_params` (行 395, 不再从 calendar_result.R_SEI 重注入) /
  `_inject_knee_params` (行 416, 同) / docstrings (行 366, 890) /
  result 实例化 (行 990)
- `docs/PARAMETERS.json::FIT-4a`: `fits` 数组删 R_SEI; `critical_constraint`
  修订; `known_limitations_v0_7_0[0]` 标记已修
- `tests/test_dm_aging.py`: T2 calendar (354-361) + T3 calendar healthy
  (572-579) 解 `@pytest.mark.xfail`; fixture truth/bounds dict 删 R_SEI key

## Alternatives

1. 保留 R_SEI 在 5-param 拟合 (现状) — J^TJ 奇异, 拟合不收敛, 物理上 R_SEI
   在 calendar I=0 模式不可识别. 拒绝.
2. R_SEI 在 FIT-4b cycle 阶段拟合 (cycle 模式 I≠0, R_SEI 项可识别) — 违反 R2
   (FIT-4a → 4b → 4c 严格顺序, R_SEI 必须在 4a) 且 paper §Cycle degradation
   明确 R_SEI 属 calendar 路径. 拒绝.
3. R_SEI 退出 fit, 走 EXP-E IR 直接测量 (本 ADR 决议) — 物理一致, paper 实际
   路径, J^TJ 不再奇异. 采用.

## Consequences

正面:
- T2 calendar round-trip + T3 calendar healthy std xfail 解除 (4 free params
  J^TJ 非奇异)
- R_SEI 路径与 paper §Calendar degradation 物理一致
- 消除 SPEC v0.7.0 frozen 时已知的误归类问题
- `fit_calendar_aging` 优化复杂度从 5D 降到 4D, 收敛性更稳

负面 / breaking:
- `FIT4ACalendarResult.R_SEI: float` 字段移除. v0.7.0 是 release/v0.7.0-fit4
  first release 含此 dataclass, 无外部消费者; 仅 CHANGELOG "Breaking changes"
  段登记
- 现场用户若无 EXP-E IR 数据, 落到 paper literature default 0.66, 模型 IR
  量化精度退化但定性正确 (SPEC §3.1 `skip_if_no_data` 已声明)
- N3 状态 (paper Fig.6c 端到端验证) 仍未通过 — forward-sim 性能根因, 留 v0.8
  (见 ADR-0017), 不构成本 ADR 阻塞

## References

- `docs/SPEC_dm_aging.md` §3.1 / §3.5 (frozen 2026-05-01) + frontmatter
  Revision history (新增 2026-05-02)
- paper Mmeka et al. 2025, J. Electrochem. Soc. 172:080538, §Calendar degradation
  p.12 (R_SEI from EXP-E IR pulses)
- `param_specs/panasonic_ncr18650b__mmeka2025.params.json::R_SEI`
  (literature_default 0.66)
- 子阶段 4 §1.3 长尾 #1 (vault/v0.7.0-fit4/fit4_subphase_4.md)
- 子阶段 5 PARAMETERS.json::FIT-4a::known_limitations_v0_7_0[0]
  (vault/v0.7.0-fit4/fit4_subphase_5.md §3)
- `tests/test_dm_aging.py` 行 354-361 (T2 calendar xfail) + 572-579 (T3 healthy xfail)
- ADR-0011 (RPT bidirectional data contract) — RPT IR 数据契约
