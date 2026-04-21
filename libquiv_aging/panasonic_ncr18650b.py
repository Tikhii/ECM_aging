"""
panasonic_ncr18650b.py
======================
Panasonic NCR18650B (3.35 Ah, NCA/石墨) 圆柱电池的参数工厂函数。

对应 Matlab 源文件 ``PanasonicNCR18650B.m``。本函数组装一个已完全配置好的
``EquivCircuitCell`` 实例，可直接调用 ``init(SOC)`` 开始仿真。

源参数来自论文 Table I，均与 MATLAB 原脚本对齐。
"""

from __future__ import annotations

import numpy as np

from .aging_kinetics import (
    AgingModel, LAMParameters, MolarVolumeModel, PlatingParameters,
    ResistanceAgingParameters, SEIParameters,
    GRAPHITE_V_REL_COEFF, NCA_V_REL_COEFF,
)
from .cell_model import EquivCircuitCell
from .lookup_tables import HalfCellThermo, ResistanceLUTs, default_data_path


def create_panasonic_ncr18650b() -> EquivCircuitCell:
    """
    创建并返回一个已完全参数化的 Panasonic NCR18650B 单体模型对象。

    注意:
    * alawa 格式的半电池数据 (GraphiteAlawa.dat, NCAAlawa.dat)
    * 电阻 2D 查找表 (ResistancesAlawa.mat)
    * 容积多项式系数 (aging_kinetics.NCA_V_REL_COEFF / GRAPHITE_V_REL_COEFF)
    都是本函数要组装的外部资源。

    返回的对象尚未初始化到具体 SOC，调用方需再执行 ``cell.init(0.5)``。
    """
    # ---------- 1. 半电池热力学 & 电阻 LUT ---------------------------
    anode_thermo = HalfCellThermo.from_dat_file(default_data_path("GraphiteAlawa.dat"))
    cathode_thermo = HalfCellThermo.from_dat_file(default_data_path("NCAAlawa.dat"))
    r_luts = ResistanceLUTs.from_mat_file(default_data_path("ResistancesAlawa.mat"))

    # ---------- 2. 电极容量 (电极平衡 from alawa) --------------------
    # alawa 参数:
    LR = 1.04                      # 负载比 = C_NE/C_PE (FIT-1 拟合结果)
    OFS = 2.0                      # 偏移 (% of PE capacity, FIT-1 拟合结果)
    # 注意 dX_PE_alawa 与论文 Table II 的 0.788 存在 2.2% 差异 (低严重度 errata S1):
    # 论文文本写 0.788 但 MATLAB 代码用 0.771，未解释原因。这里忠于 MATLAB 值。
    # 详见 docs/CRITICAL_REVIEW.md § S1。
    dX_PE_alawa = 0.7710           # alawa 给出的 PE 可循环化学计量跨度
    dX_NE_alawa = 0.9600           # alawa 给出的 NE 可循环化学计量跨度
    X0_PE_alawa = 0.95             # 新电池的 PE 化学计量
    X0_NE_alawa = 0.01             # 新电池的 NE 化学计量

    # 初始 PE 总容量 [A·s]
    # 注意: "/0.973 * 1.0275" 是 ~5.6% 的经验修正因子，用来让仿真 C/20 放电
    # 曲线与实验一致 (即这里隐含一次 FIT-0 scalar 拟合)。论文 Appendix Eq. 54
    # 上方声明: C_PE^0 "is obtained by fitting a simulation against an
    # experimental C/40 discharge curve". 切换到新电池时必须重做此拟合。
    # TODO(v2): 提供 scripts/fit_C0_PE_correction.py 自动化这一步。
    C0_PE = 3.35 / dX_PE_alawa / (1.0 - OFS / 100.0) * 3600.0 / 0.973 * 1.0275
    C0_NE = C0_PE * LR * dX_PE_alawa / dX_NE_alawa

    # 初始 SEI = OFS% 的 PE 可循环容量 (表示工艺成形时的 LLI)
    Q0_SEI_NE = C0_PE * dX_PE_alawa * OFS / 100.0

    # ---------- 3. 封装老化模型 ---------------------------------------
    mvol_ne = MolarVolumeModel(v_coeff=GRAPHITE_V_REL_COEFF)
    mvol_pe = MolarVolumeModel(v_coeff=NCA_V_REL_COEFF)

    aging = AgingModel(
        # SEI 参数 (论文 Table Ib/Ic)
        #
        # **重要 errata E1** (详见 docs/CRITICAL_REVIEW.md § E1):
        # 论文 Table Ib 报告 k_cal = 4.2e-22 A²·s 是排版错误 (多打了一个 "2"),
        # 正确值来自 MATLAB Zenodo 源码: 0.0419625 ≈ 4.2e-2 A²·s.
        # 量纲分析和前向仿真健全性检查都支持代码值。
        sei=SEIParameters(
            k_cal=0.0419625,   # [A²·s] 注意单位是 A²·s, 不是论文列的 A·s
            k_cyc=0.470222457210748,  # [F = A·s/V] (FIT-4b)
            Ea=55500.0,        # [J/mol] 注意: 只有 SEI 有 Arrhenius (S3)
            alpha_f=0.5,
        ),
        # 镀锂参数 (Table Ic)
        #
        # **errata S2** (详见 docs/CRITICAL_REVIEW.md § S2):
        # V_LP_eq = 0V 是静态假设，Beck-Greszta-Roberts-Dubarry 2024
        # (Batteries 10:408, 同一高级作者) 指出这"在稳态之外不成立"。
        # 对于 >1C 快充或 <15°C 低温场景不够准确。
        # TODO(v2): 支持动态 V_LP_eq = f(T, c_Li+) 实现 Beck 2024 修正。
        plating=PlatingParameters(
            k_LP=2.32859595117188e-4,
            alpha_LP=0.5,
            V_LP_eq=0.0,
        ),
        # LAM_PE (Table Ib/Ic)
        lam_pe=LAMParameters(
            k_cal=1.1525690494e-11,
            k_cyc=2.72698288891875e-3,
            gamma=3.1844505,
        ),
        # LAM_NE —— 论文假设 k_cal=0 (NE 日历 LAM 可忽略)
        lam_ne=LAMParameters(
            k_cal=0.0,
            k_cyc=3.87e-4,
            gamma=-53.787745,    # 虽然 k_cal=0，此值与 MATLAB 一致保留
        ),
        # 电阻退化参数 (论文 Table Ib)
        #
        # **注意** (详见 docs/CRITICAL_REVIEW.md § C3):
        # 模型假设 R_s 不随老化变化 (f_R,s=1，Eq. 46)。post-mortem 文献
        # 显示 R_s 实际会增长 10-30%，这会让模型略微低估末期极化。
        # TODO(v2): 实现 f_R_s(Q_SEI, Q_LAM) 作为可选扩展。
        #
        # **R_NE_0 必须与 R_NE_LUT 配套更新**: 切换到新电池时需从
        # 新 fresh-cell R_NE_LUT 在 (50% SOC, C/3) 处重新取值。
        resistance_aging=ResistanceAgingParameters(
            R_SEI=0.66,           # [Ω(归一化)] FIT-4a (注意: 从**日历**拟合, 不是循环)
            R_NE_0=0.018236,      # [Ω] 从 R_NE_LUT 派生的锚点
        ),
        mvol_ne=mvol_ne,
        mvol_pe=mvol_pe,
        # 初始退化态 (只有 SEI 非零，即工艺成形形成)
        Q0_LLI_PE=0.0,
        Q0_LLI_NE=Q0_SEI_NE,       # LLI_NE 初始值等于 SEI_NE 初始值
        Q0_LAM_PE=0.0,
        Q0_LAM_NE=0.0,
        Q0_SEI_NE=Q0_SEI_NE,
        Q0_PLA_NE=0.0,
        # 失去活性材料中 Li 化学计量 (论文中均设为 0)
        X_LAM_PE=lambda X_pe: 0.0,
        X_LAM_NE=lambda X_ne: 0.0,
        acceleration_factor=1.0,
    )

    # ---------- 4. 建立电池对象 (先用占位电阻函数) --------------------
    # 先用 CN = 3.35 Ah 做定标 (MATLAB 里 init 一次后再读取 cell.C)
    CN_Ah = 3.35
    CN_As = CN_Ah * 3600.0      # 标称容量 [A·s]

    # 构造 resistance closures —— 与 MATLAB 完全一致的映射:
    # 返回的电阻值已经按 CN 做了归一化反演: R = (1/CN_Ah) * R_table(...)
    def Rs_fn(T, X_ne, X_pe, I):
        c_rate = np.clip(-I * 3600.0 / CN_As, -4.0, 4.0)
        return (1.0 / CN_Ah) * r_luts.interp_Rs(c_rate, 0.0)

    def R1_fn(T, X_ne, X_pe, I):
        c_rate = -I * 3600.0 / CN_As
        return (1.0 / CN_Ah) * r_luts.interp_RNE(c_rate, X_ne)

    def R2_fn(T, X_ne, X_pe, I):
        c_rate = -I * 3600.0 / CN_As
        return (1.0 / CN_Ah) * r_luts.interp_RPE(c_rate, X_pe)

    cell = EquivCircuitCell(
        anode_thermo=anode_thermo,
        cathode_thermo=cathode_thermo,
        resistance_luts=r_luts,
        Rs_fn=Rs_fn,
        R1_fn=R1_fn,
        R2_fn=R2_fn,
        C1=949.28,       # NE 侧 RC 电容 [F]
        C2=3576.07,      # PE 侧 RC 电容 [F]
        fractionR1toRs=0.5,
        fractionR2toRs=0.5,
        fractionR3toRs=0.5,
        T_ambient=298.15,
        aging_V_max=4.2,
        aging_V_min=2.5,
        aging_C0_PE=C0_PE,
        aging_C0_NE=C0_NE,
        aging_X0_PE=X0_PE_alawa,
        aging_X0_NE=X0_NE_alawa,
        aging=aging,
        tolerance_rel=1e-8,
        tolerance_abs=1e-8,
    )
    return cell
