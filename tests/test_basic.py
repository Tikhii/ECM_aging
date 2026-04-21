"""
test_basic.py
=============
最小可运行测试集：任何破坏性改动都应该在这里首先被捕获。

运行方式::

    pytest tests/ -v
"""
from __future__ import annotations

import numpy as np
import pytest

from libquiv_aging import create_panasonic_ncr18650b


# ============================================================
# Fixtures: 每个测试各自建一个电池以避免状态污染
# ============================================================
@pytest.fixture
def fresh_cell():
    cell = create_panasonic_ncr18650b()
    cell.init(SOC=0.5)
    return cell


# ============================================================
# 1. 基础初始化
# ============================================================
class TestInitialization:
    def test_capacity_in_expected_range(self, fresh_cell):
        """标称容量应接近 3.35 Ah (模型参数化误差 < 3%)"""
        C_Ah = fresh_cell.C / 3600.0
        assert 3.3 < C_Ah < 3.5, f"容量 {C_Ah:.3f} Ah 超出预期范围"

    def test_initial_SOC(self, fresh_cell):
        assert abs(fresh_cell.SOC - 0.5) < 1e-3

    def test_initial_voltage_reasonable(self, fresh_cell):
        """50% SOC 下 NCA/Graphite 电池开路电压应在 3.5-3.8 V"""
        assert 3.5 < fresh_cell.V < 3.8

    def test_both_electrodes_positive_capacity(self, fresh_cell):
        assert fresh_cell.aging_C0_PE > 0
        assert fresh_cell.aging_C0_NE > 0
        # 绝对电极容量中 C_PE > C_NE (因为 alawa dX_PE_alawa=0.771 < dX_NE_alawa=0.96)
        # 但两者差距 < 30%
        ratio = fresh_cell.aging_C0_PE / fresh_cell.aging_C0_NE
        assert 1.0 < ratio < 1.5, f"C_PE/C_NE = {ratio:.3f} 不合理"


# ============================================================
# 2. CC/CV/CP 三种仿真模式的基本正确性
# ============================================================
class TestSimulationModes:
    def test_cc_discharge_reduces_SOC(self, fresh_cell):
        SOC_0 = fresh_cell.SOC
        fresh_cell.CC(I=1.0, duration_s=60)  # 1A 放电 1 分钟
        assert fresh_cell.SOC < SOC_0

    def test_cc_charge_increases_SOC(self, fresh_cell):
        SOC_0 = fresh_cell.SOC
        fresh_cell.CC(I=-1.0, duration_s=60)
        assert fresh_cell.SOC > SOC_0

    def test_cc_event_stops_at_threshold(self, fresh_cell):
        """CC 充电到 V>4.2 应该在 V=4.2 附近停止"""
        fresh_cell.CC(I=-1.675, duration_s=7200, break_criterion="V > 4.2")
        assert abs(fresh_cell.V - 4.2) < 0.01

    def test_cv_holds_voltage(self, fresh_cell):
        fresh_cell.CV(V=4.0, duration_s=120)
        assert abs(fresh_cell.V - 4.0) < 1e-3

    def test_cp_maintains_power(self, fresh_cell):
        """CP 放电时 P = I·V 应与设定值一致"""
        fresh_cell.CP(P=5.0, duration_s=30)
        P_actual = fresh_cell.I * fresh_cell.V
        assert abs(P_actual - 5.0) < 0.05

    def test_rest_preserves_state(self, fresh_cell):
        """静置 (I=0) 应该保留 SOC"""
        SOC_before = fresh_cell.SOC
        fresh_cell.CC(I=0.0, duration_s=600)
        assert abs(fresh_cell.SOC - SOC_before) < 1e-3
        assert abs(fresh_cell.I) < 1e-5


# ============================================================
# 3. 完整 CCCV 循环 (闭环自洽性)
# ============================================================
class TestCCCVCycle:
    def test_cccv_charge_reaches_full(self, fresh_cell):
        fresh_cell.CC(-1.675, 7200, "V > 4.2")
        fresh_cell.CV(4.2, 7200, "abs(I) < 0.065")
        # 充电结束后 SOC 应接近 1.0
        assert fresh_cell.SOC > 0.99
        assert abs(fresh_cell.V - 4.2) < 1e-3
        assert abs(fresh_cell.I) < 0.07

    def test_full_discharge_to_cutoff(self, fresh_cell):
        """标称容量的 C/5 放电应放出接近额定电荷"""
        # 先充到满
        fresh_cell.CC(-1.675, 7200, "V > 4.2")
        fresh_cell.CV(4.2, 7200, "abs(I) < 0.065")
        Q_at_full = fresh_cell.Q
        # C/5 放电到 2.5V
        fresh_cell.CC(3.35 / 5, 3600 * 6, "V < 2.5")
        Q_discharged = Q_at_full - fresh_cell.Q  # 放出电荷 (正值)
        C_Ah = Q_discharged / 3600.0
        assert 3.2 < C_Ah < 3.5, f"放出容量 {C_Ah:.3f} Ah 偏离预期"


# ============================================================
# 4. 老化模型 —— 加速因子下应可见老化
# ============================================================
class TestAging:
    def test_cell_degrades_after_cycling(self):
        """加速老化因子下，几次循环后容量应降低"""
        cell = create_panasonic_ncr18650b()
        cell.aging.acceleration_factor = 100.0
        cell.init(SOC=0.5)
        C_0 = cell.C

        # 一次完整 CCCV + C/2 放电
        for _ in range(2):
            cell.CC(-1.675, 7200, "V > 4.2")
            cell.CV(4.2, 7200, "abs(I) < 0.065")
            cell.CC(0, 60)
            cell.CC(3.35 / 2, 3600 * 3, "V < 2.5")
            cell.CC(0, 60)

        C_end = cell.C
        loss_pct = (1.0 - C_end / C_0) * 100
        assert loss_pct > 0.5, f"容量损失仅 {loss_pct:.2f}%，老化似乎未起作用"
        # 同时检查老化状态变量非零
        assert cell.aging_Q_LAM_PE > 0
        assert cell.aging_Q_SEI_NE > cell.aging.Q0_SEI_NE


# ============================================================
# 5. 查找表 / LUT 的往返正确性
# ============================================================
class TestLookupTables:
    def test_ocv_monotone_with_SOC(self, fresh_cell):
        """对于 NCA/G 电池，OCV 应随 SOC 单调递增"""
        SOCs = np.linspace(0.05, 0.95, 15)
        voltages = []
        for soc in SOCs:
            cell = create_panasonic_ncr18650b()
            cell.init(SOC=float(soc))
            voltages.append(cell.V)
        voltages = np.asarray(voltages)
        diffs = np.diff(voltages)
        assert np.all(diffs > -0.02), "OCV 应大致随 SOC 递增"

    def test_resistance_nonzero(self, fresh_cell):
        """典型工况下总电阻应在合理范围 (10 - 500 mΩ)"""
        R = fresh_cell._R_total_with_aging(T=298.0, X_NE=0.5, X_PE=0.5, I=1.0)
        assert 0.01 < R < 0.5, f"R_total = {R:.4f} Ω 不合理"
