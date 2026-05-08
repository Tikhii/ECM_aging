# 0022. LFPAlawa.dat 数据来源 (Padhi 1997 + Yamada 2006 phase diagram 派生)

**Status**: accepted
**Date**: 2026-05-07
**Origin**: v0.8 子阶段 A.1 (`v0.8/a1_lfp_alawa_draft.md`); B.1 (`v0.8/b1_spec_revision.md`) git 入库 2026-05-08

## Context

spec_assumptions §3.2 D3 物理校正确认 LFP cathode OCV 是 olivine FePO4↔LiFePO4 两相共存的材料热力学性质 (Padhi 1997 founding paper + Yamada 2006 phase diagram), vendor 间二阶差异 ~5-10 mV (universal 性质). v0.8 接入需 `libquiv_aging/data/LFPAlawa.dat` 草稿 (与 NCAAlawa / GraphiteAlawa 同三列格式 x / dH / dS).

A.1 Execution 实证: HNEI 'Alawa 公开页面 (https://www.hnei.hawaii.edu/alawa + /alawa-toolbox/) 仅描述 toolbox + 商业 license 联系方式 (matthieu@hawaii.edu), **无 LFP stock dataset 下载链接**. v0.8 dry-run 阶段 license 申请出 scope.

## Decision

LFPAlawa.dat 草稿采用 **D3 (b) Padhi 1997 + Yamada 2006 phase diagram 派生**: 三段式 V_PE(x) 模型 = [0.05, 0.89] 平台 ~3.434 V (LiFePO4/FePO4 两相共存) + 两端 single-phase region 线性外推. 1001 等距数据点 (x: 0.99→0.01), dS=0 (沿用 NCA/Graphite 默认).

实测 sanity (v0.8 A.1 sealed report `vault/v0.8/a1_lfp_alawa_draft.md` §4): 平台 V mean **3.434 V** std **0.87 mV** (n=857); 两端 |dV/dx| **2.86 + 9.33 V/x** (远超 0.5 阈值). A.2 v2 retro patch (V_AT_X_LO_END 3.55→4.20 V) 后 sha256 = `98faf7e39c430f09`, 平台不变, 仅 delithiated 单相边坡变陡 (2.86 → 19.11 V/x).

## Alternatives

- **D3 (a) HNEI 'Alawa stock LFP**: 公开页面不可获 (license-only 联系 matthieu@hawaii.edu); 出 v0.8 scope, 留 v0.9+ 评估
- **D3 (c) Plett 2024 thermodynamically-consistent OCV**: 复杂度过高于 v0.8 起步需求 (LFP universal 性质下二阶差异不值)
- **D3 (d) Battery Archive commercial cell pseudo-OCV (C/40 反推)**: 含 cell-design 噪声 (反推自整 cell 而非半电池)
- **联系 matthieu@hawaii.edu 申请 license**: 出 v0.8 scope, 工作流上不阻塞当前接入

## Consequences

- vault dry-run 起步, **fresh OCV calibrate** (A.1 后期 / 推 B.1) 锁实测值
- vendor 间二阶差异 5-10 mV 可接受 (spec_assumptions §3.2 脚注)
- 仅 IC analysis RMSE 严重超标时回头补做半电池 OCV 实测 (Step 1b 触发, A.2/B.3 评估)
- **lfp_linear mvol mode 实装为 B.2 任务** (`libquiv_aging/cell_factory.py:126` 现 NotImplementedError stub, A.1 schema validate 跳过 cell_factory 实例化)
- v0.8 D2 cell name local override `lfp_large_format_power` (动力场景, 平行 D2 (b); TASK.md §11 D2 frozen 不动)
- 两端 single-phase 仅线性外推, 非 Padhi/Yamada 多项式拟合 — 后续 FIT-1 / B.1 可替换更高保真方案

## References

- D1 Padhi A.K. et al. 1997 *J. Electrochem. Soc.* 144(4):1188 — DOI 10.1149/1.1837571
- D2 Yamada A. et al. 2006 *Nat. Mater.* 5(5):357 — DOI 10.1038/nmat1611
- A5 HNEI 'Alawa toolbox (https://www.hnei.hawaii.edu/alawa, 公开无 LFP stock)
- spec_assumptions §3.2 (`pre-release/v0.8_spec_assumptions.md`, 修订路径 Step 1a)
- v0.8 任务包 §11 D3 (`v0.8/TASK.md`, 数据来源候选)
- v0.8 A.1 sealed report (`vault/v0.8/a1_lfp_alawa_draft.md` §3 v3 audit + §4.2; Execution Agent `.cc.md` sealed 时已删除)
- v0.8 B.1 git 入库 (`vault/v0.8/b1_spec_revision.md`; `libquiv_aging/data/LFPAlawa.dat` sha256 `98faf7e39c430f09`)
