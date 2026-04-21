# 04 · 模型输出解读与评估方法

读完本文档你应当能：
- 找到每一个想要的输出变量存在哪个字段里
- 画出标准的 4 张对比图（容量、内阻、退化模式、退化机理）
- 做定量误差评估（RMSE、相对误差、knee 位置匹配度）

---

## 1. 输出分为 3 类

### 1.1 标量末态（当前状态）

运行一次 `cell.CC/CV/CP` 之后，电池对象的下列字段反映此刻状态：

```python
cell.t                   # 当前仿真时间 [s]
cell.SOC                 # 荷电状态 [0..1]
cell.V                   # 端电压 [V]
cell.I                   # 端电流 [A]
cell.Q                   # 累积交换电荷 [As]
cell.C                   # 当前实际容量 [As] (随老化变化)
```

这些最常用于实时监控 / 循环终止判据 / 打印日志。

### 1.2 时间轨迹（历史记录）

所有 `all*` 前缀的列表，每次仿真步进都会 append。示例：

```python
import numpy as np
t  = np.asarray(cell.allt)      # (N,) 时间点
V  = np.asarray(cell.allV)      # (N,) 端电压轨迹
I  = np.asarray(cell.allI)      # (N,) 电流轨迹
SOC= np.asarray(cell.allSOC)    # (N,) SOC 轨迹

# 例：画一轮 DST 循环的电压时间图
import matplotlib.pyplot as plt
plt.plot(t/60, V); plt.xlabel('Time / min'); plt.ylabel('V / V')
```

完整字段：

| 字段 | 物理意义 | 单位 |
| --- | --- | --- |
| `allt` | 时间 | s |
| `allQ` | 累积交换电荷 | As |
| `allI` | 端电流 (正号=放电) | A |
| `allV` | 端电压 | V |
| `allV0` | 当前 SOC 下的开路电压 | V |
| `allSOC` | SOC | 0..1 |
| `allT` | 温度 | K |
| `allV_RC01`, `allV_RC02` | 两个 RC 元件电压 | V |

### 1.3 老化内部状态轨迹

这是论文模型相对于普通 ECM 的价值所在。`aging_all*` 前缀：

| 字段 | 物理意义 | 单位 | 说明 |
| --- | --- | --- | --- |
| `aging_allQ_PE` | PE 半电池电荷量 | As | 放电时 ↑；LLI 时 ↓ |
| `aging_allQ_NE` | NE 半电池电荷量 | As | 充电时 ↑；LLI 时 ↓ |
| `aging_allQ_LAM_PE` | PE 活性材料损失累积 | As | 论文退化模式 LAM_PE |
| `aging_allQ_LAM_NE` | NE 活性材料损失累积 | As | 论文退化模式 LAM_NE |
| `aging_allQ_LLI_PE` | PE 侧锂库存损失 | As | 本模型中恒为 0 |
| `aging_allQ_LLI_NE` | NE 侧锂库存损失 | As | 对应论文 LLI |
| `aging_allQ_SEI_NE` | SEI 层吸收的锂 | As | LLI 的一个组成 |
| `aging_allQ_PLA_NE` | 不可逆镀锂层锂 | As | LLI 的一个组成，**knee 主角** |

注意：`Q_LLI_NE = (Q_SEI_NE - Q_SEI_NE^0) + Q_PLA_NE`（近似等式，忽略 X_LAM 贡献）。

---

## 2. 标准的 4 张对比图

论文 Figure 7 展示的 9 个 panel 里最核心是前 4 个，对应文件 `examples/figure7_simulation.py` 也会自动输出到 `examples/outputs/`。

### 2.1 归一化容量 vs. EFC

```python
EFC = np.asarray(Q_exch) / C_0                # Q_exch 的记录见 figure7_simulation.py
C_arr = np.asarray(C_trace)                   # 每次循环后的 cell.C
plt.plot(EFC, C_arr / C_0 * 100, '-', label='Sim')
plt.ylabel('Normalized capacity / %')
plt.xlabel('Equivalent full cycles')
```

**关键可观察点**：
- **膝前线性区**：前 ~400 EFC 容量呈近似线性下降
- **knee 出现时机**：论文是 ~400 EFC，由 $k_\text{LP}$ 控制
- **膝后陡降斜率**：正反馈 (R_NE ↑ → V_NE ↓ → 镀锂 ↑) 的速度

### 2.2 归一化内阻 vs. EFC

```python
R_arr = np.asarray(R_trace)                   # 每次循环 compute_IR()
plt.plot(EFC, R_arr / R_arr[0] * 100)
```

内阻的"知识约束"：
- 前期 SEI 增长主导，$R_\text{IR} \propto \sqrt{\text{time}}$
- knee 后镀锂层贡献使 $R_\text{NE}$ 陡增

### 2.3 三个退化模式 vs. EFC

```python
# 仿真端, 单位从 As 转到 Ah
sim_LLI   = np.asarray(cell.aging_allQ_LLI_NE) / 3600
sim_LAMPE = np.asarray(cell.aging_allQ_LAM_PE) / 3600
sim_LAMNE = np.asarray(cell.aging_allQ_LAM_NE) / 3600
```

解读：
- LAM_PE 和 LAM_NE 分别表示"有多少 Ah 的正极/负极材料已经失效"
- LLI 表示"有多少 Ah 的锂被不可逆占用"
- 三者合起来的总量通常**大于**整体容量损失，因为容量损失是它们的**非线性组合**（受电极平衡约束，见论文 Fig. 8b）

### 2.4 退化机理 (SEI vs Plating)

```python
plt.plot(EFC, cell.aging_allQ_SEI_NE / 3600, label='SEI')
plt.plot(EFC, cell.aging_allQ_PLA_NE / 3600, label='Plating')
```

判断模型是否"讲对了故事"的方式：
- **SEI 曲线**应该呈现 $\sqrt{t}$ 形状
- **Plating 曲线**在 knee 出现之前应该~0，knee 后陡增

---

## 3. 诊断性输出（故障排查常用）

### 3.1 电极半电池电压 V_NE, V_PE

这两个**不是**直接字段，需要后处理计算：

```python
from libquiv_aging.aging_kinetics import f_R_NE, f_R_PE
from libquiv_aging.lookup_tables import open_circuit_voltage

# 用 all* 数据反推半电池电压
all_X_NE = np.asarray(cell.aging_allQ_NE) / (cell.aging_C0_NE - np.asarray(cell.aging_allQ_LAM_NE))
all_X_PE = np.asarray(cell.aging_allQ_PE) / (cell.aging_C0_PE - np.asarray(cell.aging_allQ_LAM_PE))
V0, _, _, V0_PE, V0_NE = open_circuit_voltage(
    all_X_NE, all_X_PE, 298.15,
    cell.anode_thermo, cell.cathode_thermo
)

all_I = np.asarray(cell.allI)
# 忽略 RC 项的简化: V_NE ≈ V0_NE + I * R1 * fractionR1toRs
# (完整表达式见 cell_model.py::_ode_rhs 里的 V_NE 计算)
```

**诊断用途**：画 `V_NE` vs 时间图，如果 V_NE 长时间 < 0 V，就会触发镀锂；如果一直 > 0.1 V，基本不会镀锂。

### 3.2 瞬时老化速率

```python
# 相邻时间点的差分即瞬时速率
dt = np.diff(cell.allt)
dQ_SEI_dt = np.diff(cell.aging_allQ_SEI_NE) / dt
dQ_PLA_dt = np.diff(cell.aging_allQ_PLA_NE) / dt

# 画 rate vs 时间, 观察 plating 是否在特定工况段（充电末期）活跃
```

### 3.3 化学计量 X 的跨度随老化变化

老化之后，电池的"可用 SOC 窗口"会缩小：

```python
X_NE = cell.aging_allQ_NE / (cell.aging_C0_NE - cell.aging_allQ_LAM_NE)
# 画 X_NE vs t 能看到 X 的上下包络线逐渐收窄
```

论文 Fig. 7g/h/i 展示的就是这个效应。

---

## 4. 定量误差评估

### 4.1 容量预测 RMSE

```python
from scipy.interpolate import interp1d

# 实验数据
EFC_exp = np.array([0, 182.9, 478.4, 701.5, 902.5, 1095.5, 1296.5, 1334.7, 1382.9, 1425.1, 1463.3]) / 3.35
Cap_exp_pct = np.array([100.05, 97.49, 96.31, 95.12, 93.84, 92.56, 91.08, 90.89, 89.90, 88.72, 85.86])

# 仿真 interp 到实验 EFC 点
f_sim = interp1d(EFC_sim, C_arr / C_0 * 100, bounds_error=False)
Cap_sim_interp = f_sim(EFC_exp)

# 过滤 NaN (EFC 超出仿真范围时)
mask = ~np.isnan(Cap_sim_interp)
rmse = np.sqrt(np.mean((Cap_sim_interp[mask] - Cap_exp_pct[mask])**2))
mae  = np.mean(np.abs(Cap_sim_interp[mask] - Cap_exp_pct[mask]))
print(f"Capacity RMSE = {rmse:.2f} %, MAE = {mae:.2f} %")
```

典型阈值（给自己定的验收线）：
- **Pre-knee (EFC < 300)**: RMSE < 1%
- **Knee 过渡区 (EFC 300-500)**: RMSE < 3%
- **Post-knee (EFC > 500)**: 主要看趋势匹配度

### 4.2 Knee 位置匹配度

定义 knee 位置为容量下降到某阈值（例如 95%）时的 EFC：

```python
def knee_EFC(EFC, C_pct, threshold=95.0):
    idx = np.where(C_pct < threshold)[0]
    return EFC[idx[0]] if len(idx) > 0 else None

EFC_knee_sim = knee_EFC(EFC_sim, C_arr / C_0 * 100)
EFC_knee_exp = knee_EFC(EFC_exp, Cap_exp_pct)
print(f"Knee @ 95% cap: Sim = {EFC_knee_sim:.0f} EFC, Exp = {EFC_knee_exp:.0f} EFC")
print(f"误差: {abs(EFC_knee_sim - EFC_knee_exp):.0f} EFC 或 "
      f"{abs(EFC_knee_sim - EFC_knee_exp)/EFC_knee_exp*100:.1f}%")
```

### 4.3 退化模式分解一致性检查

物理上容量损失 $\Delta C$ 应与退化模式一致（论文讨论见 Section "Model reduction"）。 简化约束（忽略 X_LAM 贡献）：

$$
\Delta C \approx \min(\Delta C_\text{NE-accessible}, \Delta C_\text{PE-accessible})
$$

这是复杂的电极平衡问题，最直接的检验是：**把仿真得到的 LLI、LAM_PE、LAM_NE 输入一个独立的 alawa 模型，看它算出的容量是不是和仿真得到的一致**。若差异显著（> 5%），说明 SOC 标定或 X_LAM 设置有问题。

---

## 5. 输出持久化（为后续分析）

### 5.1 保存为 npz (推荐)

```python
import numpy as np
np.savez_compressed(
    'examples/outputs/run_2026_04_19.npz',
    # 时间轨迹
    t=cell.allt, V=cell.allV, I=cell.allI, SOC=cell.allSOC,
    # 老化轨迹
    Q_PE=cell.aging_allQ_PE, Q_NE=cell.aging_allQ_NE,
    Q_LAM_PE=cell.aging_allQ_LAM_PE, Q_LAM_NE=cell.aging_allQ_LAM_NE,
    Q_LLI_NE=cell.aging_allQ_LLI_NE,
    Q_SEI_NE=cell.aging_allQ_SEI_NE, Q_PLA_NE=cell.aging_allQ_PLA_NE,
    # 每圈的末态
    EFC=EFC_sim, C_Ah=C_arr/3600, R_trace=R_arr,
)
```

### 5.2 CSV (便于给同事 / 写报告)

```python
import pandas as pd
pd.DataFrame({
    'EFC': EFC_sim,
    'Capacity_pct': C_arr / C_0 * 100,
    'Resistance_pct': R_arr / R_arr[0] * 100,
    'LLI_Ah': np.interp(t_trace, cell.allt, cell.aging_allQ_LLI_NE) / 3600,
    'LAMPE_Ah': np.interp(t_trace, cell.allt, cell.aging_allQ_LAM_PE) / 3600,
    'LAMNE_Ah': np.interp(t_trace, cell.allt, cell.aging_allQ_LAM_NE) / 3600,
}).to_csv('examples/outputs/summary_2026_04_19.csv', index=False)
```

---

## 6. 与 MATLAB 原版输出的对照

如果你有 MATLAB 原代码的输出可以做 sanity check，**字段一一对应关系**：

| MATLAB 字段 (double array) | Python 字段 (list/ndarray) |
| --- | --- |
| `cell.allt` | `cell.allt` |
| `cell.allV` | `cell.allV` |
| `cell.allI` | `cell.allI` |
| `cell.allSOC` | `cell.allSOC` |
| `cell.aging_allQ_LAM_PE` | `cell.aging_allQ_LAM_PE` |
| `cell.aging_allQ_SEI_NE` | `cell.aging_allQ_SEI_NE` |
| `cell.aging_allQ_PLA_NE` | `cell.aging_allQ_PLA_NE` |

对照法：
1. 用同样的 `NO_CYCLES` 和 `ACC_FACTOR` 跑两份
2. 比较 `C / C_0` vs EFC 曲线（期望两者 RMS 差 < 2%）
3. 对比 `Q_PLA_NE` 起飞时机（期望差 < 5% of total EFC）

微小差异的合理来源：
- `solve_ivp (BDF)` 和 `ode23t` 步长自适应不完全相同
- 标量插值中 MATLAB 与 Python 浮点运算顺序差异（末位误差）
- 我移植时对 `fractionR*toRs` 的处理与 MATLAB 的 `agingDQFun` 中略不同

---

## 7. 常见评估错误

| 错误做法 | 为什么不好 | 正确做法 |
| --- | --- | --- |
| 用"每个仿真步"作为数据点 | 步长非均匀, 样本权重不对 | 先按固定 EFC 网格 resample |
| 直接比较 C_trace vs 实验数据 | 单位不一致 (As vs Ah)、没归一化 | 用 `C / C_0 * 100` (%) 归一化 |
| 只看末期容量 | 对 knee 位置完全不敏感 | 看多个 EFC 点: 100, 300, 500, knee, end |
| 加上所有退化模式判断容量 | 退化模式耦合非线性 | 要么用 alawa 推, 要么直接用 `cell.C` |
| 忘记乘 `aging_accelerationFactor` | 轨迹时间被压缩, EFC 算错 | 见 figure7_simulation.py 里的 Q_cycle 计算 |

---

## 8. 模型诊断清单（你的检查列表）

新参数化完成后逐条过一遍：

- [ ] 新电池 C_0 值 **在 ±3% 内**接近 datasheet
- [ ] 新电池 V(SOC=50%) OCV 合理 (对 NCA/G ~3.65 V, 对 LFP ~3.3 V)
- [ ] CCCV 能充到接近 100% SOC (> 98%)
- [ ] C/5 放电放出的电荷 = C_0 (± 3%)
- [ ] 前 100 EFC 容量下降 **平滑**（没有突然跳变）
- [ ] SEI 累积呈"开口朝下"的 $\sqrt{t}$ 形状（不应线性上涨）
- [ ] Knee 前 Q_PLA_NE < 5% · Q_SEI_NE（knee 主角是镀锂，前面主角是 SEI）
- [ ] Knee 后容量陡降伴随 Q_PLA_NE 陡增
- [ ] 内阻增长 40–60% 对应容量损失 10–15%（典型软件产品的质保边界）
- [ ] 三个退化模式量级合理（对 3.35 Ah 电池, knee 时 LLI ~0.3 Ah, LAM 各 0.1–0.2 Ah）

任何一项不满足，先回到 `docs/03_inputs_guide.md` 检查对应输入；如果输入都对，就该调老化参数了。

---

下一篇 `05_workflow_examples.md` 会展示几个完整的工作流案例（参数扫描、与实验拟合、新体系适配）。
