"""
lookup_tables.py
================
封装模型需要的所有查找表（Look-Up Tables, LUT）及其插值逻辑。

本模块包含两类 LUT：

1. **半电池热力学数据**（Half-Cell Thermodynamic Data）
   - 从 ``GraphiteAlawa.dat`` 和 ``NCAAlawa.dat`` 中读入的 (x, dH, dS) 表格。
   - 经过上采样到 1001 个等距 x 点（x ∈ [0, 1]，步长 0.001），方便快速线性插值。
   - 核心物理：由 dH 和 dS 可计算半电池开路电压

         V^0(X, T) = -(dH(X) - T * dS(X)) / F        (论文式 28 中的 V_PE^0, V_NE^0)

2. **电阻 LUT**（Resistance Look-Up Tables）
   - 从 ``ResistancesAlawa.mat`` 读入 ``RsAlawa``、``RNEAlawa``、``RPEAlawa``，
     尺寸均为 (1001, 2001)。
   - 第 0 维（行）对应 SOC/化学计量数（0–1，步长 0.001）；
     第 1 维（列）对应归一化电流 / C-rate（-4C 到 +4C，步长 0.004）。
   - 使用 MATLAB 原 ``interpolateR`` 中的双线性插值公式完全一致地移植，
     以保证结果可逐字节对齐 MATLAB 结果。

所有函数都返回纯 numpy 数组，便于在 ODE 右端向量化调用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

import numpy as np
from scipy.io import loadmat

from .constants import F, DATA_SUBDIR


# ----------------------------------------------------------------------------- #
# 1. 半电池热力学数据
# ----------------------------------------------------------------------------- #
@dataclass
class HalfCellThermo:
    """
    单个电极的热力学数据容器。

    字段
    ----
    dH_1001 : np.ndarray
        Enthalpy 在 x = 0, 0.001, ..., 1.0 共 1001 个点上的等距采样 [J/mol]。
    dS_1001 : np.ndarray
        Entropy 在同样的 x 网格上的等距采样 [J/(mol·K)]。

    对应 MATLAB 中的 ``deltaH_anode_1001P / deltaH_cathode_1001P`` 等字段。
    """

    dH_1001: np.ndarray
    dS_1001: np.ndarray

    # ------------------------------------------------------------------ #
    # 从 .dat 文件读取并插值到 1001 等距点
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dat_file(cls, path: str) -> "HalfCellThermo":
        """
        解析 alawa 格式的 .dat 文件 (三列: x, dH, dS, 星号开头为注释)。
        把数据线性插值到 1001 等距 x 点并返回对象。
        """
        # np.genfromtxt 跳过 '*' 注释行
        data = np.genfromtxt(path, comments="*")
        x_raw = data[:, 0]
        dh_raw = data[:, 1]
        ds_raw = data[:, 2]

        # alawa 的 x 通常是从大到小（1→0）排列，np.interp 要求 x 升序 —— 先排序
        order = np.argsort(x_raw)
        x_sorted = x_raw[order]
        dh_sorted = dh_raw[order]
        ds_sorted = ds_raw[order]

        x_grid = np.linspace(0.0, 1.0, 1001)
        dH_1001 = np.interp(x_grid, x_sorted, dh_sorted)
        dS_1001 = np.interp(x_grid, x_sorted, ds_sorted)
        return cls(dH_1001=dH_1001, dS_1001=dS_1001)

    # ------------------------------------------------------------------ #
    # 在给定 x (与 Matlab LUT_X 完全一致) 下的线性插值
    # ------------------------------------------------------------------ #
    def interp_dH_dS(self, X: np.ndarray | float) -> Tuple[np.ndarray, np.ndarray]:
        """
        以与 MATLAB 中 LUT_X 完全一致的线性插值方式，返回 (dH, dS)。

        MATLAB 源码:
            i  = X*1000 + 1;   fi = floor(i);  fi 夹在 [1, 1000]
            dH = (1-(i-fi)).*dH_1001(fi) + (i-fi).*dH_1001(fi+1);

        Python 端使用 0-index，因此索引公式为::

            i  = X * 1000
            fi = floor(i) 且 clamp(fi, 0, 999)
            frac = i - fi
            dH = (1-frac) * dH_1001[fi] + frac * dH_1001[fi+1]
        """
        X_arr = np.atleast_1d(X).astype(float)
        i = X_arr * 1000.0
        fi = np.floor(i).astype(int)
        fi = np.clip(fi, 0, 999)           # 保证 fi+1 <= 1000
        frac = i - fi.astype(float)

        dH = (1.0 - frac) * self.dH_1001[fi] + frac * self.dH_1001[fi + 1]
        dS = (1.0 - frac) * self.dS_1001[fi] + frac * self.dS_1001[fi + 1]

        if np.isscalar(X):
            return float(dH[0]), float(dS[0])
        return dH, dS


# ----------------------------------------------------------------------------- #
# 2. OCV / 电池电压计算
# ----------------------------------------------------------------------------- #
def open_circuit_voltage(
    X_ne: np.ndarray | float,
    X_pe: np.ndarray | float,
    T: np.ndarray | float,
    anode_thermo: HalfCellThermo,
    cathode_thermo: HalfCellThermo,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    给定 NE/PE 的化学计量数 X_ne, X_pe 和温度 T，返回半电池开路电压和总电池开路电压。

    对应 MATLAB 的 LUT_X 方法:
        V0_NE = -(dH_ne - T * dS_ne) / F
        V0_PE = -(dH_pe - T * dS_pe) / F
        V0    =  V0_PE - V0_NE                  (论文式 28)

    返回
    ----
    V0    : 电池开路电压 V_cell^0 = V_PE^0 - V_NE^0 [V]
    dS_NE : NE 的熵变（供温度建模使用，本代码中未进一步使用）
    dS_PE : PE 的熵变
    V0_PE : PE 半电池开路电压 [V vs Li+/Li]
    V0_NE : NE 半电池开路电压 [V vs Li+/Li]
    """
    dH_ne, dS_ne = anode_thermo.interp_dH_dS(X_ne)
    dH_pe, dS_pe = cathode_thermo.interp_dH_dS(X_pe)

    V0_NE = -(dH_ne - T * dS_ne) / F
    V0_PE = -(dH_pe - T * dS_pe) / F
    V0 = V0_PE - V0_NE
    return V0, dS_ne, dS_pe, V0_PE, V0_NE


# ----------------------------------------------------------------------------- #
# 3. 电阻查找表
# ----------------------------------------------------------------------------- #
@dataclass
class ResistanceLUTs:
    """
    资源管理器：加载并插值串联/NE/PE 电阻矩阵。

    矩阵形状约定 (与 MATLAB 完全一致):
        - 行: SOC (或化学计量数 X * 100 后再除 100 = X) 以 0.001 步长离散化，共 1001 点
        - 列: C-rate 从 -4 到 +4 以 0.004 步长离散化，共 2001 点

    插值索引公式 (与 MATLAB interpolateR 等价):
        nY = clip(SOC * 1000, 0, 1000)
        nX = clip((C_rate + 4) * 250, 0, 2000)
    """

    Rs: np.ndarray     # (1001, 2001) 串联电阻（实际上文件中是常数，仅第一列有变化的可能性）
    RNE: np.ndarray    # (1001, 2001) NE 电阻
    RPE: np.ndarray    # (1001, 2001) PE 电阻

    @classmethod
    def from_mat_file(cls, path: str) -> "ResistanceLUTs":
        """从 ResistancesAlawa.mat 加载三张 2D 电阻表。"""
        data = loadmat(path)
        return cls(Rs=data["RsAlawa"], RNE=data["RNEAlawa"], RPE=data["RPEAlawa"])

    # ------------------------------------------------------------------ #
    # 与 MATLAB interpolateR 完全一致的双线性插值
    # 提供两条路径: (1) 标量快速路径, (2) 数组广播路径
    # ------------------------------------------------------------------ #
    @staticmethod
    def _interp_scalar(R: np.ndarray, C_rate: float, SOC_percent: float) -> float:
        """标量快速路径 —— 避免 numpy 数组创建开销 (用于 ODE RHS 热循环)。"""
        # 夹持
        if C_rate > 4.0:
            C_rate = 4.0
        elif C_rate < -4.0:
            C_rate = -4.0
        if SOC_percent > 100.0:
            SOC_percent = 100.0
        elif SOC_percent < 0.0:
            SOC_percent = 0.0

        nY = SOC_percent * 10.0             # = /100 * 1000
        nX = (C_rate + 4.0) * 250.0
        fnY = int(nY)
        if fnY > 999:
            fnY = 999
        fnX = int(nX)
        if fnX > 1999:
            fnX = 1999
        fracY = nY - fnY
        fracX = nX - fnX

        v11 = R[fnY, fnX]
        v12 = R[fnY, fnX + 1]
        v21 = R[fnY + 1, fnX]
        v22 = R[fnY + 1, fnX + 1]
        v_bot = (1.0 - fracX) * v11 + fracX * v12
        v_top = (1.0 - fracX) * v21 + fracX * v22
        return (1.0 - fracY) * v_bot + fracY * v_top

    @staticmethod
    def _interp(R: np.ndarray, C_rate, SOC_percent) -> np.ndarray:
        """数组版双线性插值 (与 MATLAB interpolateR 完全一致的语义)。"""
        C_rate = np.atleast_1d(np.asarray(C_rate, dtype=float))
        SOC_percent = np.atleast_1d(np.asarray(SOC_percent, dtype=float))
        C_rate = np.clip(C_rate, -4.0, 4.0)

        nY = np.clip(SOC_percent / 100.0 * 1000.0, 0.0, 1000.0)
        fnY = np.clip(np.floor(nY).astype(int), 0, 999)
        fracY = nY - fnY.astype(float)

        nX = np.clip((C_rate + 4.0) * 250.0, 0.0, 2000.0)
        fnX = np.clip(np.floor(nX).astype(int), 0, 1999)
        fracX = nX - fnX.astype(float)

        fnY_b, fnX_b = np.broadcast_arrays(fnY, fnX)
        fracY_b, fracX_b = np.broadcast_arrays(fracY, fracX)
        v11 = R[fnY_b, fnX_b]
        v12 = R[fnY_b, fnX_b + 1]
        v21 = R[fnY_b + 1, fnX_b]
        v22 = R[fnY_b + 1, fnX_b + 1]
        v_bot = (1.0 - fracX_b) * v11 + fracX_b * v12
        v_top = (1.0 - fracX_b) * v21 + fracX_b * v22
        return (1.0 - fracY_b) * v_bot + fracY_b * v_top

    # ---- 3 个公开插值方法 (返回 Python float) --------------------------- #
    def interp_Rs(self, C_rate: float, SOC_percent: float = 0.0) -> float:
        """Rs 仅有电流依赖（SOC 无关——在 alawa 中 Rs 是列向量常数）。"""
        return self._interp_scalar(self.Rs, C_rate, SOC_percent)

    def interp_RNE(self, C_rate: float, X_ne: float) -> float:
        """X_ne ∈ [0, 1]，内部转换为 SOC 百分比 = X_ne * 100。"""
        if X_ne < 0.0:
            X_ne = 0.0
        elif X_ne > 1.0:
            X_ne = 1.0
        return self._interp_scalar(self.RNE, C_rate, X_ne * 100.0)

    def interp_RPE(self, C_rate: float, X_pe: float) -> float:
        if X_pe < 0.0:
            X_pe = 0.0
        elif X_pe > 1.0:
            X_pe = 1.0
        return self._interp_scalar(self.RPE, C_rate, X_pe * 100.0)


# ----------------------------------------------------------------------------- #
# 4. 工具: 解析工程内 data/ 文件路径
# ----------------------------------------------------------------------------- #
def default_data_path(filename: str) -> str:
    """
    返回封装在包内的数据文件绝对路径。

    用于 ``HalfCellThermo.from_dat_file(default_data_path('GraphiteAlawa.dat'))``
    等场景。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, DATA_SUBDIR, filename)
