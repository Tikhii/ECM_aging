# 02 · 模型结构综述

读完这一篇你应该：
- 清楚模型是由哪些物理过程 + 哪些微分 / 代数方程组成。
- 知道每个代码模块对应论文中的哪些方程。
- 能独立讲清楚"知道 I(t)、就能算出 SOC、V、老化状态随时间演化"这件事是怎么实现的。

---

## 1. 模型在做什么（一句话）

**给定加在电池两端的电流、电压或功率历史，预测端电压、SOC 及内部所有老化状态（LLI、LAM_PE、LAM_NE、SEI、Li 镀层）随时间的演化。**

它是一个"等效电路 + 物理信息老化子模型"的耦合系统，能同时做两件事：

1. **电池行为仿真**（像普通 ECM 那样，给 I 算 V）
2. **内部物理状态演化**（追踪正负极活性材料损失、锂库存损失等，能预测"knee" —— 容量衰减的非线性转折点）

---

## 2. 等效电路结构（对应论文 Fig. 1）

```
                        +---[R₁(NE)]---+
                        |              |
                        |   [C₁(NE)]   |
                        |              |
 V_NE⁰ ○───────────●────+--------------+--[R_NE_stat]──┐
                   │                                    │
                   │                                    │
     (半电池串联)   │                                    ○  I_cell
                   │                                    │
 V_PE⁰ ○───────────●────+--------------+--[R_PE_stat]──┘
                        |              |
                        |   [C₂(PE)]   |
                        |              |
                        +---[R₂(PE)]---+
                        
                        (还有串联的 Rs 代表电解液/集流)
```

电池两端电压 $V_\text{cell}$ 由论文式 (1):

$$
V_\text{cell} = V_{PE}^0(X_{PE}) - V_{NE}^0(X_{NE}) - I_\text{cell}(R_s + R_{PE}^{stat} + R_{NE}^{stat}) - V_{PE}^{RC} - V_{NE}^{RC}
$$

其中 $V_{i}^{RC}$ 是 RC 元件两端电压，由论文式 (2)(3) 描述的一阶动力学给出：

$$
\frac{dV^{RC}_i}{dt} = \frac{1}{C^{dyn}_i}\left(I_\text{cell} - \frac{V^{RC}_i}{R^{dyn}_i}\right)
$$

代码中这两个方程位于 **`cell_model.py` → `_ode_rhs`** 里：

```python
dydt[1] = (I - V_RC1 / R1_eff) / self.C1    # NE 的 V_RC 动力学
dydt[2] = (I - V_RC2 / R2_eff) / self.C2    # PE 的 V_RC 动力学
```

---

## 3. 半电池开路电压：热力学查找表

$V_{PE}^0(X_{PE})$ 和 $V_{NE}^0(X_{NE})$ 不解析求，而是从实验半电池 OCV 曲线查表。内部实现的关键公式是：

$$
V^0(X, T) = -\frac{\Delta H(X) - T \cdot \Delta S(X)}{F}
$$

其中 $\Delta H(X)$ 和 $\Delta S(X)$ 是反应的摩尔焓与摩尔熵，从 `GraphiteAlawa.dat` / `NCAAlawa.dat` 文件中线性插值得到。

代码位置：**`lookup_tables.py` → `HalfCellThermo.interp_dH_dS`** + `open_circuit_voltage()`。

> 对于简化应用（不考虑温度），可以认为 $V^0 \approx -\Delta H/F$；数据文件里 $\Delta S$ 本身就是零。

---

## 4. 电阻：二维查找表（I × X_stoichiometry）

电阻 $R_s$、$R_1$（NE 侧）、$R_2$（PE 侧）不是常数，而是从 `ResistancesAlawa.mat` 中读入的三张 (1001 × 2001) 矩阵：

- 行（1001）：化学计量 / SOC 从 0 到 1，步长 0.001
- 列（2001）：C-rate 从 −4C 到 +4C，步长 0.004

这体现了 ECM 的"半物理"性质：用电位曲线 + 电阻曲线拟合，而非纯代数模型。

代码位置：**`lookup_tables.py` → `ResistanceLUTs._interp_scalar`**（热循环里大量被调，是性能关键点，已做标量化优化）。

---

## 5. 老化：5 个退化过程

论文的创新点在这里 —— 将 3 个宏观退化模式（LLI、LAM_PE、LAM_NE）拆解成 5 个物理机理：

| 机理 | 速率记号 | 论文公式 | 代码函数 | 驱动因素 |
| --- | --- | --- | --- | --- |
| SEI 生长 (NE 上) | $I_\text{SEI,NE}$ | (36) | `aging_kinetics.I_SEI_NE` | NE 电位 + 循环体积变化 |
| 不可逆镀锂 (NE 上) | $I_\text{LP,NE}$ | (39) | `aging_kinetics.I_PLA_NE` | NE 电位 < 0 V (vs Li) |
| LAM_PE (日历 + 循环) | $I_\text{LAM,PE}$ | (40) | `aging_kinetics.I_LAM_PE` | PE 电位 + \|I·dv/dX\| |
| LAM_NE (纯循环) | $I_\text{LAM,NE}$ | (41) | `aging_kinetics.I_LAM_NE` | \|I·dv/dX\| |
| LLI_PE | $I_\text{LLI,PE}$ | (42) | `aging_kinetics.I_LLI_PE` | 本论文中恒为 0 |

所有速率都以"电流"为单位表达（$A = C/s$）——将退化反应当电化学反应看，数学上非常自洽。

### 5.1 SEI 生长的代表性公式 (论文式 36)

$$
I_\text{SEI,NE} = \frac{1}{Q_\text{SEI}} \exp\!\left[-\frac{E_a}{R}\left(\frac1T - \frac1{T_\text{ref}}\right)\right]
\left[
\underbrace{k_\text{cal}\,\exp\!\left(-\frac{\alpha_f F}{RT}V_{NE}\right)}_\text{日历项}
+
\underbrace{k_\text{cyc}\,\left|I \cdot \frac{dv/v_0}{dX}\right|_{NE}}_\text{循环项}
\right]
\cdot \frac{C_\text{NE}}{C_\text{NE}^0}
$$

各因子的物理含义（对应 `aging_kinetics.py` 中注释）：
- $1/Q_\text{SEI}$：自抑制（SEI 越厚长得越慢，符合 $\sqrt{t}$ 动力学）
- Arrhenius 因子：温度依赖
- 日历项：NE 电位越低（越接近 Li/Li⁺ 电位），SEI 反应越激烈
- 循环项：体积变化诱发 SEI 破裂、暴露新活性表面
- $C_\text{NE}/C_\text{NE}^0 = 1 - Q_\text{LAM,NE}/C_\text{NE}^0$：活性材料越少，反应面越小

### 5.2 镀锂是"knee" 的主凶（论文式 39）

$$
I_\text{LP,NE} = \max\!\left(0,\; k_\text{LP}\left[\exp\!\left(\tfrac{-\alpha F}{RT}V_{NE}\right) - \exp\!\left(\tfrac{\alpha F}{RT}V_{NE}\right)\right]\right) \cdot \frac{C_\text{NE}}{C_\text{NE}^0}
$$

`max(0, …)` 保证反应不可逆。只有当 $V_{NE} < 0\,V$（vs Li⁺/Li，即过电位）时才有正速率。

随着 SEI 和 LAM 累积，R₁ 越来越大 → 放电时 V_NE 被拉低 → 镀锂速率陡增 → Q_PLA 进一步贡献 R₁ → **正反馈循环形成 knee**。

---

## 6. DAE 系统全貌

整个模型是 18 维的微分代数方程，其中：

- **微分变量 (12 个)**：Q_cell, V_RC1, V_RC2, V_RC3, Q_PE, Q_NE, Q_LAM_PE, Q_LAM_NE, Q_LLI_PE, Q_LLI_NE, Q_SEI_NE, Q_PLA_NE
- **代数变量 (6 个)**：I_cell, V_cell, SOC, T, V_hys, SOC_surf

### 6.1 Python 端的处理策略

scipy 原生不支持质量矩阵 DAE，所以我们**把代数方程在每次 ODE 右端评估时显式求解**，系统化归为 12 维 ODE：

| 工作模式 | 代数求解方法 |
| --- | --- |
| **CC (给定 I)** | I 直接用；V、SOC 等均为显式代数公式 |
| **CV (给定 V)** | I 由 $V_\text{target} = V^0 - I\cdot R - V_{RC}$ 解出（Newton warm-start） |
| **CP (给定 P)** | I 由二次方程 $P = I \cdot V(I)$ 解出（同上） |

代码位置：**`cell_model.py` → `_solve_algebraic`**。

### 6.2 时间积分器

使用 `scipy.integrate.solve_ivp` 的 **BDF** 方法（隐式多步，适合刚性问题）。`max_step` 被显式限制以避免事件检测漏掉跳变。

---

## 7. 全局数据流图

```
┌───────────────────────┐
│ panasonic_ncr18650b.py│ (参数工厂)
│  - LR, OFS            │──────┐
│  - 初始容量 C_PE, C_NE │      │
│  - 所有老化速率常数    │      │
└───────────────────────┘      │
                               ▼
                     ┌─────────────────────┐
                     │  EquivCircuitCell   │
                     │  (cell_model.py)    │
                     │                     │
                     │  state: Q, Q_PE,    │
                     │  Q_NE, Q_LAM_*,     │
                     │  Q_LLI_*, ...       │
                     └──────────┬──────────┘
                                │
   ┌────────────────────────────┼──────────────────────────┐
   │                            │                          │
   ▼                            ▼                          ▼
┌─────────────┐       ┌──────────────────┐       ┌──────────────────┐
│ half-cell   │       │ resistance LUT   │       │ aging_kinetics.py│
│ LUT (V⁰)    │       │ (R_s, R_NE, R_PE) │      │ I_SEI, I_LP,     │
│             │       │                  │       │ I_LAM_PE, ...    │
│ GraphiteDat │       │  ResistancesMat  │       │                  │
│ NCAAlawa    │       │                  │       │ (参数见 Table I) │
└─────────────┘       └──────────────────┘       └──────────────────┘
      ▲                       ▲                          ▲
      │                       │                          │
    实验获取                 实验获取                    参数辨识
  (见 03_inputs_guide.md)
```

---

## 8. 对应代码的对照速查表

| 论文公式 | 物理意义 | 代码位置 |
| --- | --- | --- |
| (1) V_cell 表达式 | ECM 电压方程 | `cell_model._solve_algebraic` |
| (2)(3) dV_RC/dt | RC 动力学 | `cell_model._ode_rhs` (dydt[1], dydt[2]) |
| (18)(19) dQ_PE, dQ_NE | 半电池电荷平衡 | `cell_model._ode_rhs` (dydt[4], dydt[5]) |
| (20) dQ_cell = -I | 总电荷平衡 | `cell_model._ode_rhs` (dydt[0]) |
| (25)(26) X_i = Q_i/(C^0 - Q_LAM) | 化学计量 | `cell_model._ode_rhs` (顶部) |
| (27) SOC 定义 | SOC 计算 | `cell_model._aging_calibrate_SOC` |
| (28) OCV = V_PE - V_NE | 半电池合成 | `lookup_tables.open_circuit_voltage` |
| (36) SEI 速率 | 老化 | `aging_kinetics.I_SEI_NE` |
| (39) 镀锂速率 | 老化 (knee 来源) | `aging_kinetics.I_PLA_NE` |
| (40) LAM_PE 速率 | 老化 | `aging_kinetics.I_LAM_PE` |
| (41) LAM_NE 速率 | 老化 | `aging_kinetics.I_LAM_NE` |
| (44) f_R,PE 退化因子 | 电阻老化 | `aging_kinetics.f_R_PE` |
| (45) f_R,NE 退化因子 | 电阻老化 | `aging_kinetics.f_R_NE` |

---

## 9. 关键假设一览（引用时不要忘记）

论文和本代码都用了如下简化假设 —— 改体系或做严谨研究时要重新审视：

1. **等温模型**：T ≡ T_ambient，没有热耦合。
2. **单颗粒假设**：不考虑电极内部空间梯度（是 ECM 的本质代价）。
3. **X_LAM = 0**：失去的活性材料完全脱锂（论文拟合所需）。
4. **LLI_PE ≡ 0**：PE 侧无锂库存损失（如 CEI 被忽略）。
5. **镀锂不可逆**：$V_{NE}^{LP,0}=0$, 不考虑镀锂后的部分剥离。
6. **滞回项 = 0**：OCV 无滞回。
7. **串联电阻不退化**：$f_{Rs} = 1$（论文式 46）。

这些假设的松弛都可以通过修改 `aging_kinetics.py` 或 `cell_model.py` 相应函数实现。

---

## 10. 小结

如果你把这套模型当"黑盒"看，它就是：

```
       输入                         →  模型  →         输出
 ┌────────────────┐                            ┌─────────────────────┐
 │ I(t) 或 V(t)   │                            │ V(t) 或 I(t)        │
 │ 或 P(t)       │       EquivCircuitCell      │ SOC(t), T(t)         │
 │                │       (18D DAE, Py ODE)   │ 内部退化: Q_LAM_*,   │
 │                │                            │   Q_SEI, Q_PLA, ...  │
 └────────────────┘                            └─────────────────────┘
```

读完后再回头看 `cell_model.py::_ode_rhs` 的代码，你会发现它几乎是论文公式的逐行实现。下一篇 `03_inputs_guide.md` 会详细讲"黑盒左边"的那些输入怎么来。
