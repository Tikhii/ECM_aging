"""
test_panasonic_equivalence.py
=============================
Verify that the refactored panasonic_ncr18650b.py (compatibility shim)
produces numerically identical simulation results to the pre-refactor
version.

The golden snapshot is generated on first run and stored as a JSON file.
Subsequent runs compare against the snapshot with tight floating-point
tolerance (1e-9) to catch any numerical drift introduced by the shim.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from libquiv_aging import create_panasonic_ncr18650b

SNAPSHOT_PATH = Path(__file__).parent / "golden_panasonic_snapshot.json"


def _run_simulation():
    """Run the standard smoke-test sequence and return key outputs."""
    cell = create_panasonic_ncr18650b()
    cell.init(0.5)

    # Record initial state
    init_V = cell.V
    init_SOC = cell.SOC
    init_C = cell.C

    # CC discharge at C/5 for 600 seconds
    C_rate = cell.C / 3600.0 / 5.0  # C/5 in A
    cell.CC(I=C_rate, duration_s=600, break_criterion="V < 2.5")

    return {
        "init_V": init_V,
        "init_SOC": init_SOC,
        "init_C": init_C,
        "final_V": cell.V,
        "final_SOC": cell.SOC,
        "final_Q": cell.Q,
        "final_C": cell.C,
        "aging_C0_PE": cell.aging_C0_PE,
        "aging_C0_NE": cell.aging_C0_NE,
        "aging_Q_SEI_NE": cell.aging_Q_SEI_NE,
        "allV_last10": cell.allV[-10:],
        "allI_last10": cell.allI[-10:],
    }


def _serialize(data: dict) -> dict:
    """Convert numpy arrays/floats to JSON-serializable types."""
    out = {}
    for k, v in data.items():
        if isinstance(v, (list, np.ndarray)):
            out[k] = [float(x) for x in v]
        elif isinstance(v, (float, np.floating)):
            out[k] = float(v)
        else:
            out[k] = v
    return out


class TestPanasonicEquivalence:
    def test_simulation_matches_golden_snapshot(self):
        """Simulation output matches the golden snapshot within 1e-9."""
        results = _run_simulation()

        if not SNAPSHOT_PATH.exists():
            # First run: generate snapshot
            with open(SNAPSHOT_PATH, "w") as f:
                json.dump(_serialize(results), f, indent=2)
            # First run always passes (we just created the reference)
            return

        # Compare against snapshot
        with open(SNAPSHOT_PATH) as f:
            golden = json.load(f)

        for key in golden:
            actual = results[key]
            expected = golden[key]
            if isinstance(expected, list):
                np.testing.assert_allclose(
                    actual, expected, atol=1e-9, rtol=0,
                    err_msg=f"Mismatch in {key}",
                )
            else:
                np.testing.assert_allclose(
                    float(actual), float(expected), atol=1e-9, rtol=0,
                    err_msg=f"Mismatch in {key}",
                )

    def test_init_and_basic_properties(self):
        """Basic sanity: cell initializes and has expected rough properties."""
        cell = create_panasonic_ncr18650b()
        cell.init(0.5)

        assert 3.0 < cell.C / 3600.0 < 4.0, f"Capacity {cell.C/3600:.3f} Ah out of range"
        assert 3.5 < cell.V < 3.8, f"Voltage {cell.V:.4f} V out of range"
        assert 0.45 < cell.SOC < 0.55, f"SOC {cell.SOC:.4f} out of range"
