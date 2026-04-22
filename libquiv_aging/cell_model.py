"""
cell_model.py
=============
等效电路电池模型主类 ``EquivCircuitCell``。

对应 Matlab 源文件 ``LIBquivAging.m`` 中的 ``classdef LIBquivAging``。

---------------------------------------------------------------
模型 (DAE 系统) 概述
---------------------------------------------------------------
论文式 (1)-(30) 描述的一套微分代数方程系统，共 18 个状态变量：

   # | 变量        | 物理含义                                  | 方程类型
   --+--------------+-------------------------------------------+---------
   1 | Q            | 外部累积电荷 (cell charge)               | 微分
   2 | I            | 总电流 (正为放电)                         | 代数
   3 | SOC          | 荷电状态                                  | 代数
   4 | V            | 电池端电压                                | 代数
   5 | T            | 温度 (本实现为常数 T_ambient)             | 代数
   6 | V_RC1        | NE 的 RC 动态电压                         | 微分
   7 | V_RC2        | PE 的 RC 动态电压                         | 微分
   8 | V_RC3        | 额外 RC (本论文未使用)                    | 微分
   9 | V_hys        | 滞回电压 (本实现为 0)                     | 代数
  10 | SOC_surf     | "表面" SOC (= Q/C)                        | 代数
  11 | Q_PE         | PE 半电池电荷                             | 微分
  12 | Q_NE         | NE 半电池电荷                             | 微分
  13 | Q_LAM_PE     | PE 活性材料损失累积                       | 微分
  14 | Q_LAM_NE     | NE 活性材料损失累积                       | 微分
  15 | Q_LLI_PE     | PE 侧锂库存损失累积 (本论文中速率恒为 0)  | 微分
  16 | Q_LLI_NE     | NE 侧锂库存损失累积 (含 SEI+PLA)          | 微分
  17 | Q_SEI_NE     | SEI 贡献的电荷                            | 微分
  18 | Q_PLA_NE     | 不可逆镀锂贡献的电荷                      | 微分

---------------------------------------------------------------
Python 端的求解策略
---------------------------------------------------------------
由于 scipy 原生不支持质量矩阵式 DAE，我们在每次 RHS 评估时**显式地**
求解全部代数方程，将 18 维 DAE 化归为 12 维显式 ODE：

* 在 CC 模式下，I 由用户给定 ⇒ 其余代数方程都是直接赋值；
* 在 CV 模式下，V 由用户给定 ⇒ I 从代数方程
      V = V0 - I·R_total - V_RC1 - V_RC2 - V_RC3
  显式求解 (R_total 对 I 弱依赖，用 1-2 次 Newton 迭代)；
* 在 CP 模式下，P 由用户给定 ⇒ I 满足二次方程
      P = I · V_cell(I)
  同样通过 brentq/Newton 求解。

时间积分使用 ``scipy.integrate.solve_ivp`` 的 BDF 方法 (隐式多步法，适合刚性系统)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from . import aging_kinetics as ak
from .aging_kinetics import AgingModel
from .lookup_tables import (
    HalfCellThermo,
    ResistanceLUTs,
    open_circuit_voltage,
)


# =============================================================================
# 电池类
# =============================================================================
@dataclass
class EquivCircuitCell:
    """
    老化敏感等效电路电池模型。

    用户典型使用流程::

        cell = create_panasonic_ncr18650b()   # 从 parameterization 模块
        cell.init(SOC=0.5)                     # 初始化状态
        cell.CC(I=-1.6, duration_s=3600, break_criterion='V > 4.2')
        cell.CV(V=4.2, duration_s=3600, break_criterion='abs(I) < 0.065')
        cell.CP(P=-10.0, duration_s=60)
        print(cell.C / 3600, 'Ah')

    字段分为三大类：公开参数（可配置）、私有状态（仿真期间更新）、
    历史轨迹（``all*`` 数组，供绘图使用）。
    """

    # ---- 热力学 LUT ---------------------------------------------------------
    anode_thermo: HalfCellThermo
    cathode_thermo: HalfCellThermo
    resistance_luts: ResistanceLUTs

    # ---- 电阻/电容 (lambda 形式便于保持与 MATLAB 一致的调用签名) ---------
    # 签名: R(T, X_NE, X_PE, I) -> float [Ω]
    Rs_fn: Callable[[float, float, float, float], float]
    R1_fn: Callable[[float, float, float, float], float]
    R2_fn: Callable[[float, float, float, float], float]
    R3_fn: Callable[[float, float, float, float], float] = field(
        default=lambda T, X_NE, X_PE, I: 0.0
    )

    C1: float = 0.0      # NE 侧 RC 电容 [F]
    C2: float = 0.0      # PE 侧 RC 电容 [F]
    C3: float = 0.0      # 额外 RC (未使用)

    # ---- 电极电阻的 static / dynamic 劈分因子 ------------------------------
    # fractionR1toRs : float
    #     R_NE 电极电阻中分配给 static 分支（串联无电容）的比例，
    #     余下部分进入 dynamic 分支（与 C1 并联）。范围 (0, 1)，
    #     默认 0.5（论文 Panasonic NCR18650B 的 FIT-3 结果）。
    #
    #     命名陷阱：字段名中的 "toRs" 是历史遗留（延续 MATLAB 原版），
    #     不表示与 R_s（电解液/集流体串联电阻）的任何语义关系。
    #     R_s 和电极电阻在模型中是物理上独立的对象——R_s 假设不退化
    #     ($f_{R,s}=1$)，而电极电阻通过 $f_{R,NE}$/$f_{R,PE}$ 随
    #     SEI、LAM、镀锂演化。详见 docs/06_parameter_sourcing.md §3.3。
    #
    # fractionR2toRs : float
    #     R_PE 的同类参数（对称版本）。命名陷阱同上。
    fractionR1toRs: float = 0.0
    fractionR2toRs: float = 0.0
    fractionR3toRs: float = 0.0

    # ---- 环境和初始电极容量 -------------------------------------------------
    T_ambient: float = 298.15
    aging_V_max: float = 4.2
    aging_V_min: float = 2.5

    aging_C0_PE: float = 0.0         # 初始 PE 总容量 [A·s]
    aging_C0_NE: float = 0.0         # 初始 NE 总容量 [A·s]

    aging_X0_PE: float = 0.95        # 出厂时 PE 的锂化学计量数
    aging_X0_NE: float = 0.01        # 出厂时 NE 的锂化学计量数

    # ---- 老化模型 (策略对象) -----------------------------------------------
    aging: AgingModel = None

    # ---- 求解器参数 ---------------------------------------------------------
    tolerance_rel: float = 1e-8
    tolerance_abs: float = 1e-8

    # ==================================================================== #
    # 私有（运行时）状态变量 —— 与 MATLAB 同名对齐，便于对照阅读
    # ==================================================================== #
    # 当前标量状态（一次仿真结束后的末态）
    SOC: float = 0.0
    I: float = 0.0
    V: float = 0.0
    Q: float = 0.0               # 外部累积电荷 [A·s]
    T: float = 298.15
    V_RC1: float = 0.0
    V_RC2: float = 0.0
    V_RC3: float = 0.0
    V_hys: float = 0.0
    t: float = 0.0
    SOC_surf: float = 0.0

    aging_Q_PE: float = 0.0
    aging_Q_NE: float = 0.0
    aging_Q_LAM_PE: float = 0.0
    aging_Q_LAM_NE: float = 0.0
    aging_Q_LLI_PE: float = 0.0
    aging_Q_LLI_NE: float = 0.0
    aging_Q_SEI_NE: float = 0.0
    aging_Q_PLA_NE: float = 0.0

    # 电池容量 & 边界化学计量 (由 agingCalibrateQ_SOC_X_CN 填充)
    C: float = 0.0                   # 实时总可用容量 [A·s]
    aging_Q_SOC_0: float = 0.0
    aging_Q_SOC_1: float = 0.0
    X_an_lower: float = 0.0
    X_an_upper: float = 1.0
    X_ca_lower: float = 0.0
    X_ca_upper: float = 1.0

    # ==================================================================== #
    # 历史轨迹存储 (list[float])；init / clear 中会重置
    # ==================================================================== #
    allt: List[float] = field(default_factory=list)
    allSOC: List[float] = field(default_factory=list)
    allI: List[float] = field(default_factory=list)
    allV: List[float] = field(default_factory=list)
    allV0: List[float] = field(default_factory=list)
    allQ: List[float] = field(default_factory=list)
    allT: List[float] = field(default_factory=list)
    allV_RC01: List[float] = field(default_factory=list)
    allV_RC02: List[float] = field(default_factory=list)
    allV_RC03: List[float] = field(default_factory=list)
    allV_hys: List[float] = field(default_factory=list)
    allSOC_surf: List[float] = field(default_factory=list)

    aging_allQ_PE: List[float] = field(default_factory=list)
    aging_allQ_NE: List[float] = field(default_factory=list)
    aging_allQ_LAM_PE: List[float] = field(default_factory=list)
    aging_allQ_LAM_NE: List[float] = field(default_factory=list)
    aging_allQ_LLI_PE: List[float] = field(default_factory=list)
    aging_allQ_LLI_NE: List[float] = field(default_factory=list)
    aging_allQ_SEI_NE: List[float] = field(default_factory=list)
    aging_allQ_PLA_NE: List[float] = field(default_factory=list)

    # ==================================================================== #
    # ① 初始化
    # ==================================================================== #
    def init(self, SOC: float) -> None:
        """
        将电池对象置为指定 SOC 的初始状态。

        步骤（与 MATLAB init 完全对齐）:
        1. 根据 aging_X0_PE/NE, 初始 LLI/SEI/PLA/LAM 设置半电池电荷 Q_PE, Q_NE
        2. 调用 agingCalibrateQ_SOC_X_CN 求出 Q_SOC_0, Q_SOC_1, C 等
        3. 按 (SOC_target - 计算出的 SOC) 的差值 dQ 修正 Q_PE, Q_NE, Q
        4. 清空轨迹存储，记下初始点
        """
        assert self.aging is not None, "需要先配置 aging 属性"

        # --- 1. 从初始化学计量数 + 初始退化电荷出发，算出 Q_PE, Q_NE ---
        self.aging_Q_LAM_PE = self.aging.Q0_LAM_PE
        self.aging_Q_LAM_NE = self.aging.Q0_LAM_NE
        self.aging_Q_LLI_PE = self.aging.Q0_LLI_PE
        self.aging_Q_LLI_NE = self.aging.Q0_LLI_NE
        self.aging_Q_SEI_NE = self.aging.Q0_SEI_NE
        self.aging_Q_PLA_NE = self.aging.Q0_PLA_NE

        self.aging_Q_PE = (
            self.aging_X0_PE * self.aging_C0_PE
            - self.aging.Q0_LLI_PE
            - self.aging.X_LAM_PE(self.aging_X0_PE) * self.aging.Q0_LAM_PE
        )
        self.aging_Q_NE = (
            self.aging_X0_NE * self.aging_C0_NE
            - self.aging.Q0_LLI_NE
            - self.aging.Q0_SEI_NE
            - self.aging.Q0_PLA_NE
            - self.aging.X_LAM_NE(self.aging_X0_NE) * self.aging.Q0_LAM_NE
        )

        # 其它初始状态
        self.Q = 0.0
        self.T = self.T_ambient
        self.V_hys = 0.0
        self.I = 0.0
        self.V_RC1 = 0.0
        self.V_RC2 = 0.0
        self.V_RC3 = 0.0
        self.t = 0.0

        # --- 2. SOC 定标 ---
        self._aging_calibrate_SOC()

        # --- 3. 调整到目标 SOC ---
        dQ = self.C * (SOC - self.SOC)
        self.aging_Q_PE -= dQ
        self.aging_Q_NE += dQ
        self.Q += dQ
        self.SOC = (self.Q - self.aging_Q_SOC_0) / (self.aging_Q_SOC_1 - self.aging_Q_SOC_0)
        self.V = self.open_circuit_voltage_cell()

        # --- 4. 清空轨迹并记下 t=0 点 ---
        self._clear_history()

    def _clear_history(self) -> None:
        """重置所有 all* 轨迹 list 至只包含当前状态点。"""
        self.allt = [self.t]
        self.allSOC = [self.SOC]
        self.allI = [self.I]
        self.allV = [self.V]
        self.allV0 = [self.open_circuit_voltage_cell()]
        self.allQ = [self.Q]
        self.allT = [self.T]
        self.allV_RC01 = [self.V_RC1]
        self.allV_RC02 = [self.V_RC2]
        self.allV_RC03 = [self.V_RC3]
        self.allV_hys = [self.V_hys]
        self.allSOC_surf = [self.SOC_surf]
        self.aging_allQ_PE = [self.aging_Q_PE]
        self.aging_allQ_NE = [self.aging_Q_NE]
        self.aging_allQ_LAM_PE = [self.aging_Q_LAM_PE]
        self.aging_allQ_LAM_NE = [self.aging_Q_LAM_NE]
        self.aging_allQ_LLI_PE = [self.aging_Q_LLI_PE]
        self.aging_allQ_LLI_NE = [self.aging_Q_LLI_NE]
        self.aging_allQ_SEI_NE = [self.aging_Q_SEI_NE]
        self.aging_allQ_PLA_NE = [self.aging_Q_PLA_NE]

    # ==================================================================== #
    # ② LUT / 开路电压计算
    # ==================================================================== #
    def LUT_X(self, X_ne, X_pe, T):
        """对应 MATLAB LUT_X。返回 (V0, dS_NE, dS_PE, V0_PE, V0_NE)。"""
        return open_circuit_voltage(X_ne, X_pe, T, self.anode_thermo, self.cathode_thermo)

    def open_circuit_voltage_cell(self) -> float:
        """返回当前化学计量下的电池开路电压。"""
        X_ne = self.X_an_from_SOC(self.SOC)
        X_pe = self.X_ca_from_SOC(self.SOC)
        V0, *_ = self.LUT_X(X_ne, X_pe, self.T)
        return float(np.atleast_1d(V0)[0])

    def X_an_from_SOC(self, SOC: float) -> float:
        """线性插值化学计量 NE = SOC * (X_upper - X_lower) + X_lower"""
        return SOC * (self.X_an_upper - self.X_an_lower) + self.X_an_lower

    def X_ca_from_SOC(self, SOC: float) -> float:
        """PE 的化学计量随 SOC 递减（充电时 PE 脱锂）"""
        return (1.0 - SOC) * (self.X_ca_upper - self.X_ca_lower) + self.X_ca_lower

    # ==================================================================== #
    # ③ SOC 定标（核心辅助函数）
    # ==================================================================== #
    def _aging_calibrate_SOC(self) -> None:
        """
        计算当前退化态下的 Q_SOC_0, Q_SOC_1, 电池容量 C, 以及
        X_an_lower/upper, X_ca_lower/upper 边界。

        与 MATLAB ``agingCalibrateQ_SOC_X_CN`` 完全对应：
        找到电荷偏移 dQ 使得 V_cell(dQ) = V_min (empty) / V_max (full)。
        """
        # 采用 I = 0 简化求解 (MATLAB 中 I 默认也设为 0)
        dQ0 = (self.aging_Q_NE + self.aging_Q_PE) / 2.0

        def V_minus_target(dQ: float, target: float) -> float:
            return self._V_at_dQ(dQ, I=0.0) - target

        # Lower 边界 (V = V_min)
        # 用扩展括号 [-dQ0 * 3, dQ0 * 3] 保证覆盖零点
        search_range = max(abs(dQ0) * 3.0, 1.0)
        dQ_low = brentq(
            V_minus_target, -search_range, search_range,
            args=(self.aging_V_min,), xtol=1e-6, maxiter=200,
        )
        self.aging_Q_SOC_0 = self.Q + dQ_low
        self.X_ca_upper = (self.aging_Q_PE - dQ_low) / (self.aging_C0_PE - self.aging_Q_LAM_PE)
        self.X_an_lower = (self.aging_Q_NE + dQ_low) / (self.aging_C0_NE - self.aging_Q_LAM_NE)

        # Upper 边界 (V = V_max)
        dQ_high = brentq(
            V_minus_target, -search_range, search_range,
            args=(self.aging_V_max,), xtol=1e-6, maxiter=200,
        )
        self.aging_Q_SOC_1 = self.Q + dQ_high
        self.X_ca_lower = (self.aging_Q_PE - dQ_high) / (self.aging_C0_PE - self.aging_Q_LAM_PE)
        self.X_an_upper = (self.aging_Q_NE + dQ_high) / (self.aging_C0_NE - self.aging_Q_LAM_NE)

        self.C = self.aging_Q_SOC_1 - self.aging_Q_SOC_0
        self.SOC = (self.Q - self.aging_Q_SOC_0) / (self.aging_Q_SOC_1 - self.aging_Q_SOC_0)

    def _V_at_dQ(self, dQ: float, I: float) -> float:
        """
        在给定 dQ (从当前 Q 出发的电荷偏移) 下计算电池电压。
        与 MATLAB ``agingDQFun`` 等价。
        """
        X_PE = (self.aging_Q_PE - dQ) / (self.aging_C0_PE - self.aging_Q_LAM_PE)
        X_NE = (self.aging_Q_NE + dQ) / (self.aging_C0_NE - self.aging_Q_LAM_NE)
        X_PE = float(np.clip(X_PE, 0.0, 1.0))
        X_NE = float(np.clip(X_NE, 0.0, 1.0))
        V0, *_ = self.LUT_X(X_NE, X_PE, self.T)
        V0 = float(np.atleast_1d(V0)[0])
        R_total = self._R_total_with_aging(self.T, X_NE, X_PE, I)
        return V0 - R_total * I

    def _R_total_with_aging(self, T: float, X_NE: float, X_PE: float, I: float) -> float:
        """返回应用完老化因子后的总电阻 (Rs + R1 + R2 + R3)。"""
        Rs = self.Rs_fn(T, X_NE, X_PE, I)
        R1 = self.R1_fn(T, X_NE, X_PE, I)
        R2 = self.R2_fn(T, X_NE, X_PE, I)
        R3 = self.R3_fn(T, X_NE, X_PE, I)

        # 老化因子
        R1 *= ak.f_R_NE(
            self.aging_Q_LAM_NE, self.aging_Q_SEI_NE, self.aging_Q_PLA_NE,
            self.aging.Q0_SEI_NE, self.aging_C0_NE,
            self.aging.resistance_aging,
        )
        R2 *= ak.f_R_PE(self.aging_Q_LAM_PE, self.aging_C0_PE)
        # Rs, R3 不退化
        return Rs + R1 + R2 + R3

    # ==================================================================== #
    # ④ 稳态电压 (用于内阻估算)
    # ==================================================================== #
    def calculate_steady_state_voltage(self, T: float, I: float, SOC: float) -> float:
        """
        返回给定 SOC 稳定工作条件下的电压（无 RC 瞬态）。
        论文中 IR (论文式 30) 的计算基于此。
        """
        X_ne = self.X_an_from_SOC(SOC)
        X_ca = self.X_ca_from_SOC(SOC)
        V0, *_ = self.LUT_X(X_ne, X_ca, T)
        V0 = float(np.atleast_1d(V0)[0])
        R_total = self._R_total_with_aging(T, X_ne, X_ca, I)
        return V0 - R_total * I if I != 0 else V0

    # ==================================================================== #
    # ⑤ 用户接口: CC / CV / CP
    # ==================================================================== #
    def CC(self, I: float, duration_s: float, break_criterion: str = "") -> None:
        """恒流 (Constant Current) 仿真。I>0 放电, I<0 充电。"""
        self._solve_transient("I", I, duration_s, break_criterion)

    def CV(self, V: float, duration_s: float, break_criterion: str = "") -> None:
        """恒压 (Constant Voltage) 仿真。"""
        self._solve_transient("V", V, duration_s, break_criterion)

    def CP(self, P: float, duration_s: float, break_criterion: str = "") -> None:
        """恒功率 (Constant Power) 仿真。P>0 放电, P<0 充电。"""
        self._solve_transient("P", P, duration_s, break_criterion)

    # ==================================================================== #
    # ⑥ 瞬态求解核心
    # ==================================================================== #
    def _solve_transient(
        self, setpoint: str, value: float, duration_s: float, break_criterion: str
    ) -> None:
        """
        将 DAE 系统约化为 12 维显式 ODE，用 scipy.integrate.solve_ivp 求解。

        12 个微分状态 (y 向量) 的顺序:
            [Q, V_RC1, V_RC2, V_RC3, Q_PE, Q_NE,
             Q_LAM_PE, Q_LAM_NE, Q_LLI_PE, Q_LLI_NE, Q_SEI_NE, Q_PLA_NE]

        在每次 RHS 评估时：I、V、SOC、T 等代数量由 ``_evaluate_algebraic`` 显式给出。
        """
        y0 = np.array([
            self.Q, self.V_RC1, self.V_RC2, self.V_RC3,
            self.aging_Q_PE, self.aging_Q_NE,
            self.aging_Q_LAM_PE, self.aging_Q_LAM_NE,
            self.aging_Q_LLI_PE, self.aging_Q_LLI_NE,
            self.aging_Q_SEI_NE, self.aging_Q_PLA_NE,
        ], dtype=float)

        t_span = (self.t, self.t + duration_s)

        # 缓存每步的 I 估计值（用于 CV/CP 模式的迭代初值）
        # 使用一个可变列表绕过 Python 闭包变量作用域限制
        cached_I = [self.I]

        def rhs(t, y):
            return self._ode_rhs(t, y, setpoint, value, cached_I)

        events: Optional[List[Callable]] = None
        if break_criterion and break_criterion != "0":
            events = [self._make_event(break_criterion, setpoint, value, cached_I)]
            events[0].terminal = True
            events[0].direction = 0  # 双向触发

        sol = solve_ivp(
            rhs, t_span, y0,
            method="BDF",                 # 刚性系统首选
            rtol=self.tolerance_rel,
            atol=self.tolerance_abs,
            events=events,
            dense_output=False,
            max_step=max(duration_s / 10.0, 1.0),  # 避免跳步过大
        )
        if not sol.success:
            # 在一些难收敛时段回退到 LSODA
            sol = solve_ivp(
                rhs, t_span, y0,
                method="LSODA",
                rtol=self.tolerance_rel * 10,
                atol=self.tolerance_abs * 10,
                events=events,
            )
            if not sol.success:
                raise RuntimeError(f"求解器失败: {sol.message}")

        # 存储结果 (跳过 t[0]，因为它与上一阶段末态重复)
        ts = sol.t
        ys = sol.y                # shape (12, n_steps)
        for k in range(1, len(ts)):
            self._push_state(ts[k], ys[:, k], setpoint, value, cached_I)

        # 与 MATLAB solveTransient 末尾一致: 重新标定老化后电池的 SOC 区间、C 等
        self._aging_calibrate_SOC()

    # ==================================================================== #
    # ⑦ ODE 右端: 计算 12 个微分状态的 dy/dt
    # ==================================================================== #
    def _ode_rhs(
        self, t: float, y: np.ndarray,
        setpoint: str, value: float,
        cached_I: List[float],
    ) -> np.ndarray:
        """返回 dy/dt (12 维)。"""
        Q, V_RC1, V_RC2, V_RC3 = y[0], y[1], y[2], y[3]
        Q_PE, Q_NE = y[4], y[5]
        Q_LAM_PE, Q_LAM_NE = y[6], y[7]
        Q_LLI_PE, Q_LLI_NE = y[8], y[9]
        Q_SEI_NE, Q_PLA_NE = y[10], y[11]

        # 化学计量数
        X_ne = Q_NE / (self.aging_C0_NE - Q_LAM_NE)
        X_pe = Q_PE / (self.aging_C0_PE - Q_LAM_PE)
        X_ne = float(np.clip(X_ne, 0.0, 1.0))
        X_pe = float(np.clip(X_pe, 0.0, 1.0))

        T = self.T_ambient
        V_hys = 0.0

        # 获取代数变量 (I, V) 及应用了老化和 fractionR 后的电阻
        I, V, Rs_eff, R1_eff, R2_eff, V0, V0_PE, V0_NE = self._solve_algebraic(
            setpoint, value, T, X_ne, X_pe,
            V_RC1, V_RC2, V_RC3, V_hys,
            Q_LAM_PE, Q_LAM_NE, Q_SEI_NE, Q_PLA_NE,
            cached_I,
        )
        cached_I[0] = I   # 更新缓存

        # 半电池电压 (用于老化速率表达式, 论文式 37)
        V_PE = V0_PE - V_RC2 - I * R2_eff * self.fractionR2toRs
        V_NE = V0_NE + V_RC1 + I * R1_eff * self.fractionR1toRs

        # ---- 老化速率 (都已乘以 acceleration_factor) --------------------
        acc = self.aging.acceleration_factor
        I_SEI = acc * ak.I_SEI_NE(
            I, T, V_NE, X_ne, Q_LLI_NE, Q_LAM_NE, Q_SEI_NE,
            self.aging.sei, self.aging.mvol_ne, self.aging_C0_NE,
        )
        I_PLA = acc * ak.I_PLA_NE(
            I, T, V_NE, X_ne, Q_LLI_NE, Q_LAM_NE,
            self.aging.plating, self.aging_C0_NE,
        )
        I_LAM_PE_rate = acc * ak.I_LAM_PE(
            I, T, V_PE, X_pe, Q_LAM_PE,
            self.aging.lam_pe, self.aging.mvol_pe,
        )
        I_LAM_NE_rate = acc * ak.I_LAM_NE(
            I, T, V_NE, X_ne, Q_LAM_NE, Q_LLI_NE,
            self.aging.lam_ne, self.aging.mvol_ne,
        )
        I_LLI_PE_rate = acc * ak.I_LLI_PE()
        I_LLI_NE_rate = 0.0   # 在此模型中 LLI_NE 总量由 SEI + PLA 累加；下面式中单独处理

        # 失去活性材料中所含 Li 的化学计量
        X_LAM_PE_val = self.aging.X_LAM_PE(X_pe)
        X_LAM_NE_val = self.aging.X_LAM_NE(X_ne)

        # ---- 12 个微分方程的 RHS ----------------------------------------
        dydt = np.zeros(12)
        dydt[0] = -I                                    # dQ/dt
        # RC 动力学 (论文式 2, 3)
        if R1_eff > 0 and self.C1 > 0:
            dydt[1] = (I - V_RC1 / R1_eff) / self.C1
        if R2_eff > 0 and self.C2 > 0:
            dydt[2] = (I - V_RC2 / R2_eff) / self.C2
        # R3/C3 通常为 0, 可跳过以减少 LUT 调用开销
        if self.C3 > 0:
            R3 = self.R3_fn(T, X_ne, X_pe, I)
            if R3 > 0:
                R3_eff = R3 * (1.0 - self.fractionR3toRs)
                if R3_eff > 0:
                    dydt[3] = (I - V_RC3 / R3_eff) / self.C3
        # 老化微分方程 (论文式 18, 19, 6, 8, 13, 12, 10, 11 的积分形式)
        dydt[4] = I - I_LLI_PE_rate - X_LAM_PE_val * I_LAM_PE_rate    # dQ_PE/dt
        dydt[5] = -I - I_LLI_NE_rate - X_LAM_NE_val * I_LAM_NE_rate - I_SEI - I_PLA  # dQ_NE/dt
        dydt[6] = I_LAM_PE_rate                                         # dQ_LAM_PE/dt
        dydt[7] = I_LAM_NE_rate                                         # dQ_LAM_NE/dt
        dydt[8] = I_LLI_PE_rate + X_LAM_PE_val * I_LAM_PE_rate          # dQ_LLI_PE/dt
        dydt[9] = I_LLI_NE_rate + X_LAM_NE_val * I_LAM_NE_rate + I_SEI + I_PLA  # dQ_LLI_NE/dt
        dydt[10] = I_SEI                                                # dQ_SEI_NE/dt
        dydt[11] = I_PLA                                                # dQ_PLA_NE/dt

        if np.any(np.isnan(dydt)) or np.any(np.isinf(dydt)):
            raise RuntimeError(f"RHS 发散 at t={t}")
        return dydt

    # ==================================================================== #
    # ⑧ 代数方程求解 (决定 I, V)
    # ==================================================================== #
    def _solve_algebraic(
        self, setpoint: str, value: float,
        T: float, X_ne: float, X_pe: float,
        V_RC1: float, V_RC2: float, V_RC3: float, V_hys: float,
        Q_LAM_PE: float, Q_LAM_NE: float, Q_SEI_NE: float, Q_PLA_NE: float,
        cached_I: List[float],
    ):
        """
        返回 (I, V, Rs_eff, R1_eff, R2_eff, V0, V0_PE, V0_NE) ——
        将论文式 (1) 中的代数关系在不同模式下显式解出。

        ``Rs_eff``、``R1_eff``、``R2_eff`` 都是应用了**老化因子**后再做了
        ``fractionR*toRs`` 转移处理的最终电阻值。
        """
        V0, _, _, V0_PE, V0_NE = self.LUT_X(X_ne, X_pe, T)
        V0 = float(np.atleast_1d(V0)[0])
        V0_PE = float(np.atleast_1d(V0_PE)[0])
        V0_NE = float(np.atleast_1d(V0_NE)[0])

        # 先计算老化因子 (不依赖 I)
        f_R1 = ak.f_R_NE(
            Q_LAM_NE, Q_SEI_NE, Q_PLA_NE,
            self.aging.Q0_SEI_NE, self.aging_C0_NE,
            self.aging.resistance_aging,
        )
        f_R2 = ak.f_R_PE(Q_LAM_PE, self.aging_C0_PE)

        def resistances(I_guess: float):
            """给定 I，计算应用老化因子和 fractionR 后的 R1_eff, R2_eff, Rs_eff。"""
            Rs0 = self.Rs_fn(T, X_ne, X_pe, I_guess)
            R1 = self.R1_fn(T, X_ne, X_pe, I_guess) * f_R1
            R2 = self.R2_fn(T, X_ne, X_pe, I_guess) * f_R2
            # 本电池 C3=0, 通常 R3=0, 避开 LUT 调用
            R3 = 0.0 if self.C3 == 0.0 else self.R3_fn(T, X_ne, X_pe, I_guess)
            # 把部分 R1/R2/R3 转到 Rs
            Rs_eff = (Rs0
                      + self.fractionR1toRs * R1
                      + self.fractionR2toRs * R2
                      + self.fractionR3toRs * R3)
            R1_eff = R1 * (1.0 - self.fractionR1toRs)
            R2_eff = R2 * (1.0 - self.fractionR2toRs)
            return Rs_eff, R1_eff, R2_eff, R3

        # --------- CC: I 已知 ---------------------------------------------
        if setpoint == "I":
            I = value
            Rs_eff, R1_eff, R2_eff, _ = resistances(I)
            V = V0 + V_hys - I * Rs_eff - V_RC1 - V_RC2 - V_RC3
            return I, V, Rs_eff, R1_eff, R2_eff, V0, V0_PE, V0_NE

        # --------- CV: V 已知, 解 I --------------------------------------
        if setpoint == "V":
            V_target = value

            def residual_V(I_guess: float) -> float:
                Rs_eff, *_ = resistances(I_guess)
                return (V0 + V_hys - I_guess * Rs_eff
                        - V_RC1 - V_RC2 - V_RC3) - V_target

            # 用缓存的 I 做初值，牛顿迭代几步
            I = self._solve_scalar_current(residual_V, cached_I[0])
            Rs_eff, R1_eff, R2_eff, _ = resistances(I)
            V = V_target
            return I, V, Rs_eff, R1_eff, R2_eff, V0, V0_PE, V0_NE

        # --------- CP: P 已知, 解 I --------------------------------------
        if setpoint == "P":
            P_target = value

            def residual_P(I_guess: float) -> float:
                Rs_eff, *_ = resistances(I_guess)
                V_g = V0 + V_hys - I_guess * Rs_eff - V_RC1 - V_RC2 - V_RC3
                return I_guess * V_g - P_target

            I = self._solve_scalar_current(residual_P, cached_I[0])
            Rs_eff, R1_eff, R2_eff, _ = resistances(I)
            V = V0 + V_hys - I * Rs_eff - V_RC1 - V_RC2 - V_RC3
            return I, V, Rs_eff, R1_eff, R2_eff, V0, V0_PE, V0_NE

        raise ValueError(f"未知设定模式 setpoint={setpoint!r}")

    @staticmethod
    def _solve_scalar_current(residual_fn: Callable[[float], float],
                              I0: float) -> float:
        """
        快速解 residual(I) = 0。

        策略: **Newton 优先** + brentq 兜底。
        - 在 CP/CV 模式下 I 通常与上一步非常接近, 2-3 步 Newton 即收敛。
        - 若 Newton 失败 (div by 0 或不收敛), 退到宽括号 brentq。
        """
        # ---- 1. Newton (warm-started) ------------------------------
        I = I0
        for _ in range(10):
            f = residual_fn(I)
            if abs(f) < 1e-9:
                return I
            h = 1e-3 if abs(I) < 1.0 else abs(I) * 1e-3
            fp = (residual_fn(I + h) - f) / h
            if abs(fp) < 1e-14:
                break
            dI = f / fp
            I_new = I - dI
            # 防止 Newton 步跑飞
            if abs(I_new) > 100.0:
                break
            I = I_new
            if abs(dI) < 1e-9:
                return I

        # ---- 2. brentq 兜底 ---------------------------------------
        for lo, hi in [(-20.0, 20.0), (-100.0, 100.0)]:
            try:
                f_lo = residual_fn(lo)
                f_hi = residual_fn(hi)
                if f_lo * f_hi < 0.0:
                    return brentq(residual_fn, lo, hi, xtol=1e-8, maxiter=60)
            except Exception:
                continue

        # 实在不行返回最后一次迭代
        return float(I)

    # ==================================================================== #
    # ⑨ 记录/推入一个时间点的状态
    # ==================================================================== #
    def _push_state(
        self, t: float, y: np.ndarray,
        setpoint: str, value: float,
        cached_I: List[float],
    ) -> None:
        """把当前时间点的状态存入轨迹、并更新私有字段。"""
        Q, V_RC1, V_RC2, V_RC3 = y[0], y[1], y[2], y[3]
        Q_PE, Q_NE = y[4], y[5]
        Q_LAM_PE, Q_LAM_NE = y[6], y[7]
        Q_LLI_PE, Q_LLI_NE = y[8], y[9]
        Q_SEI_NE, Q_PLA_NE = y[10], y[11]

        X_ne = float(np.clip(Q_NE / (self.aging_C0_NE - Q_LAM_NE), 0.0, 1.0))
        X_pe = float(np.clip(Q_PE / (self.aging_C0_PE - Q_LAM_PE), 0.0, 1.0))
        T = self.T_ambient

        I, V, *_ = self._solve_algebraic(
            setpoint, value, T, X_ne, X_pe,
            V_RC1, V_RC2, V_RC3, 0.0,
            Q_LAM_PE, Q_LAM_NE, Q_SEI_NE, Q_PLA_NE, cached_I,
        )
        cached_I[0] = I

        V0, *_ = self.LUT_X(X_ne, X_pe, T)
        V0 = float(np.atleast_1d(V0)[0])

        # 更新标量末态
        self.t = float(t)
        self.Q = float(Q)
        self.V_RC1 = float(V_RC1)
        self.V_RC2 = float(V_RC2)
        self.V_RC3 = float(V_RC3)
        self.I = float(I)
        self.V = float(V)
        self.T = float(T)
        self.V_hys = 0.0
        self.aging_Q_PE = float(Q_PE)
        self.aging_Q_NE = float(Q_NE)
        self.aging_Q_LAM_PE = float(Q_LAM_PE)
        self.aging_Q_LAM_NE = float(Q_LAM_NE)
        self.aging_Q_LLI_PE = float(Q_LLI_PE)
        self.aging_Q_LLI_NE = float(Q_LLI_NE)
        self.aging_Q_SEI_NE = float(Q_SEI_NE)
        self.aging_Q_PLA_NE = float(Q_PLA_NE)

        # 重新计算 SOC (依赖于 Q_SOC_0/1，在阶段结束时重新标定)
        if self.aging_Q_SOC_1 - self.aging_Q_SOC_0 > 0:
            self.SOC = (self.Q - self.aging_Q_SOC_0) / (self.aging_Q_SOC_1 - self.aging_Q_SOC_0)
        self.SOC_surf = self.Q / self.C if self.C > 0 else 0.0

        # 推入历史
        self.allt.append(self.t)
        self.allQ.append(self.Q)
        self.allI.append(self.I)
        self.allV.append(self.V)
        self.allV0.append(V0)
        self.allSOC.append(self.SOC)
        self.allT.append(self.T)
        self.allV_RC01.append(self.V_RC1)
        self.allV_RC02.append(self.V_RC2)
        self.allV_RC03.append(self.V_RC3)
        self.allV_hys.append(self.V_hys)
        self.allSOC_surf.append(self.SOC_surf)
        self.aging_allQ_PE.append(self.aging_Q_PE)
        self.aging_allQ_NE.append(self.aging_Q_NE)
        self.aging_allQ_LAM_PE.append(self.aging_Q_LAM_PE)
        self.aging_allQ_LAM_NE.append(self.aging_Q_LAM_NE)
        self.aging_allQ_LLI_PE.append(self.aging_Q_LLI_PE)
        self.aging_allQ_LLI_NE.append(self.aging_Q_LLI_NE)
        self.aging_allQ_SEI_NE.append(self.aging_Q_SEI_NE)
        self.aging_allQ_PLA_NE.append(self.aging_Q_PLA_NE)

    # ==================================================================== #
    # ⑩ 事件函数 (break criterion)
    # ==================================================================== #
    def _make_event(
        self, criterion: str, setpoint: str, value: float, cached_I: List[float],
    ) -> Callable:
        """
        将 MATLAB 式的字符串判据 ('V > 4.2', 'abs(I) < 0.065') 转换成
        scipy solve_ivp 所需的事件函数 (返回 0 时触发)。

        支持的语法 (保持与 MATLAB 原 break_criterion 一致):
            'V > X', 'V < X', 'V >= X', 'V <= X'
            'abs(I) < X', 'abs(I) > X'
            'I > X', 'I < X'
            'SOC > X', 'SOC < X'
        """
        import re
        m = re.match(
            r"\s*(abs\(I\)|V|I|SOC|T)\s*(>=|<=|>|<)\s*([\-\d\.eE]+)\s*$",
            criterion,
        )
        if not m:
            # 未识别 → 始终不触发
            return lambda t, y: 1.0

        var, op, thresh_str = m.group(1), m.group(2), m.group(3)
        thresh = float(thresh_str)

        def event_fn(t: float, y: np.ndarray) -> float:
            # 解包当前状态
            Q, V_RC1, V_RC2, V_RC3 = y[0], y[1], y[2], y[3]
            Q_PE, Q_NE = y[4], y[5]
            Q_LAM_PE, Q_LAM_NE = y[6], y[7]
            Q_SEI_NE, Q_PLA_NE = y[10], y[11]
            X_ne = float(np.clip(Q_NE / (self.aging_C0_NE - Q_LAM_NE), 0.0, 1.0))
            X_pe = float(np.clip(Q_PE / (self.aging_C0_PE - Q_LAM_PE), 0.0, 1.0))
            I, V, *_ = self._solve_algebraic(
                setpoint, value, self.T_ambient, X_ne, X_pe,
                V_RC1, V_RC2, V_RC3, 0.0,
                Q_LAM_PE, Q_LAM_NE, Q_SEI_NE, Q_PLA_NE, cached_I,
            )
            # 当前值
            if var == "V":
                cur = V
            elif var == "I":
                cur = I
            elif var == "abs(I)":
                cur = abs(I)
            elif var == "SOC":
                cur = ((Q - self.aging_Q_SOC_0)
                       / (self.aging_Q_SOC_1 - self.aging_Q_SOC_0))
            elif var == "T":
                cur = self.T_ambient
            else:
                return 1.0

            # 返回 (cur - thresh)，符号变化即触发
            # 同时保证事件只在符合操作符方向时触发
            diff = cur - thresh
            if op in (">", ">="):
                # 希望从 cur < thresh 过渡到 cur > thresh → 负变正
                return diff
            else:  # < or <=
                return -diff

        return event_fn
