# 03 · 输入数据获取与格式化完全指南

本文档回答一个核心问题："**如果我要把这套模型用到我自己的电池上，我需要哪些输入？分别怎么得到？怎么变成模型能读的格式？**"

> ⚠️ **使用前请必读**：[`docs/CRITICAL_REVIEW.md`](CRITICAL_REVIEW.md) 描述本模型的作用域限制（温度、C-rate、电压范围等）和已知简化假设。不熟悉作用域会导致外推到不适用场景时做出误导性预测。

按获取难度由易到难排序：

| 输入项 | 难度 | 通常来源 |
| --- | --- | --- |
| ① 电池基本规格 (容量/电压上下限) | ★ | 厂家 datasheet |
| ② 工况协议 (I(t), V(t), P(t) 目标) | ★ | 自己设计 |
| ③ 活性材料相对摩尔体积 $v(X)/v_0$ | ★★ | 文献 / XRD |
| ④ 半电池开路电压 $V^0(X)$ | ★★★ | 半电池 C/40 测试 |
| ⑤ 电阻二维查找表 $R(I, SOC)$ | ★★★★ | GITT / pulse test |
| ⑥ 老化速率常数 $k_\text{SEI}, k_\text{LP}, \ldots$ | ★★★★★ | 长时间老化实验 + 拟合 |

下面逐项详细说明。

---

## ① 电池基本规格 (最容易)

**在哪里改**：`libquiv_aging/panasonic_ncr18650b.py` 中的这些字段

```python
aging_V_max=4.2,        # 充电截止电压 [V]
aging_V_min=2.5,        # 放电截止电压 [V]
C1=949.28,              # NE 侧 RC 电容 [F]
C2=3576.07,             # PE 侧 RC 电容 [F]
```

以及 C0_PE 的计算行（这里用 Panasonic 的 3.35 Ah 标定了一个 C/20 放电测得的名义容量）：

```python
C0_PE = 3.35 / dX_PE_alawa / (1.0 - OFS / 100.0) * 3600.0 / 0.973 * 1.0275
```

**对于你自己的电池**：

1. **名义容量**：做一次 C/20 标准放电（几乎无内阻压降），从 V_max 放到 V_min，测得的 Ah 就是 $C^0$。
2. **V_max / V_min**：直接取 datasheet，或根据你的测试协议设定。
3. **RC 电容 $C_1, C_2$**：需要拟合阶跃响应 —— 给一个电流阶跃（如 C/2），看电压弛豫曲线，拟合 $V(t) = V_0 - IR - IR_{dyn}\,e^{-t/\tau}$ 得 $\tau = R^{dyn} C^{dyn}$，分别处理 PE 和 NE 的阶跃段。**或者**用公开的 EIS 谱、用一个简化拟合策略。如果你暂时没有这类数据，先用 Panasonic 的值（量级通常差不多），后面有经验数据了再细调。

### 建立你自己的参数工厂

```bash
# 复制一份模板
cp libquiv_aging/panasonic_ncr18650b.py libquiv_aging/my_cell.py
```

改里面的 `create_panasonic_ncr18650b()` 为 `create_my_cell()`，改参数值，然后在 `libquiv_aging/__init__.py` 里加一行 `from .my_cell import create_my_cell`。

---

## ② 工况协议 (驱动输入)

"协议" = 对电池施加的 I(t)、V(t) 或 P(t) 序列。

在代码里就是一系列 `cell.CC(...)`, `cell.CV(...)`, `cell.CP(...)` 调用。下面列出论文和实际研究中常见的几种：

### 2.1 CCCV 充电

```python
cell.CC(I=-1.675, duration_s=7200, break_criterion="V > 4.2")   # 充到 4.2 V
cell.CV(V=4.2,   duration_s=7200, break_criterion="abs(I) < 0.065")  # 保持 4.2 V 直到截止电流
```

### 2.2 恒流放电

```python
cell.CC(I=+1.0, duration_s=3600 * 6, break_criterion="V < 2.5")
```

### 2.3 DST (Dynamic Stress Test) 动态应力测试

USABC 的 360 秒动态工况序列，见 `examples/figure7_simulation.py` 第 40-50 行。你可以把表里的 `DST_DURATION` 和 `DST_POWER_PCT` 替换成 WLTP、NEDC、UDDS 或你自己的工况。

### 2.4 自定义工况的通用模板

```python
# 表: [(时长秒, 模式 'I'/'V'/'P', 目标值, break 判据), ...]
protocol = [
    (60,   'I', 0.0,   ''),              # 静置 1 min
    (3600, 'I', -1.67, 'V > 4.2'),       # CC 充电
    (7200, 'V', 4.2,   'abs(I) < 0.1'),  # CV 保持
    (60,   'I', 0.0,   ''),              # 静置
    (3600, 'I', 0.67,  'V < 2.5'),       # C/5 放电
]
for duration, mode, value, crit in protocol:
    if mode == 'I':   cell.CC(value, duration, crit)
    elif mode == 'V': cell.CV(value, duration, crit)
    elif mode == 'P': cell.CP(value, duration, crit)
```

### 2.5 从 CSV 读入真实测量工况

如果你的工况是一条离散时间序列（例如来自真实车辆的电流记录），可以这样处理 —— 每个采样点当作一个短 CC 段：

```python
import pandas as pd
df = pd.read_csv('my_drive_cycle.csv')  # 含 time_s 和 current_A 两列
for i in range(len(df)-1):
    dt = df['time_s'].iloc[i+1] - df['time_s'].iloc[i]
    I  = df['current_A'].iloc[i]
    cell.CC(I, dt, 'V < 2.0')   # 加个兜底 break 判据防止跑飞
```

---

## ③ 活性材料相对摩尔体积 $v(X)/v_0$

**文件位置**：`libquiv_aging/aging_kinetics.py` 中的两个 numpy 数组：

```python
NCA_V_REL_COEFF = np.array([ ... 10 个多项式系数 ... ])
GRAPHITE_V_REL_COEFF = np.array([ ... 10 个多项式系数 ... ])
```

这是 **9 阶多项式拟合** $v(X)/v_0$ 曲线的系数（按高到低次排列，与 `np.polyval` 约定一致）。

**如何获取你材料的系数**：

1. **从文献查**：原论文引用的 Schmider 2022 提供了 NCA、NMC、LCO、Graphite、Si-Graphite 等多种常见材料的数据。一般体积文献会以 XRD (晶格参数) 或 dilatometry (膨胀率) 给出 $v(X)$ 或 $a(X), c(X)$。
2. **自己拟合**：从文献图中提数据 → 用 `numpy.polyfit(x, v_over_v0, deg=9)` 算系数 → 替换数组。
3. **近似**：若实在没有数据，可用"线性膨胀"代替：$v(X)/v_0 \approx 1 + \epsilon X$，系数为 `np.array([0, ..., 0, ε, 1])`。这对大多数 LFP/NMC 日历分析够用，但会低估石墨循环应力。

### 替换示例（假设是 LFP）

```python
# 在 aging_kinetics.py 顶部加
LFP_V_REL_COEFF = np.polyfit(x_data, v_data_over_v0, deg=9)

# 在你的参数工厂里
mvol_pe = MolarVolumeModel(v_coeff=LFP_V_REL_COEFF)
```

---

## ④ 半电池开路电压 $V^0(X)$

**文件位置**：`libquiv_aging/data/GraphiteAlawa.dat` 和 `NCAAlawa.dat`。

### 格式说明（Alawa 标准格式）

文本文件，3 列，星号开头为注释：

```
* Electrode material: Graphite
* Source dH: ...
* x []          dH [J/mol]      dS [J/mol/K]
0.9700000       -1249.390       0.000000
0.9690400       -1466.854       0.000000
...
```

其中：
- **x** 是锂化学计量数（0 ≤ x ≤ 1）
- **dH(x)** 是摩尔焓 [J/mol]，与 $V^0$ 的关系：$V^0 = -\Delta H / F$（取 $\Delta S = 0$ 时）
- **dS(x)** 是摩尔熵 [J/(mol·K)]，通常在 alawa 数据里置 0（等温假设）

### 如何从实验 OCV 曲线生成

假设你测了一份某电极 vs Li/Li+ 金属半电池的 C/40 极缓慢充放电数据：

```python
import numpy as np
import pandas as pd

# 输入：电极上的 Ah 和对 Li 的电位 (V)
data = pd.read_csv("my_graphite_half_cell_C40.csv")  # columns: Ah, V_vs_Li
Q_max_Ah = data['Ah'].max()                # 满脱锂到满嵌锂一次往返的总电荷
X = 1 - data['Ah'] / Q_max_Ah              # 假设：满充时 X=1（全嵌锂）
V_vs_Li = data['V_vs_Li']

F = 96485  # C/mol
dH = -V_vs_Li * F                          # 单位 J/mol
dS = np.zeros_like(dH)                     # 等温假设

# 输出为 alawa 格式
with open('libquiv_aging/data/MyGraphiteAlawa.dat', 'w') as f:
    f.write("* Electrode material: MyGraphite\n")
    f.write("* From C/40 half-cell test on my sample\n")
    f.write("* x []          dH [J/mol]      dS [J/mol/K]\n")
    for x, h, s in zip(X, dH, dS):
        f.write(f"{x:.7f}\t{h:.3f}\t{s:.6f}\n")
```

然后修改参数工厂：

```python
anode_thermo = HalfCellThermo.from_dat_file(default_data_path("MyGraphiteAlawa.dat"))
```

### 关键坑

- **X 方向**：约定 X = 1 对应 "嵌锂饱和" (对石墨就是 LiC6，对 NCA 就是满放电态)。
- **X 覆盖范围**：要覆盖 [0, 1] 区间。实验一般只到如 X=0.01..0.97（完全脱锂 / 完全嵌锂难达到），插值时用端点外推即可。
- **C/40 vs C/20**：C/40 是业界标准的"准平衡" OCV 测试速率，偏离平衡时 < 5 mV。C/20 数据也可用，但精度略差。

---

## ⑤ 电阻二维查找表

**文件位置**：`libquiv_aging/data/ResistancesAlawa.mat`。

这是最复杂的输入，但也是现有代码中**容错度最高**的部分——只要数量级对、形状对，模型就能跑。

> ⚠️ **关键事实（给所有读者）**：
> 电阻 LUT **只在 fresh cell 上测量一次**（EXP-B3, B4）。老化期间电阻的增长完全由模型内部的老化因子 $f_{R,*}$ 公式 (44)(45) 推导——不需要也不应该在老化过程中重新构建 LUT。
> 唯一需要从老化实验拟合的电阻相关参数是 **`R_SEI`**（SEI 比电阻），它在 **FIT-4a (日历老化拟合)** 步骤中与其他 SEI 参数一起识别。详见 `PARAMETER_SOP.md §四 FIT-4a`。

### 格式说明

`.mat` 文件包含 3 个变量：

- `RsAlawa` : 串联电阻 (1001 × 2001)
- `RNEAlawa`: NE 电阻 (1001 × 2001)
- `RPEAlawa`: PE 电阻 (1001 × 2001)

索引约定：
- 第 0 维（行索引 0..1000）：**化学计量 × 100**（即 0..100，对应 SOC 0..100% 的 0.1% 步长）
- 第 1 维（列索引 0..2000）：**C-rate** 从 −4C 到 +4C 的 0.004C 步长

数值约定（很关键）：**表里存储的是 1/(C_nominal_Ah) · 真实电阻**，在 `panasonic_ncr18650b.py` 里看：

```python
def Rs_fn(T, X_ne, X_pe, I):
    c_rate = np.clip(-I * 3600.0 / CN_As, -4.0, 4.0)
    return (1.0 / CN_Ah) * r_luts.interp_Rs(c_rate, 0.0)   # 乘回 CN_Ah 得真实电阻
```

### 如何自己构造

如果你有自己的 pulse test 数据（不同 SOC × 不同 C-rate 的内阻测量），可以这样生成 `.mat`：

```python
import numpy as np
from scipy.io import savemat
from scipy.interpolate import RegularGridInterpolator

# 假设你有稀疏采样数据
SOC_samples = np.array([0.1, 0.3, 0.5, 0.7, 0.9])   # 5 个 SOC
I_samples   = np.array([-2, -1, -0.5, 0.5, 1, 2])   # 6 个电流 (A)
R_NE_meas   = np.random.rand(5, 6) * 0.05 + 0.02    # 实测 NE 电阻, 单位 Ω

# 用 SOC 和 C-rate 做网格插值
CN_Ah = 3.35
C_rate_samples = I_samples / CN_Ah

f_interp = RegularGridInterpolator(
    (SOC_samples, C_rate_samples), R_NE_meas,
    bounds_error=False, fill_value=None   # 越界线性外推
)

# 建立 alawa 风格的 1001 x 2001 大表
SOC_grid = np.linspace(0, 1, 1001)
C_rate_grid = np.linspace(-4, 4, 2001)
SS, CC = np.meshgrid(SOC_grid, C_rate_grid, indexing='ij')
points = np.stack([SS.ravel(), CC.ravel()], axis=-1)

RNE_full = f_interp(points).reshape(1001, 2001)
RNE_full *= CN_Ah       # 要先乘以 CN_Ah 存入表 (见上面约定)

# Rs 常数 + 简单 RPE 也构造
Rs_full = np.full((1001, 2001), 0.01 * CN_Ah)    # 假定 Rs = 10 mΩ 常数
RPE_full = np.full((1001, 2001), 0.005 * CN_Ah)  # 假定 RPE = 5 mΩ 常数

savemat('libquiv_aging/data/MyResistances.mat', {
    'RsAlawa': Rs_full,
    'RNEAlawa': RNE_full,
    'RPEAlawa': RPE_full,
})
```

### 简化版：常数电阻

如果你暂时只有"一个 SOC、一个 C-rate" 下的单个电阻值（例如 EIS 测的 10 kHz 实部），可以直接把表填成常数，让 `Rs_full = np.full((1001, 2001), your_R_value * CN_Ah)`。模型还能跑，只是丢了 SOC/电流依赖。

---

## ⑥ 老化速率常数

这是最棘手的部分。**新体系的老化常数必须用老化实验去拟合**。

> ⚠️ **权威来源**：所有老化参数的来源、代码位置、拟合步骤由 [`docs/PARAMETERS.json`](PARAMETERS.json) 定义；
> 详细的分步拟合 SOP 在 [`docs/PARAMETER_SOP.md`](PARAMETER_SOP.md)。
> 本文中的描述只是**面向新手的解释**，正式执行时**以 JSON + SOP 为准**。

### 参数分组（按拟合步骤）

| 组 | 参数 | 实验 | 拟合步骤 |
| --- | --- | --- | --- |
| **日历组** | `k_SEI_cal`, `E_a`, `k_LAM_PE_cal`, `γ_PE`, **`R_SEI`** | EXP-E（日历老化 + IR 测量） | FIT-4a |
| **循环组** | `k_SEI_cyc`, `k_LAM_PE_cyc`, `k_LAM_NE_cyc` | EXP-F（循环到 knee 前） | FIT-4b（**关 plating**） |
| **Knee 组** | `k_LP` | EXP-G（循环到 knee 后） | FIT-4c（**冻结其他参数**） |

### 重要事实

1. **`R_SEI` 在日历组**：论文明确说"所有电阻相关老化参数都取自日历老化研究"。日历条件下没有镀锂，内阻增长只来自 SEI + LAM，`R_SEI` 能唯一识别。
2. **循环组拟合时必须关 plating**（`k_LP = 0`），否则 knee 出现后数据会污染 `k_SEI_cyc` 的估计。
3. **Knee 组拟合时其他所有参数冻结**（论文 p.13："The plating rate coefficient was then adjusted such that simulated capacity loss matches the experimentally-observed knee"）。

### 需要的实验

详见 `PARAMETERS.json::experiments::EXP-{E|F|G}` 和 `PARAMETER_SOP.md §二`。

### 拟合脚本

由 SOP-5 规范：`scripts/fit_calendar.py`, `fit_cycle_preknee.py`, `fit_knee.py`。
见 `examples/analysis_template.py` 做为起点模板。

---

## 小结：最小可用输入清单

对于"我只想用这个模型做一个初步分析"的人：

| 必须有 | 建议有 | 可以默认 |
| --- | --- | --- |
| 名义容量 $C^0$ | RC 电容 $C_1, C_2$ | 摩尔体积多项式 (用 Panasonic 默认) |
| V_max, V_min | 半电池 OCV 曲线 | 电阻 LUT (用 Panasonic 默认 × 容量比例) |
| 工况协议 | 一个循环老化曲线 | 老化速率常数 |

**最小修改法**：复制 `panasonic_ncr18650b.py` → `my_cell.py`，只改名义容量、电压上下限和工况，其它保持 Panasonic 默认。先看定性行为合不合理，再逐步替换。

**Claude Code 使用提示**："`帮我把 panasonic_ncr18650b.py 复制成 my_cell.py, 把 C0 改成 5 Ah, V_max 改成 4.35 V, 并做一个测试运行`" —— 这种简单改造直接丢给它就行。
