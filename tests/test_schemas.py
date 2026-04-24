"""
test_schemas.py
===============
Schema self-validation and spec compliance tests for the double-spec architecture.

Tests that:
1. JSON Schema files are valid schemas loadable by jsonschema
2. Example spec files pass schema validation
3. Various violation patterns are correctly rejected
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, ValidationError, validate

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

MATERIAL_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "material.schema.v1.json"
PARAMS_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "params_mmeka2025.schema.v1.json"
MATERIAL_SPEC_PATH = PROJECT_ROOT / "material_specs" / "panasonic_ncr18650b.material.json"
PARAMS_SPEC_PATH = PROJECT_ROOT / "param_specs" / "panasonic_ncr18650b__mmeka2025.params.json"


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def material_schema():
    return _load_json(MATERIAL_SCHEMA_PATH)


@pytest.fixture(scope="module")
def params_schema():
    return _load_json(PARAMS_SCHEMA_PATH)


@pytest.fixture(scope="module")
def material_spec():
    return _load_json(MATERIAL_SPEC_PATH)


@pytest.fixture(scope="module")
def params_spec():
    return _load_json(PARAMS_SPEC_PATH)


# ===========================================================================
# 1. Schema self-validation (schemas are valid JSON Schema draft-07)
# ===========================================================================
class TestSchemaValidity:
    def test_material_schema_is_valid(self, material_schema):
        """material.schema.v1.json is a valid JSON Schema draft-07."""
        Draft7Validator.check_schema(material_schema)

    def test_params_schema_is_valid(self, params_schema):
        """params_mmeka2025.schema.v1.json is a valid JSON Schema draft-07."""
        Draft7Validator.check_schema(params_schema)


# ===========================================================================
# 2. Example specs pass schema validation
# ===========================================================================
class TestSpecCompliance:
    def test_material_spec_validates(self, material_schema, material_spec):
        """panasonic_ncr18650b.material.json passes material schema."""
        validate(instance=material_spec, schema=material_schema)

    def test_params_spec_validates(self, params_schema, params_spec):
        """panasonic_ncr18650b__mmeka2025.params.json passes params schema."""
        validate(instance=params_spec, schema=params_schema)


# ===========================================================================
# 3. Violation patterns are correctly rejected
# ===========================================================================
class TestViolationDetection:
    def test_missing_required_field_material(self, material_schema, material_spec):
        """Missing a required field (cell_type) is rejected."""
        bad = copy.deepcopy(material_spec)
        del bad["cell_type"]
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_wrong_schema_version(self, material_schema, material_spec):
        """Wrong schema_version value is rejected."""
        bad = copy.deepcopy(material_spec)
        bad["schema_version"] = "material.v99"
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_invalid_status_enum(self, material_schema, material_spec):
        """Invalid status enum value is rejected."""
        bad = copy.deepcopy(material_spec)
        bad["C_nominal_Ah"]["status"] = "guessed"
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_fitted_status_requires_fit_fields(self, material_schema, material_spec):
        """status=fitted with null fit_r_squared is rejected."""
        bad = copy.deepcopy(material_spec)
        bad["C_nominal_Ah"]["status"] = "fitted"
        bad["C_nominal_Ah"]["fit_step"] = "FIT-0"
        bad["C_nominal_Ah"]["fit_source"] = "scripts/fit.py"
        bad["C_nominal_Ah"]["fit_script_version"] = "abc123"
        # fit_r_squared is still null -> should fail
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_non_fitted_status_rejects_fit_fields(self, material_schema, material_spec):
        """status=datasheet with non-null fit_step is rejected."""
        bad = copy.deepcopy(material_spec)
        bad["C_nominal_Ah"]["fit_step"] = "FIT-0"  # status is datasheet
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_additional_properties_rejected(self, material_schema, material_spec):
        """Extra top-level properties are rejected (additionalProperties=false)."""
        bad = copy.deepcopy(material_spec)
        bad["bogus_field"] = 42
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_mvol_ne_graphite_standard_with_coeff_rejected(
        self, material_schema, material_spec
    ):
        """graphite_standard mode with non-null coeff is rejected."""
        bad = copy.deepcopy(material_spec)
        bad["mvol_ne_mode"] = "graphite_standard"
        bad["mvol_ne_coeff"] = [1.0] * 10
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=material_schema)

    def test_missing_required_field_params(self, params_schema, params_spec):
        """Missing a required field (k_SEI_cal) in params spec is rejected."""
        bad = copy.deepcopy(params_spec)
        del bad["k_SEI_cal"]
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=params_schema)

    def test_wrong_model_version(self, params_schema, params_spec):
        """Wrong model_version value is rejected."""
        bad = copy.deepcopy(params_spec)
        bad["model_version"] = "mmeka2099"
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=params_schema)

    def test_invalid_resistance_mode(self, params_schema, params_spec):
        """Invalid resistance_mode enum is rejected."""
        bad = copy.deepcopy(params_spec)
        bad["resistance_mode"] = "unknown_mode"
        with pytest.raises(ValidationError):
            validate(instance=bad, schema=params_schema)
