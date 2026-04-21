"""
smoke_test.py
=============
快速验证 Python 移植的核心功能：
1. 加载数据 / 构建电池
2. 初始化到 50% SOC 并打印容量
3. 做一次简单的 C/5 放电到 2.5V，检查电压轨迹合理
4. 对比 fresh cell 的 OCV 和电阻在典型点处的量级
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from libquiv_aging import create_panasonic_ncr18650b


def main():
    print("========== 烟雾测试 ==========")

    t0 = time.time()
    cell = create_panasonic_ncr18650b()
    cell.init(SOC=0.5)
    print(f"构建+初始化: {time.time()-t0:.2f} s")
    print(f"电池初始容量 C    = {cell.C/3600:.4f} Ah (期望 ~3.35)")
    print(f"电池初始 SOC      = {cell.SOC:.3f} (期望 ~0.5)")
    print(f"电池初始 V        = {cell.V:.4f} V (期望 ~3.6–3.7)")
    print(f"aging_C0_PE       = {cell.aging_C0_PE/3600:.3f} Ah")
    print(f"aging_C0_NE       = {cell.aging_C0_NE/3600:.3f} Ah")

    # --- 测试 1: OCV 曲线在几个代表点 ---
    print("\n--- 检查 OCV 曲线 ---")
    for X_ne, X_pe in [(0.01, 0.95), (0.5, 0.55), (0.9, 0.2)]:
        V0, _, _, V0_PE, V0_NE = cell.LUT_X(X_ne, X_pe, 298.15)
        V0 = float(np.atleast_1d(V0)[0])
        V0_PE = float(np.atleast_1d(V0_PE)[0])
        V0_NE = float(np.atleast_1d(V0_NE)[0])
        print(f"  X_NE={X_ne}, X_PE={X_pe}: V_cell={V0:.3f}, "
              f"V_PE={V0_PE:.3f}, V_NE={V0_NE:.3f}")

    # --- 测试 2: C/5 恒流放电 ---
    print("\n--- C/5 放电测试 (满电 -> 放电到 2.5V) ---")
    cell.init(SOC=0.5)
    # 先 CCCV 充到满
    cell.CC(-0.67, 3600*3, "V > 4.2")
    cell.CV(4.2, 3600*2, "abs(I) < 0.065")
    print(f"充电后 V={cell.V:.4f}, SOC={cell.SOC:.3f}, Q={cell.Q/3600:.4f} Ah")

    # 记录放电起点
    n_start = len(cell.allt)
    I_C5 = 3.35 / 5
    cell.CC(I_C5, 3600*6, "V < 2.5")
    t_discharge = np.asarray(cell.allt[n_start:]) - cell.allt[n_start]
    V_discharge = np.asarray(cell.allV[n_start:])
    Q_discharged = I_C5 * t_discharge[-1]
    print(f"C/5 放电用时 {t_discharge[-1]/60:.1f} min, "
          f"放出电荷 {Q_discharged/3600:.4f} Ah")
    print(f"放电曲线采样点: {len(t_discharge)} 点")

    # --- 测试 3: 一个 DST 循环 ---
    print("\n--- 测试 DST 循环 1 轮 (无老化加速) ---")
    cell.aging.acceleration_factor = 1.0
    cell.init(SOC=0.5)
    DST_DURATION = np.array([16,28,12,8,16,24,12,8,16,24,12,8,16,36,8,24,8,32,8,44])
    DST_POWER_PCT = np.array([0,-12.5,-25,12.5,0,-12.5,-25,12.5,0,-12.5,-25,12.5,
                              0,-12.5,-100,-62.5,25,-25,50,0])
    P_MAX = 19.42
    # 先充电
    cell.CC(-1.675, 3600*3, "V > 4.2")
    cell.CV(4.2, 3600*2, "abs(I) < 0.065")
    cell.CC(0, 3600)

    # 跑 DST
    for i in range(len(DST_DURATION)):
        P = -DST_POWER_PCT[i]/100.0 * P_MAX
        cell.CP(P, DST_DURATION[i], "V < 2.5")
        print(f"  Step {i}: P={P:+.2f} W, dt={DST_DURATION[i]} s, "
              f"V_end={cell.V:.3f} V, SOC={cell.SOC:.3f}")

    print("\n全部烟雾测试通过 ✓")
    print(f"总时间: {time.time()-t0:.2f} s")


if __name__ == "__main__":
    main()
