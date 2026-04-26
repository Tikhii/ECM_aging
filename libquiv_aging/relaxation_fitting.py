"""
relaxation_fitting.py
=====================
RC 弛豫 (relaxation) 数据的两指数模型拟合, 服务 FIT-2 (C1, C2 提取)。

升级路径
--------
当前实现仅 'two_exponential' 模型 (论文 Mmeka 2025 等价 RC 拓扑)。未来若引入
分数阶 RC / Mittag-Leffler 弛豫等替代模型, 在 RELAXATION_MODELS 字典中追加,
并通过 fit_two_exponential_relaxation 同模式的接口供 scripts 调用。
docs/UPGRADE_LITERATURE/fractional_order_RC.md 描述了升级动机与候选文献。
"""

from __future__ import annotations

import warnings

import numpy as np
from scipy.optimize import curve_fit


def two_exponential_model(
    t: np.ndarray,
    V_inf: float,
    A1: float,
    tau1: float,
    A2: float,
    tau2: float,
) -> np.ndarray:
    """V(t) = V_inf + A1 * exp(-t / tau1) + A2 * exp(-t / tau2)."""
    return V_inf + A1 * np.exp(-t / tau1) + A2 * np.exp(-t / tau2)


def _initial_guess(
    t: np.ndarray,
    v: np.ndarray,
) -> tuple[float, float, float, float, float]:
    """根据数据范围给出 [V_inf, A1, tau1, A2, tau2] 的合理初值。

    策略:
        V_inf  ≈ 末段电压
        总幅值 dV = v[0] - V_inf, 拆为 A1=0.6*dV, A2=0.4*dV
        tau1 ≈ 0.05 * 总窗口长度 (快段)
        tau2 ≈ 0.5  * 总窗口长度 (慢段, 强制 tau2 > tau1)
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    if t.size < 5:
        raise ValueError(
            f"Relaxation 数据点过少: {t.size} < 5, 无法做两指数拟合。"
        )

    V_inf0 = float(v[-1])
    dV = float(v[0] - V_inf0)
    if abs(dV) < 1e-9:
        dV = float(np.sign(v[0] - v[-1])) * max(np.std(v), 1e-3) or 1e-3

    window = float(t[-1] - t[0])
    if window <= 0.0:
        raise ValueError(
            f"Relaxation 时间窗口非正: t[0]={t[0]}, t[-1]={t[-1]}"
        )

    tau1_0 = max(window * 0.05, 1e-3)
    tau2_0 = max(window * 0.5, tau1_0 * 5.0)
    A1_0 = 0.6 * dV
    A2_0 = 0.4 * dV
    return (V_inf0, A1_0, tau1_0, A2_0, tau2_0)


def fit_two_exponential_relaxation(
    t: np.ndarray,
    v: np.ndarray,
    p0: tuple[float, float, float, float, float] | None = None,
    bounds: tuple[tuple, tuple] | None = None,
    maxfev: int = 5000,
) -> dict:
    """两指数弛豫拟合, V(t) = V_inf + A1*exp(-t/tau1) + A2*exp(-t/tau2)。

    Parameters
    ----------
    t : np.ndarray
        时间轴 [s], 必须从 0 开始的相对时间 (脉冲终止时刻 = 0)。
    v : np.ndarray
        电压观测 [V]。
    p0 : tuple, optional
        初值 (V_inf, A1, tau1, A2, tau2)。None 则自动推断。
    bounds : (lower, upper) tuple, optional
        参数下/上界。None 则用宽松默认: V_inf ∈ ±10V, A_i ∈ ±10V,
        tau_i ∈ [1e-3, 1e5] s。
    maxfev : int
        curve_fit 最大函数调用数。

    Returns
    -------
    dict
        {
          'V_inf', 'A1', 'tau1', 'A2', 'tau2',                # 排序后 tau1 < tau2
          'sigma_V_inf', 'sigma_A1', 'sigma_tau1',
          'sigma_A2', 'sigma_tau2',
          'rmse', 'r_squared',
          'converged': bool,
          'pcov': np.ndarray (5,5),
        }

    Raises
    ------
    RuntimeError
        若 curve_fit 抛出 RuntimeError 或返回非有限协方差。调用方按
        FIT2-E002 处理。
    ValueError
        若数据点过少或时间窗口非正。
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)

    if p0 is None:
        p0 = _initial_guess(t, v)

    if bounds is None:
        bounds = (
            (-10.0, -10.0, 1e-3, -10.0, 1e-3),
            (10.0, 10.0, 1e5, 10.0, 1e5),
        )

    try:
        popt, pcov = curve_fit(
            two_exponential_model,
            t,
            v,
            p0=p0,
            bounds=bounds,
            maxfev=maxfev,
        )
    except RuntimeError as e:
        raise RuntimeError(
            f"two_exponential curve_fit 未收敛: {e}"
        ) from e

    if not np.all(np.isfinite(pcov)):
        raise RuntimeError(
            "two_exponential 协方差矩阵含 inf/nan, 拟合不可信。"
        )

    V_inf, A1, tau1, A2, tau2 = popt

    if tau2 < tau1:
        tau1, tau2 = tau2, tau1
        A1, A2 = A2, A1
        idx = [0, 3, 4, 1, 2]
        pcov = pcov[np.ix_(idx, idx)]

    diag = np.diag(pcov)
    if np.any(diag < 0):
        warnings.warn(
            "协方差对角线含负值, 不确定度部分置 nan。"
        )
    sigma = np.where(diag >= 0, np.sqrt(np.abs(diag)), float("nan"))

    v_pred = two_exponential_model(t, V_inf, A1, tau1, A2, tau2)
    residuals = v - v_pred
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((v - np.mean(v)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else (1.0 if ss_res == 0 else 0.0)

    return {
        "V_inf": float(V_inf),
        "A1": float(A1),
        "tau1": float(tau1),
        "A2": float(A2),
        "tau2": float(tau2),
        "sigma_V_inf": float(sigma[0]),
        "sigma_A1": float(sigma[1]),
        "sigma_tau1": float(sigma[2]),
        "sigma_A2": float(sigma[3]),
        "sigma_tau2": float(sigma[4]),
        "rmse": rmse,
        "r_squared": float(r_squared),
        "converged": True,
        "pcov": pcov,
    }


RELAXATION_MODELS = {
    "two_exponential": fit_two_exponential_relaxation,
}


def get_relaxation_model(name: str):
    """根据名称返回弛豫拟合函数。当前仅 'two_exponential'。"""
    if name not in RELAXATION_MODELS:
        raise ValueError(
            f"未知 relaxation_model: {name!r}。可选: {sorted(RELAXATION_MODELS)}"
        )
    return RELAXATION_MODELS[name]
