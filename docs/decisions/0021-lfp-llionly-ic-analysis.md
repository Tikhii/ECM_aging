# 0021. IC analysis 在 LFP 上 LLI-only 退化

**Status**: accepted
**Date**: 2026-05-07
**Origin**: v0.8 子阶段 A.2 (`v0.8/a2_ic_analysis_lli_only.md`); B.1 (`v0.8/b1_spec_revision.md`) git 入库 2026-05-08

## Context

LFP cathode OCV 在 ~3.43-3.45 V vs Li/Li⁺ 平台横跨 ~84% SOC (LiFePO₄ ↔ FePO₄ 两相共存, Padhi 1997 + Yamada 2006). 平台两端有窄 single-phase 区间 (X_PE ∈ [0, 0.05] + [0.89, 1], ~16% SOC), dV/dX ≠ 0 仅在此处. Mmeka 2025 的三 DM (LLI + LAM_PE + LAM_NE) IC analysis 在 NCA 上由整 X 域 [0.162, 0.95] 80% SOC 数据支撑; 在 LFP 上 ~16% SOC 数据 + 平台主导 → 三参数 J^TJ 在 16% 子集上接近奇异.

spec_assumptions §2.5 三选项: (A) LLI-only IC analysis / (B) DV-IC graphite stage IIL→II 30-40 mV step / (C) 绕过 IC + FIT-4. A.2 实证选 A.

## Decision

**LFP cell IC analysis 退化为 LLI-only 单参数 fit**. 通过 D4 (a) `ic_analysis.py` 同 module 增分支实装: `material_spec["chemistry"]` 含 "LFP" 时, 跳过 LAM_PE / LAM_NE 自由度, 仅 LLI 经 `scipy.optimize.least_squares` 反演.

`ICAnalysisResult.LAM_PE_Ah / LAM_NE_Ah → NaN` + 新增 `lfp_degraded_branch: bool = True` flag (B.2 实装决定具体字段 vs 子类 dataclass).

## Empirical evidence

A.2 synthetic LFP cell (180 Ah / X0_PE=0.95 / X0_NE=0.01 / dX_PE=0.85 / dX_NE=0.96 / LR=1.10 / OFS=7) + LFPAlawa 三段式 V_PE(x) (Padhi/Yamada 派生, sha256 `98faf7e39c430f09`) + LLI_truth=9 Ah:

- **LLI-only round-trip** (V_min_eff=2.4 V, V_max=3.8 V): plan-literal subset n=998 err=1.6e-12% σ=9.1e-14 Ah; xpe-edge subset n=28 err=1.0e-04% σ=3.6e-5 Ah; full-curve n=1000 err=1.6e-12%. 三 subset 浮点精度内 PASS, J^TJ > 0.
- **3-DM 对照 (negative control)**: xpe-edge subset cond(J^TJ)=1.9e8 (4 orders ↑ over v1 V_max=3.65 跑), σ_LAM_NE=117 Ah (~13× C_nominal), σ_LLI=84.6 Ah (~9× truth). 真实噪声 5-10 mV × √cond ~14000 → LLI 估扰动 1.5-3% C_nominal, edge-only fit 工程上不可接受.

详见 v0.8 A.2 sealed report (`vault/v0.8/a2_ic_analysis_lli_only.md` §4 综合 + Execution `.cc.md` v2, sealed 时删) 类 3-4.

## Alternatives

- **选项 B (DV-IC graphite stage IIL→II)**: 30-40 mV NE peak 在 LFP 平台内 mid-SOC ~60% 提供 LAM_NE 信号 (G 类技术综述). 不走 (A.2 default A.3 OFF), 留 v0.9+ 评估若 B.3 真实数据 LLI 估精度不足时升级.
- **选项 C (绕过 IC + FIT-4)**: FIT-4 反演链需 LLI 输入, 跳 IC 不可行. 不走.

## Consequences

- v0.8 LFP 接入仅 LLI 单退化模式可识别; LAM_PE / LAM_NE 留 v0.9+ 评估 (FIT-4 反演链 LAM 输入 v0.8 不强求).
- B.2 任务包: ic_analysis.py 增 LFP 分支 + ICAnalysisResult flag + tests/test_ic_analysis.py LFP variant.
- **B.1 已落 (V_min consistency)**: A.2 v2 实证 spec V_min=2.0 V 与 X_NE budget 不一致, B.1 T2 analytic calibrate 锁 X0_NE = 0.0153 (forward-solve `V_PE(0.95) - V_NE(X0_NE) = V_min_target=2.0V`, brentq); status=`literature_default`, fit_source=`analytic_calibrate_2026-05-08_v0.8_b1`. 数值待 B.3 fresh OCV 实测 calibrate refine (上调至 0.02-0.03 量级 if needed).

## References

- Mmeka 2025 *J. Electrochem. Soc.* 172:080538 (本工程主论文)
- A1 Birkl 2017 *J. Power Sources* (DM IC analysis methodology)
- Padhi 1997 *J. Electrochem. Soc.* 144:1188 (LFP olivine 两相)
- Yamada 2006 *Nat. Mater.* 5:357 (LFP phase diagram, [0.05, 0.89] miscibility gap)
- B3 ScienceDirect 2022 LFP cathode review (LLI 主导 LFP cell capacity fade 信号)
- spec_assumptions §2.5 (`pre-release/v0.8_spec_assumptions.md`)
- v0.8 A.2 sealed report (`vault/v0.8/a2_ic_analysis_lli_only.md` §4 综合; Execution Agent `.cc.md` v1 + v2 sealed 时删除)
- v0.8 B.1 git 入库 (`vault/v0.8/b1_spec_revision.md`; `docs/SPEC_ic_analysis.md` Revision history 2026-05-07; `docs/SPEC_dm_aging.md §3.1` Cell type routing 表)
