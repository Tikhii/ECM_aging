# 批判性审查：Mmeka-Dubarry-Bessler 2025 模型的已知问题与局限

**审查日期**：2026-04-20  
**审查对象**：Mmeka P O, Dubarry M, Bessler W G. *Physics-Informed Aging-Sensitive Equivalent Circuit Model for Predicting the Knee in Lithium-Ion Batteries*. J. Electrochem. Soc. 172:080538 (2025). [DOI: 10.1149/1945-7111/adf9cb](https://iopscience.iop.org/article/10.1149/1945-7111/adf9cb/meta)  
**MATLAB 源码**：[Zenodo 10.5281/zenodo.15833031](https://doi.org/10.5281/zenodo.15833031)

---

## 使用说明

本文档是对原论文和其 MATLAB 源代码的批判性审查结果。目的是：

1. **帮助 Claude Code 准确诊断**：当用户问"为什么某个参数要这样"时，Claude Code 应能引用本文档的具体条目。
2. **保护下游用户**：让任何人基于这套代码做工程化应用时，清楚知道哪些假设适用，哪些不适用。
3. **指导扩展**：如果要用到更激进的工况 (快充、低温、大容量)，明确哪些模块需要升级。

**所有发现都有对应的 `PARAMETERS.json::critical_review_findings` 条目**，便于机读检索。

---

## 一、已确认的错误（需要修正）

### E1 [HIGH] `k_SEI_cal` 在 Table Ib 的数值是 10²⁰ 量级的排版错误

**问题**：  
论文 Table Ib 报告 `k_SEI,cal = 4.2 × 10⁻²² A²·s`。

**事实**：  
MATLAB Zenodo 源码使用 `k_cal_SEI = 0.0419625`，即约 **4.2 × 10⁻²** A²·s。

**证据链**：  
1. **量纲分析**：Eq. 36 写为 `I_SEI = (1/Q_SEI) × exp(...) × [k_cal × exp(...) + k_cyc × |I·dv/dX|] × (C_NE/C_NE⁰)`。左侧是电流 [A]，`1/Q_SEI` 在 [A·s]⁻¹，所以中括号里必须是 A²·s，即 `k_cal` 单位确为 **A²·s**。
2. **前向仿真校验**：使用代码值 `0.0419625`，50% SOC 下一年日历老化 LLI 约 0.1 Ah，与论文 Fig. 4c 吻合。若用 `4.2 × 10⁻²²` 则 LLI 在一年内几乎不动。
3. **印刷错误合理性**：`10⁻²²` 很可能来自 `10⁻²` 在 LaTeX 渲染或拷贝时意外多了一个 `2`。

**严重性**：HIGH。这个错误会让任何"直接从 Table Ib 读数值做仿真"的人得到完全错误的结果。

**推荐做法**：  
- 始终以 MATLAB Zenodo 源码为准（即 0.0419625 A²·s）
- 如要引用论文值，注明："as corrected from apparent typesetting error in Table Ib"

---

### E2 [HIGH] 论文 p.10 文本把 `k_SEI,cyc` 错列入日历参数

**问题**：  
论文第 10 页正文（Calendar degradation 小节）写："calendar degradation rate constants **k_SEI,cyc**, k_LAM,PE,cal, γ_PE, R_SEI"。

**事实**：  
Table Ib 清楚地把 `k_SEI,cal` 列在日历栏，`k_SEI,cyc` 在 Table Ic 循环栏。正文里的 `k_SEI,cyc` 与表自相矛盾。

**判断**：叙述性错别字，Table 是对的。

**下游影响**：这类错误会让粗心的读者把 `k_SEI,cyc` 的拟合数据源搞错。本文档和 `PARAMETERS.json` 都以 Table 为准。

---

### S1 [LOW-MODERATE] `dX_PE_alawa` 论文 0.788 vs 代码 0.771 的 2.2% 差异

**问题**：  
论文 Table II 报告 `dX_PE_alawa = 0.788`，但 MATLAB Zenodo 源码用 `0.771`。

**最可能解释**：论文文本冻结后，作者又做了一次半电池数据的微调。两者都在 0.77–0.79 的实验合理范围内（参见 Baure-Dubarry 2019 对同款 NCR 18650B 的分析）。

**选择**：本工程使用代码值 0.771，因为这是生成论文 Fig. 6–7 的实际参数。

**下游影响**：对容量预测误差 <2%；对定性趋势几乎无影响。

---

## 二、已知的简化假设（有明确作用域）

以下假设都是论文作者**主动做出的建模选择**。对 Panasonic NCR 18650B 的 DST 老化数据，这些假设是合理的。但外推到其他场景时需要审视。

### S2 [MODERATE] `V_LP_eq = 0 V` 的静态镀锂起始电位

**问题**：  
论文把镀锂平衡电位 $V_\text{LP}^\text{eq}$ 固定为 0 V (vs Li⁺/Li)，独立于温度、C-rate、Li⁺ 浓度。

**文献依据**（同一高级作者的最新工作！）：  
Beck, Greszta, Roberts, Dubarry 2024. *Improved Mechanistic Degradation Modes Modeling of Lithium and Sodium Plating*. Batteries **10**(12):408. [DOI: 10.3390/batteries10120408](https://doi.org/10.3390/batteries10120408)

Beck 等明确指出：

> "Typical testing and modeling assume that plating occurs at 0 V when measured against the charge carrier. While this might be true under thermodynamic equilibrium, **this is not true outside of steady state**."

Beck 2024 提出了 C-rate 和温度耦合的动态 $V_\text{LP}^\text{eq}$ 修正。这是 Dubarry 课题组自己在 2024 年发表的方法学改进。

**Mmeka 论文对 Beck 2024 的响应**：似乎未引用此修正。

**作用域限制**：
- ✅ 适用于 Baure-Dubarry 2019 的实验条件（25°C 环境，≤1C 循环，4.2V 截止）
- ❌ 不适用于：快充 (>1C)、低温 (<15°C)、高倍率放电的 knee 预测

**代码 TODO 标记**：`aging_kinetics.py::PlatingParameters` 和 `panasonic_ncr18650b.py` 都已加警告注释。

**升级路径**：  
```python
# 目标接口
PlatingParameters(
    k_LP=2.33e-4,
    V_LP_eq=lambda T, c_Li: beck_2024_dynamic_onset(T, c_Li),  # 扩展接口
)
```

---

### S3 [LOW-MODERATE] 只有 SEI 有 Arrhenius，其他过程无温度依赖

**问题**：  
在 MATLAB 源码中，Arrhenius 因子 `exp(-Ea/R × (1/T - 1/T_ref))` 只出现在 SEI 速率（Eq. 36）里。Plating (Eq. 39)、LAM_PE (Eq. 40)、LAM_NE (Eq. 41) 没有温度依赖项。

**影响**：  
- 在等温测试条件下完全没问题
- 在温度范围扩展时：
  - 镀锂在低温下会更严重（动力学慢，过电位放大）—— 模型不会捕捉
  - PE/NE 结构退化有温度依赖（Si、NCA 的 phase transition 与温度相关）—— 模型不会捕捉

**代码位置**：`aging_kinetics.py::PlatingParameters`, `LAMParameters` 都没有 `Ea` 字段。

**升级路径**：  
为所有三类参数都加 `Ea` 字段，文献典型值：
- Plating: Ea ≈ 25–40 kJ/mol（较 SEI 低，因为动力学受限）
- LAM_PE (NCA 高 V): Ea ≈ 40–60 kJ/mol
- LAM_NE (石墨): 通常与循环 stress 主导，温度依赖较弱

---

### C1 [MODERATE] 等温假设

**问题**：模型假设 `T = T_ambient = const`，无热耦合。

**实际情况**：  
Ren et al. 2024 (J. Power Sources) 等表明：**DST 循环在 18650 电池中可产生 5–10 K 的瞬态温升**。在 $E_a = 55.5$ kJ/mol 时，10 K 温升可使 SEI 速率加速 1.8×。

**作用域限制**：
- ✅ 小型单体 (18650, pouch < 10 Ah) 在带温控的测试箱中
- ❌ 大容量电池组 (> 30 Ah)、无温控的真实车辆工况

**升级路径**：  
加入简单的 lumped 热模型：$c_p m \, dT/dt = I^2 R - h A (T - T_\text{env})$。需要：
- $c_p$ (比热容)、$m$ (质量)：datasheet 或测量
- $hA$ (热散射系数)：从热稳态测量拟合

---

### C2 [MODERATE (general) / LOW (this cell)] `max(0, BV)` 的不可逆镀锂

**问题**：模型把 Butler-Volmer 的负半边截断（即镀锂反应不可逆，不考虑剥离）。

**文献对比**：  
- O'Kane et al. 2022 (Phys. Chem. Chem. Phys. 24:7909, PyBaMM 基础) 实现了**双向镀锂 + 死锂衰减率**。
- Baure-Dubarry 2019 在同款 NCR 18650B 上**实验观测到没有镀锂剥离**：  
  > "lithium plating was completely irreversible, as evidenced by the absence of additional electrochemical features in the voltage response during discharge"

**结论**：对本模型所针对的电池和工况，单向镀锂是合理的经验近似。但不能直接外推到：
- 快充测试（镀锂常常部分可逆）
- 高 SOC 储存（可能有"化学剥离"即 Li + electrolyte → SEI）

---

### C3 [MODERATE] `R_s` 不退化假设

**问题**：模型假设 $f_{R,s} \equiv 1$（即串联电阻不随老化变化）。

**Post-mortem 文献**：  
- Stiaszny et al. 2014 (J. Power Sources 251:439)：商用 18650 老化后 $R_s$ 增长 10–30%
- 近期 2025 J. Power Sources 814-cell 分析同样确认此趋势

**来源**：电解液分解、集流体/活性材料接触损失、粘结剂退化。

**对模型的影响**：  
- 早期（C < 10% 衰减）：影响可忽略
- 末期（临近 knee 或 knee 后）：低估 NE 极化 10–30%，可能**延后预测的 knee 出现时机**

**代码 TODO 标记**：已加到 `ResistanceAgingParameters`。

**升级路径**：  
```python
# 目标
f_R_s = 1.0 + alpha_Rs_SEI * (Q_SEI - Q_SEI_0) + alpha_Rs_LAM * Q_LAM
```
需要从长周期老化数据拟合 `alpha_Rs_*`。

---

### C4 [MODERATE at high V] `LLI_PE = 0`：忽略 PE 侧锂库存损失

**问题**：模型假设正极侧没有锂库存损失（`Q_LLI_PE = 0` 始终）。

**文献**：  
- Zülke et al. 2021 (Batt. Supercaps)：NCA 电池在 >4.2 V 时有 CEI 生长
- Sun group 2019 (ACS Energy Lett.)：NCA 微裂纹暴露新表面导致 CEI 持续生长

**作用域**：
- ✅ $V_\text{max} \leq 4.2$ V 且温度 ≤ 35 °C 的中周期
- ❌ $V_\text{max} > 4.25$ V、高温存储、接近 EOL 的末期

---

### C5 [MODERATE] `|dv/dX|` 作为机械退化代理的局限

**问题**：LAM 速率中用 `|I · dv/dX|` 代表机械应力。这只捕捉了"扩散诱导应力"的一部分。

**遗漏的物理**：
- C-rate 直接影响浓度梯度（只有 `|I × dv/dX|` 线性依赖，真实应力可能是 $I^{1.5}$）
- 相变诱导应力（NCA 的 H2–H3 转变、石墨的 stage transition）：很难用单峰值代替
- 疲劳累积（Ai et al. 2022, J. Power Sources 544:231805）：需要显式的历史变量

**对当前模型的影响**：单次拟合参数 $k_\text{LAM,cyc}, \gamma$ 已经吸收了大部分这些效应的等效表现，但外推到新化学体系时要小心。

---

### C6 [LOW (scoped) / MODERATE (generalized)] knee 机理属性

**问题**：  
Mmeka 论文只实现了**一种 knee 机理**：镀锂-电阻正反馈。

**文献综述**（Attia et al. 2022, J. Electrochem. Soc. 169:060517）：至少有 **6 种公认的 knee 通路**：
1. 镀锂触发 (本模型)
2. 电极饱和 (负极锂位点耗尽)
3. 电阻增长超阈值
4. 电解液/添加剂耗竭
5. 连通性 percolation
6. 机械形变

**判断**：对 NCR 18650B 在 DST 下，镀锂通路是主导的（有 Baure-Dubarry 2019 的观测支持）。**但不要把此模型推广成"通用 knee 预测器"**，除非能先确认目标电池的 knee 机理属于同一类。

---

### C7 [MODERATE for long pulses / low T, LOW for short pulses near room T] RC 拓扑对长弛豫的不足

**问题**：
论文 (Mmeka 2025) 与 FIT-2 中使用的两段 RC (R1‖C1) - (R2‖C2) 串联拓扑只能精确
表示两个集中时间常数 tau1, tau2。但实测在 ≥100 s 量级的弛豫窗口里, 残差常呈
系统性结构 (慢段拖尾、固相扩散主导项), 双指数模型无法充分捕获。FIT-3 的
`known_limitation` 字段已注明 RMSE 30-50 mV 的下限来自此源。

**遗漏的物理**：
- 固相扩散 (Warburg-like ω^{-1/2} 阻抗) 对应分布式时间常数, 集中 RC 必失真
- 多孔电极内部分布式 RC ladder
- 双层电容受 SOC / SOH 的弱依赖被强行吸收进 lumped C_i
- 低温下离子迁移变慢, 时间常数显著拉长且分布展宽, 双指数偏差放大

**证据**：
- 论文 Fig. 3d 在 ~250 s 电压阶跃下 RC ladder 跟不上的现象
- FIT-2 实测残差结构 (本工程 v0.5.0 实施过程中收集)
- 文献中 fractional-order ECM / Constant Phase Element / Mittag-Leffler 弛豫 /
  DRT (Distribution of Relaxation Times) 已被多次提议为长尾弛豫的更适配描述

**判断**：
保留两段 RC 作为缺省机制 (室温短脉冲下足够), 但暴露质量信号:
- FIT2-W001 在 marginal 区间触发, 提示数据/模型边界
- FIT2-E003 在 fail 区间拒绝写回, 防止劣质拟合污染下游
- `relaxation_fitting.py` 已为升级预留 `RELAXATION_MODELS` 字典与
  `--relaxation-model` CLI 入口, 当前仅 `two_exponential`

**升级路径**：
见 `docs/UPGRADE_LITERATURE/fractional_order_RC.md`。短期评估分数阶 RC (CPE) +
Mittag-Leffler 弛豫的实用性, 中长期可考虑 DRT 反问题方法。引入新模型必须保留
`two_exponential` 作为兼容回退, 且 fit_report 需注明所选模型。

---

### C_X_LAM [LOW] `X_LAM = 0` 约定

**问题**：论文假设"失去的活性材料是完全脱锂态"（Li 含量 = 0）。

**文献依据**：这是 alawa 框架的标准约定（Dubarry-Truchot-Liaw 2012）。识别性研究（Lin & Khoo 2024）表明全电池 OCV 对"失去时的锂态"的敏感性很弱。

**判断**：可接受的简化，无需修正。

---

### N1 [MODERATE] LR 与 OFS 在 V_cell(SOC) 上的共线性

**问题**：
LR 和 OFS 在 V_cell(SOC) 数据上存在强共线性。OFS 仅通过 (1 - OFS/100) 因子
影响 X_PE 的 SOC 范围, 这可被 LR 对 X_NE 范围的调整反向补偿。OFS 的独立可
识别性依赖半电池 OCV 在特定 X 值附近的局部特征 (stage transitions, dV/dX 极值),
要求 EXP-A 数据 SOC 覆盖到这些特征点。

**证据**：
v0.4.0 FIT-1 实施过程中, 100 点均匀采样的合成数据上, LR 反演相对误差 0.04%,
OFS 反演相对误差 3.8%。真实 EXP-A 数据可能因为 stage transition 附近自然采样
更密而表现更好, 但未验证。

**判断**：
记录现象。FIT-1 工作流上, 若 OFS uncertainty 偏大, 考虑 `--fix-OFS` 选项
(待 v0.4.x 实施) 把 OFS 固定到 datasheet 或 alawa 默认值, 只拟合 LR。

---

### N2 [MODERATE] pseudo-OCV 残留 IR 与 hysteresis 偏移 (Marinescu phantom)

学术界 IC / DMA 实践中, pseudo-OCV (实际 C/40 测量) 不是真正的 OCV — 它残留两类 non-degradation 贡献:

1. **SOC-dependent ohmic IR drop**: 即使在 C/40 这样低的 C-rate 下, 半电池及电解质仍贡献量级在 tens of millivolts 的 IR offset, 且 SOC 依赖
2. **Intrinsic charge-discharge hysteresis**: graphite-SiOx (C/SiOx) 体系尤其严重, 纯 graphite 较弱但仍存在, NCA/NMC 系 PE 也有较小贡献

NLS V(Q) 拟合会把这些 non-degradation 贡献误归到 (LLI, LAM_PE, LAM_NE) DMs, 产生 phantom degradation。

**实证**: Asheruddin et al. (2025) arXiv:2512.19773 (Imperial College London, Marinescu PI) 实测两款商用 21700 cells:
- LG M50T (高内阻): 不做 IR 校正会**抑制** PE-LAM 与 LLI 反演, 同时**夸大** apparent graphite loss (反直觉但严重的 attribution bias)
- Molicel P45B (低内阻): hysteresis 与 voltage-windowing 主导 charge-discharge branch 之间的 inferred Si loss 差异

**本工程影响**: 主体系 NCA/G (SiOx hysteresis 不存在, graphite hysteresis + IR 残留仍存在). v0.5.2 实测未暴露 phantom-driven misattribution, 但**未做跨化学体系 stress test**。

**当前处理**: 通过 `fit_quality` RMSE 阈值 (20/15 mV) 间接吸收 — RMSE > 15 mV 触发 `ICA-W001`, 下游 (FIT-4a/4b) 看到 warning 后会降权重消费. **无显式 IR 校正逻辑**。

**升级路径**: v0.6+ 候选改进, 详见 `docs/UPGRADE_LITERATURE/ic_analysis_methodology_review.md` §4.1 (引入可选 `--ir-correction` 参数, 接受 R_Omega(SOC) LUT 输入)。

### N3 [MODERATE] sum(DMs) ≠ cap_loss 非线性关系 (跨化学体系普遍现象)

学术界跨化学体系 (NCA/G, NMC/G, LFP/G, NCA/G+Si, ...) IC analysis 实践中, 普遍观察到 sum(LLI + LAM_PE + LAM_NE) ≠ cap_loss, 这不是计算错误而是物理现象:

**物理原因**: LAM 损失可被未使用的 SOC 范围部分吸收 (电极 SOC 窗口耦合非线性). 即, 当 PE / NE 损失的 active material 处于 cell 实际 cycling 不触及的 stoichiometry 区间时, 它不直接贡献到 cell capacity 损失。

**实证**:
- **Mmeka 2025 paper Fig. 6c** (本工程主 paper §"Cycle degradation"): 143 EFC calibration sum=0.25 / cap_loss=0.11 / ratio = 2.27
- **本工程 v0.5.2 子阶段 4 实测**: cycle ratio 1.66 / 2.29 / 2.97 (light / moderate / severe), 与 paper 同量级且非线性递增
- **Dubarry & Anseán (2022)** *Front. Energy Res.* 10:1023555 §best practices 跨多化学体系系统讨论此现象

**本工程影响 (T4 测试改写)**: v0.4 → v0.5.2 升级中, T4 cap_loss self-consistency 测试由 sum 守恒 (Birkl 2017 风格) 改为 forward 物理一致性验证: 给定 (LLI, LAM_PE, LAM_NE), 用 forward model 计算 cap_loss(LLI, LAM_PE, LAM_NE), 与 ground truth cap_loss 比对。详见 `docs/MIGRATION_NOTES.md` §20.6 完整决策记录。

**工程意义 (FIT-4a/4b 消费 IC 输出时必须遵守)**: 拟合 LLI / LAM 时**不能假设 sum 守恒**。DMs 时间序列与 cap_loss 时间序列应**各自独立拟合**, 不通过 sum constraint 联系。

**升级路径**: 本现象不需要 fix (是物理事实), 仅需 FIT-4 series 消费时正确遵守。详见 `docs/UPGRADE_LITERATURE/ic_analysis_methodology_review.md` §3.3 Item 7。

## 三、作用域卡片（给下游使用者）

当你实例化 `create_panasonic_ncr18650b()` 时，请默认以下前提：

| 条件 | 允许范围 |
| --- | --- |
| 电池体系 | NCA / 石墨（类似 18650 NCR 系列） |
| 环境温度 | 20 – 35 °C |
| 充电 C-rate | ≤ 1C（快充未验证） |
| 放电 C-rate | ≤ 2C（典型 DST 峰值） |
| 充电上限电压 | ≤ 4.2 V |
| 镀锂状态 | 不可逆镀锂主导（快充可逆镀锂未实现） |
| 温度耦合 | 无（等温，小电池低 C-rate OK） |
| 老化阶段 | ≥ 80% SOH 有较高置信度；< 70% SOH 预测不确定度显著上升 |

**对新场景的升级提示**：

- **快充应用** → 必须升级 S2（动态 V_LP_eq，Beck 2024）+ S3（plating 的 Arrhenius）
- **低温应用** → S2 + S3 + C3（R_s 动力学受限在低温下更显著）
- **大容量电池组** → 必加 C1（热耦合）
- **EV 长寿命预测** → 加 C3（R_s 退化）+ C4（LLI_PE，若使用高 V）
- **Si 复合负极** → C5（更强的机械模型）

---

## 四、参考文献汇总

核心参考（本审查的证据链）：

1. **Mmeka, Dubarry, Bessler 2025** — 本次审查的主论文  
   J. Electrochem. Soc. 172:080538. DOI: [10.1149/1945-7111/adf9cb](https://iopscience.iop.org/article/10.1149/1945-7111/adf9cb/meta)

2. **Beck, Greszta, Roberts, Dubarry 2024** — 最重要的对照基准（同作者的修正）  
   *Improved Mechanistic Degradation Modes Modeling of Lithium and Sodium Plating*. Batteries 10(12):408.  
   DOI: [10.3390/batteries10120408](https://doi.org/10.3390/batteries10120408)

3. **Baure, Dubarry 2019** — 实验数据源  
   *Synthetic vs Real Driving Cycles: A Comparison of Electric Vehicle Battery Degradation*. Batteries 5:42.  
   DOI: [10.3390/batteries5020042](https://doi.org/10.3390/batteries5020042)

4. **Devie, Dubarry 2016** — alawa 框架基础  
   Batteries 2:28. DOI: [10.3390/batteries2030028](https://doi.org/10.3390/batteries2030028)

5. **Attia et al. 2022** — knee 机制综述  
   J. Electrochem. Soc. 169:060517. DOI: [10.1149/1945-7111/ac6d13](https://doi.org/10.1149/1945-7111/ac6d13)

6. **Reniers, Mulder, Howey 2019** — 日历老化参数基础  
   J. Electrochem. Soc. 166:A3189. DOI: [10.1149/2.0281914jes](https://doi.org/10.1149/2.0281914jes)

7. **Yang et al. 2017** — 镀锂-SEI 正反馈机理的开创  
   J. Power Sources 360:28. DOI: [10.1016/j.jpowsour.2017.05.110](https://doi.org/10.1016/j.jpowsour.2017.05.110)

8. **O'Kane et al. 2022** — 双向镀锂实现的参考  
   Phys. Chem. Chem. Phys. 24:7909. DOI: [10.1039/D2CP00417H](https://doi.org/10.1039/D2CP00417H)

9. **Lin et al. 2013** — 摩尔体积数据源  
   J. Electrochem. Soc. 160:A1701. DOI: [10.1149/2.040310jes](https://doi.org/10.1149/2.040310jes)

10. **Stiaszny et al. 2014** — post-mortem R_s 退化证据  
    J. Power Sources 251:439. DOI: [10.1016/j.jpowsour.2013.11.080](https://doi.org/10.1016/j.jpowsour.2013.11.080)

---

## 五、对 Claude Code 的操作指令

当用户问以下类型的问题时，Claude Code 应引用本文档：

| 问题模式 | 引用本文档的哪一节 |
| --- | --- |
| "为什么 k_SEI_cal 是 0.04 不是 10⁻²²" | § E1 |
| "V_LP_eq=0 合理吗" | § S2 |
| "能预测快充下的 knee 吗" | § S2 + § 三作用域卡片 |
| "为什么 R_s 不退化" | § C3 |
| "能不能用于大电池组" | § C1 + § 三作用域卡片 |
| "这模型能解释所有 knee 吗" | § C6 |
| "新体系怎么扩展" | § 三升级路径 |
| "OFS 拟合不准 / LR OFS 共线" | § N1 |
| "RC 暂态拟合 RMSE 持续高 / 残差系统性" | § C7 + UPGRADE_LITERATURE/fractional_order_RC.md |

当用户提出"代码里为什么是这个值"时，Claude Code 应：

1. 先查 `docs/PARAMETERS.json` 里该参数的 `paper_errata` 字段
2. 若有对应 errata，再引用本文档的详细解释
3. 若没有（说明是正常参数），直接从 JSON entry 回答

---

## 版本记录

| 日期 | 变更 |
| --- | --- |
| 2026-04-20 | 初版。12 条 findings (E1-E2, S1-S3, C1-C6, C_X_LAM) 全部记录。与 `PARAMETERS.json v2.0` 配套。 |
| 2026-04-25 | 新增 N1 (LR/OFS 共线性)。v0.4.0 FIT-1 实施中发现, 详见 MIGRATION_NOTES §十五。 |
| 2026-04-26 | 新增 C7 (RC 拓扑对长弛豫的不足)。v0.5.0 FIT-2 实施中暴露的 RMSE 下限来源, 升级路径见 docs/UPGRADE_LITERATURE/fractional_order_RC.md, 详见 MIGRATION_NOTES §十八。 |
