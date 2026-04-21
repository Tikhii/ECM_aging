"""
figure7_simulation.py
=====================
复现论文 Figure 7 的循环老化仿真 (DST 协议驱动)。

对应 MATLAB 源文件 ``Figure7Simulation.m``。用法::

    cd /path/to/libquiv_aging_py
    python examples/figure7_simulation.py

核心流程:
1. 创建 Panasonic NCR18650B 电池对象，初始化到 50% SOC。
2. 循环 N 次:
   a. CCCV 充电到 4.2 V 截止（I_cutoff = 65 mA）。
   b. 静置 2 h (模拟 RPT 之前的弛豫)。
   c. 连续运行 DST 动态应力测试周期直到电压降到 2.5 V。
   d. 静置 4 h。
3. 每次循环后记录容量、内阻、退化模式、SEI/镀锂。
4. 与 Dubarry 2019 实验数据对照绘图。

用户可调 ``NO_CYCLES`` 与 ``ACC_FACTOR`` 来缩短仿真时间:
- NO_CYCLES = 500, ACC_FACTOR = 1 : 完整论文设置 (~数小时)
- NO_CYCLES = 10,  ACC_FACTOR = 50: 快速测试 (~数分钟)，等价于 ~500 个完整循环
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 允许直接在源码树下运行
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libquiv_aging import create_panasonic_ncr18650b, default_data_path


# =============================================================================
# 用户可调参数
# =============================================================================
NO_CYCLES = 10              # 要仿真的循环次数
ACC_FACTOR = 50             # 老化加速因子 (乘到所有老化速率上)

# 工作条件（全部来自 MATLAB 源脚本 Figure7Simulation.m）
V_MAX = 4.2           # 充电截止电压 [V]
V_MIN = 2.5           # 放电截止电压 [V]
I_CHG = 1.6750        # 充电电流 [A]   (C/2)
I_CUTOFF = 0.065      # CV 阶段截止电流 [A]
P_MAX = 19.42         # DST 100% 功率对应的实际功率 [W]
SOC_IR = 0.5          # 计算内阻所用的 SOC

# DST 时间/功率 (取自 USABC EV 测试手册, Revision 2, 1996)
DST_DURATION = np.array(
    [16, 28, 12, 8, 16, 24, 12, 8, 16, 24, 12, 8, 16, 36, 8, 24, 8, 32, 8, 44]
)   # [s]
DST_POWER_PERCENT = np.array(
    [0, -12.5, -25, 12.5, 0, -12.5, -25, 12.5,
     0, -12.5, -25, 12.5, 0, -12.5, -100, -62.5, 25, -25, 50, 0]
)   # [%]


# =============================================================================
# 主仿真
# =============================================================================
def main():
    # ---- 1. 创建电池并初始化 --------------------------------------------
    cell = create_panasonic_ncr18650b()
    cell.aging.acceleration_factor = ACC_FACTOR
    cell.init(SOC=0.5)
    C_0 = cell.C
    print(f"初始容量: {C_0 / 3600:.5f} Ah")
    print(f"加速因子: {ACC_FACTOR}, 循环次数: {NO_CYCLES}")

    # 计算"新电池"的内阻作为参考 (论文式 30)
    def compute_IR() -> float:
        V_C3 = cell.calculate_steady_state_voltage(298.0, 3.35 / 3, SOC_IR)
        V_C5 = cell.calculate_steady_state_voltage(298.0, 3.35 / 5, SOC_IR)
        return 1.0 / (3.35 / 3 - 3.35 / 5) * (-V_C3 + V_C5)

    C_trace = [cell.C]
    Q_exch = [0.0]                 # 累积交换电荷 [A·s]
    R_trace = [compute_IR()]
    t_trace = [cell.t]
    last_hist_end = len(cell.allt) - 1   # 上一个 cycle 末尾在 all* 中的位置

    # ---- 2. 循环仿真 ----------------------------------------------------
    t_start_wall = time.time()
    for n in range(1, NO_CYCLES + 1):
        n_save = len(cell.allt)

        print(f"\n--- Cycle {n}/{NO_CYCLES} ---")
        # ---- a. CCCV 充电 ------------------------------------------------
        # 小电流 10 s 先进行数值"引导"
        cell.CC(-I_CHG / 50, 10, f"V > {V_MAX}")
        # 主充电
        cell.CC(-I_CHG, 3.35 / I_CHG * 3600 * 1.5, f"V > {V_MAX}")
        # CV 初始短 60 s
        cell.CV(V_MAX, 60, f"abs(I) < {I_CUTOFF}")
        # CV 主阶段
        cell.CV(V_MAX, 3600 * 2, f"abs(I) < {I_CUTOFF}")

        # ---- b. 静置 2 h --------------------------------------------------
        cell.CC(0.0, 3600 * 2)

        # ---- c. 循环 DST 放电直到达截止 -----------------------------------
        reached_end = False
        while not reached_end:
            while cell.V > V_MIN:
                for k in range(len(DST_DURATION)):
                    P_step = -DST_POWER_PERCENT[k] / 100.0 * P_MAX
                    cell.CP(P_step, DST_DURATION[k], f"V < {V_MIN}")
                    if cell.V < V_MIN:
                        reached_end = True
                        break
                if reached_end:
                    break

        # ---- d. 静置 4 h --------------------------------------------------
        cell.CC(0.0, 3600 * 4)

        # ---- e. 存储结果 --------------------------------------------------
        # 积分本 cycle 期间 |I| 得到交换的总电荷
        t_segment = np.asarray(cell.allt[n_save:])
        I_segment = np.asarray(cell.allI[n_save:])
        # 把 n_save-1 位置 (上阶段末) 的 (t, I) 也包含进来，保证积分起点对齐
        t_full = np.asarray(cell.allt[n_save - 1:])
        I_full = np.asarray(cell.allI[n_save - 1:])
        Q_cycle = ACC_FACTOR * np.trapezoid(np.abs(I_full), t_full)
        Q_exch.append(Q_exch[-1] + Q_cycle / 2.0)

        C_trace.append(cell.C)
        R_trace.append(compute_IR())
        t_trace.append(cell.t)

        print(
            f"  末态容量 = {cell.C / 3600:.4f} Ah  |  "
            f"EFC = {Q_exch[-1] / C_0:.2f}  |  "
            f"墙钟用时 = {time.time() - t_start_wall:.1f} s"
        )

    print(f"\n最终容量: {cell.C / 3600:.5f} Ah")
    print(f"总墙钟时间: {time.time() - t_start_wall:.1f} s")

    # ---- 3. 后处理和绘图 -------------------------------------------------
    EFC_sim = np.asarray(Q_exch) / C_0
    C_arr = np.asarray(C_trace)
    R_arr = np.asarray(R_trace)

    # 读入实验数据 (位于包内 data/ 目录)
    data_dir = Path(default_data_path("GraphiteAlawa.dat")).parent
    cap_exp = pd.read_csv(
        data_dir / "Dubarry_2019_Batteries_Capacity_Fig__3a.csv",
        skiprows=2, header=None,
    ).dropna().values
    ir_exp = pd.read_csv(
        data_dir / "Dubarry_2019_Batteries_IR_Fig__3b.csv",
        skiprows=2, header=None,
    ).dropna().values
    EFC_cap_exp = cap_exp[:, 0] / 3.35
    EFC_ir_exp = ir_exp[:, 0] / 3.35

    # --- Figure 1: 归一化容量 ---
    fig1, ax = plt.subplots()
    ax.plot(EFC_sim, C_arr / C_0 * 100, "-", linewidth=2, label="Simulation")
    ax.plot(EFC_cap_exp, cap_exp[:, 1], "o--", linewidth=1.5, markersize=8, label="Experiment")
    ax.set_xlabel("Equivalent full cycles / -")
    ax.set_ylabel("Normalized capacity / %")
    ax.set_ylim([75, 100.5])
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig1.tight_layout()

    # --- Figure 2: 归一化内阻 ---
    fig2, ax = plt.subplots()
    ax.plot(EFC_sim, R_arr / R_arr[0] * 100, "-", linewidth=2, label="Simulation")
    ax.plot(EFC_ir_exp, ir_exp[:, 1] + 100, "o--", linewidth=1.5, markersize=8, label="Experiment")
    ax.set_xlabel("Equivalent full cycles / -")
    ax.set_ylabel("Normalized resistance / %")
    ax.set_xlim([0, 500])
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig2.tight_layout()

    # --- Figure 3: 退化模式对比 (LAM_PE, LAM_NE, LLI) ---
    dX_PE_alawa = 0.7710
    dX_NE_alawa = 0.9600
    dm_exp = pd.read_csv(
        data_dir / "Dubarry_2019_Batteries_Degradation_Modes_DST_Fig__9.csv",
        skiprows=2, header=None,
    ).values
    # 第 0/2/4/6 列是交换电荷 (Ah), 第 1/3/5/7 列分别是 LLI, LAM_PE, RDFNE, LAM_NE 的 %
    EFC_exp_LLI = dm_exp[:, 0] / 3.35
    EFC_exp_PE = dm_exp[:, 2] / 3.35
    EFC_exp_NE = dm_exp[:, 6] / 3.35
    exp_LLI_Ah = dm_exp[:, 1] / 100.0 * cell.aging_C0_PE / 3600.0 * dX_PE_alawa
    exp_LAMPE_Ah = dm_exp[:, 3] / 100.0 * cell.aging_C0_PE / 3600.0 * dX_PE_alawa
    exp_LAMNE_Ah = dm_exp[:, 7] / 100.0 * cell.aging_C0_NE / 3600.0 * dX_NE_alawa

    # 仿真端：在 t_trace 处插值 all 轨迹
    sim_LLI_all = np.asarray(cell.aging_allQ_LLI_NE) + np.asarray(cell.aging_allQ_LLI_PE)
    sim_LAMPE_all = np.asarray(cell.aging_allQ_LAM_PE)
    sim_LAMNE_all = np.asarray(cell.aging_allQ_LAM_NE)
    t_all = np.asarray(cell.allt)

    t_trace_arr = np.asarray(t_trace)
    sim_LLI = (np.interp(t_trace_arr, t_all, sim_LLI_all)
               - sim_LLI_all[0]) / 3600.0
    sim_LAMPE = (np.interp(t_trace_arr, t_all, sim_LAMPE_all)
                 - sim_LAMPE_all[0]) / 3600.0
    sim_LAMNE = (np.interp(t_trace_arr, t_all, sim_LAMNE_all)
                 - sim_LAMNE_all[0]) / 3600.0

    fig3, ax = plt.subplots()
    ax.plot(EFC_sim, sim_LAMPE, "-", linewidth=2, label="LAM$_{PE}$ Sim.")
    ax.plot(EFC_sim, sim_LAMNE, "-", linewidth=2, label="LAM$_{NE}$ Sim.")
    ax.plot(EFC_sim, sim_LLI,  "-", linewidth=2, label="LLI Sim.")
    ax.plot(EFC_exp_PE, exp_LAMPE_Ah, "o--", markersize=6, alpha=0.7, label="LAM$_{PE}$ Exp.")
    ax.plot(EFC_exp_NE, exp_LAMNE_Ah, "s--", markersize=6, alpha=0.7, label="LAM$_{NE}$ Exp.")
    ax.plot(EFC_exp_LLI, exp_LLI_Ah, "^--", markersize=6, alpha=0.7, label="LLI Exp.")
    ax.set_xlabel("Equivalent full cycles / -")
    ax.set_ylabel("Degradation mode / Ah")
    ax.set_ylim([0, 1.5])
    ax.legend(loc="upper left", ncol=2)
    ax.grid(True, alpha=0.3)
    fig3.tight_layout()

    # --- Figure 4: 退化机制 (SEI, Plating 随 EFC) ---
    sim_SEI_all = np.asarray(cell.aging_allQ_SEI_NE)
    sim_PLA_all = np.asarray(cell.aging_allQ_PLA_NE)
    sim_SEI = np.interp(t_trace_arr, t_all, sim_SEI_all) / 3600.0
    sim_PLA = np.interp(t_trace_arr, t_all, sim_PLA_all) / 3600.0

    fig4, ax = plt.subplots()
    ax.plot(EFC_sim, sim_SEI, "-", linewidth=2, label="SEI")
    ax.plot(EFC_sim, sim_PLA, "-", linewidth=2, label="Plating")
    ax.set_xlabel("Equivalent full cycles / -")
    ax.set_ylabel("Degradation / Ah")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig4.tight_layout()

    # 保存图片
    outdir = Path(__file__).resolve().parent / "outputs"
    outdir.mkdir(exist_ok=True)
    fig1.savefig(outdir / "figure7a_capacity.png", dpi=150)
    fig2.savefig(outdir / "figure7b_resistance.png", dpi=150)
    fig3.savefig(outdir / "figure7c_degradation_modes.png", dpi=150)
    fig4.savefig(outdir / "figure7d_mechanisms.png", dpi=150)
    print(f"\n图片已保存到: {outdir}")

    plt.show()


if __name__ == "__main__":
    main()
