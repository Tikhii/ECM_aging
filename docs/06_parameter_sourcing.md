# 06 · 模型参数来源梳理与新体系实验设计（LFP-Gr 案例）

本文档彻底回答三个问题：

1. **每一个模型参数到底怎么来的？** —— 实验直测？从测量数据拟合？文献查得？作者经验？
2. **这些参数需要什么样的实验？** —— 从最简单的 C/20 放电到复杂的半电池 GITT，逐个对应。
3. **面对一个新的电池体系（本例 LFP/石墨），完整的实验-拟合流程长什么样？** —— 给出可执行的实验表 + 拟合脚本框架。

读完后你会有一份清晰的"数据需求清单"和"实验 → 代码字段"的映射表。

---

## 0. 先看总表

所有模型参数按"获取难度 / 所需实验复杂度"分四级：

| 级别 | 获取方式 | 参数数 | 代表参数 | 所需实验 |
| --- | --- | --- | --- | --- |
| **Ⅰ. 直测** | 实验直接读数 | ~5 | 名义容量 $C^0$, $V_\text{max}$, $V_\text{min}$ | 简单标准充放电 |
| **Ⅱ. 从测量数据插值** | 构建查找表 | ~4 (LUT) | 半电池 OCV $V^0(X)$, 电阻 $R(I, X)$ | 半电池测试 + GITT/pulse |
| **Ⅲ. 参数化拟合** | 从测量数据通过拟合得到少量常数 | ~3 | 电极平衡 LR / OFS, RC 时间常数 $\tau_1, \tau_2$ | 全电池 OCV + 瞬态响应 |
| **Ⅳ. 老化参数辨识** | 从长时间老化实验数据反推 | ~10 | $k_\text{SEI,cal}$, $k_\text{LP}$, $\gamma_\text{PE}$ 等 | 日历 + 循环老化实验 + 增量容量分析 |

---

## 1. Ⅰ 级参数 — 直接测量

### 1.1 标称容量 $C^0$

**论文值**：3.35 Ah（Panasonic datasheet 标称）

**代码字段**：`panasonic_ncr18650b.py` 中 `C0_PE` 计算行里的 `3.35` 常数

**实验方法**：
- C/20 或 C/40 恒流放电，从 $V_\text{max}$ 放到 $V_\text{min}$
- 记录总电荷量 $\int I \, dt$ 即为 $C^0$（单位 Ah）
- 可重复 3 次取均值，误差通常 < 1%

**为什么不能更高速率**：高 C-rate 放电会有明显内阻压降，测得的"容量"偏小，不代表电极真实可容纳的锂量。

### 1.2 工作电压窗口 $V_\text{max}, V_\text{min}$

**论文值**：4.2 V / 2.5 V（典型 NCA/G 电池）

**代码字段**：`aging_V_max`, `aging_V_min`

**实验方法**：直接从 datasheet 或你的测试协议设定值读取，不需测量。

### 1.3 CV 截止电流 $I_\text{cutoff}$

**论文值**：0.065 A（约 C/50）

**代码字段**：在 `figure7_simulation.py` 中是用户选定的协议参数，不在 cell 对象内

**实验方法**：是测试人员选定的阈值，通常取 C/20 到 C/50。

### 1.4 初始化学计量 $X^0_\text{PE}, X^0_\text{NE}$

**论文值**：$X^0_\text{PE} = 0.95$, $X^0_\text{NE} = 0.01$

**代码字段**：`aging_X0_PE`, `aging_X0_NE`

**实验方法**：这是"新电池满放电状态时 PE/NE 各自剩余多少锂"的定义。**严格来说不是实验直测，而是约定**：
- 新电池做一次 C/40 完整放电到 $V_\text{min}$
- 此时定义 PE 处于"满嵌锂状态"（X_PE ≈ 0.95，因 NCA 材料 X 只能在 0.17–0.95 间变化）
- 相应 NE 处于"几乎全脱锂"（X_NE ≈ 0.01，因石墨 X 在 0.01–0.97 间变化）

通过半电池实验（后面 §2.1）可以校验这个约定是否合理。

---

## 2. Ⅱ 级参数 — 测量数据直接做查找表

这一级涉及**两类测量**：半电池测试（获得 OCV 曲线）和脉冲/GITT 测试（获得电阻 map）。

### 2.1 半电池 OCV 曲线 $V^0_\text{PE}(X)$, $V^0_\text{NE}(X)$

**论文值**：存在 `GraphiteAlawa.dat` 和 `NCAAlawa.dat`；格式是 (X, dH, dS) 三列

**代码字段**：由 `HalfCellThermo.from_dat_file()` 加载，`open_circuit_voltage()` 调用

#### 2.1.1 实验设计

最标准的做法是**三电极半电池**（half-cell）：

```
     [待测电极] —— [电解液 + 隔膜] —— [锂金属参比/对电极]
```

1. **取待测电极材料**：从商业电池拆出极片（需做干燥处理），或用自己涂的电极片
2. **组装 CR2032 扣式半电池**：
   - 工作电极：待测 PE 或 NE 极片（~14 mm 圆片）
   - 对电极 / 参比电极：锂金属箔
   - 电解液：与目标全电池一致（通常 1 M LiPF6 in EC:DMC 1:1）
3. **化成（formation）**：C/10 循环 2–3 次，稳定 SEI
4. **C/40 完整充放电**：
   - 石墨侧：0.005–1.5 V vs Li（或更保守 0.01–1.2 V）
   - NCA 侧：3.0–4.3 V vs Li
   - 每 0.01 Ah 记录一个电压点
5. **处理数据**：取**放电支**（或充放电平均）作为 $V^0(X)$ —— 这假设 C/40 已经接近准静态

#### 2.1.2 转换成 alawa 格式

```python
import numpy as np
import pandas as pd

F = 96485  # C/mol
data = pd.read_csv('my_graphite_C40_discharge.csv')  # columns: Ah, V_vs_Li

Q_max = data['Ah'].max()              # 完全嵌锂总电荷
X = 1 - data['Ah'] / Q_max            # 约定: X=1 对应满嵌锂 (放电前)
V = data['V_vs_Li']

dH = -V * F                           # [J/mol],  V^0 = -dH/F
dS = np.zeros_like(dH)                # 等温假设, dS 置 0

with open('libquiv_aging/data/MyGraphiteAlawa.dat', 'w') as f:
    f.write("* Electrode material: My Graphite\n")
    f.write("* Source: my C/40 half-cell test on 2026-xx-xx\n")
    f.write("* x []\tdH [J/mol]\tdS [J/mol/K]\n")
    for x, h, s in zip(X, dH, dS):
        f.write(f"{x:.7f}\t{h:.3f}\t{s:.6f}\n")
```

#### 2.1.3 无条件做半电池时的替代方案

如果没有半电池测试条件：

1. **文献查询**：Karthikeyan 2008（NCA）、Safari 2011（石墨）等文献给出了通用曲线
2. **从全电池反推**：结合全电池 OCV + 已知一个电极的 OCV → 反推另一个电极（复杂且易出错）
3. **直接用本工程的 NCA/Graphite 数据**：若你的体系也是 NCA/G 或 NMC/G（前者 OCV 形状接近），定性分析可以复用

---

### 2.2 电阻二维查找表 $R_s(I)$, $R_\text{NE}(I, X)$, $R_\text{PE}(I, X)$

**论文值**：存在 `ResistancesAlawa.mat` 里，三个 1001×2001 的矩阵

**代码字段**：`ResistanceLUTs.from_mat_file()`

#### 2.2.1 实验设计：GITT（Galvanostatic Intermittent Titration Technique）

GITT 是最直接测量"电阻 vs SOC vs 电流"的方法：

1. **把全电池或半电池充到满电**
2. **施加一个电流脉冲**（如 C/5，持续 10 分钟）→ 测得瞬时电压跳变 $\Delta V$
3. **静置 1–2 小时**让电池松弛回 OCV
4. **从电压跳变算阻抗**：$R \approx \Delta V / I$
5. **重复**：改变 SOC（例如按 10% 间隔）、改变电流（例如 C/10, C/5, C/2, 1C）

这样可以得到一个稀疏的 $(I, \text{SOC}, R)$ 数据集。

#### 2.2.2 从稀疏 GITT 数据生成 alawa 格式

```python
import numpy as np
from scipy.io import savemat
from scipy.interpolate import RegularGridInterpolator

# 你的 GITT 数据: SOC × C-rate 网格, 每格一个 R_total 值
SOC_samples = np.array([0.1, 0.3, 0.5, 0.7, 0.9])          # 5 个 SOC 点
I_samples   = np.array([-2, -1, -0.5, 0.5, 1, 2])          # 6 个电流 (A)
CN_Ah = 3.0
C_rate_samples = I_samples / CN_Ah

# 假设测到的全电池总电阻 (需要进一步把 PE/NE/Rs 分开, 见下一节)
R_total = np.array([
    [0.045, 0.042, 0.040, 0.040, 0.043, 0.048],   # SOC=10%
    [0.038, 0.036, 0.034, 0.034, 0.037, 0.041],   # SOC=30%
    [0.035, 0.033, 0.032, 0.032, 0.034, 0.038],   # SOC=50%
    [0.037, 0.035, 0.033, 0.033, 0.036, 0.040],   # SOC=70%
    [0.046, 0.043, 0.041, 0.041, 0.044, 0.049],   # SOC=90%
])  # 单位 Ω

# 插值到 alawa 的 1001 × 2001 网格
interp = RegularGridInterpolator(
    (SOC_samples, C_rate_samples), R_total,
    bounds_error=False, fill_value=None
)
SOC_grid = np.linspace(0, 1, 1001)
C_rate_grid = np.linspace(-4, 4, 2001)
SS, CC = np.meshgrid(SOC_grid, C_rate_grid, indexing='ij')
points = np.stack([SS.ravel(), CC.ravel()], axis=-1)
R_full = interp(points).reshape(1001, 2001) * CN_Ah  # 注意要乘 CN_Ah 存入

# 保存
savemat('my_R.mat', {
    'RsAlawa':  np.full_like(R_full, 0.010 * CN_Ah),  # 简化: Rs 常数
    'RNEAlawa': R_full * 0.6,                          # 简化: NE 占 60%
    'RPEAlawa': R_full * 0.4,                          # 简化: PE 占 40%
})
```

#### 2.2.3 R_NE, R_PE, R_s 的分配问题

**这是个难题**：全电池测得的是 $R_\text{total} = R_s + R_\text{NE} + R_\text{PE}$，怎么分成三部分？

**论文的做法**：从 alawa 框架的**半电池 GITT 数据**直接得到 $R_\text{NE}(I,X)$ 和 $R_\text{PE}(I,X)$，$R_s$ 由 EIS 的高频实部给出。详见论文 Ref. 13 (Devie & Dubarry 2016)。

**没有半电池 GITT 时的简化**：
1. **EIS 分层**：做一次 EIS，高频实轴截距 = $R_s$；第一个半圆 = NE 的 $R_\text{NE}^\text{dyn}$；第二个半圆 = PE 的 $R_\text{PE}^\text{dyn}$
2. **按经验比例分**：文献中 NCA/G 的 R_NE : R_PE 通常在 5:3 到 3:2 之间
3. **模型容错性高**：即使分配不完美，ECM 的总响应仍然对就行（只是内部的 V_NE 会有偏差，影响老化率准确性）

---

## 3. Ⅲ 级参数 — 从测量数据做轻度拟合

这类参数需要的不是简单读数，但拟合对象只是 1–2 个标量，非常稳定。

### 3.1 电极平衡参数 LR 和 OFS

**论文值**：$\text{LR} = 1.04$, $\text{OFS} = 2.0 \%$

**代码字段**：`panasonic_ncr18650b.py` 中的 `LR = 1.04`, `OFS = 2.0`

**物理意义**：
- **LR (Loading Ratio)** = $C_\text{NE} / C_\text{PE}$（alawa 定义下 NE 容量 / PE 容量）
- **OFS (Offset)** = 新电池成形后已被 SEI 吃掉的锂占 PE 可循环容量的百分比

**获取方法**：
1. 测全电池的 C/40 OCV 曲线 $V_\text{cell}(\text{SOC})$
2. 从 §2.1 得到半电池 OCV $V^0_\text{PE}(X_\text{PE})$ 和 $V^0_\text{NE}(X_\text{NE})$
3. 在数学上，通过两个自由参数 LR 和 OFS 把两个半电池曲线"对齐"到全电池曲线：
   $$
   V_\text{cell}(\text{SOC}) = V^0_\text{PE}(X_\text{PE}(\text{SOC}; \text{LR, OFS})) - V^0_\text{NE}(X_\text{NE}(\text{SOC}; \text{LR, OFS}))
   $$
4. 用 `scipy.optimize.minimize` 拟合 LR 和 OFS

这是 alawa 框架的核心；论文 Ref. 13 详细描述了这个拟合。

#### 3.1.1 一个简化的 Python 拟合示例

```python
from scipy.optimize import minimize
import numpy as np

# 假设你已经有:
V_cell_exp, SOC_exp = ...           # 全电池 C/40 数据
V0_PE = lambda X: ...                # 来自你的 NCA 半电池 dat
V0_NE = lambda X: ...                # 来自你的 Graphite 半电池 dat

dX_PE = 0.77                         # 你的 PE 可循环范围 (从半电池读)
dX_NE = 0.96                         # 你的 NE 可循环范围

def V_cell_model(SOC, LR, OFS):
    # X_PE 随 SOC 从 X0_PE 线性减到 X0_PE - dX_PE
    X_PE = 0.95 - SOC * dX_PE * (1 - OFS/100)
    X_NE = 0.01 + SOC * dX_NE * LR * dX_PE / dX_NE
    return V0_PE(X_PE) - V0_NE(X_NE)

def loss(params):
    LR, OFS = params
    V_model = np.array([V_cell_model(s, LR, OFS) for s in SOC_exp])
    return np.sum((V_model - V_cell_exp)**2)

res = minimize(loss, x0=[1.0, 2.0], method='Nelder-Mead')
LR_fit, OFS_fit = res.x
print(f"拟合结果: LR = {LR_fit:.3f}, OFS = {OFS_fit:.2f}%")
```

---

### 3.2 RC 电容 $C_1, C_2$（动力学时间常数）

**论文值**：$C_1 = 949.28$ F (NE), $C_2 = 3576.07$ F (PE)

**代码字段**：`panasonic_ncr18650b.py` 中的 `C1=949.28, C2=3576.07`

**物理意义**：RC 元件捕捉"电流变化后电压慢慢弛豫"的动力学。时间常数 $\tau = R \cdot C$ 决定弛豫快慢。

**获取方法 —— 阶跃响应拟合**：

1. **让电池先静置**（例如 2 h，保证起点稳态）
2. **突加一个恒流**（如 C/2 放电 10 分钟）
3. **突然断开**，继续静置 1–2 h
4. **测 OCV 弛豫曲线** $V(t)$

理论上松弛曲线是两段指数衰减（NE 和 PE 各一个）：
$$
V(t) = V_\infty + A_1 e^{-t/\tau_1} + A_2 e^{-t/\tau_2}
$$

用 `scipy.optimize.curve_fit` 拟合出 $\tau_1, \tau_2$。已知 $R_1, R_2$ 后反推：
$$
C_i = \tau_i / R_i
$$

#### 3.2.1 简化情况

如果你不在意动力学精度（只关心容量和长期老化），可以直接沿用 Panasonic 的值——**这对总电压的稳态预测影响小于 5%**。本工程的 15 个测试里没有一个依赖 RC 电容精确值。

---

### 3.3 resistance "fraction" 分配 (fractionR1toRs 等)

**论文值**：两个都为 0.5。**注意**：这个 0.5 不是"未调过的默认值"，而是论文针对 Panasonic NCR18650B 的 FIT 结果（见 `PARAMETERS.json::parameters::fractionR1toRs::notes`：
> "Despite the 0.5 value looking like a default, it is in fact a FIT RESULT for this specific cell."

新体系不能假定 0.5 仍然适用，应重新走 FIT-3。

**物理意义**：把 R-RC 元件中的 R 劈一部分给串联 Rs，其余留给 RC-R（动态部分）。这是**经验劈分因子**，用来让动态电压响应更贴合实测。

**获取方法**：属于 FIT-3（电阻分配）。**数据来源是 EXP-D 的 DST 首循环**（`experiments/EXP-D/cell_01_dst_firstcycle.csv`），不是 EXP-C 阶跃。完整流程（粗扫 → 精扫、验收标准、已知 RC 模型限制）见 `PARAMETER_SOP.md §SOP-3::FIT-3`。

**如果没数据**：沿用论文的 0.5 / 0.5 作 placeholder，稳态误差可接受，但须在参数工厂处加 TODO。

---

## 4. Ⅳ 级参数 — 老化速率常数（最难）

这是整个模型最难参数化的部分。论文里这组参数都**通过老化实验 + 手动拟合**得到的。没有任何办法从"一天就能做完的实验"里得到这些值。

### 4.1 参数清单

| 参数 | 论文值 | 含义 | 对应公式 |
| --- | --- | --- | --- |
| $E_a$ | 55500 J/mol | SEI Arrhenius 激活能 | (36) |
| $k_\text{SEI,cal}$ | 0.0420 | 日历 SEI 速率常数 | (36) |
| $k_\text{SEI,cyc}$ | 0.470 | 循环 SEI 速率常数 | (36) |
| $\alpha_f$ | 0.5 | SEI 电化学对称因子 | (36) |
| $k_\text{LP}$ | 2.33e-4 | 镀锂交换电流常数 | (39) |
| $\alpha_\text{LP}$ | 0.5 | 镀锂对称因子 | (39) |
| $V_\text{LP}^{0}$ | 0 V | 镀锂平衡电位 | (39) |
| $k_\text{LAM,PE,cal}$ | 1.15e-11 | 日历 LAM_PE 常数 | (40) |
| $k_\text{LAM,PE,cyc}$ | 2.73e-3 | 循环 LAM_PE 常数 | (40) |
| $\gamma_\text{PE}$ | 3.18 | LAM_PE 电位指数 | (40) |
| $k_\text{LAM,NE,cyc}$ | 3.87e-4 | 循环 LAM_NE 常数 | (41) |
| $R_\text{SEI}$ | 0.66 | SEI 比电阻 | (45) |

### 4.2 实验设计（论文原文的做法）

**日历老化实验**（论文 Fig. 4 的数据）：
- **3 个 SOC 点**：0% / 50% / 100%
- **2–3 个温度**：25°C / 40°C / 60°C（多温度是为了拟合 $E_a$）
- **存储时长**：60–70 周，中间每隔 ~9 周做一次 RPT
- **拟合参数**：$k_\text{SEI,cal}$, $k_\text{LAM,PE,cal}$, $\gamma_\text{PE}$, $R_\text{SEI}$, $E_a$

**循环老化实验**（论文 Fig. 6–7 的数据）：
- **工况**：DST 协议（动态应力测试）
- **时长**：至少跑到 ~500 EFC 才能看到 knee
- **RPT 频率**：每 50–100 EFC 做一次
- **拟合参数**：$k_\text{SEI,cyc}$, $k_\text{LAM,PE,cyc}$, $k_\text{LAM,NE,cyc}$, $k_\text{LP}$

### 4.3 RPT（参考性能测试）做什么？

每次 RPT 不是跑全套老化，而是一套标准诊断流程：

1. **C/5 充放电** → 得到当前容量 $C(t)$
2. **EIS 或脉冲测试** → 得到内阻 $R(t)$
3. **C/40 慢速 OCV 测试** → 得到 $V_\text{cell}(\text{SOC})$
4. **增量容量分析 (IC) 或差分电压 (DV)** 从 C/40 OCV 曲线提取 LLI、LAM_PE、LAM_NE 三个退化模式

步骤 4 是关键——**你需要 LLI、LAM_PE、LAM_NE 各自随时间的演化曲线**，这样才能分别约束不同的速率常数。论文里用 alawa 软件做 IC 分析，也可以用开源工具如 `PyLab` 或 Dubarry 的 alawa Python 移植版。

### 4.4 老化参数拟合策略（分步）

> ⚠️ **权威版本**：详细 SOP 见 [`docs/PARAMETER_SOP.md`](PARAMETER_SOP.md)。本节为简要介绍；有冲突时以 SOP 为准。

**论文明确说参数是"手动调参"**（manually adjusted），但可以按以下顺序自动化。**关键是按"参数能被什么数据唯一识别"来分步**：

**FIT-4a — 日历老化参数**（需 EXP-E 数据，含 IR 测量）
```
拟合: k_SEI_cal, E_a, k_LAM_PE_cal, gamma_PE, R_SEI
约束: 同时匹配 Capacity(t)、IR(t)、LLI(t)、LAM_PE(t) 四条曲线

关键洞察 (论文 p.12):
    "所有电阻相关老化参数都取自日历老化研究"
    原因: 日历条件下 Q_PLA_NE = 0, 内阻增长纯来自 SEI + LAM
    ⇒ R_SEI 在日历数据上唯一识别, 不应放到循环拟合中
```

**FIT-4b — 循环老化参数，knee 前**（需 EXP-F 数据）
```
前提: FIT-4a 结果全部冻结, 包括 R_SEI
设置: k_LP = 0 (显式关闭 plating)
拟合: k_SEI_cyc, k_LAM_PE_cyc, k_LAM_NE_cyc
约束: 匹配 LLI(EFC), LAM_PE(EFC), LAM_NE(EFC) 在 knee 前区域
```

**FIT-4c — Knee 位置**（需 EXP-G 数据，circle 到 knee 后）
```
前提: FIT-4a 和 4b 的所有结果都冻结
只调一个参数: k_LP
目标: 让仿真的 knee 出现时机与实验吻合
算法: 1D scipy.optimize.minimize_scalar
```

---

## 5. 针对 LFP / 石墨 体系的完整方案

LFP (LiFePO₄) / 石墨是与 NCA / 石墨差异很大的体系：
- LFP 的 OCV 曲线**极其平坦**（3.2–3.4 V 间有一个很长的平台）→ 对 SOC 估计极不友好
- LFP 的体积变化**极小**（~6.8% vs NCA 的 ~6%）
- LFP 几乎不发生 LAM_PE（循环中结构非常稳定）
- LFP 电池的**老化主导机制是 NE 侧的 SEI 生长和镀锂**

### 5.1 实验规划表（现实可执行）

假设你有 1 款 LFP/G 软包或圆柱电池，名义 3.0 Ah，目标是在 12 个月内完成模型参数化。

| 阶段 | 实验 | 时长 | 电池数 | 产出 |
| --- | --- | --- | --- | --- |
| **阶段 0** 基础表征 | C/40 完整 OCV 充放电 | 1 周 | 2 | $C^0$ 确认 (§1.1), 全电池 OCV 曲线 |
| **阶段 1** 半电池 | 拆电池 → 组装 CR2032 → C/40 | 2 周 | 2（拆件） | $V^0_\text{PE}(X), V^0_\text{NE}(X)$ (§2.1) |
| **阶段 2** 动力学 | GITT + 阶跃响应（**仅 fresh cell**） | 1 周 | 2 | $R(I,X)$ LUT (§2.2), $C_1, C_2$ (§3.2) |
| **阶段 3** 电极平衡 | 从阶段 0 + 1 数据后处理 | 1 周 | — | LR, OFS (§3.1) |
| **阶段 4** 日历老化 | 25/40/60°C × 0/50/100% SOC 储存 | 26 周（连续） | 18 | $k_\text{SEI,cal}, E_a, k_\text{LAM,PE,cal}, \gamma_\text{PE}, R_\text{SEI}$ (§4) |
| **阶段 5** 循环老化 (knee 前) | 1C 充 / 1C 放 循环，带 RPT | 12 周（连续） | 6 | $k_\text{SEI,cyc}, k_\text{LAM,PE,cyc}, k_\text{LAM,NE,cyc}$ (§4) |
| **阶段 5b** 循环老化 (到 knee) | 继续循环到 70% SOH | +10 周 | 同上 | $k_\text{LP}$ (§4) |
| **阶段 6** 验证 | 独立工况（例如 WLTP）循环 | 10 周 | 2 | 模型外推可信度评估 |

**并行执行后总工期 ~7 个月**（若条件充分）；基础阶段 0–3 给你"可用模型"（不含老化），4–5 给老化预测能力。

> ⚠️ **每次 RPT 必测 IR（阶段 4、5、5b 都一样）**：  
> 否则 $R_\text{SEI}$ 无法在 FIT-4a 中识别。具体 RPT 流程见 `PARAMETER_SOP.md §二`。
> 可用 C/3 脉冲（简单）或 EIS 高频实部（精确）测量。

### 5.2 只跑"最小实验套"的捷径

如果预算有限，可以只做**阶段 0 + 阶段 1 + 阶段 5（简化版）**：
- 阶段 0：2 周
- 阶段 1：2 周
- 阶段 5：跑 ~400 EFC（3–4 个月），比论文的 500 EFC 短一点

**代价**：
- 不拆全部电池 → 只能粗略分 $R_\text{NE}$ / $R_\text{PE}$
- 只跑一个温度 → 无法拟合 $E_a$，把它固定到文献值（50000–60000 J/mol 是 SEI 的典型范围）
- 没有日历老化数据 → 把 $k_\text{SEI,cal}$ 固定为论文值，只拟合循环参数

这样做出的模型**可以回放实验数据**，但外推能力（不同 T、不同工况下）不可靠。

---

## 6. 拟合代码骨架（现在就能跑）

我在 `examples/` 下加一个 LFP 参数化模板 `lfp_parameterization.py`，分 3 个子函数对应三步老化拟合。

### 6.1 LFP 参数工厂（Step 1 初稿）

```python
# libquiv_aging/lfp_graphite.py
import numpy as np
from .aging_kinetics import (
    AgingModel, LAMParameters, MolarVolumeModel, PlatingParameters,
    ResistanceAgingParameters, SEIParameters, GRAPHITE_V_REL_COEFF
)
from .cell_model import EquivCircuitCell
from .lookup_tables import HalfCellThermo, ResistanceLUTs, default_data_path


# LFP 的相对体积变化极小 (~6.8%); 这里用简单一次项近似
LFP_V_REL_COEFF = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0.068, 1.0])


def create_lfp_graphite_cell(
    *,
    C_nominal_Ah: float = 3.0,
    LR: float = 1.05,                  # 有数据后更新
    OFS: float = 3.0,
    dX_PE_alawa: float = 0.95,         # LFP 可用 X 范围
    dX_NE_alawa: float = 0.96,
    X0_PE: float = 0.95,
    X0_NE: float = 0.01,
    V_max: float = 3.6,
    V_min: float = 2.0,
    # 老化参数: 初始给论文 NCA/G 值作为 placeholder, 拟合时再替换
    k_SEI_cal: float = 0.0420,
    k_SEI_cyc: float = 0.470,
    k_LP: float = 2.33e-4,
    k_LAM_PE_cyc: float = 0.0,         # LFP 几乎不 LAM_PE, 建议默认 0
    k_LAM_NE_cyc: float = 3.87e-4,
    Ea_SEI: float = 55500.0,
    R_SEI: float = 0.66,
    R_NE_0: float = 0.020,
) -> EquivCircuitCell:
    """
    LFP / 石墨电池参数工厂。所有参数都暴露为关键字参数, 
    以便 Claude Code / 拟合脚本直接覆盖。
    """

    # 半电池 OCV —— 用户必须提供 LFP 的 .dat 文件
    anode_thermo = HalfCellThermo.from_dat_file(default_data_path("GraphiteAlawa.dat"))
    cathode_thermo = HalfCellThermo.from_dat_file(default_data_path("LFPAlawa.dat"))
    # ^ 需要你放一份 LFPAlawa.dat 到 data/ 下

    # 电阻 LUT —— 首版可暂时复用 NCA 的, 有 GITT 数据后替换
    r_luts = ResistanceLUTs.from_mat_file(default_data_path("ResistancesAlawa.mat"))

    # 初始电极容量
    C0_PE = C_nominal_Ah / dX_PE_alawa / (1.0 - OFS / 100.0) * 3600.0
    C0_NE = C0_PE * LR * dX_PE_alawa / dX_NE_alawa
    Q0_SEI_NE = C0_PE * dX_PE_alawa * OFS / 100.0

    aging = AgingModel(
        sei=SEIParameters(k_cal=k_SEI_cal, k_cyc=k_SEI_cyc, Ea=Ea_SEI, alpha_f=0.5),
        plating=PlatingParameters(k_LP=k_LP, alpha_LP=0.5, V_LP_eq=0.0),
        lam_pe=LAMParameters(k_cal=0.0, k_cyc=k_LAM_PE_cyc, gamma=1.0),
        lam_ne=LAMParameters(k_cal=0.0, k_cyc=k_LAM_NE_cyc, gamma=0.0),
        resistance_aging=ResistanceAgingParameters(R_SEI=R_SEI, R_NE_0=R_NE_0),
        mvol_ne=MolarVolumeModel(GRAPHITE_V_REL_COEFF),
        mvol_pe=MolarVolumeModel(LFP_V_REL_COEFF),
        Q0_SEI_NE=Q0_SEI_NE,
        Q0_LLI_NE=Q0_SEI_NE,
    )

    CN_As = C_nominal_Ah * 3600.0

    def Rs_fn(T, X_ne, X_pe, I):
        c_rate = np.clip(-I * 3600.0 / CN_As, -4.0, 4.0)
        return (1.0 / C_nominal_Ah) * r_luts.interp_Rs(c_rate, 0.0)

    def R1_fn(T, X_ne, X_pe, I):
        c_rate = -I * 3600.0 / CN_As
        return (1.0 / C_nominal_Ah) * r_luts.interp_RNE(c_rate, X_ne)

    def R2_fn(T, X_ne, X_pe, I):
        c_rate = -I * 3600.0 / CN_As
        return (1.0 / C_nominal_Ah) * r_luts.interp_RPE(c_rate, X_pe)

    cell = EquivCircuitCell(
        anode_thermo=anode_thermo,
        cathode_thermo=cathode_thermo,
        resistance_luts=r_luts,
        Rs_fn=Rs_fn, R1_fn=R1_fn, R2_fn=R2_fn,
        C1=1000.0, C2=3000.0,
        fractionR1toRs=0.5, fractionR2toRs=0.5,
        aging_V_max=V_max, aging_V_min=V_min,
        aging_C0_PE=C0_PE, aging_C0_NE=C0_NE,
        aging_X0_PE=X0_PE, aging_X0_NE=X0_NE,
        aging=aging,
    )
    return cell
```

### 6.2 参数拟合流程（脚本骨架）

> ⚠️ 正式的脚本由 [`docs/PARAMETER_SOP.md`](PARAMETER_SOP.md) 的 SOP-5 规范，位于 `scripts/fit_calendar.py`、`fit_cycle_preknee.py`、`fit_knee.py`。以下是简化演示，说明三步拟合的核心逻辑。

```python
# examples/lfp_fitting_pipeline.py  (简化演示, 正式版见 scripts/)
import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from libquiv_aging.lfp_graphite import create_lfp_graphite_cell


# ========== Step 1: 加载你的老化实验数据 ==========
calendar = pd.read_csv('experiments/EXP-E/cell_E1_rpt.csv')  # 含 time_s, C_Ah, IR_mOhm, LLI_Ah, LAM_PE_Ah
cycle    = pd.read_csv('experiments/EXP-F/cell_F1_rpt.csv')  # 含 EFC, LLI_Ah, LAM_PE_Ah, LAM_NE_Ah
knee     = pd.read_csv('experiments/EXP-G/cell_G1_rpt.csv')  # 含 EFC, C_Ah (跨越 knee)


# ========== Step 2: 定义仿真 runner (在不同阶段复用) ==========
def simulate(params: dict, protocol: str, n_cycles: int, acc: float = 20):
    """跑一个老化协议, 返回所有关心的时间轨迹."""
    cell = create_lfp_graphite_cell(**params)
    cell.aging.acceleration_factor = acc
    cell.init(SOC=0.5)
    C0 = cell.C
    # ... 运行 protocol, 收集 EFC/time, C, IR, LLI, LAM_PE, LAM_NE
    # 具体实现见 analysis_template.py
    return EFC, time_s, C_trace, IR_trace, LLI_trace, LAM_PE_trace, LAM_NE_trace


# ========== Step 3: FIT-4a  日历老化参数 (含 R_SEI!) ==========
# 拟合: k_SEI_cal, k_LAM_PE_cal, gamma_PE, R_SEI (E_a 固定到文献 55500 若单温度)
def loss_calendar(x_log, exp_t, exp_C, exp_IR, exp_LLI, exp_LAM_PE):
    log_k_SEI_cal, log_k_LAM_PE_cal, gamma_PE, log_R_SEI = x_log
    params = dict(
        k_SEI_cal    = 10 ** log_k_SEI_cal,
        k_LAM_PE_cal = 10 ** log_k_LAM_PE_cal,
        gamma_PE     = gamma_PE,
        R_SEI        = 10 ** log_R_SEI,    # ← 关键: R_SEI 在这里拟合!
    )
    _, t, C, IR, LLI, LAM_PE, _ = simulate(params, protocol='calendar', n_cycles=...)
    # 四个归一化 MSE 相加
    def nmse(y_sim, y_exp):
        y_s = np.interp(exp_t, t, y_sim)
        return np.mean((y_s - y_exp)**2) / np.mean(y_exp**2)
    return nmse(C, exp_C) + nmse(IR, exp_IR) + nmse(LLI, exp_LLI) + nmse(LAM_PE, exp_LAM_PE)

res_4a = minimize(
    loss_calendar,
    x0=[np.log10(0.04), np.log10(1e-11), 3.0, np.log10(0.66)],
    args=(calendar['time_s'].values, calendar['C_Ah'].values,
          calendar['IR_mOhm'].values, calendar['LLI_Ah'].values,
          calendar['LAM_PE_Ah'].values),
    method='Nelder-Mead', options={'maxiter': 200, 'disp': True}
)
params_4a = dict(
    k_SEI_cal    = 10 ** res_4a.x[0],
    k_LAM_PE_cal = 10 ** res_4a.x[1],
    gamma_PE     = res_4a.x[2],
    R_SEI        = 10 ** res_4a.x[3],
)
print(f"FIT-4a 完成: {params_4a}")


# ========== Step 4: FIT-4b  循环老化参数 (R_SEI 冻结, 关 plating) ==========
def loss_cycle(x_log, exp_EFC, exp_LLI, exp_LAM_PE, exp_LAM_NE):
    log_k_SEI_cyc, log_k_LAM_PE_cyc, log_k_LAM_NE_cyc = x_log
    params = dict(
        **params_4a,                          # 冻结 FIT-4a 所有结果 (含 R_SEI)
        k_SEI_cyc    = 10 ** log_k_SEI_cyc,
        k_LAM_PE_cyc = 10 ** log_k_LAM_PE_cyc,
        k_LAM_NE_cyc = 10 ** log_k_LAM_NE_cyc,
        k_LP = 0.0,                           # 关 plating
    )
    EFC, _, _, _, LLI, LAM_PE, LAM_NE = simulate(params, protocol='cycle_DST', n_cycles=...)
    def nmse(y_sim, y_exp):
        y_s = np.interp(exp_EFC, EFC, y_sim)
        return np.mean((y_s - y_exp)**2) / np.mean(y_exp**2)
    return nmse(LLI, exp_LLI) + nmse(LAM_PE, exp_LAM_PE) + nmse(LAM_NE, exp_LAM_NE)

pre_knee_mask = cycle['EFC'] < cycle['EFC'].max() * 0.7  # knee 前区域
res_4b = minimize(
    loss_cycle,
    x0=[np.log10(0.47), np.log10(2.7e-3), np.log10(3.87e-4)],
    args=(cycle.loc[pre_knee_mask, 'EFC'].values,
          cycle.loc[pre_knee_mask, 'LLI_Ah'].values,
          cycle.loc[pre_knee_mask, 'LAM_PE_Ah'].values,
          cycle.loc[pre_knee_mask, 'LAM_NE_Ah'].values),
    method='Nelder-Mead', options={'maxiter': 100, 'disp': True}
)
params_4b = dict(
    **params_4a,
    k_SEI_cyc    = 10 ** res_4b.x[0],
    k_LAM_PE_cyc = 10 ** res_4b.x[1],
    k_LAM_NE_cyc = 10 ** res_4b.x[2],
)
print(f"FIT-4b 完成: {params_4b}")


# ========== Step 5: FIT-4c  Knee 位置 (只调 k_LP) ==========
def knee_EFC_at_threshold(EFC, C_pct, threshold=95.0):
    idx = np.where(C_pct < threshold)[0]
    return EFC[idx[0]] if len(idx) else None

exp_knee_EFC = knee_EFC_at_threshold(
    knee['EFC'].values, knee['C_Ah'].values / knee['C_Ah'].iloc[0] * 100
)

def loss_knee(log_k_LP):
    params = dict(**params_4b, k_LP = 10 ** log_k_LP)
    EFC, _, C, *_ = simulate(params, protocol='cycle_DST', n_cycles=...)
    sim_knee = knee_EFC_at_threshold(EFC, C / C[0] * 100)
    return abs(sim_knee - exp_knee_EFC) if sim_knee else 1e6

res_4c = minimize_scalar(loss_knee, bracket=(-5, -3), method='brent')
k_LP_fit = 10 ** res_4c.x
print(f"FIT-4c 完成: k_LP = {k_LP_fit:.3e}")


# ========== Step 6: 汇总结果 ==========
final_params = dict(**params_4b, k_LP=k_LP_fit)
print("\n=== 全部拟合完成 ===")
for k, v in final_params.items():
    print(f"  {k:20s} = {v}")
```

**关键注意事项**（与论文完全一致）：

1. **R_SEI 在 FIT-4a（日历）拟合**，不在 FIT-4b（循环）。论文 Fig. 6b 显示：循环内阻预测"开箱即用"（come for free），因为日历拟合已经给出了 R_SEI。
2. **FIT-4b 必须关闭 plating**（`k_LP = 0`），否则 knee 之后的数据会污染 k_SEI_cyc 估计。
3. **FIT-4c 冻结所有其他参数**，只调 k_LP 匹配 knee 位置。这是论文 p.13 原文的做法。

### 6.3 把拟合结果写回参数工厂

拟合完成后，把结果填回 `libquiv_aging/lfp_graphite.py` 的默认参数，或在自己的脚本里用关键字参数覆盖：

```python
cell = create_lfp_graphite_cell(
    k_SEI_cyc=k_SEI_cyc_fit,
    k_LAM_NE_cyc=k_LAM_NE_cyc_fit,
    k_LP=k_LP_fit,
)
```

---

## 7. 关于参数不确定性

任何测量都有误差，任何拟合都有多解性。一个健康的工作流会**评估参数不确定性**：

1. **蒙特卡洛**：对测量值加 ±5% 噪声，重跑 50 次拟合，看参数方差
2. **剖面似然**：固定一个参数扫描，看其他参数如何被"补偿"
3. **交叉验证**：用 70% 数据拟合，30% 数据预测，看误差变化

在 `examples/lfp_fitting_pipeline.py` 跑通之后再做这层。

---

## 8. 一张参数速查图

```
─────────── 不需实验 ──────────────────────┐
 - V_max, V_min:    从 datasheet 读         │
 - X0_PE, X0_NE:    约定值 (可半电池校验)    │
 - acceleration_factor:  用户运行参数       │
                                            │
─────────── 简单实验直测 ───────────────────┤
 - C_nominal: C/40 完整放电总电荷量          │     Ⅰ 级参数
                                            │
─────────── 半电池 / GITT / 阶跃 ───────────┤
 - V^0_PE(X), V^0_NE(X):   半电池 C/40      │
 - R(I, X):       GITT + EIS                │     Ⅱ 级参数  
 - LR, OFS:       全电池+半电池 OCV 拟合     │
 - C1, C2:        阶跃响应拟合               │     Ⅲ 级参数
                                            │
─────────── 长时间老化实验 + IC 分析 ────────┤
 - k_SEI_cal:     多 T 日历存储              │
 - k_SEI_cyc:     循环早期 (pre-knee)        │
 - k_LAM_PE,NE:   循环早期                   │     Ⅳ 级参数
 - k_LP:          循环到 knee                │
 - Ea, R_SEI, γ_PE: 需多 T 数据              │
─────────────────────────────────────────────┘
```

---

## 9. 立即行动建议

**如果你明天就想动手，先做最小集**：

1. 阅读完本文档
2. 决定你能搞到的实验数据类型
3. 用 Claude Code 说：
   > "`读 docs/06_parameter_sourcing.md, 然后根据我手头的数据 [列出]，帮我写一个 lfp_parameterization.py 的第一版本，先让模型能跑起来，不追求拟合精度。`"

**如果你已有旧电池的实验数据**：

1. 先把数据整理成 `EFC`, `Capacity_pct`, `IR_pct`, `LLI_Ah`, `LAM_PE_Ah`, `LAM_NE_Ah` 六列的 CSV
2. 用 §6.2 的拟合骨架，先跑 Step 3a（循环参数）看结果是否合理
3. 如果有 knee 数据，继续跑 Step 3b
4. 报告拟合 RMSE 和残差分布给 Claude Code，让它建议下一步

---

**底线**：这个模型对"参数全凭经验"的新体系（只有 datasheet、没有任何测量数据）也能运行，但只有**物理合理性校核**的价值；要做**定量预测**必须有至少阶段 0+1+5 的实验数据。论文作者花了多年建立 Panasonic 电池的完整数据集，这部分工作在新体系上无法跳过。
