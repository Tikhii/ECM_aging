"""Tests for scripts/fit_electrode_balance.py — FIT-1 electrode balance fitting."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fit_electrode_balance.py"
PANASONIC_SPEC = ROOT / "material_specs" / "panasonic_ncr18650b.material.json"


def _run_script(*args, timeout=120) -> subprocess.CompletedProcess:
    """Run fit_electrode_balance.py as a subprocess."""
    cmd = [sys.executable, str(SCRIPT)] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=str(ROOT))


def _copy_spec_to_tmp(tmp_path: Path) -> Path:
    """Copy panasonic spec + schema dir into tmp_path for isolated testing."""
    dst = tmp_path / "test.material.json"
    shutil.copy2(PANASONIC_SPEC, dst)
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    shutil.copy2(
        ROOT / "schemas" / "material.schema.v1.json",
        schema_dir / "material.schema.v1.json",
    )
    return dst


def _generate_synthetic_csv(tmp_path: Path, spec_path: Path) -> Path:
    """Generate a synthetic EXP-A CSV from spec parameters using the model."""
    # Import here to avoid slow top-level import
    sys.path.insert(0, str(ROOT / "scripts"))
    from fit_electrode_balance import V_cell_model_array, _project_root
    from libquiv_aging.lookup_tables import HalfCellThermo

    with open(spec_path) as f:
        spec = json.load(f)

    project_root = _project_root()
    anode_thermo = HalfCellThermo.from_dat_file(
        project_root / spec["anode_thermo_dat"]
    )
    cathode_thermo = HalfCellThermo.from_dat_file(
        project_root / spec["cathode_thermo_dat"]
    )

    SOC = np.linspace(0.05, 0.95, 100)
    V_cell = V_cell_model_array(
        SOC, 1.04, 2.0,
        X0_PE=spec["X0_PE"]["value"],
        X0_NE=spec["X0_NE"]["value"],
        dX_PE=spec["dX_PE_alawa"]["value"],
        dX_NE=spec["dX_NE_alawa"]["value"],
        C_nominal_Ah=spec["C_nominal_Ah"]["value"],
        V_min=spec["V_min"]["value"],
        V_max=spec["V_max"]["value"],
        anode_thermo=anode_thermo,
        cathode_thermo=cathode_thermo,
        T_ref=298.15,
    )

    csv_path = tmp_path / "exp_a_synthetic.csv"
    pd.DataFrame({"SOC": SOC, "V_cell": V_cell}).to_csv(csv_path, index=False)
    return csv_path


class TestDryRun:
    def test_dry_run_succeeds(self):
        result = _run_script(
            "--material-spec", str(PANASONIC_SPEC),
            "--dry-run",
        )
        assert result.returncode == 0, (
            f"dry-run failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout
        assert "LR=" in result.stdout


class TestPreflightOnly:
    def test_preflight_passes(self):
        result = _run_script(
            "--material-spec", str(PANASONIC_SPEC),
            "--preflight-only",
        )
        assert result.returncode == 0
        assert "preflight 通过" in result.stdout

    def test_preflight_missing_dX(self, tmp_path):
        dst = _copy_spec_to_tmp(tmp_path)
        with open(dst) as f:
            spec = json.load(f)
        spec["dX_PE_alawa"]["value"] = None
        spec["dX_PE_alawa"]["status"] = "pending_fit"
        # Must nullify fit fields for pending_fit status
        spec["dX_PE_alawa"]["fit_step"] = None
        spec["dX_PE_alawa"]["fit_source"] = None
        spec["dX_PE_alawa"]["fit_script_version"] = None
        spec["dX_PE_alawa"]["fit_r_squared"] = None
        with open(dst, "w") as f:
            json.dump(spec, f)

        result = _run_script(
            "--material-spec", str(dst),
            "--preflight-only",
        )
        assert result.returncode == 80
        assert "FIT1-E001" in result.stderr


class TestPreflightCsvMissing:
    def test_nonexistent_csv(self):
        result = _run_script(
            "--material-spec", str(PANASONIC_SPEC),
            "--exp-a-csv", "/tmp/nonexistent_csv_12345.csv",
        )
        # Should fail with error about missing CSV
        assert result.returncode != 0


class TestRealFitPanasonic:
    def test_real_fit(self, tmp_path):
        """End-to-end: generate noiseless synthetic EXP-A CSV,
        run FIT-1, verify spec is updated correctly."""
        spec_path = _copy_spec_to_tmp(tmp_path)
        csv_path = _generate_synthetic_csv(tmp_path, spec_path)

        result = _run_script(
            "--material-spec", str(spec_path),
            "--exp-a-csv", str(csv_path),
        )
        assert result.returncode == 0, (
            f"fit failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify spec was updated
        with open(spec_path) as f:
            updated = json.load(f)

        # LR should be close to true value 1.04
        assert abs(updated["LR"]["value"] - 1.04) / 1.04 < 0.005, (
            f"LR={updated['LR']['value']} too far from 1.04"
        )
        assert updated["LR"]["status"] == "fitted"
        assert updated["LR"]["fit_step"] == "FIT-1"
        assert updated["LR"]["fit_r_squared"] is not None
        assert updated["LR"]["fit_r_squared"] > 0.99

        # OFS: relaxed tolerance (weakly identifiable)
        assert abs(updated["OFS"]["value"] - 2.0) / 2.0 < 0.25, (
            f"OFS={updated['OFS']['value']} too far from 2.0"
        )
        assert updated["OFS"]["status"] == "fitted"
        assert updated["OFS"]["fit_step"] == "FIT-1"

        # Top-level last_modified_at should be updated
        assert updated["last_modified_at"] != "2026-04-24T00:00:00Z"

        # Output should mention results
        assert "FIT-1" in result.stdout
        assert "Artifacts:" in result.stdout
