"""
libquiv_aging
=============
物理信息化老化敏感等效电路锂离子电池模型 (Python 移植)。

主要 API:
    - ``EquivCircuitCell``  : 单体电池类
    - ``AgingModel``        : 老化参数策略容器
    - ``create_panasonic_ncr18650b()`` : 预参数化好的 NCR18650B 工厂

原 MATLAB 实现和本论文:
    Patricia O. Mmeka, Matthieu Dubarry, Wolfgang G. Bessler,
    "Physics-Informed Aging-Sensitive Equivalent Circuit Model for Predicting
    the Knee in Lithium-Ion Batteries",
    J. Electrochem. Soc. 172 080538 (2025).
"""

from .aging_kinetics import (
    AgingModel, LAMParameters, MolarVolumeModel, PlatingParameters,
    ResistanceAgingParameters, SEIParameters,
)
from .cell_model import EquivCircuitCell
from .lookup_tables import (
    HalfCellThermo, ResistanceLUTs, default_data_path, open_circuit_voltage,
)
from .cell_factory import create_cell_from_specs
from .panasonic_ncr18650b import create_panasonic_ncr18650b

__all__ = [
    "EquivCircuitCell",
    "AgingModel",
    "SEIParameters",
    "PlatingParameters",
    "LAMParameters",
    "ResistanceAgingParameters",
    "MolarVolumeModel",
    "HalfCellThermo",
    "ResistanceLUTs",
    "open_circuit_voltage",
    "default_data_path",
    "create_panasonic_ncr18650b",
    "create_cell_from_specs",
]
