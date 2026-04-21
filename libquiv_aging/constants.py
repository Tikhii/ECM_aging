"""
constants.py
============
物理常数和全局默认配置。

对应 Matlab 原代码中直接出现的数值常量（如 F = 96485, R = 8.314）。
在 Python 端集中管理，便于后续维护和单位的一致性检查。
"""

# --- 普世物理常数 ---
F: float = 96485.0        # 法拉第常数 [C/mol]，与 LIBquivAging.m 中 self.F 对应
R_GAS: float = 8.314      # 气体常数   [J/(mol·K)]
T_REF: float = 298.15     # 参考温度   [K]，用于 Arrhenius 项

# --- 数据文件查找 ---
# 封装进包内的数据目录名称。cell_model / parameterization 中通过 importlib.resources 解析。
DATA_SUBDIR: str = "data"
