"""Tests for libquiv_aging/fitting.py — FIT script shared infrastructure."""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from libquiv_aging.fitting import (
    PreflightError,
    RunArtifactWriter,
    compute_r_squared,
    compute_rmse,
    estimate_uncertainty_2var,
    get_git_commit_hash,
    hash_file,
    make_value_with_provenance,
    numerical_hessian_2x2,
    preflight_csv,
    preflight_material_spec,
    write_back_to_material_spec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PANASONIC_SPEC = ROOT / "material_specs" / "panasonic_ncr18650b.material.json"


def _copy_spec(tmp_path: Path) -> Path:
    """Copy the panasonic spec into tmp_path and return the new path."""
    dst = tmp_path / "test.material.json"
    shutil.copy2(PANASONIC_SPEC, dst)
    # Also copy the schema directory so write_back can find it
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    shutil.copy2(
        ROOT / "schemas" / "material.schema.v1.json",
        schema_dir / "material.schema.v1.json",
    )
    return dst


def _make_test_csv(tmp_path: Path, n_rows: int = 100,
                   soc_range: tuple = (0.0, 1.0),
                   columns: list | None = None) -> Path:
    """Create a test CSV with SOC and V_cell columns."""
    if columns is None:
        columns = ["SOC", "V_cell"]
    soc = np.linspace(soc_range[0], soc_range[1], n_rows)
    data = {"SOC": soc, "V_cell": 3.0 + 1.0 * soc}
    df = pd.DataFrame({c: data.get(c, np.zeros(n_rows)) for c in columns})
    path = tmp_path / "test_exp.csv"
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# preflight_material_spec
# ---------------------------------------------------------------------------

class TestPreflightMaterialSpec:
    def test_ok(self):
        spec = preflight_material_spec(
            PANASONIC_SPEC,
            required_fields=["dX_PE_alawa", "dX_NE_alawa", "X0_PE", "X0_NE"],
        )
        assert spec["cell_type"] == "panasonic_ncr18650b"

    def test_missing_dX(self, tmp_path):
        dst = _copy_spec(tmp_path)
        with open(dst) as f:
            spec = json.load(f)
        spec["dX_PE_alawa"]["value"] = None
        spec["dX_PE_alawa"]["status"] = "pending_fit"
        with open(dst, "w") as f:
            json.dump(spec, f)

        with pytest.raises(PreflightError) as exc_info:
            preflight_material_spec(
                dst,
                required_fields=["dX_PE_alawa", "dX_NE_alawa", "X0_PE", "X0_NE"],
            )
        assert exc_info.value.code == "FIT1-E001"
        assert exc_info.value.exit_code == 80


# ---------------------------------------------------------------------------
# preflight_csv
# ---------------------------------------------------------------------------

class TestPreflightCsv:
    def test_ok(self, tmp_path):
        csv_path = _make_test_csv(tmp_path, n_rows=100, soc_range=(0.0, 1.0))
        df = preflight_csv(
            csv_path,
            required_columns=["SOC", "V_cell"],
            min_rows=50, soc_min=0.05, soc_max=0.95,
        )
        assert len(df) == 100

    def test_missing_column(self, tmp_path):
        csv_path = _make_test_csv(tmp_path, columns=["SOC"])
        with pytest.raises(PreflightError) as exc_info:
            preflight_csv(csv_path, required_columns=["SOC", "V_cell"])
        assert exc_info.value.code == "DATA-E001"

    def test_too_few_rows(self, tmp_path):
        csv_path = _make_test_csv(tmp_path, n_rows=30)
        with pytest.raises(PreflightError) as exc_info:
            preflight_csv(csv_path, required_columns=["SOC", "V_cell"],
                          min_rows=50)
        assert exc_info.value.code == "DATA-E001"

    def test_soc_not_covering(self, tmp_path):
        csv_path = _make_test_csv(tmp_path, n_rows=100, soc_range=(0.5, 0.6))
        with pytest.raises(PreflightError) as exc_info:
            preflight_csv(csv_path, required_columns=["SOC", "V_cell"],
                          soc_min=0.05, soc_max=0.95)
        assert exc_info.value.code == "DATA-E001"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class TestDiagnostics:
    def test_compute_rmse(self):
        residuals = np.array([1.0, -1.0, 1.0, -1.0])
        assert compute_rmse(residuals) == pytest.approx(1.0)
        assert compute_rmse(np.zeros(10)) == pytest.approx(0.0)

    def test_compute_r_squared(self):
        # Perfect fit
        y = np.array([1.0, 2.0, 3.0])
        assert compute_r_squared(y, y) == pytest.approx(1.0)

        # Uncorrelated
        y_obs = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([2.0, 2.0, 2.0])  # mean prediction
        assert compute_r_squared(y_pred, y_obs) == pytest.approx(0.0)

    def test_numerical_hessian_2x2(self):
        # f(x, y) = x^2 + 2*y^2  =>  H = [[2, 0], [0, 4]]
        def quadratic(x):
            return x[0] ** 2 + 2.0 * x[1] ** 2

        H = numerical_hessian_2x2(quadratic, np.array([0.0, 0.0]), args=())
        np.testing.assert_allclose(H, [[2.0, 0.0], [0.0, 4.0]], atol=1e-4)

    def test_estimate_uncertainty_2var_well_posed(self):
        # Quadratic loss => well-defined uncertainty
        def loss(x):
            return x[0] ** 2 + 2.0 * x[1] ** 2

        s1, s2 = estimate_uncertainty_2var(
            loss, np.array([0.0, 0.0]), args=(),
            n_data=100, residual_sse=1.0,
        )
        assert np.isfinite(s1) and s1 > 0
        assert np.isfinite(s2) and s2 > 0

    def test_estimate_uncertainty_2var_singular(self):
        # Degenerate loss: f(x,y) = (x+y)^2  => H is singular
        def loss(x):
            return (x[0] + x[1]) ** 2

        s1, s2 = estimate_uncertainty_2var(
            loss, np.array([0.0, 0.0]), args=(),
            n_data=100, residual_sse=1.0,
        )
        # Hessian diagonal is positive but matrix is rank-1, so
        # either NaN from inversion issues or negative cov diagonal
        # In practice the Hessian [[2,2],[2,2]] is singular
        assert np.isnan(s1) or np.isnan(s2)


# ---------------------------------------------------------------------------
# value_with_provenance
# ---------------------------------------------------------------------------

class TestMakeValueWithProvenance:
    def test_status_fitted(self):
        vp = make_value_with_provenance(
            value=1.04, status="fitted",
            fit_step="FIT-1", fit_source="exp_a.csv@abc123",
            fit_script_version="deadbeef",
            fit_r_squared=0.999, uncertainty=0.001,
        )
        assert vp["value"] == 1.04
        assert vp["status"] == "fitted"
        assert vp["fit_step"] == "FIT-1"
        assert vp["fit_r_squared"] == 0.999
        assert vp["last_modified_at"] is not None

    def test_status_pending(self):
        vp = make_value_with_provenance(value=0.0, status="pending_fit")
        assert vp["fit_step"] is None
        assert vp["fit_source"] is None
        assert vp["fit_r_squared"] is None

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid status"):
            make_value_with_provenance(value=1.0, status="bogus")


# ---------------------------------------------------------------------------
# write_back_to_material_spec
# ---------------------------------------------------------------------------

class TestWriteBackToMaterialSpec:
    def test_write_back(self, tmp_path):
        dst = _copy_spec(tmp_path)

        LR_vp = make_value_with_provenance(
            value=1.05, status="fitted",
            fit_step="FIT-1", fit_source="test@hash",
            fit_script_version="abc", fit_r_squared=0.999,
        )
        OFS_vp = make_value_with_provenance(
            value=2.5, status="fitted",
            fit_step="FIT-1", fit_source="test@hash",
            fit_script_version="abc", fit_r_squared=0.999,
        )

        write_back_to_material_spec(dst, {"LR": LR_vp, "OFS": OFS_vp})

        with open(dst) as f:
            updated = json.load(f)

        assert updated["LR"]["value"] == 1.05
        assert updated["LR"]["status"] == "fitted"
        assert updated["LR"]["fit_step"] == "FIT-1"
        assert updated["OFS"]["value"] == 2.5
        # top-level last_modified_at should be updated
        assert updated["last_modified_at"] != "2026-04-24T00:00:00Z"

    def test_schema_validation_failure(self, tmp_path):
        dst = _copy_spec(tmp_path)

        # Save original for comparison
        with open(dst) as f:
            original = f.read()

        bad_vp = make_value_with_provenance(value=1.05, status="fitted")
        # 'fitted' status requires non-null fit_step etc. — but we left them null
        # This should fail schema validation

        with pytest.raises(ValueError, match="Schema validation failed"):
            write_back_to_material_spec(dst, {"LR": bad_vp})

        # File should not have been modified
        with open(dst) as f:
            assert f.read() == original


# ---------------------------------------------------------------------------
# Provenance tools
# ---------------------------------------------------------------------------

class TestProvenanceTools:
    def test_get_git_commit_hash(self):
        h = get_git_commit_hash()
        assert h != "unknown"
        assert len(h) >= 7  # short hash at minimum

    def test_hash_file(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("hello world\n")
        h1 = hash_file(p)
        assert len(h1) == 12
        # Stable: same content same hash
        h2 = hash_file(p)
        assert h1 == h2


# ---------------------------------------------------------------------------
# RunArtifactWriter
# ---------------------------------------------------------------------------

class TestRunArtifactWriter:
    def test_creates_artifacts(self, tmp_path):
        writer = RunArtifactWriter("fit1", "test_cell", base_dir=tmp_path)
        assert writer.run_dir.exists()

        writer.write_config(
            cli_args={"material_spec": "test.json", "dry_run": True},
            spec_hashes={"material": "abc123"},
            csv_hash="def456",
        )
        writer.write_report_md({
            "timestamp": "2026-04-25T00:00:00Z",
            "cell_type": "test_cell",
            "fit_step": "FIT-1",
            "parameters": {
                "LR": {"value": 1.04, "uncertainty": 0.001},
            },
            "rmse": 0.005,
            "r_squared": 0.999,
            "verdict": "pass",
            "converged": True,
            "n_iterations": 42,
            "optimizer_message": "Optimization terminated successfully.",
        })
        writer.write_diagnostic_json({
            "residuals": [0.001, -0.002],
            "hessian": [[2.0, 0.0], [0.0, 4.0]],
        })

        assert (writer.run_dir / "fit_config.json").exists()
        assert (writer.run_dir / "fit_report.md").exists()
        assert (writer.run_dir / "fit_diagnostic.json").exists()

        # Check config content
        with open(writer.run_dir / "fit_config.json") as f:
            config = json.load(f)
        assert config["run_id"] == writer.run_id
        assert config["cli_args"]["dry_run"] is True

        # Check report content
        report = (writer.run_dir / "fit_report.md").read_text()
        assert "LR" in report
        assert "RMSE" in report
