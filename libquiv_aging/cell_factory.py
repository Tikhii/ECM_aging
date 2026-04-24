"""
cell_factory.py
===============
Generic loader for the double-spec cell type architecture.

The primary entry point is ``create_cell_from_specs(material_spec_path,
params_spec_path)``, which:

1. Validates both spec files against their respective JSON schemas.
2. Verifies that the params spec's material_spec_ref matches the given
   material spec path.
3. Derives dynamic quantities (C0_PE, C0_NE, Q0_SEI_NE, Q0_LLI_NE).
4. Loads half-cell thermodynamics and resistance LUTs.
5. Resolves molar volume models.
6. Dispatches to the appropriate model version for AgingModel assembly
   and resistance closure construction.
7. Constructs and returns an ``EquivCircuitCell``.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from .aging_kinetics import (
    GRAPHITE_V_REL_COEFF,
    MolarVolumeModel,
    NCA_V_REL_COEFF,
)
from .cell_model import EquivCircuitCell
from .lookup_tables import HalfCellThermo, ResistanceLUTs
from .model_versions import get_model_version


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Find the project root by searching upward for pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise FileNotFoundError(
        "Cannot find project root (no pyproject.toml found in parent directories)."
    )


def _load_spec(path: Path, schema_path: Path) -> dict:
    """Load a JSON spec file and validate it against the given schema.

    Raises jsonschema.ValidationError on schema violations.
    """
    with open(path) as f:
        spec = json.load(f)
    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.validate(instance=spec, schema=schema)
    return spec


def _extract_value(field_dict: dict, field_name: str) -> float:
    """Extract the numeric value from a value_with_provenance dict.

    Raises ValueError if value is None (pending_fit).
    """
    val = field_dict["value"]
    if val is None:
        raise ValueError(
            f"Field '{field_name}' has value=null (status='{field_dict['status']}'). "
            f"Cannot construct cell with pending_fit parameters. "
            f"Run the appropriate FIT script first."
        )
    return val


def _resolve_path(rel_path: str) -> Path:
    """Resolve a project-root-relative path to an absolute Path."""
    return _project_root() / rel_path


def _derive_C0_PE(material_spec: dict, params_spec: dict) -> float:
    """Derive initial PE capacity [A*s].

    C0_PE = C_nominal_Ah / dX_PE_alawa / (1 - OFS/100) * 3600
            * C0_PE_correction_factor
    """
    C_nom = _extract_value(material_spec["C_nominal_Ah"], "C_nominal_Ah")
    dX_PE = _extract_value(material_spec["dX_PE_alawa"], "dX_PE_alawa")
    OFS = _extract_value(material_spec["OFS"], "OFS")
    corr = _extract_value(params_spec["C0_PE_correction_factor"], "C0_PE_correction_factor")
    return C_nom / dX_PE / (1.0 - OFS / 100.0) * 3600.0 * corr


def _derive_C0_NE(C0_PE: float, material_spec: dict) -> float:
    """Derive initial NE capacity [A*s].

    C0_NE = C0_PE * LR * dX_PE_alawa / dX_NE_alawa
    """
    LR = _extract_value(material_spec["LR"], "LR")
    dX_PE = _extract_value(material_spec["dX_PE_alawa"], "dX_PE_alawa")
    dX_NE = _extract_value(material_spec["dX_NE_alawa"], "dX_NE_alawa")
    return C0_PE * LR * dX_PE / dX_NE


def _derive_Q0_SEI_NE(C0_PE: float, material_spec: dict) -> float:
    """Derive initial SEI charge on NE [A*s].

    Q0_SEI_NE = C0_PE * dX_PE_alawa * OFS / 100
    """
    dX_PE = _extract_value(material_spec["dX_PE_alawa"], "dX_PE_alawa")
    OFS = _extract_value(material_spec["OFS"], "OFS")
    return C0_PE * dX_PE * OFS / 100.0


def _load_mvol_model(mode: str, coeff_or_none) -> MolarVolumeModel:
    """Construct a MolarVolumeModel from the mode selector and optional coefficients."""
    if mode == "graphite_standard":
        return MolarVolumeModel(v_coeff=GRAPHITE_V_REL_COEFF)
    elif mode == "nca_standard":
        return MolarVolumeModel(v_coeff=NCA_V_REL_COEFF)
    elif mode == "lfp_linear":
        raise NotImplementedError(
            "Molar volume mode 'lfp_linear' is not yet implemented. "
            "Contributions welcome."
        )
    elif mode == "custom":
        if coeff_or_none is None:
            raise ValueError(
                "Molar volume mode 'custom' requires non-null coeff array."
            )
        import numpy as np
        return MolarVolumeModel(v_coeff=np.array(coeff_or_none))
    else:
        raise ValueError(f"Unknown molar volume mode '{mode}'.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_cell_from_specs(
    material_spec_path,
    params_spec_path,
) -> EquivCircuitCell:
    """Create an EquivCircuitCell from a material spec and a params spec.

    Parameters
    ----------
    material_spec_path : str or Path
        Path to the material spec JSON file (absolute or relative to project root).
    params_spec_path : str or Path
        Path to the params spec JSON file (absolute or relative to project root).

    Returns
    -------
    EquivCircuitCell
        A fully parameterized cell, not yet initialized to a specific SOC.
    """
    root = _project_root()

    # Normalize paths to absolute
    material_spec_path = Path(material_spec_path)
    params_spec_path = Path(params_spec_path)
    if not material_spec_path.is_absolute():
        material_spec_path = root / material_spec_path
    if not params_spec_path.is_absolute():
        params_spec_path = root / params_spec_path

    # Determine schema paths from schema_version
    material_schema_path = root / "schemas" / "material.schema.v1.json"
    params_schema_path = root / "schemas" / "params_mmeka2025.schema.v1.json"

    # 1. Load and validate specs
    material_spec = _load_spec(material_spec_path, material_schema_path)
    params_spec = _load_spec(params_spec_path, params_schema_path)

    # 2. Verify material_spec_ref consistency
    ref_path = (root / params_spec["material_spec_ref"]).resolve()
    actual_path = material_spec_path.resolve()
    if ref_path != actual_path:
        raise ValueError(
            f"material_spec_ref mismatch: params spec references "
            f"'{params_spec['material_spec_ref']}' (resolves to {ref_path}), "
            f"but material spec was loaded from {actual_path}."
        )

    # 3. Derive dynamic quantities
    C0_PE = _derive_C0_PE(material_spec, params_spec)
    C0_NE = _derive_C0_NE(C0_PE, material_spec)
    Q0_SEI_NE = _derive_Q0_SEI_NE(C0_PE, material_spec)
    Q0_LLI_NE = Q0_SEI_NE  # LLI_NE initial = SEI_NE initial

    # 4. Load half-cell thermodynamics and resistance LUTs
    anode_thermo = HalfCellThermo.from_dat_file(
        _resolve_path(material_spec["anode_thermo_dat"])
    )
    cathode_thermo = HalfCellThermo.from_dat_file(
        _resolve_path(material_spec["cathode_thermo_dat"])
    )
    r_luts = ResistanceLUTs.from_mat_file(
        _resolve_path(params_spec["resistance_mat"])
    )

    # 5. Resolve molar volume models
    mvol_ne = _load_mvol_model(
        material_spec["mvol_ne_mode"], material_spec["mvol_ne_coeff"]
    )
    mvol_pe = _load_mvol_model(
        material_spec["mvol_pe_mode"], material_spec["mvol_pe_coeff"]
    )

    # 6. Dispatch to model version
    model_version = params_spec["model_version"]
    mv = get_model_version(model_version)

    aging = mv["assemble"](
        params_spec, material_spec, mvol_ne, mvol_pe, Q0_SEI_NE, Q0_LLI_NE
    )
    Rs_fn, R1_fn, R2_fn = mv["resistance"](r_luts, material_spec, params_spec)

    # 7. Construct EquivCircuitCell
    V_max = _extract_value(material_spec["V_max"], "V_max")
    V_min = _extract_value(material_spec["V_min"], "V_min")
    X0_PE = _extract_value(material_spec["X0_PE"], "X0_PE")
    X0_NE = _extract_value(material_spec["X0_NE"], "X0_NE")

    cell = EquivCircuitCell(
        anode_thermo=anode_thermo,
        cathode_thermo=cathode_thermo,
        resistance_luts=r_luts,
        Rs_fn=Rs_fn,
        R1_fn=R1_fn,
        R2_fn=R2_fn,
        C1=_extract_value(params_spec["C1"], "C1"),
        C2=_extract_value(params_spec["C2"], "C2"),
        fractionR1toRs=_extract_value(params_spec["fractionR1toRs"], "fractionR1toRs"),
        fractionR2toRs=_extract_value(params_spec["fractionR2toRs"], "fractionR2toRs"),
        fractionR3toRs=0.5,
        T_ambient=298.15,
        aging_V_max=V_max,
        aging_V_min=V_min,
        aging_C0_PE=C0_PE,
        aging_C0_NE=C0_NE,
        aging_X0_PE=X0_PE,
        aging_X0_NE=X0_NE,
        aging=aging,
        tolerance_rel=1e-8,
        tolerance_abs=1e-8,
    )
    return cell
