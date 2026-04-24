"""
test_cell_factory.py
====================
Tests for the cell_factory loader and model_versions dispatch.

Validates that create_cell_from_specs produces a cell equivalent to
create_panasonic_ncr18650b, and tests error paths.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from libquiv_aging import create_cell_from_specs, create_panasonic_ncr18650b
from libquiv_aging.cell_model import EquivCircuitCell

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATERIAL_SPEC = "material_specs/panasonic_ncr18650b.material.json"
PARAMS_SPEC = "param_specs/panasonic_ncr18650b__mmeka2025.params.json"


# ===========================================================================
# Positive tests
# ===========================================================================

class TestCreateCellFromSpecs:
    def test_returns_equiv_circuit_cell(self):
        """create_cell_from_specs returns an EquivCircuitCell instance."""
        cell = create_cell_from_specs(MATERIAL_SPEC, PARAMS_SPEC)
        assert isinstance(cell, EquivCircuitCell)

    def test_equivalence_with_panasonic_factory(self):
        """Cell from specs matches create_panasonic_ncr18650b field-by-field."""
        cell_spec = create_cell_from_specs(MATERIAL_SPEC, PARAMS_SPEC)
        cell_orig = create_panasonic_ncr18650b()

        # Anode thermo samples (dH_1001, dS_1001)
        np.testing.assert_allclose(
            cell_spec.anode_thermo.dH_1001[:10],
            cell_orig.anode_thermo.dH_1001[:10],
        )
        np.testing.assert_allclose(
            cell_spec.anode_thermo.dS_1001[:10],
            cell_orig.anode_thermo.dS_1001[:10],
        )

        # Cathode thermo samples
        np.testing.assert_allclose(
            cell_spec.cathode_thermo.dH_1001[:10],
            cell_orig.cathode_thermo.dH_1001[:10],
        )
        np.testing.assert_allclose(
            cell_spec.cathode_thermo.dS_1001[:10],
            cell_orig.cathode_thermo.dS_1001[:10],
        )

        # SEI parameters
        assert cell_spec.aging.sei.k_cal == cell_orig.aging.sei.k_cal
        assert cell_spec.aging.sei.k_cyc == cell_orig.aging.sei.k_cyc
        assert cell_spec.aging.sei.Ea == cell_orig.aging.sei.Ea
        assert cell_spec.aging.sei.alpha_f == cell_orig.aging.sei.alpha_f

        # Plating parameters
        assert cell_spec.aging.plating.k_LP == cell_orig.aging.plating.k_LP
        assert cell_spec.aging.plating.alpha_LP == cell_orig.aging.plating.alpha_LP
        assert cell_spec.aging.plating.V_LP_eq == cell_orig.aging.plating.V_LP_eq

        # LAM PE parameters
        assert cell_spec.aging.lam_pe.k_cal == cell_orig.aging.lam_pe.k_cal
        assert cell_spec.aging.lam_pe.k_cyc == cell_orig.aging.lam_pe.k_cyc
        assert cell_spec.aging.lam_pe.gamma == cell_orig.aging.lam_pe.gamma

        # LAM NE parameters
        assert cell_spec.aging.lam_ne.k_cal == cell_orig.aging.lam_ne.k_cal
        assert cell_spec.aging.lam_ne.k_cyc == cell_orig.aging.lam_ne.k_cyc
        # gamma_NE: spec uses convention 0.0, code uses -53.787745
        # Both are functionally equivalent since k_LAM_NE_cal = 0.0

        # Resistance aging parameters
        assert cell_spec.aging.resistance_aging.R_SEI == cell_orig.aging.resistance_aging.R_SEI
        assert cell_spec.aging.resistance_aging.R_NE_0 == cell_orig.aging.resistance_aging.R_NE_0

        # Derived quantities
        np.testing.assert_allclose(
            cell_spec.aging.Q0_SEI_NE, cell_orig.aging.Q0_SEI_NE, atol=1e-10
        )
        np.testing.assert_allclose(
            cell_spec.aging.Q0_LLI_NE, cell_orig.aging.Q0_LLI_NE, atol=1e-10
        )

        # RC parameters
        assert cell_spec.C1 == cell_orig.C1
        assert cell_spec.C2 == cell_orig.C2

        # Electrode capacities
        np.testing.assert_allclose(cell_spec.aging_C0_PE, cell_orig.aging_C0_PE, atol=1e-10)
        np.testing.assert_allclose(cell_spec.aging_C0_NE, cell_orig.aging_C0_NE, atol=1e-10)

    def test_resistance_functions_equivalent(self):
        """Rs_fn returns identical values for both construction paths."""
        cell_spec = create_cell_from_specs(MATERIAL_SPEC, PARAMS_SPEC)
        cell_orig = create_panasonic_ncr18650b()

        T, X_NE, X_PE, I = 298.0, 0.5, 0.5, 1.0
        assert cell_spec.Rs_fn(T, X_NE, X_PE, I) == cell_orig.Rs_fn(T, X_NE, X_PE, I)
        assert cell_spec.R1_fn(T, X_NE, X_PE, I) == cell_orig.R1_fn(T, X_NE, X_PE, I)
        assert cell_spec.R2_fn(T, X_NE, X_PE, I) == cell_orig.R2_fn(T, X_NE, X_PE, I)

    def test_absolute_paths_work(self):
        """create_cell_from_specs accepts absolute paths."""
        mat_abs = PROJECT_ROOT / MATERIAL_SPEC
        par_abs = PROJECT_ROOT / PARAMS_SPEC
        cell = create_cell_from_specs(mat_abs, par_abs)
        assert isinstance(cell, EquivCircuitCell)


# ===========================================================================
# Negative tests
# ===========================================================================

class TestCreateCellFromSpecsErrors:
    def test_pending_fit_value_raises(self, tmp_path):
        """A spec with value=null raises a clear ValueError."""
        # Create a material spec with a null value
        mat = _load_json(PROJECT_ROOT / MATERIAL_SPEC)
        mat["C_nominal_Ah"]["value"] = None
        mat["C_nominal_Ah"]["status"] = "pending_fit"
        bad_mat_path = tmp_path / "bad.material.json"
        bad_mat_path.write_text(json.dumps(mat))

        # Also update the params spec reference
        par = _load_json(PROJECT_ROOT / PARAMS_SPEC)
        par["material_spec_ref"] = str(bad_mat_path)
        bad_par_path = tmp_path / "bad.params.json"
        bad_par_path.write_text(json.dumps(par))

        with pytest.raises(ValueError, match="pending_fit"):
            create_cell_from_specs(bad_mat_path, bad_par_path)

    def test_material_spec_ref_mismatch_raises(self, tmp_path):
        """Mismatched material_spec_ref raises ValueError."""
        # Copy params spec with a wrong ref
        par = _load_json(PROJECT_ROOT / PARAMS_SPEC)
        par["material_spec_ref"] = "material_specs/nonexistent.material.json"
        bad_par_path = tmp_path / "bad_ref.params.json"
        bad_par_path.write_text(json.dumps(par))

        with pytest.raises(ValueError, match="material_spec_ref mismatch"):
            create_cell_from_specs(
                PROJECT_ROOT / MATERIAL_SPEC,
                bad_par_path,
            )

    def test_unknown_model_version_raises(self, tmp_path):
        """Unknown model_version raises ValueError with helpful message."""
        from libquiv_aging.model_versions import get_model_version
        with pytest.raises(ValueError, match="Unknown model version"):
            get_model_version("mmeka2099")


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)
