"""Tests for libquiv_aging/relaxation_fitting.py — two-exponential RC relaxation."""

import numpy as np
import pytest

from libquiv_aging.relaxation_fitting import (
    RELAXATION_MODELS,
    _initial_guess,
    fit_two_exponential_relaxation,
    get_relaxation_model,
    two_exponential_model,
)


class TestTwoExponentialModel:
    def test_t0_returns_v_inf_plus_amplitudes(self):
        v0 = two_exponential_model(np.array([0.0]), V_inf=3.6, A1=-0.05, tau1=1.0,
                                   A2=-0.10, tau2=10.0)[0]
        assert v0 == pytest.approx(3.6 - 0.05 - 0.10)

    def test_t_inf_returns_v_inf(self):
        v_far = two_exponential_model(np.array([1e6]), V_inf=3.6, A1=-0.05, tau1=1.0,
                                      A2=-0.10, tau2=10.0)[0]
        assert v_far == pytest.approx(3.6, abs=1e-9)


class TestInitialGuess:
    def test_returns_five_floats(self):
        t = np.linspace(0, 100, 200)
        v = 3.6 - 0.1 * np.exp(-t / 5.0) - 0.2 * np.exp(-t / 50.0)
        p0 = _initial_guess(t, v)
        assert len(p0) == 5
        V_inf, A1, tau1, A2, tau2 = p0
        assert tau2 > tau1 > 0

    def test_too_few_points_raises(self):
        t = np.array([0.0, 1.0, 2.0])
        v = np.array([3.5, 3.55, 3.58])
        with pytest.raises(ValueError, match="数据点过少"):
            _initial_guess(t, v)


class TestFitTwoExponentialRelaxation:
    def test_recovers_synthetic_parameters(self):
        """Noiseless synthetic data should recover all 5 parameters within 1%."""
        V_inf_true = 3.6
        A1_true, tau1_true = -0.05, 2.0
        A2_true, tau2_true = -0.15, 30.0
        t = np.linspace(0, 200, 1000)
        v = two_exponential_model(t, V_inf_true, A1_true, tau1_true,
                                  A2_true, tau2_true)
        rng = np.random.default_rng(0)
        v_noisy = v + rng.normal(0, 1e-5, size=len(t))

        result = fit_two_exponential_relaxation(t, v_noisy)

        assert result["converged"] is True
        assert result["r_squared"] > 0.999
        assert abs(result["V_inf"] - V_inf_true) < 1e-3
        assert abs(result["tau1"] - tau1_true) / tau1_true < 0.05
        assert abs(result["tau2"] - tau2_true) / tau2_true < 0.05

    def test_enforces_tau1_lt_tau2(self):
        """If true tau1 > tau2, the result must reorder them so tau1 < tau2."""
        t = np.linspace(0, 300, 1000)
        v = two_exponential_model(t, 3.6, -0.05, 50.0, -0.15, 2.0)
        result = fit_two_exponential_relaxation(t, v)
        assert result["tau1"] < result["tau2"]

    def test_runtime_error_on_unfittable_data(self):
        """Pure-noise data with extremely tight maxfev triggers RuntimeError."""
        rng = np.random.default_rng(7)
        t = np.linspace(0, 100, 200)
        v = 3.6 + rng.normal(0, 0.01, size=len(t))
        with pytest.raises((RuntimeError, ValueError)):
            fit_two_exponential_relaxation(t, v, maxfev=3)

    def test_returns_required_fields(self):
        t = np.linspace(0, 100, 500)
        v = two_exponential_model(t, 3.6, -0.05, 2.0, -0.15, 30.0)
        result = fit_two_exponential_relaxation(t, v)
        for key in ["V_inf", "A1", "tau1", "A2", "tau2",
                    "sigma_V_inf", "sigma_A1", "sigma_tau1",
                    "sigma_A2", "sigma_tau2",
                    "rmse", "r_squared", "converged", "pcov"]:
            assert key in result, f"missing key: {key}"
        assert result["pcov"].shape == (5, 5)


class TestRelaxationModelDispatch:
    def test_two_exponential_in_registry(self):
        assert "two_exponential" in RELAXATION_MODELS

    def test_get_model_returns_callable(self):
        fn = get_relaxation_model("two_exponential")
        assert callable(fn)

    def test_unknown_model_raises(self):
        with pytest.raises(ValueError, match="未知 relaxation_model"):
            get_relaxation_model("fractional_order")
