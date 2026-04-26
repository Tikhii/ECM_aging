"""Tests for scripts/fit_rc_transient.py — FIT-2 RC transient fitting."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fit_rc_transient.py"
PANASONIC_MATERIAL = ROOT / "material_specs" / "panasonic_ncr18650b.material.json"
PANASONIC_PARAMS = ROOT / "param_specs" / "panasonic_ncr18650b__mmeka2025.params.json"


def _run_script(*args, timeout=120) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT)] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=str(ROOT))


def _copy_specs_to_tmp(tmp_path: Path) -> tuple[Path, Path]:
    """Copy material+params specs and schemas dir into tmp_path."""
    material_dst = tmp_path / "test.material.json"
    params_dst = tmp_path / "test.params.json"
    shutil.copy2(PANASONIC_MATERIAL, material_dst)
    shutil.copy2(PANASONIC_PARAMS, params_dst)

    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    shutil.copy2(
        ROOT / "schemas" / "material.schema.v1.json",
        schema_dir / "material.schema.v1.json",
    )
    shutil.copy2(
        ROOT / "schemas" / "params_mmeka2025.schema.v1.json",
        schema_dir / "params_mmeka2025.schema.v1.json",
    )
    return material_dst, params_dst


def _generate_synthetic_csv(
    tmp_path: Path,
    material_path: Path,
    params_path: Path,
    soc: float = 0.5,
    I_pre: float = 1.0,
    C1_true: float = 950.0,
    C2_true: float = 3500.0,
    noise_V: float = 1e-4,
) -> Path:
    """Synthesize a relaxation CSV consistent with the LUTs and material spec."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from fit_rc_transient import _stoichiometry_from_soc

    from libquiv_aging.lookup_tables import ResistanceLUTs

    with open(material_path) as f:
        material = json.load(f)
    with open(params_path) as f:
        params = json.load(f)

    luts = ResistanceLUTs.from_mat_file(str(ROOT / params["resistance_mat"]))
    X_PE, X_NE = _stoichiometry_from_soc(
        soc,
        material["X0_PE"]["value"], material["X0_NE"]["value"],
        material["dX_PE_alawa"]["value"], material["dX_NE_alawa"]["value"],
        material["LR"]["value"], material["OFS"]["value"],
    )
    C_nominal = material["C_nominal_Ah"]["value"]
    C_rate = I_pre / C_nominal
    R_NE = float(luts.interp_RNE(C_rate, X_NE))
    R_PE = float(luts.interp_RPE(C_rate, X_PE))

    tau1_true = R_NE * C1_true
    tau2_true = R_PE * C2_true
    if tau2_true < tau1_true:
        tau1_true, tau2_true = tau2_true, tau1_true
        A1, A2 = -I_pre * R_PE, -I_pre * R_NE
    else:
        A1, A2 = -I_pre * R_NE, -I_pre * R_PE

    V_inf = 3.6
    t_step = 100.0
    t_rel = np.linspace(0, max(5 * tau2_true, 100.0), 400)
    t_abs = t_rel + t_step
    rng = np.random.default_rng(42)
    v = V_inf + A1 * np.exp(-t_rel / tau1_true) + A2 * np.exp(-t_rel / tau2_true)
    v_noisy = v + rng.normal(0, noise_V, size=len(t_rel))

    csv_path = tmp_path / "exp_b4_synthetic.csv"
    pd.DataFrame({
        "time_s": t_abs,
        "voltage_V": v_noisy,
        "current_pre_step_A": np.full_like(t_abs, I_pre),
        "soc_at_step": np.full_like(t_abs, soc),
        "t_step_s": np.full_like(t_abs, t_step),
    }).to_csv(csv_path, index=False)
    return csv_path


class TestDryRun:
    def test_dry_run_succeeds(self):
        result = _run_script(
            "--material-spec", str(PANASONIC_MATERIAL),
            "--params-spec", str(PANASONIC_PARAMS),
            "--dry-run",
        )
        assert result.returncode == 0, (
            f"dry-run failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout
        assert "C1=" in result.stdout


class TestPreflightOnly:
    def test_preflight_passes(self):
        result = _run_script(
            "--material-spec", str(PANASONIC_MATERIAL),
            "--params-spec", str(PANASONIC_PARAMS),
            "--preflight-only",
        )
        assert result.returncode == 0
        assert "preflight 通过" in result.stdout


class TestPreflightCsvErrors:
    def test_missing_required_column(self, tmp_path):
        material_dst, params_dst = _copy_specs_to_tmp(tmp_path)
        bad_csv = tmp_path / "bad.csv"
        pd.DataFrame({"time_s": [1.0, 2.0], "voltage_V": [3.6, 3.6]}).to_csv(
            bad_csv, index=False
        )
        # min_rows=10 will also fire; just check exit code is 20 or 90
        result = _run_script(
            "--material-spec", str(material_dst),
            "--params-spec", str(params_dst),
            "--exp-b4-csv", str(bad_csv),
        )
        assert result.returncode != 0


class TestRealFit:
    def test_real_fit_writes_back(self, tmp_path):
        """End-to-end: synthesize CSV, run FIT-2, verify spec is updated."""
        material_dst, params_dst = _copy_specs_to_tmp(tmp_path)
        csv_path = _generate_synthetic_csv(tmp_path, material_dst, params_dst)

        result = _run_script(
            "--material-spec", str(material_dst),
            "--params-spec", str(params_dst),
            "--exp-b4-csv", str(csv_path),
        )
        assert result.returncode in (0, 93), (
            f"fit failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        with open(params_dst) as f:
            updated = json.load(f)

        # C1 close to 950, C2 close to 3500 (within 5% for noisy synthetic)
        C1_fit = updated["C1"]["value"]
        C2_fit = updated["C2"]["value"]
        assert abs(C1_fit - 950.0) / 950.0 < 0.05, f"C1={C1_fit} too far from 950"
        assert abs(C2_fit - 3500.0) / 3500.0 < 0.05, f"C2={C2_fit} too far from 3500"

        assert updated["C1"]["status"] == "fitted"
        assert updated["C1"]["fit_step"] == "FIT-2"
        assert updated["C1"]["fit_r_squared"] is not None
        assert updated["C1"]["fit_r_squared"] > 0.99
        assert "relaxation_metadata" in updated["C1"]
        assert updated["C1"]["relaxation_metadata"]["model"] == "two_exponential"

        assert updated["C2"]["status"] == "fitted"
        assert updated["C2"]["fit_step"] == "FIT-2"
        assert "relaxation_metadata" in updated["C2"]

        assert updated["last_modified_at"] != "2026-04-24T00:00:00Z"

        assert "FIT-2" in result.stdout
        assert "Artifacts:" in result.stdout


class TestRequirePending:
    def test_require_pending_refuses_already_fitted(self, tmp_path):
        material_dst, params_dst = _copy_specs_to_tmp(tmp_path)

        with open(params_dst) as f:
            spec = json.load(f)
        spec["C1"]["status"] = "fitted"
        spec["C1"]["fit_step"] = "FIT-2"
        spec["C1"]["fit_source"] = "previous_run"
        spec["C1"]["fit_script_version"] = "abc123"
        spec["C1"]["fit_r_squared"] = 0.999
        with open(params_dst, "w") as f:
            json.dump(spec, f)

        csv_path = _generate_synthetic_csv(tmp_path, material_dst, params_dst)
        result = _run_script(
            "--material-spec", str(material_dst),
            "--params-spec", str(params_dst),
            "--exp-b4-csv", str(csv_path),
            "--require-pending",
        )
        assert result.returncode == 1
        assert "require-pending" in result.stderr or "fitted" in result.stderr


class TestRelaxationModelOption:
    def test_default_is_two_exponential(self, tmp_path):
        material_dst, params_dst = _copy_specs_to_tmp(tmp_path)
        csv_path = _generate_synthetic_csv(tmp_path, material_dst, params_dst)
        result = _run_script(
            "--material-spec", str(material_dst),
            "--params-spec", str(params_dst),
            "--exp-b4-csv", str(csv_path),
            "--relaxation-model", "two_exponential",
        )
        assert result.returncode in (0, 93)

    def test_unknown_model_rejected(self):
        result = _run_script(
            "--material-spec", str(PANASONIC_MATERIAL),
            "--params-spec", str(PANASONIC_PARAMS),
            "--relaxation-model", "fractional_order",
            "--dry-run",
        )
        assert result.returncode != 0
