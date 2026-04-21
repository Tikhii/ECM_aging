"""
aging_kinetics.py
=================
论文第 "Degradation Mechanisms" 小节中描述的所有物理信息速率律。

本文件里的函数对应 MATLAB 参数化脚本 ``PanasonicNCR18650B.m`` 中那些
``@(I,T,V_NE,...)`` 匿名函数，现在被重写为独立 Python 函数或 dataclass。

所有速率的单位都是 A (安培, 即每秒 C/s)，符合论文式 (6)-(13) 的习惯:
将化学反应的速率表达为电化学电流。正号表示生成次生相 (SEI 长厚/Li 镀层增加)。

主要输出 (均为时间导数方程 RHS):
- ``I_SEI_NE``  : 式 (36)，SEI 生长速率
- ``I_PLA_NE``  : 式 (39)，不可逆镀锂速率
- ``I_LAM_PE``  : 式 (40)，PE 活性材料损失速率
- ``I_LAM_NE``  : 式 (41)，NE 活性材料损失速率
- ``I_LLI_PE``  : 式 (42)，PE 侧 LLI (本论文假设为 0)
- 电阻退化因子 f_R1, f_R2, f_Rs : 式 (43)-(46)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .constants import F, R_GAS, T_REF


# =============================================================================
# 1. 分子容积 (molar volume) 的相对变化
#    论文式 (31)(32): 循环退化的驱动量 |I * dv/dX|
# =============================================================================
@dataclass
class MolarVolumeModel:
    """
    活性材料的相对摩尔体积多项式 v(X)/v0 及其对 X 的导数。

    论文中的具体数值来自 Schmider 等人 (Ref. 37) 的文献整理，
    系数按从高次到低次排列，用 ``np.polyval`` 即可求值 ——
    与 MATLAB 的 ``polyval`` 约定完全一致。
    """

    v_coeff: np.ndarray          # v(X)/v0 的多项式系数
    dv_dX_coeff: np.ndarray = field(init=False)  # v/v0 对 X 的导数

    def __post_init__(self) -> None:
        # 解析求导：p(x) = Σ c_i x^(n-i) → p'(x) = Σ c_i*(n-i) x^(n-i-1)
        n = len(self.v_coeff) - 1
        # MATLAB: (length(p)-1:-1:1) .* p(1:end-1)
        factors = np.arange(n, 0, -1)
        self.dv_dX_coeff = factors * self.v_coeff[:-1]

    def dv_dX(self, X: np.ndarray | float) -> np.ndarray | float:
        """返回 d(v/v0)/dX 在给定 X 上的值。"""
        return np.polyval(self.dv_dX_coeff, X)


# 论文中给出的两个具体材料多项式系数 (取自 PanasonicNCR18650B.m):
NCA_V_REL_COEFF = np.array([
    -32.9124670292972, 164.034122838353, -346.243102861452, 402.199791697668,
    -279.198026321213, 117.139029663712, -28.1019548541470, 3.06011969427768,
    0.0748644428734603, 0.947622729224261,
])
GRAPHITE_V_REL_COEFF = np.array([
    -0.570474317499545, -19.1220232496479, 80.3500522207527, -126.491321956319,
    95.9539905660636, -34.8304071844916, 4.74833875007453, -0.104781310349451,
    0.180994823054113, 1.0,
])


# =============================================================================
# 2. 退化速率律的参数集（dataclass）
# =============================================================================
@dataclass
class SEIParameters:
    """
    SEI (NE 上) 生长速率的参数，对应论文式 (36)。

    .. note::
        **单位纠错**: 论文 Table Ib 把 k_cal 的单位写为 A²·s，值写为 4.2e-22，
        但通过量纲分析 Eq. 36 和 MATLAB 源码验证，**正确值是 0.0419625 (= 4.2e-2 A²·s)**，
        论文里的 10⁻²² 是排版错误（详见 docs/CRITICAL_REVIEW.md § E1）。

        **k_cyc 单位**: 从 Eq. 36 的量纲分析，|I·dv/dX| 的内部单位是 A·V，
        因此 k_cyc 的单位是 A·s/V = F (法拉)，虽然这是一个不寻常的复合单位。

    .. note::
        **部分 Arrhenius 限制**: 只有 SEI 生长有 Arrhenius 温度项。Plating、
        LAM_PE、LAM_NE 没有温度依赖。因此对于 <15°C 或 >40°C 的外推，
        这些非 SEI 速率将失准。详见 docs/CRITICAL_REVIEW.md § S3。
    """
    k_cal: float            # 日历 SEI 速率常数 [A²·s] (非论文 Table Ib 的 10⁻²²)
    k_cyc: float            # 循环 SEI 速率常数 [F = A·s/V]
    Ea: float = 55500.0     # 激活能 [J/mol]，仅 SEI 有温度依赖
    alpha_f: float = 0.5    # 对称因子 α_f


@dataclass
class PlatingParameters:
    """
    不可逆镀锂速率参数，对应论文式 (39)。

    .. warning::
        **V_LP_eq = 0V 是简化假设** (详见 docs/CRITICAL_REVIEW.md § S2)：
        Beck, Greszta, Roberts, Dubarry 2024 (Batteries 10:408, 同一高级作者)
        明确指出静态 0V 假设"在稳态外不成立"。对于以下场景需要升级为动态形式：

        - 快充 (>1C)：V_LP_eq 应与局部 Li⁺ 浓度耦合
        - 低温 (<15°C)：V_LP_eq 应有温度依赖
        - 不可逆性假设：只对 Baure-Dubarry 2019 的 NCR 18650B 在 DST 协议下验证

        **TODO**: 实现 Beck 2024 的动态 V_LP_eq(T, c_Li+) 修正函数作为扩展接口。
    """
    k_LP: float                    # 交换电流密度相关常数 [A]
    alpha_LP: float = 0.5          # 对称因子
    V_LP_eq: float = 0.0           # 镀锂平衡电位 (vs Li/Li+) [V]
                                    # TODO(v2): 支持 V_LP_eq = callable(T, c_Li)


@dataclass
class LAMParameters:
    """PE 或 NE 活性材料损失速率参数，对应论文式 (40)(41)。"""
    k_cal: float = 0.0   # 日历速率 [A]；NE 的 k_cal = 0 (假设可忽略)
    k_cyc: float = 0.0   # 循环速率 [-]
    gamma: float = 0.0   # 电压依赖指数；NE 的 gamma 通常无直接意义，仅 PE 用


@dataclass
class ResistanceAgingParameters:
    """
    电阻退化因子的参数，对应论文式 (45)。

    .. note::
        **R_NE_0 必须与 R_NE_LUT 配套更新** (详见 PARAMETERS.json):
        每次替换 fresh-cell 电阻 LUT 时，R_NE_0 应重新从 LUT 在 50% SOC、C/3
        工况点取值。当前实现把它作为独立输入，是一个已知的**隐性耦合**。

    .. warning::
        **R_s 非退化假设** (详见 docs/CRITICAL_REVIEW.md § C3):
        本模型假设串联电阻 R_s 不随老化变化 (论文 Eq. 46, f_R,s=1)。
        但 post-mortem 文献 (Stiaszny 2014 等) 显示 R_s 在全生命周期中
        会增长 10-30%。这会让模型**低估末期（knee 附近）的极化**，
        可能轻微延后预测的 knee 位置。

        **TODO(v2)**: 实现 f_R,s(Q_SEI, Q_LAM) 作为可选扩展。
    """
    R_SEI: float = 0.66    # SEI 本征比电阻 [Ω·无因次分母]
    R_NE_0: float = 0.018236   # 初始 NE 总电阻 [Ω]；
                                # TODO(v2): derive_R_NE_0() 自动从 LUT 派生


# =============================================================================
# 3. 退化速率函数 (返回 **时间导数** 的 RHS, 单位 A)
# =============================================================================
def I_SEI_NE(I: float, T: float, V_NE: float, X_NE: float,
             Q_LLI_NE: float, Q_LAM_NE: float, Q_SEI_NE: float,
             params: SEIParameters, mvol: MolarVolumeModel,
             C0_NE: float) -> float:
    """
    SEI 生长速率。论文式 (36):

        I_SEI = (1/Q_SEI) * exp(-Ea/R*(1/T - 1/T_ref)) *
                [ k_cal * exp(-α_f*F/(RT) * V_NE)  +
                  k_cyc * |I * dv/dX|_NE ] *
                (C_NE / C_NE^0)

    物理含义：
    * 1/Q_SEI 因子：扩散受限，使得 SEI 厚度越厚长得越慢 ⇒ √t 动力学
    * exp 中的 Arrhenius 项：温度依赖
    * 日历部分 k_cal * exp(-α_f·F·V_NE/RT)：电位越低（越接近 Li/Li+）SEI 越活跃
    * 循环部分 k_cyc * |I·dv/dX|：循环时体积变化导致 SEI 破裂再生长
    * 最后的 (C_NE / C_NE^0) = (1 - Q_LAM_NE/C_NE^0)：活性物质减少则反应界面变少
    """
    arrhenius = np.exp(-params.Ea / R_GAS * (1.0 / T - 1.0 / T_REF))
    q_safe = max(Q_SEI_NE, 1e-3)    # 数值稳定性保护，与 MATLAB 完全一致

    calendar = params.k_cal * np.exp(-params.alpha_f * F / (R_GAS * T) * V_NE)
    cycle = params.k_cyc * abs(I * mvol.dv_dX(X_NE))
    area_factor = (C0_NE - Q_LAM_NE) / C0_NE

    return arrhenius / q_safe * (calendar + cycle) * area_factor


def I_PLA_NE(I: float, T: float, V_NE: float, X_NE: float,
             Q_LLI_NE: float, Q_LAM_NE: float,
             params: PlatingParameters, C0_NE: float) -> float:
    """
    不可逆镀锂速率。论文式 (39) 的 Butler-Volmer 形式:

        I_LP = max(0, k_LP * [exp(-α·F·(V_NE - V_LP_eq)/RT)
                              - exp( α·F·(V_NE - V_LP_eq)/RT) ]) * (C_NE / C_NE^0)

    * ``max(0, …)`` 保证反应不可逆（只向镀锂方向进行；反向剥离被阻止）
    * 当 V_NE < V_LP_eq = 0 时（即半电池电位低于锂平衡电位），才会有正的净速率
    """
    a = params.alpha_LP * F / (R_GAS * T)
    dv = V_NE - params.V_LP_eq
    rate = params.k_LP * (np.exp(-a * dv) - np.exp(a * dv))
    return max(0.0, rate) * (C0_NE - Q_LAM_NE) / C0_NE


def I_LAM_PE(I: float, T: float, V_PE: float, X_PE: float, Q_LAM_PE: float,
             params: LAMParameters, mvol: MolarVolumeModel) -> float:
    """
    PE 活性材料损失速率。论文式 (40):

        I_LAM_PE = k_cal * exp(γ · V_PE) + k_cyc * |I · dv/dX|_PE

    日历部分：PE 电位越高，衰减越快 (经验化指数)。
    循环部分：与 NE 相同的体积变化驱动机制。
    """
    calendar = params.k_cal * np.exp(params.gamma * V_PE)
    cycle = params.k_cyc * abs(I * mvol.dv_dX(X_PE))
    return calendar + cycle


def I_LAM_NE(I: float, T: float, V_NE: float, X_NE: float,
             Q_LAM_NE: float, Q_LLI_NE: float,
             params: LAMParameters, mvol: MolarVolumeModel) -> float:
    """
    NE 活性材料损失速率。论文式 (41):

        I_LAM_NE = k_cal·exp(γ·V_NE) + k_cyc·|I·dv/dX|_NE

    对本论文的 NCA/Graphite 电池，作者设 k_cal = 0 (日历 LAM_NE 近似为 0)。
    """
    calendar = params.k_cal * np.exp(params.gamma * V_NE)
    cycle = params.k_cyc * abs(I * mvol.dv_dX(X_NE))
    return calendar + cycle


def I_LLI_PE() -> float:
    """论文式 (42): 本模型不考虑 PE 上的 LLI (如 CEI 形成)，恒为 0。"""
    return 0.0


# =============================================================================
# 4. 电阻退化因子（论文式 43-46）
# =============================================================================
def f_R_PE(Q_LAM_PE: float, C0_PE: float) -> float:
    """
    PE 电阻退化因子。论文式 (44):
        f = 1 / (1 - Q_LAM_PE / C_PE^0)
    丢失越多 PE 活性材料，电阻越大；全丢光则发散。
    """
    return 1.0 / (1.0 - Q_LAM_PE / C0_PE)


def f_R_NE(Q_LAM_NE: float, Q_SEI_NE: float, Q_PLA_NE: float,
           Q_SEI0_NE: float, C0_NE: float,
           params: ResistanceAgingParameters) -> float:
    """
    NE 电阻退化因子。论文式 (45):

        f = 1/(1 - Q_LAM_NE / C_NE^0)  +
            R_SEI · (Q_SEI - Q_SEI^0 + Q_PLA) / (R_NE^0 · C_NE^0)

    物理: (1) 活性材料失效导致电流挤压；(2) SEI 累积和镀锂提供附加的 Li⁺ 传输电阻。
    """
    lam_factor = 1.0 / (1.0 - Q_LAM_NE / C0_NE)
    sei_factor = params.R_SEI * (Q_SEI_NE - Q_SEI0_NE + Q_PLA_NE) / (params.R_NE_0 * C0_NE)
    return lam_factor + sei_factor


def f_Rs() -> float:
    """论文式 (46): 串联电阻不受退化影响 (电解液+集流体被假设为稳定)。"""
    return 1.0


# =============================================================================
# 5. 一个容纳所有老化参数+函数的"策略"容器
# =============================================================================
@dataclass
class AgingModel:
    """
    将所有老化相关参数、MV 模型集成到一个对象中；
    单元类 ``EquivCircuitCell`` 将持有该对象并在右端函数中直接调用。
    """
    sei: SEIParameters
    plating: PlatingParameters
    lam_pe: LAMParameters
    lam_ne: LAMParameters
    resistance_aging: ResistanceAgingParameters

    mvol_ne: MolarVolumeModel
    mvol_pe: MolarVolumeModel

    # --- 初始退化状态（对应 MATLAB 中 aging_Q0_* 参数） ---
    Q0_LLI_PE: float = 0.0
    Q0_LLI_NE: float = 0.0
    Q0_LAM_PE: float = 0.0
    Q0_LAM_NE: float = 0.0
    Q0_SEI_NE: float = 0.0
    Q0_PLA_NE: float = 0.0

    # --- 失去的活性材料中锂的化学计量 (论文中对本电池均设为 0) ---
    X_LAM_PE: Callable[[float], float] = field(default=lambda X_pe: 0.0)
    X_LAM_NE: Callable[[float], float] = field(default=lambda X_ne: 0.0)

    # --- 全局加速因子 (用于缩短仿真时间) ---
    acceleration_factor: float = 1.0
