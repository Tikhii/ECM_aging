# 05 · 常见工作流示例

本文档聚焦于"拿来就能改、改了就能跑"的几种典型用例。每个工作流都配有完整可执行脚本。

---

## 工作流 A：改一个参数，看结果变化

**场景**：我想知道"如果 SEI 的激活能再高 5000 J/mol，容量衰减会慢多少？"

```python
# workflow_A_param_sensitivity.py
import matplotlib.pyplot as plt
import numpy as np
from libquiv_aging import create_panasonic_ncr18650b


def run_single_case(Ea, NO_CYCLES=3, ACC=100):
    cell = create_panasonic_ncr18650b()
    cell.aging.sei.Ea = Ea              # 改参数
    cell.aging.acceleration_factor = ACC
    cell.init(SOC=0.5)

    C_0 = cell.C
    EFC_list = [0.0]
    Cap_list = [100.0]

    for n in range(1, NO_CYCLES + 1):
        # 一轮完整工况 (简化: CCCV 充 + C/2 放)
        n_save = len(cell.allt)
        cell.CC(-1.675, 7200, 'V > 4.2')
        cell.CV(4.2, 7200, 'abs(I) < 0.065')
        cell.CC(0, 3600 * 2)
        cell.CC(1.675, 7200, 'V < 2.5')
        cell.CC(0, 3600 * 4)

        t_full = np.asarray(cell.allt[n_save - 1:])
        I_full = np.asarray(cell.allI[n_save - 1:])
        Q_cycle = ACC * np.trapezoid(np.abs(I_full), t_full) / 2
        EFC_list.append(EFC_list[-1] + Q_cycle / C_0)
        Cap_list.append(cell.C / C_0 * 100)
    return np.array(EFC_list), np.array(Cap_list)


if __name__ == '__main__':
    fig, ax = plt.subplots()
    for Ea in [50000, 55500, 60000, 65000]:
        EFC, Cap = run_single_case(Ea)
        ax.plot(EFC, Cap, 'o-', label=f'Ea = {Ea} J/mol')
    ax.set_xlabel('Equivalent full cycles')
    ax.set_ylabel('Normalized capacity / %')
    ax.legend()
    plt.savefig('examples/outputs/workflow_A.png', dpi=150)
```

**Claude Code 操作**：
> `把上面这段存成 workflow_A.py 并运行，总结一下 Ea 增大对 knee 位置的影响。`

---

## 工作流 B：用真实驾驶周期替换 DST

**场景**：我有一条 WLTC 工况曲线 CSV (time_s, power_W)，想看同样 500 EFC 后的老化情况。

```python
# workflow_B_realworld_cycle.py
import pandas as pd
import numpy as np
from libquiv_aging import create_panasonic_ncr18650b


def apply_power_profile(cell, profile_csv, repeat=1):
    """
    用一条 (time_s, power_W) CSV 连续驱动电池 repeat 次。
    CSV 的 time_s 应从 0 开始, power_W 正号 = 放电。
    """
    df = pd.read_csv(profile_csv)
    times = df['time_s'].values
    powers = df['power_W'].values
    for _ in range(repeat):
        for i in range(len(times) - 1):
            dt = times[i+1] - times[i]
            cell.CP(powers[i], dt, 'V < 2.3 or V > 4.3')  # 安全兜底


if __name__ == '__main__':
    cell = create_panasonic_ncr18650b()
    cell.aging.acceleration_factor = 50  # 加速 50 倍
    cell.init(SOC=0.9)

    # 假设 my_wltc.csv 有一个 1800s 的 WLTC 片段, 功率范围 -20 到 +30 W
    # 可以重复 N 次, 然后做一个 CCCV 补电后再重复
    NO_CYCLES = 5
    for cyc in range(NO_CYCLES):
        print(f"Cycle {cyc+1}: V={cell.V:.2f}, SOC={cell.SOC:.2f}")
        apply_power_profile(cell, 'my_wltc.csv', repeat=10)  # 模拟 10 次 WLTC
        cell.CC(-1.675, 7200, 'V > 4.2')                      # 充电回满
        cell.CV(4.2, 3600, 'abs(I) < 0.065')

    print(f"Final C = {cell.C/3600:.4f} Ah, "
          f"Plating = {cell.aging_Q_PLA_NE/3600:.4f} Ah")
```

**常见坑**：
- 工况 CSV 的功率符号约定（很多数据集是 "正=充电"）—— 记得乘 -1。
- 如果工况包含高温/低温段，本模型（等温）不能直接捕捉。要加温度效应，需要扩展 `cell_model.py` 让 T 成为微分状态。

---

## 工作流 C：参数辨识（手动 + 自动）

> ⚠️ **重要**：完整的参数辨识流程由 [`docs/PARAMETER_SOP.md`](PARAMETER_SOP.md) 定义，应严格按 FIT-4a → FIT-4b → FIT-4c **分三步**执行。
> 本小节给出的是最简化的演示，**仅适用于你已冻结 `R_SEI` 等日历参数、只想粗调循环参数**的场景。
> 正式工作请用 `PARAMETER_SOP.md` 的完整流程。

**场景**：我有自己的 3 Ah LFP 电池，实验测了一组 "EFC vs Capacity %" 数据，要**粗略**找出 (k_SEI,cyc, k_LP) 使仿真与实验一致（已接受 `R_SEI` 暂用文献值）。

### C.1 手动调参（推荐先做）

直接在 Jupyter Notebook 里交互式调：

```python
# Cell 1
from libquiv_aging import create_panasonic_ncr18650b
import matplotlib.pyplot as plt
import numpy as np

exp = np.array([
    [0, 100], [100, 98.5], [200, 96.8], [300, 94.5],
    [400, 91.2], [500, 86.8], [600, 78.5],     # knee 明显在 ~450
])

def sim(k_SEI_cyc, k_LP, n_cycles=7, acc=80):
    cell = create_panasonic_ncr18650b()
    cell.aging.sei.k_cyc = k_SEI_cyc
    cell.aging.plating.k_LP = k_LP
    cell.aging.acceleration_factor = acc
    cell.init(SOC=0.5)
    C0 = cell.C
    EFC, Cap = [0], [100.0]
    for _ in range(n_cycles):
        ns = len(cell.allt)
        cell.CC(-1.675, 7200, 'V > 4.2')
        cell.CV(4.2, 7200, 'abs(I) < 0.065')
        cell.CC(0, 3600 * 2)
        cell.CC(1.675, 7200, 'V < 2.5')
        cell.CC(0, 3600 * 4)
        t_full = np.asarray(cell.allt[ns-1:])
        I_full = np.asarray(cell.allI[ns-1:])
        Q_cyc = acc * np.trapezoid(np.abs(I_full), t_full) / 2
        EFC.append(EFC[-1] + Q_cyc / C0)
        Cap.append(cell.C / C0 * 100)
    return np.array(EFC), np.array(Cap)

# Cell 2 - 画图交互
fig, ax = plt.subplots()
ax.plot(exp[:,0], exp[:,1], 'ko', ms=8, label='Exp')
for k_LP in [1e-4, 2.3e-4, 5e-4]:
    EFC, Cap = sim(k_SEI_cyc=0.47, k_LP=k_LP)
    ax.plot(EFC, Cap, '-', label=f'k_LP = {k_LP:.1e}')
ax.legend(); plt.show()
```

一边改，一边肉眼对比，通常 3–5 次迭代就能落在合理区间。

### C.2 自动辨识（用 scipy.optimize）

```python
# workflow_C_autotune.py
from scipy.optimize import minimize
import numpy as np
from libquiv_aging import create_panasonic_ncr18650b

EFC_exp = np.array([0, 100, 200, 300, 400, 500, 600])
Cap_exp = np.array([100, 98.5, 96.8, 94.5, 91.2, 86.8, 78.5])


def simulate(params, ACC=80, n=7):
    """参数 = [k_SEI_cyc, k_LP]"""
    k_SEI_cyc, k_LP = params
    if k_SEI_cyc <= 0 or k_LP <= 0:
        return None  # 不合法
    cell = create_panasonic_ncr18650b()
    cell.aging.sei.k_cyc = k_SEI_cyc
    cell.aging.plating.k_LP = k_LP
    cell.aging.acceleration_factor = ACC
    cell.init(SOC=0.5)
    C0 = cell.C
    EFC_sim = [0.0]
    Cap_sim = [100.0]
    for _ in range(n):
        ns = len(cell.allt)
        cell.CC(-1.675, 7200, 'V > 4.2')
        cell.CV(4.2, 7200, 'abs(I) < 0.065')
        cell.CC(0, 3600 * 2)
        cell.CC(1.675, 7200, 'V < 2.5')
        cell.CC(0, 3600 * 4)
        t_full = np.asarray(cell.allt[ns-1:])
        I_full = np.asarray(cell.allI[ns-1:])
        Q_cyc = ACC * np.trapezoid(np.abs(I_full), t_full) / 2
        EFC_sim.append(EFC_sim[-1] + Q_cyc / C0)
        Cap_sim.append(cell.C / C0 * 100)
    return np.array(EFC_sim), np.array(Cap_sim)


def loss(params_log):
    # 在 log 空间搜 (参数跨越数量级)
    params = 10**np.asarray(params_log)
    result = simulate(params)
    if result is None:
        return 1e6
    EFC_sim, Cap_sim = result
    Cap_interp = np.interp(EFC_exp, EFC_sim, Cap_sim)
    return float(np.sqrt(np.mean((Cap_interp - Cap_exp)**2)))


if __name__ == '__main__':
    # 初值 (log10 空间): k_SEI_cyc ~ 0.5, k_LP ~ 2e-4
    x0 = [np.log10(0.5), np.log10(2e-4)]
    res = minimize(
        loss, x0,
        method='Nelder-Mead',
        options={'xatol': 0.05, 'fatol': 0.1, 'maxiter': 50, 'disp': True},
    )
    k_opt = 10**res.x
    print(f"\n拟合结果: k_SEI_cyc = {k_opt[0]:.4f}, k_LP = {k_opt[1]:.2e}")
    print(f"残差 RMSE = {res.fun:.3f} %")
```

**运行时间估计**：Nelder-Mead 每次 50 次迭代 × 每次仿真 ~60 s = **50 分钟**。如果忍不了，减 `n_cycles` 或用 `differential_evolution` 并行。

---

## 工作流 D：部署到更复杂的新电池体系（例如 LFP/石墨）

**场景**：我要从 NCA/G 换成 LFP/G，要改哪些东西？

### D.1 替换清单

| 改什么 | 文件 | 怎么改 |
| --- | --- | --- |
| **PE OCV 曲线** | `libquiv_aging/data/` | 新建 `LFPHalfCell.dat`，格式见 `03_inputs_guide.md §4` |
| **PE 摩尔体积** | `aging_kinetics.py` | 新建 `LFP_V_REL_COEFF`（LFP 体积变化 < 2%，近似常数） |
| **电极平衡 LR/OFS** | `my_lfp_cell.py` | 由 full-cell OCV vs half-cell OCV 拟合 |
| **初始容量 C0_PE** | 同上 | 由 C/20 放电测得 |
| **电压窗口** | 同上 | LFP 是 2.0–3.6 V 通常 |
| **老化常数** | 同上 | 需重新辨识 (工作流 C) |

### D.2 起步模板

```python
# libquiv_aging/my_lfp_cell.py  (改自 panasonic_ncr18650b.py)
from .aging_kinetics import (
    AgingModel, LAMParameters, MolarVolumeModel, PlatingParameters,
    ResistanceAgingParameters, SEIParameters, GRAPHITE_V_REL_COEFF
)
from .cell_model import EquivCircuitCell
from .lookup_tables import HalfCellThermo, ResistanceLUTs, default_data_path
import numpy as np


# LFP 的体积变化约 6.8% (AL vs FL) - 用 10 阶多项式占位, 数值仅示例
LFP_V_REL_COEFF = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0.068, 1.0])


def create_lfp_graphite_cell():
    anode = HalfCellThermo.from_dat_file(default_data_path("GraphiteAlawa.dat"))
    cathode = HalfCellThermo.from_dat_file(default_data_path("LFPHalfCell.dat"))   # 你提供
    r_luts = ResistanceLUTs.from_mat_file(default_data_path("ResistancesAlawa.mat"))  # 先复用, 后替换

    LR, OFS = 1.05, 3.0             # 来自你的 full-cell OCV 拟合
    dX_PE = 0.95                    # LFP 可用 X 范围
    dX_NE = 0.96
    CN_Ah = 3.0                     # 新电池 C/20 容量
    C0_PE = CN_Ah / dX_PE / (1 - OFS/100) * 3600
    C0_NE = C0_PE * LR * dX_PE / dX_NE

    aging = AgingModel(
        sei=SEIParameters(k_cal=0.04, k_cyc=0.47),      # 待辨识, 先用 NCA 默认
        plating=PlatingParameters(k_LP=1e-4),
        lam_pe=LAMParameters(k_cal=0.0, k_cyc=1e-4, gamma=1.0),  # LFP 的 LAM 通常小
        lam_ne=LAMParameters(k_cal=0.0, k_cyc=3.87e-4, gamma=0),
        resistance_aging=ResistanceAgingParameters(R_SEI=0.66, R_NE_0=0.02),
        mvol_ne=MolarVolumeModel(GRAPHITE_V_REL_COEFF),
        mvol_pe=MolarVolumeModel(LFP_V_REL_COEFF),
        Q0_SEI_NE=C0_PE * dX_PE * OFS / 100,
        Q0_LLI_NE=C0_PE * dX_PE * OFS / 100,
    )

    # 电阻闭包 - 沿用 NCR18650B 的形式
    def Rs_fn(T, X_ne, X_pe, I):
        c_rate = np.clip(-I * 3600.0 / (CN_Ah*3600), -4.0, 4.0)
        return (1.0 / CN_Ah) * r_luts.interp_Rs(c_rate, 0.0)
    # ... R1_fn, R2_fn 同理 ...

    cell = EquivCircuitCell(
        anode_thermo=anode, cathode_thermo=cathode, resistance_luts=r_luts,
        Rs_fn=Rs_fn, R1_fn=..., R2_fn=...,                   # 补齐
        C1=1000.0, C2=3000.0,
        fractionR1toRs=0.5, fractionR2toRs=0.5,
        aging_V_max=3.6, aging_V_min=2.0,
        aging_C0_PE=C0_PE, aging_C0_NE=C0_NE,
        aging_X0_PE=0.95, aging_X0_NE=0.01,
        aging=aging,
    )
    return cell
```

完成后在 `libquiv_aging/__init__.py` 加一行:

```python
from .my_lfp_cell import create_lfp_graphite_cell
__all__.append("create_lfp_graphite_cell")
```

跑一个 smoke test，确认 OCV 曲线和容量合理（LFP 满电 3.4–3.45 V）。

---

## 工作流 E：把模型接到控制/管理算法

**场景**：用这个模型做"虚拟电池"给 BMS 算法做回放测试。

```python
# workflow_E_virtual_battery.py
from libquiv_aging import create_panasonic_ncr18650b

class VirtualCell:
    """轻量封装: 给你的 BMS 代码一个熟悉的接口。"""
    def __init__(self):
        self._cell = create_panasonic_ncr18650b()
        self._cell.init(SOC=0.5)

    def apply_current(self, I_A: float, dt_s: float):
        """施加 dt 秒的恒流, 返回 (V, SOC, 真实可用容量 Ah)"""
        # 如果电压越界, 自动 rest
        safe = self._cell.V > 2.3 and self._cell.V < 4.3
        if not safe:
            return self._cell.V, self._cell.SOC, self._cell.C / 3600
        self._cell.CC(I_A, dt_s, 'V < 2.0 or V > 4.3')
        return self._cell.V, self._cell.SOC, self._cell.C / 3600

    @property
    def state_of_health(self) -> float:
        """SoH % = 当前可用容量 / 初始容量"""
        # 假定初始容量存在构造时刻
        return self._cell.C / self._C0 * 100 if hasattr(self, '_C0') else 100.0


if __name__ == '__main__':
    # 示范: 你的 BMS 算法 (随机 U(-2,+2) 电流) 驱动虚拟电池
    import numpy as np
    vb = VirtualCell()
    for step in range(100):
        I = np.random.uniform(-2, 2)
        V, SOC, C_Ah = vb.apply_current(I, dt_s=30)
        print(f"step {step}: I={I:+.2f}A, V={V:.3f}, SOC={SOC:.3f}")
```

这种模式下你的 BMS 能感受到电池慢慢老化（C_Ah 会减小），非常适合验证 SoH 估计算法。

---

## Claude Code 实用对话片段

### 导览型
> `从 examples/figure7_simulation.py 开始讲,逐步进入 cell_model.py, 讲清楚每次 cell.CC 被调用时内部到底发生什么。`

### 修改型
> `我要把 SEI 速率律从论文的 (36) 式改成 Ramadass 2004 的模型,格式是 ...,帮我改 aging_kinetics.py 并保持与旧接口兼容。`

### 诊断型
> `figure7_simulation.py 跑完 10 个循环, 最后 cell.aging_Q_PLA_NE=0, 但论文明明在 400 EFC 就出现镀锂了。帮我诊断。`

### 拓展型
> `我想加入温度耦合: 让 T 成为一个 state, 加入简单的热平衡 dT/dt = (I^2 R - h(T-T_env))/mc。需要改 cell_model.py 哪些地方? 列出改动 diff。`

---

## 下一步

这套文档加代码足够你：
1. 完整复现论文
2. 把模型迁移到自己的电池
3. 评估仿真与实验的差距
4. 用 Claude Code 的帮助做进一步的研究性扩展

遇到具体问题最高效的方式：**把相关代码片段 + 报错 + 你想达到的结果** 一起丢给 Claude Code，它能在 90% 的情况下直接给出可运行的修改。

祝研究顺利。
