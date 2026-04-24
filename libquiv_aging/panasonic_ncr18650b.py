"""
panasonic_ncr18650b.py
======================
Panasonic NCR18650B (3.35 Ah, NCA/Graphite) compatibility shim.

**This module is now a compatibility layer.** The actual cell parameters
are stored in:

- ``material_specs/panasonic_ncr18650b.material.json``
- ``param_specs/panasonic_ncr18650b__mmeka2025.params.json``

The ``create_panasonic_ncr18650b()`` function signature and behavior are
unchanged from v0.2.x. It internally calls ``create_cell_from_specs()``
to construct the cell from the spec files.

New cell types should use ``create_cell_from_specs()`` directly rather
than creating a similar hardcoded factory module.
"""

from __future__ import annotations

from .cell_model import EquivCircuitCell


def create_panasonic_ncr18650b() -> EquivCircuitCell:
    """
    Create and return a fully parameterized Panasonic NCR18650B cell.

    This is a compatibility shim that delegates to
    ``create_cell_from_specs()`` with the bundled NCR18650B spec files.

    The returned object is not yet initialized to a specific SOC;
    call ``cell.init(0.5)`` before simulation.
    """
    from .cell_factory import create_cell_from_specs, _project_root

    root = _project_root()
    material_path = root / "material_specs" / "panasonic_ncr18650b.material.json"
    params_path = root / "param_specs" / "panasonic_ncr18650b__mmeka2025.params.json"
    return create_cell_from_specs(material_path, params_path)
