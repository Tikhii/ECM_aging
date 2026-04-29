# IC Analysis 方法学综述: 学术合理性 + 升级路径文献入口

> 状态: 学术合理性综述 + 升级路径文献入口
> 本文不进入 R5 一致性扫描范围, 但其触发的派生 entry (CRITICAL_REVIEW.md N2/N3,
> PARAMETERS.json::critical_review_findings, CLAUDE.md 任务路由表, MIGRATION_NOTES
> 版本表) 仍在 R5 范围内
> 文献条目默认 `[verified: pending]`, 已 web search 核验的条目标 `[verified: 2026-04-29]`

---

## §1 Purpose 与边界声明

### 1.1 本文是什么

本文档对 `release/v0.5.2-ic-analysis` 落地的 IC 曲线分析算法做学术合理性综述, 并为
未来 v0.6+ / v0.7+ 升级方向建立文献入口。三大目标:

1. **方法学定位**: 在学术 SOTA 谱系中标记本工程实现的位置 (流派 A 全曲线 OCV-fitting,
   与 Birkl 2017 + Mmeka 2025 主流一致)
2. **七项核对结论固化**: 把 v0.5.2 release 后 web chat 端做的 review 成果落到工程档案,
   避免未来任务包重复检索
3. **升级路径登记**: 让 critical_review_findings::N2/N3 + 本文一同消费, 让 FIT-4a/4b 等
   下游使用 IC 输出时能感知 caveats

### 1.2 本文不是什么

- **不是 SPEC 扩展**. `docs/SPEC_ic_analysis.md` 已 frozen, 本文不重打开.
- **不是 errata**. 已知错误进 `docs/CRITICAL_REVIEW.md` §一, 本文涉及的 N2/N3 是
  "已知简化假设" (作用域内合法但需感知), 进 §二.
- **不是单一文献 starter pack**. 与 `fractional_order_RC.md` 不同, 本文含本工程算法
  实现剖析与 7 项学术对照核对的具体论证, 不只是文献清单.

### 1.3 引用约定

本文引用文献遵循 `COLLABORATION_PROTOCOL.md §6.3` 三类定义:
- 第一类: 本工程主 paper (Mmeka, Dubarry, Bessler 2025)
- 第二类: 主 paper 直接引用的关键文献
- 第三类: 物理建模或方法学相关的其他文献 (无论主 paper 是否引用)

完整清单见 §5. 本文行文中文献以 "Author Year" 简写, 详见 §5 卷号 / DOI / arXiv ID.

### 1.4 作者修正记录 (子阶段 0/1 实证驱动校验产出)

子阶段 1 web search 核验时, 修正了 v0.5.2 review 阶段两处作者名错误:

| 概念 | v0.5.2 review 误记 | 实际正确引用 |
|---|---|---|
| Identifiability via Fisher information + N/P 参数化 | "Olson 2024" | **Lin & Khoo (2024)** *J. Power Sources* 605:234446 |
| 流派 B peak-tracking | "Chen-Tsai-Marinescu (2021) *J. Energy Storage* 45:103814" | **Chen, Marlow, Jiang, Wu (2022)** *J. Energy Storage* |
| pOCV phantom 风险 | "Marinescu group 2025" (作者顺序模糊) | **Asheruddin et al. (2025)** arXiv:2512.19773 (Marinescu 通讯, Imperial College London) |

这是 `COLLABORATION_PROTOCOL.md §6.3` 实证驱动校验在子阶段 1 web search 上的正面应用.

---

## §2 学术界 IC 分析方法学谱系

### 2.1 Dubarry alawa 框架 (2012-2024) — OCV 合成 + LR/OFS 参数化的源头

`alawa` 是 Hawai'i Natural Energy Institute (HNEI) 由 Matthieu Dubarry 等开发的
mechanistic emulator 框架, 主入口 https://www.soest.hawaii.edu/HNEI/alawa/, 在 `Front.
Energy Res. 2022` *Best practices for incremental capacity analysis* 中详细描述.

**核心思路**: 把电池 OCV 视为两个半电池 OCP (PE 和 NE) 的代数差, 通过两组退化模式参数
(LR = Loss Ratio, OFS = Offset) 调控半电池 OCP 在 SOC 轴上的伸缩 / 平移, 反推
(LLI, LAM_PE, LAM_NE) 三组 degradation modes (DMs).

LR / OFS 与 (LLI, LAM_PE, LAM_NE) 之间是代数等价, 不是物理上的两套独立参数:

- LAM_PE / LAM_NE → 半电池 OCP 在 SOC 轴上的 stretch (LR)
- LLI → 两半电池相对偏移 (OFS)
- 给定一对 (LR_PE, LR_NE, OFS), DMs 唯一确定; 反之亦然

**本工程关系**:
- `libquiv_aging/ic_analysis.py::synthesize_V_ocv` 是 alawa forward emulator 的 Python
  实现 (paper Eqs. 21-26 algebraic 实现 + dual brentq 求解 PE/NE stoichiometry +
  bracket 增强保证收敛)
- `analyze_ic` 反推 (LLI, LAM_PE, LAM_NE) 时实质上等价于反推 alawa 的 (LR, OFS) +
  代数变换
- `X^0` stoichiometry 约定有两套: paper Table I 用 SOC=1 reference, 本工程 spec 用
  V_min state 与 FIT-1 一致 (子阶段 0/2_revised_v2 决策); 两套口径互补, 不冲突

### 2.2 Birkl Oxford diagnostics (2017) — 流派 A 全曲线 OCV-fitting

Birkl, Roberts, McTurk, Bruce, Howey (2017) *J. Power Sources* 341:373-386,
*Degradation Diagnostics for Lithium Ion Cells* `[verified: 2026-04-29]`.

**核心方法**: 给定 fresh-cell 半电池 OCP 模板 (PE 和 NE), 通过 NLS V(Q) 曲线拟合反推三组
DMs. 不直接做 dQ/dV peak detection, 而是在电压域评估残差.

**关键贡献**:
- 三组 DMs (LLI, LAM_PE, LAM_NE) 对 cell OCV 的影响是 distinguishable 的, 每个 mode 在
  曲线上有 unique fingerprint (paper Figs. 1-3 系统化论证)
- 使用 RMSE-based error bars 量化拟合不确定度 (注: Hessian 协方差是更强的方法, 见 §3)
- 提供 commercial pouch cell 实测案例, RMSE 量级 ~10 mV, 置信区间合理

**本工程关系**: 本工程 `analyze_ic` 沿用此流派 (NLS + 电压域残差), `fit_quality` 阈值
(RMSE 20/15 mV, R² 0.99/0.999) 直接以 Birkl 2017 实测水平 + Phantom LAM (Asheruddin
2025) IR 量级 + SOP §3.2 三方对齐.

**本工程超越 Birkl 2017 的两点**:
1. **协方差**: 用 Hessian 协方差矩阵导出参数 std (full covariance), 比 Birkl 2017 仅有
   RMSE-based marginal error bars 强 (与 Lin & Khoo 2024 同水平)
2. **物理一致性**: T4 测试基于 cap_loss self-consistency 验证 (而非 sum(DMs) 守恒, 见
   §3.3 Item 7), 这超越 Birkl 2017 的简单 sum check

### 2.3 Chen, Marlow, Jiang, Wu (2022) peak-tracking — 流派 B

Chen, Marlow, Jiang, Wu (2022) *J. Energy Storage*, *Peak-tracking method to quantify
degradation modes in lithium-ion batteries via differential voltage and incremental
capacity* `[verified: 2026-04-29]` (Imperial College London; Marinescu 同 group 但未
署名本文).

**核心方法**: 在 dQ/dV 域识别显著 peaks, 跟踪每个 peak 的位置 / 强度 / 面积变化,
通过 graphite stage transition 信号反推 LLI / LAM. 不在电压域全曲线拟合.

**适用场景**:
- onboard BMS (算力受限, 处理实时数据流)
- graphite-anode + 化学体系 stage features 显著 (NCA/G, NMC/G 较好)

**缺点**:
- 只用部分曲线信息 (peak 附近), 信号利用率低
- 依赖 graphite stage feature 可见性, 老化后期或 noise 大时 peak 模糊
- LFP/G 体系 peak 不显著, 此方法不适用 (Dubarry & Anseán 2022 §best practice 也明确
  指出 LFP 上 IC peak 太弱, 应改用 differential voltage)

**本工程立场**: **不采用流派 B**. 理由:
- 本工程目标是离线 RPT 诊断精度优先, 而非 onboard
- 主体系 NCA/G + LFP/G 兼容 (见 paper §Cycle degradation), 流派 A 在 LFP 上仍 robust
  (虽然 IC peak 弱, 但全曲线 OCV shape 仍可拟合), 流派 B 在 LFP 上失效

但这并不否定流派 B 的工程价值, 在合适场景 (NCA/G + onboard) 它是 valid alternative.

### 2.4 Lin & Khoo (2024) identifiability — Fisher information + N/P 参数化

Lin & Khoo (2024) *J. Power Sources* 605:234446 (arXiv:2309.17331),
*Identifiability Study of Lithium-Ion Battery Capacity Fade Using Degradation Mode
Sensitivity for a Minimally and Intuitively Parametrized Electrode-Specific Cell
Open-Circuit Voltage Model* `[verified: 2026-04-29]` (A*STAR Singapore).

**核心贡献**:
- 提出 N/P (negative-to-positive) 与 Li/P (lithium-to-positive) 参数化, 替代经典 LR/OFS,
  让 SOH 参数与 cutoff voltage 解耦, 更对称 / 更直观
- 通过 Fisher information matrix 系统量化 (LLI, LAM_PE, LAM_NE) 在不同 SOC 窗口的
  identifiability
- 指出 fresh-near regime 下 LAM_NE 在某些 cell geometry 下识别性最弱 (本工程 v0.5.2
  子阶段 2_revised_v2 实测 light case LAM_NE 25% 偏差但 std=4.8 mAh 涵盖, 正符合此
  predict)

**本工程关系**:
- 本工程沿用 alawa LR/OFS 参数化, 没有切换到 N/P. 这是 v0.7+ 候选改进 (见 §4.2)
- 本工程 `ICA-W002` 警告 + std 报告设计是 Lin & Khoo identifiability framework 的工程
  操作化 (用户接收 std 后能判断当前结果是否在 well-identified regime)

### 2.5 Asheruddin et al. (2025) phantom LAM/LLI — pOCV 残留风险 ⚠️

Asheruddin et al. (2025) arXiv:2512.19773, *Phantom LAM and LLI: Resistance and
Hysteresis Bias in Voltage-Curve Degradation Mode Analysis* `[verified: 2026-04-29]`
(Imperial College London; Marinescu PI).

**核心问题**: 学术界 IC / DMA 实践中常用的 pseudo-OCV (实际 C/40 测量) 不是真正的 OCV,
它残留两类 non-degradation 贡献:
1. **SOC-dependent ohmic IR drop**: 即使在 C/40 这样低的 C-rate 下, 半电池及电解质
   仍贡献量级在 tens of millivolts 的 IR offset, 且 SOC 依赖 (具体值随化学体系与 SOC
   区段而异; paper 用 LG M50T 与 Molicel P45B 商用 21700 cells 实测各 SOC 区段值)
2. **Intrinsic charge-discharge hysteresis**: graphite-SiOx (C/SiOx) 体系尤其严重,
   纯 graphite 较弱但仍存在, NCA/NMC 系 PE 也有较小贡献

**关键发现** (paper Highlights):
- LG M50T (高内阻 cell): 不做 IR 校正会**抑制** PE-LAM 与 LLI 反演, 同时**夸大** apparent
  graphite loss (这是反直觉但严重的 attribution bias)
- Molicel P45B (低内阻 cell): hysteresis + voltage-windowing 主导 charge-discharge
  branch 之间的 inferred Si loss 差异
- Paper 推荐处方: instantaneous R_Ω(SOC) (~50 ms pulses) + harmonized voltage window
  + discharge-branch DMA

**本工程影响 (NCA/G 体系评估)**:
- SiOx hysteresis 在本工程不存在 (主体系 NCA/G, 纯 graphite anode)
- Graphite hysteresis 仍有但量级较小
- IR 残留**仍存在**, RPT 协议是否做了 instantaneous IR 校正取决于实验数据来源

**当前处理**: 本工程 `analyze_ic` **间接吸收** 此风险:
- `_smooth_voltage` 不能消除 IR 偏移 (smooth 处理频域 high-frequency noise, 不处理
  systematic bias)
- `fit_quality` RMSE 阈值 (20 / 15 mV) 间接覆盖 — 若 IR 残留 + hysteresis 把 RMSE 推到
  > 15 mV, 会触发 `ICA-W001`, 下游 (FIT-4a/4b) 看到 warning 后会降权重消费
- **无显式 IR 校正逻辑**, 这是 v0.6+ 候选改进 (见 §4.1) + `critical_review_findings::N2`
  登记项

**本文档触发的派生 entry**:
- `CRITICAL_REVIEW.md` §二 N2: pOCV 残留 IR + hysteresis 偏移
- `PARAMETERS.json::critical_review_findings::N2_pOCV_phantom_offset` (4 字段 schema:
  severity / summary / evidence / action, 子阶段 0 reconnaissance 实测 N1 既有 schema
  确认, 不引入 name / discovered_date / affected_parameters)

### 2.6 数据预处理: Savitzky-Golay 及替代方案

**SG 是 IC 分析的 de facto 主流**: Marinescu group 系列工作 (Chen et al. 2022,
Asheruddin et al. 2025), Mmeka 2025 paper Appendix MATLAB code, Dubarry & Anseán 2022
*best practices* 都使用 SG. 本工程 `_smooth_voltage` 沿用此选择.

**Schmid, Rath, Diebold (2022)** *ACS Meas. Sci. Au* 2(2):185-196, *Why and How
Savitzky-Golay Filters Should Be Replaced* `[verified: 2026-04-29]` (TU Wien) 系统批评
SG 的两点弱点 + 给出三套替代方案:

| 方法 | 缩写 | 核心改进 |
|---|---|---|
| SG with Hann-square 加权 | SGW | stopband 衰减提升, 边界 artifact 缓解 |
| Modified Sinc kernel + 线性外推 | MS | 边界 artifact 最小, 数值稳定 |
| Whittaker-Henderson smoothing | WH | 边界值原生处理, 频域响应更干净 |

注: Schmid 2022 不是 battery / IC 分析专题文献, 是通用 signal processing methodology.
但 SG 在本工程的应用 (V(Q) → smoothed V → 用于 forward residual 评估) 直接相关.

**本工程实际影响评估**: **小**. 理由:
- 本工程目标函数是**电压域全曲线残差** (流派 A), 不是 dQ/dV 域 peak detection (流派 B);
  smoothing 后 systematic bias 通过 NLS 拟合 robustly 吸收, SG 边界 artifact 不直接
  传播到 (LLI, LAM_PE, LAM_NE) 反演结果
- v0.5.2 实测 RMSE / R² 在 fresh-near regime 表现良好, 没有暴露 smoothing 短板

**升级路径**: 见 §4.3, v0.7+ 候选, 优先级低. `pybaselines` Python 包提供 WH 实现, 可作
plug-in 替换 (signature 与 `scipy.signal.savgol_filter` 相近).

---

## §3 本工程算法实现剖析

### 3.1 主要 module 与函数 (libquiv_aging/ic_analysis.py)

`release/v0.5.2-ic-analysis` 落地的核心 module 文件 658 行, 关键函数:

| 函数 | 作用 | 数学/算法 |
|---|---|---|
| `synthesize_V_ocv(LLI, LAM_PE, LAM_NE, SOC, ...)` | Forward model: DMs → V_cell(SOC) | paper Eqs. 21-26 algebraic; dual brentq 解 X_PE / X_NE; bracket 增强保证收敛 |
| `_smooth_voltage(V, window, poly)` | RPT 数据预处理 | Savitzky-Golay 在 V 上, **不**在 dQ/dV 上 |
| `analyze_ic(SOC, V_meas, ...)` | Inverse problem: V(SOC) → DMs | scipy least_squares trf + bounds + Hessian 协方差 |
| `heuristic_initial_guess(...)` | 初始猜测 | 基于 fresh-cell **模型容量**, 不是 datasheet C_nominal |
| `_fresh_state_model_capacity_Ah` | Fresh capacity 计算 | 与 forward model 同代码路径 (避免 dual-source drift) |

### 3.2 流派归属

**流派 A 全曲线 OCV-fitting**, 与 Birkl 2017 + Mmeka 2025 主 paper 同源, 与 Dubarry &
Anseán 2022 *best practices* 推荐路径一致 (paper §IV "Direct extraction from voltage
response", 流派 A 是其主推荐).

**关键算法约定**:
- 残差在**电压域** (V_obs(SOC) - V_synth(SOC))²
- 不预先做 dQ/dV (避免 dQ/dV 域噪声放大问题, Dubarry & Anseán 2022 §III.B 反复强调)
- Smoothing 仅用于稳定 forward residual 评估, 不用于 peak feature extraction

### 3.3 与学术 SOTA 七项核对

每项给出 (a) 维度 + 评估 / (b) 学术对照 / (c) 本工程实证 / (d) 结论.

#### Item 1: Forward model 数学结构 — ✓ 完全合理

**a)** Mmeka 2025 paper Eqs. 21-26 给出 3 DMs → (X_PE, X_NE) → V^0_PE - V^0_NE 的代数式.
本工程 `synthesize_V_ocv` 严格实装, 含 dual brentq 解逆向 stoichiometry.

**b)** alawa framework (Dubarry HNEI) 给出同等价代数等价结构, 仅参数化习惯不同
(LR/OFS vs LLI/LAM). Birkl 2017 也用同等价 forward model.

**c)** v0.5.2 子阶段 2_revised_v2 的 forward-only 实测 (`scripts/ic_analysis_smoke.py`)
在 light/moderate/severe 三档 ground truth 下 round-trip 一致 (synthesize → analyze 还原
误差在 std 涵盖范围内).

**d)** ✓. 不需要修改.

#### Item 2: 数据预处理 (Savitzky-Golay) — ✓ 主流做法

**a)** SG 在 V 上, window / poly 经 SOP §3.2 校准.

**b)** Marinescu group 系列 (2022, 2025) + Mmeka 2025 + Dubarry & Anseán 2022 都用 SG.
Schmid 2022 给出替代方案但本工程实际影响小 (§2.6).

**c)** v0.5.2 测试 suite 109 passed, 无 smoothing-induced 异常.

**d)** ✓ 当代主流, v0.7+ 候选切换 WH (§4.3), 不阻塞.

#### Item 3: 目标函数 (电压域残差) — ✓ 完全正确

**a)** `analyze_ic` 用 (V_obs - V_synth)² 残差, scipy least_squares trf.

**b)** 这是流派 A 的灵魂. Dubarry & Anseán 2022 §IV 明确推荐: 不要直接在 dQ/dV 域做
NLS, 因为 dQ/dV 是导数, noise 被放大, 数值条件数差.

**c)** v0.5.2 测试 light/moderate case RMSE 在 ~5-15 mV 量级, R² > 0.99, 与 Birkl 2017
实测水平相当.

**d)** ✓.

#### Item 4: Hessian 协方差不确定度 — ✓ 优于 Birkl 2017

**a)** `analyze_ic` 用 Hessian = J^T J 反推 covariance matrix, 导出参数 std + 95% CI.
LinAlgError fallback 写 NaN std (不 crash).

**b)** Birkl 2017 仅给 RMSE-based marginal error bars (无完整协方差). Lin & Khoo 2024
推荐使用 Fisher information matrix (本工程 Hessian 是 FIM 的渐近等价, 在 NLS 大样本下
等价).

**c)** v0.5.2 子阶段 2_revised_v2 light case LAM_NE 25% 反演偏差但 std=4.8 mAh, 85%
CI 涵盖 ground truth, 这正是 Hessian 协方差正确工作的实证.

**d)** ✓ 与 Lin & Khoo 2024 同水平, 优于 Birkl 2017.

#### Item 5: Identifiability 处理 — ✓ 与 SOTA 一致

**a)** `analyze_ic` 报告 std + bounds_hit; std 过大或 bounds_hit=True 时触发
`ICA-W002` 警告.

**b)** Lin & Khoo 2024 framework: identifiability 通过 Fisher information matrix 系统
量化, 表现为参数协方差矩阵 condition number. 本工程 std + bounds_hit 是该 framework 的
工程操作化 (用户拿到 std 后能判断 well-identified vs ill-identified regime).

**c)** v0.5.2 ICA-W002 在 LAM_NE 反演上正面 trigger (light case 触发 W002, severe case
不触发), 与 Lin & Khoo 2024 fresh-near regime 弱可识别预测一致.

**d)** ✓ N/P 参数化重写是 v0.7+ 候选 (§4.2), 不阻塞当前.

#### Item 6: Marinescu phantom 风险 — ⚠️ 间接处理

**a)** 本工程当前处理: `fit_quality` RMSE 阈值兜底, 无显式 IR / hysteresis 校正.

**b)** Asheruddin et al. (2025) 实测 LG M50T + Molicel P45B 显示 IR + hysteresis 可
**主导** DMA attribution, 不只是 marginal correction. C/SiOx 体系尤其严重, NCA/G 较轻.

**c)** 本工程主体系 NCA/G (SiOx hysteresis 不存在, graphite hysteresis + IR 残留仍存在);
v0.5.2 实测未暴露 phantom-driven misattribution, 但**未做 systematic stress test**
(因为没有跨化学体系大数据集).

**d)** ⚠️ 升级到 `critical_review_findings::N2`. 详见 §4.1.

#### Item 7: Forward model 物理一致性 (cap_loss) — ✓ 超越 Birkl 2017

**a)** v0.5.2 子阶段 4 T4 测试改写为 cap_loss self-consistency (而非 sum(DMs) 守恒):
forward 计算 cap_loss(LLI, LAM_PE, LAM_NE) → 与 ground truth cap_loss 比对.

**b)** Dubarry & Anseán 2022 paper 反复强调: sum(DMs) ≠ cap_loss 是跨化学体系普遍现象,
LAM 损失可被未使用的 SOC 范围部分吸收 (电极 SOC 窗口耦合非线性). Mmeka 2025 paper
§"Cycle degradation" Fig. 6c 实测 143 EFC calibration: sum=0.25 / cap_loss=0.11 /
ratio 2.27.

**c)** v0.5.2 子阶段 4 实测 cycle ratio 1.66 / 2.29 / 2.97 (light/moderate/severe), 与
paper 同量级且非线性递增. 这是 v0.4 → v0.5.2 升级中获得的关键认知. 详见
`MIGRATION_NOTES.md` §20.6.

**d)** ✓ 升级到 `critical_review_findings::N3`. 物理意义: FIT-4a/4b 拟合 LLI / LAM 时
**不能假设 sum 守恒**, DMs 时间序列与 cap_loss 时间序列各自独立拟合. 详见 §4 + N3 entry.

---

## §4 潜在改进路径

### 4.1 v0.6+ 候选: Marinescu phantom 处理 (IR 校正)

**触发**: §3.3 Item 6 ⚠️.

**问题陈述**: pOCV 残留 IR + hysteresis 在 C/SiOx 体系可主导 DMA attribution, 在 NCA/G
体系次要但仍存在. 本工程当前无显式 IR 校正.

**改进方向**: 引入可选 `--ir-correction` 参数到 `analyze_ic` 接口:

```python
def analyze_ic(
    SOC, V_meas, ...,
    ir_correction: Optional[Callable[[float], float]] = None,  # R_Omega(SOC) LUT
):
    if ir_correction is not None:
        V_corr = V_meas + I_used * ir_correction(SOC)
    else:
        V_corr = V_meas
    # ... 后续 NLS 同 v0.5.2 ...
```

**数据来源**: R_Omega(SOC) 来自 GITT (galvanostatic intermittent titration technique)
或 instantaneous IR pulse (Asheruddin 2025 推荐 ~50 ms pulses), 由用户在 RPT 协议中
独立测量后传入.

**与 paper 框架兼容性**: paper Eq. 1 已显式分离 R_stat + R_dyn 项. IC 分析层接受
quasi-OCV 输入 (SPEC 内部约定), 所以 IR 校正是 **layer 上层扩展**, 不动 SPEC 内部.

**优先级**: 中 (NCA/G 主体系次要, SiOx 体系关键. 本工程当前数据集不含 SiOx, 暂不
紧急).

**`critical_review_findings::N2` JSON 草稿** (4 字段 schema, 与 N1 一致):

```json
"N2_pOCV_phantom_offset": {
  "severity": "MODERATE",
  "summary": "pseudo-OCV (实际 C/40 测量) 残留 SOC-dependent ohmic IR drop + intrinsic charge-discharge hysteresis 量级 tens of millivolts. NLS V(Q) 拟合会把这些 non-degradation 贡献误归到 (LLI, LAM_PE, LAM_NE) DMs, 产生 phantom degradation. C/SiOx 体系尤其严重, NCA/G 次要 (SiOx hysteresis 不存在, graphite hysteresis + IR 残留仍存在)。",
  "evidence": "Asheruddin et al. (2025) arXiv:2512.19773 实测 LG M50T (高内阻) + Molicel P45B (低内阻) 商用 21700 cells: 不做 IR 校正会抑制 PE-LAM + LLI 反演并夸大 apparent graphite loss; hysteresis + voltage-windowing 主导 charge-discharge branch 间的 Si loss 差异。本工程主体系 NCA/G 实测未暴露但未做跨化学体系 stress test。",
  "action": "记录现象。本工程当前通过 fit_quality RMSE 阈值 (20/15 mV) 间接吸收, 无显式 IR 校正。v0.6+ 候选改进: 引入可选 --ir-correction 参数到 analyze_ic, 接受 R_Omega(SOC) LUT 输入, V_corr = V_obs + I·R_Omega(SOC) 后再拟合。详见 docs/UPGRADE_LITERATURE/ic_analysis_methodology_review.md §4.1。"
}
```

### 4.2 v0.7+ 候选: Lin & Khoo N/P 参数化分析层重写

**触发**: §2.4 + §3.3 Item 5.

**问题陈述**: 本工程沿用 alawa LR/OFS 参数化, Lin & Khoo 2024 显示 N/P + Li/P 参数化让
Fisher information 分析更直接, condition number 在某些 regime 更优.

**改进方向**: 仅在 analysis layer 做 reparameterization (forward model 不动). 后处理时
把 (LLI, LAM_PE, LAM_NE) 转换到等价 (Li_max, Q_PE_max, Q_NE_max) 表征, 比较 condition
number.

**优先级**: 低 (本工程 ICA-W002 + std 已经是 Lin & Khoo framework 的工程操作化, 业务层
等价收益; reparameterization 主要让 analysis 数值更稳, 不解决新的物理问题).

### 4.3 SG 替代 (Whittaker-Henderson / Modified Sinc)

**触发**: §2.6 + Schmid 2022.

**问题陈述**: SG stopband 衰减不理想 + 边界 artifact, 在 dQ/dV 域 peak shape 失真显著
(本工程做电压域残差, 影响轻).

**改进方向**: `_smooth_voltage` 切换 plug-in 替换:

```python
def _smooth_voltage(V, method: Literal["sg", "wh", "ms"] = "sg", ...):
    if method == "wh":
        from pybaselines import Baseline  # Whittaker-Henderson
        ...
    elif method == "ms":
        ...
    else:  # sg
        from scipy.signal import savgol_filter
        ...
```

**优先级**: 低 (本工程电压域残差 robust 吸收 SG 边界 artifact, 实际收益小).

### 4.4 充电 IC 联合分析扩展 (LFP/Gr 体系下识别性提升)

**触发**: Dubarry & Anseán 2022 §best practices 推荐充电 + 放电联合 IC.

**问题陈述**: 本工程 SPEC 当前接受单 branch (放电) IC 数据. LFP/Gr 体系上 IC peaks 弱,
单 branch identifiability 不足.

**改进方向**: 扩展 SPEC 接受充电 RPT 数据, 联合拟合: 残差 = w_dis · ||V_obs_dis -
V_synth_dis||² + w_chg · ||V_obs_chg - V_synth_chg||². Asheruddin 2025 同时也指出
charge-discharge branch 对 hysteresis 敏感差异大, 联合时需配合 IR 校正 (§4.1).

**优先级**:
- NCA/G (本工程主体系): **小** — IC peaks 已显著, 单 branch 充足
- LFP/Gr: **显著** — IC peak 弱, 联合分析 identifiability 提升明显 (Dubarry & Anseán
  2022 §VI 给出 LFP 实测对照)

---

## §5 文献清单 (三类, 符合 COLLABORATION_PROTOCOL §6.3)

### 第一类: 本工程主 paper

- **Mmeka, Dubarry, Bessler (2025)** *J. Electrochem. Soc.* 172:080538.
  Physics-informed equivalent circuit model with degradation mode integration.
  含 §"Cycle degradation" 实测 sum=0.25 / cap_loss=0.11 / ratio 2.27 (Fig. 6c) +
  Zenodo 配套 MATLAB code. `[verified: in-context PDF]`

### 第二类: 主 paper 直接引用的关键文献

- **alawa framework** (Dubarry et al., HNEI). Mechanistic emulator framework.
  https://www.soest.hawaii.edu/HNEI/alawa/. 本工程 OCV 合成 + LR/OFS 参数化的源头.

- **Dubarry & Anseán (2022)** *Front. Energy Res.* 10:1023555.
  *Best practices for incremental capacity analysis*.
  DOI: 10.3389/fenrg.2022.1023555. (Corrigendum 2023, Front. Energy Res. 11:1203569,
  Fig. 13 重复修正). `[verified: 2026-04-29]`

- **Birkl, Roberts, McTurk, Bruce, Howey (2017)** *J. Power Sources* 341:373-386.
  *Degradation Diagnostics for Lithium Ion Cells*.
  DOI: 10.1016/j.jpowsour.2016.12.011. Oxford degradation diagnostics 本工程 fit_quality
  RMSE / R² 阈值的方法学依据. `[verified: 2026-04-29]`

- **Schmider et al.** d ν̄/dX 体积变化输入 (paper Mmeka 2025 Fig. 5 input). `[verified:
  pending — 详见 paper Reference 列表]`

### 第三类: 物理建模 / 方法学相关其他文献

- **Asheruddin, Leal De Souza, Holland, Folkson, Offer, Marinescu (2025)** arXiv:2512.19773
  (Imperial College London). *Phantom LAM and LLI: Resistance and Hysteresis Bias in
  Voltage-Curve Degradation Mode Analysis*. 本工程 N2 条目源头. `[verified: 2026-04-29]`

- **Chen, Marlow, Jiang, Wu (2022)** *J. Energy Storage*. *Peak-tracking method to quantify
  degradation modes in lithium-ion batteries via differential voltage and incremental
  capacity*. 流派 B peak-tracking 代表作; 本工程不采用此流派但作为对照. `[verified: 2026-04-29]`

- **Lin & Khoo (2024)** *J. Power Sources* 605:234446 (arXiv:2309.17331; A*STAR Singapore).
  *Identifiability Study of Lithium-Ion Battery Capacity Fade Using Degradation Mode
  Sensitivity for a Minimally and Intuitively Parametrized Electrode-Specific Cell
  Open-Circuit Voltage Model*. Fisher information + N/P 参数化 framework. `[verified:
  2026-04-29]`

- **近期 IC-DV review** (2024) *Energies* 17(17):4309. *A Review of Methods of Generating
  Incremental Capacity-Differential Voltage Curves for Battery Health Determination*.
  https://www.mdpi.com/1996-1073/17/17/4309. 综述当前各类 IC/DV 计算方法学 + filter 选择.
  `[verified: 2026-04-29 — 作者名待 fetch 确认]`

- **Schmid, Rath, Diebold (2022)** *ACS Meas. Sci. Au* 2(2):185-196.
  *Why and How Savitzky-Golay Filters Should Be Replaced*.
  DOI: 10.1021/acsmeasuresciau.1c00054 (TU Wien). 通用 SG 替代方案 (SGW / MS / WH)
  方法论文. `[verified: 2026-04-29]`

- **Yang et al. (2017)** Knee point formation, SEI-plating positive feedback.
  Paper Mmeka 2025 §Discussion 引用. `[verified: pending]`

- **O'Kane et al. (2022)** Four-DM DFN model. Paper Mmeka 2025 §Discussion 对照.
  `[verified: pending]`

- **Kupper et al. (2018)** DFN + 电极 dry-out. Paper Mmeka 2025 §Discussion 对照.
  `[verified: pending]`

---

## §6 维护说明

### 6.1 更新触发条件

- 本工程 IC 分析 SPEC 修改 → §3 同步修改, 不动 §1, §2, §5
- §4 候选改进路径升级到 v0.6+ / v0.7+ 实施 → 把对应小节移到 `MIGRATION_NOTES.md`
  实施记录, 在本文留 "已升级" 状态标记
- 新文献发现 → 加入 §5 第二/第三类清单 + (若揭示新工程 caveat) 升级到
  `critical_review_findings::N4+`
- `[verified: pending]` 条目逐次清理 (优先级低, 不阻塞主流程)

### 6.2 R5 派生层引用关系

本文档触发的 `R5` 派生层目标 (修改本文时同步检查):

| 派生层 | 关系 | 同步动作 |
|---|---|---|
| `docs/CRITICAL_REVIEW.md` §二 N2 / N3 | 本文 §2.5 + §3.3 Item 7 触发 | 修改本文 N2/N3 内容 → CRITICAL_REVIEW 同步 |
| `docs/PARAMETERS.json::critical_review_findings::N2 / N3` | 同上 | JSON entry 严格 4 字段 (severity/summary/evidence/action) |
| `docs/CLAUDE.md` 任务路由表 | 指向本文的路由行 | 路由表 IC 相关行修改 → 本文 §1.2 cross-reference 同步 |
| `docs/MIGRATION_NOTES.md` 版本表 | v0.5.3 patch 决策记录 | 版本表追加, 不动 §二十 正文 |
| `README.md` L178 | 语义文档表格行 (UPGRADE_LITERATURE 子目录) | 扩充措辞 "含 fractional_order_RC.md / ic_analysis_methodology_review.md" |

注: README L101 (目录树) 已含 `UPGRADE_LITERATURE/`, **不需要补缺** (子阶段 0
reconnaissance 实测确认, 修正了任务包 §5.5 误诊).

### 6.3 本文与 fractional_order_RC.md 的差异

| 项 | `ic_analysis_methodology_review.md` (本文) | `fractional_order_RC.md` |
|---|---|---|
| 类型 | 学术合理性综述 + 升级路径 | 升级方向 starter pack |
| 行数 | ~400 | 171 |
| §主体 | 学术谱系 + 7 项核对 + 改进路径 | 候选模型方向 + 文献入口 |
| 触发 critical_review_findings | N2 + N3 | C7 |
| 本工程实证含量 | 高 (含 v0.5.2 实测对比) | 低 (占位 starter pack) |

二者**互补**, 都放在 `docs/UPGRADE_LITERATURE/`, 但定位不同.

---

**End of IC Analysis Methodology Review.**
