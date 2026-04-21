"""
analysis_template.py
====================
**分析工作的起点模板**。复制这个文件，改名为 my_experiment.py，
在里面写你自己的仿真 + 分析逻辑。

本模板展示 3 个最常用的任务：
  1) 跑一轮 CCCV + DST, 保存所有轨迹到 npz
  2) 从 npz 重新加载并画标准 4 图
  3) 与实验数据对比并计算 RMSE

使用方式::

    python examples/analysis_template.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 允许在源码树下直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libquiv_aging import create_panasonic_ncr18650b, default_data_path


# ============================================================================
# 1. 用户可调参数 (快速改这里, 不要深入核心包)
# ============================================================================
NO_CYCLES = 5            # 要仿真的循环次数
ACC_FACTOR = 100         # 老化加速因子 (1=真实时间; 100=100 倍加速)
OUT_DIR = Path(__file__).resolve().parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)


# ============================================================================
# 2. 仿真主函数
# ============================================================================
def run_simulation() -> dict:
    """
    跑完整仿真, 返回一个 dict 包含所有关心的轨迹和每轮末态。
    """
    cell = create_panasonic_ncr18650b()
    cell.aging.acceleration_factor = ACC_FACTOR
    cell.init(SOC=0.5)
    C_0 = cell.C
    print(f"初始容量 C_0 = {C_0/3600:.4f} Ah")

    EFC_per_cycle = [0.0]
    C_per_cycle = [cell.C]
    R_per_cycle = [
        1 / (3.35 / 3 - 3.35 / 5) *
        (-cell.calculate_steady_state_voltage(298, 3.35 / 3, 0.5)
         + cell.calculate_steady_state_voltage(298, 3.35 / 5, 0.5))
    ]

    t0 = time.time()
    for n in range(1, NO_CYCLES + 1):
        n_save = len(cell.allt)

        # ---- CCCV 充电 ----
        cell.CC(-1.675 / 50, 10, "V > 4.2")
        cell.CC(-1.675, 7200, "V > 4.2")
        cell.CV(4.2, 60, "abs(I) < 0.065")
        cell.CV(4.2, 7200, "abs(I) < 0.065")
        # ---- 静置 2h ----
        cell.CC(0, 3600 * 2)
        # ---- 简化放电 (用 C/2 恒流, 而不是 DST - 快 10 倍) ----
        cell.CC(1.675, 7200, "V < 2.5")
        # ---- 静置 4h ----
        cell.CC(0, 3600 * 4)

        # 记录每轮末态
        t_full = np.asarray(cell.allt[n_save - 1:])
        I_full = np.asarray(cell.allI[n_save - 1:])
        Q_cycle = ACC_FACTOR * np.trapezoid(np.abs(I_full), t_full) / 2
        EFC_per_cycle.append(EFC_per_cycle[-1] + Q_cycle / C_0)
        C_per_cycle.append(cell.C)
        R_per_cycle.append(
            1 / (3.35 / 3 - 3.35 / 5) *
            (-cell.calculate_steady_state_voltage(298, 3.35 / 3, 0.5)
             + cell.calculate_steady_state_voltage(298, 3.35 / 5, 0.5))
        )
        print(f"  Cycle {n}: EFC={EFC_per_cycle[-1]:.1f}, "
              f"C={cell.C/3600:.3f} Ah, R/R0={R_per_cycle[-1]/R_per_cycle[0]*100:.1f}%")

    print(f"总仿真时间: {time.time() - t0:.1f} s")

    # 打包结果
    return dict(
        # 每轮末态
        EFC=np.asarray(EFC_per_cycle),
        C_per_cycle=np.asarray(C_per_cycle),
        R_per_cycle=np.asarray(R_per_cycle),
        C_0=C_0,
        # 完整时间轨迹
        t=np.asarray(cell.allt),
        V=np.asarray(cell.allV),
        I=np.asarray(cell.allI),
        SOC=np.asarray(cell.allSOC),
        # 老化状态轨迹
        Q_LAM_PE=np.asarray(cell.aging_allQ_LAM_PE),
        Q_LAM_NE=np.asarray(cell.aging_allQ_LAM_NE),
        Q_LLI_NE=np.asarray(cell.aging_allQ_LLI_NE),
        Q_SEI_NE=np.asarray(cell.aging_allQ_SEI_NE),
        Q_PLA_NE=np.asarray(cell.aging_allQ_PLA_NE),
    )


# ============================================================================
# 3. 持久化 / 加载
# ============================================================================
def save_results(results: dict, filename: str = "run_latest.npz"):
    """保存为 npz (比 csv 快, 压缩, 保留 float64 精度)"""
    fp = OUT_DIR / filename
    np.savez_compressed(fp, **results)
    print(f"结果已保存: {fp}  ({fp.stat().st_size / 1024:.1f} KB)")
    return fp


def load_results(fp: Path) -> dict:
    """从 npz 加载。"""
    data = np.load(fp)
    return {k: data[k] for k in data.files}


# ============================================================================
# 4. 绘图与评估
# ============================================================================
def plot_standard_4_panels(results: dict, save_to: Path | None = None):
    """论文 Figure 7a-d 的对应"""
    fig, axs = plt.subplots(2, 2, figsize=(10, 7))

    # (a) 归一化容量
    axs[0, 0].plot(results['EFC'], results['C_per_cycle'] / results['C_0'] * 100,
                   'o-', linewidth=2)
    axs[0, 0].set_xlabel('Equivalent full cycles')
    axs[0, 0].set_ylabel('Normalized capacity / %')
    axs[0, 0].grid(True, alpha=0.3)
    axs[0, 0].set_title('(a) Capacity fade')

    # (b) 归一化内阻
    axs[0, 1].plot(results['EFC'], results['R_per_cycle'] / results['R_per_cycle'][0] * 100,
                   'o-', linewidth=2, color='C1')
    axs[0, 1].set_xlabel('Equivalent full cycles')
    axs[0, 1].set_ylabel('Normalized resistance / %')
    axs[0, 1].grid(True, alpha=0.3)
    axs[0, 1].set_title('(b) Internal resistance')

    # (c) 退化模式 - 插值到每轮末态
    t_trace = np.linspace(results['t'][0], results['t'][-1], len(results['EFC']))
    LLI = np.interp(t_trace, results['t'], results['Q_LLI_NE']) / 3600
    LAMPE = np.interp(t_trace, results['t'], results['Q_LAM_PE']) / 3600
    LAMNE = np.interp(t_trace, results['t'], results['Q_LAM_NE']) / 3600
    axs[1, 0].plot(results['EFC'], LLI - LLI[0], 'o-', label='LLI')
    axs[1, 0].plot(results['EFC'], LAMPE - LAMPE[0], 's-', label='LAM$_{PE}$')
    axs[1, 0].plot(results['EFC'], LAMNE - LAMNE[0], '^-', label='LAM$_{NE}$')
    axs[1, 0].set_xlabel('Equivalent full cycles')
    axs[1, 0].set_ylabel('Degradation mode / Ah')
    axs[1, 0].legend()
    axs[1, 0].grid(True, alpha=0.3)
    axs[1, 0].set_title('(c) Degradation modes')

    # (d) 退化机理 (SEI vs Plating)
    SEI = np.interp(t_trace, results['t'], results['Q_SEI_NE']) / 3600
    PLA = np.interp(t_trace, results['t'], results['Q_PLA_NE']) / 3600
    axs[1, 1].plot(results['EFC'], SEI, 'o-', label='SEI')
    axs[1, 1].plot(results['EFC'], PLA, 's-', label='Plating')
    axs[1, 1].set_xlabel('Equivalent full cycles')
    axs[1, 1].set_ylabel('Degradation / Ah')
    axs[1, 1].legend()
    axs[1, 1].grid(True, alpha=0.3)
    axs[1, 1].set_title('(d) Degradation mechanisms')

    fig.tight_layout()
    if save_to:
        fig.savefig(save_to, dpi=150)
        print(f"图片已保存: {save_to}")
    return fig


def compare_with_experiment(results: dict, cap_exp_csv: str | None = None):
    """
    与实验数据比较 + 计算 RMSE。
    默认用 Dubarry 2019 的数据。
    """
    if cap_exp_csv is None:
        cap_exp_csv = default_data_path("Dubarry_2019_Batteries_Capacity_Fig__3a.csv")

    exp = pd.read_csv(cap_exp_csv, skiprows=2, header=None).dropna().values
    EFC_exp = exp[:, 0] / 3.35
    Cap_exp = exp[:, 1]

    # 仿真插值到实验 EFC 点
    Cap_sim_pct = results['C_per_cycle'] / results['C_0'] * 100
    f_interp = np.interp(EFC_exp, results['EFC'], Cap_sim_pct,
                         left=np.nan, right=np.nan)
    mask = ~np.isnan(f_interp)
    if mask.sum() == 0:
        print("仿真 EFC 范围未覆盖任何实验点")
        return
    rmse = float(np.sqrt(np.mean((f_interp[mask] - Cap_exp[mask]) ** 2)))
    mae = float(np.mean(np.abs(f_interp[mask] - Cap_exp[mask])))

    # 画对比图
    fig, ax = plt.subplots()
    ax.plot(results['EFC'], Cap_sim_pct, '-', linewidth=2, label='Simulation')
    ax.plot(EFC_exp, Cap_exp, 'ko', markersize=7, label='Dubarry 2019 Exp.')
    ax.set_xlabel('Equivalent full cycles')
    ax.set_ylabel('Normalized capacity / %')
    ax.set_title(f'Comparison (RMSE = {rmse:.2f}%, MAE = {mae:.2f}%)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    print(f"\n--- 实验对比 ---")
    print(f"覆盖实验点数: {mask.sum()}/{len(EFC_exp)}")
    print(f"RMSE = {rmse:.3f} %")
    print(f"MAE  = {mae:.3f} %")

    return rmse, mae, fig


# ============================================================================
# 5. Main
# ============================================================================
if __name__ == "__main__":
    # 任务 1: 跑仿真
    results = run_simulation()

    # 任务 2: 保存轨迹
    fp = save_results(results, "analysis_template_run.npz")

    # 任务 3: 画 4 图
    plot_standard_4_panels(results, save_to=OUT_DIR / "analysis_template_4panels.png")

    # 任务 4: 与实验对比
    compare_with_experiment(results)

    plt.show()

    print("\n完成。修改此文件开始你自己的分析。")
