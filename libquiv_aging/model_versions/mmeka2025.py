"""
mmeka2025.py
============
Assembly logic for the mmeka2025 degradation mechanism model.

This module implements the mechanism described in:
    Patricia O. Mmeka, Matthieu Dubarry, Wolfgang G. Bessler,
    "Physics-Informed Aging-Sensitive Equivalent Circuit Model for Predicting
    the Knee in Lithium-Ion Batteries",
    J. Electrochem. Soc. 172 080538 (2025).

Scope and assumptions:
- SEI growth (calendar + cyclic) with Arrhenius temperature dependence
- Irreversible lithium plating (Butler-Volmer, static V_LP_eq)
- LAM for both PE and NE (calendar + cyclic, volume-change driven)
- Resistance degradation via f_R_NE (SEI + LAM) and f_R_PE (LAM only)
- R_s assumed non-degrading (f_R_s = 1)
- No PE-side LLI (I_LLI_PE = 0)

The ``assemble_aging_model`` function constructs an ``AgingModel`` from
unpacked spec dictionaries. The ``build_resistance_closures`` function
constructs the three resistance closure functions (Rs_fn, R1_fn, R2_fn)
matching the original panasonic_ncr18650b.py behavior.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

import numpy as np

from ..aging_kinetics import (
    AgingModel,
    LAMParameters,
    MolarVolumeModel,
    PlatingParameters,
    ResistanceAgingParameters,
    SEIParameters,
)
from ..lookup_tables import ResistanceLUTs


def assemble_aging_model(
    params_spec: dict,
    material_spec: dict,
    mvol_ne: MolarVolumeModel,
    mvol_pe: MolarVolumeModel,
    Q0_SEI_NE: float,
    Q0_LLI_NE: float,
) -> AgingModel:
    """Construct an AgingModel from unpacked spec dictionaries.

    Parameters
    ----------
    params_spec : dict
        The full params spec dictionary (already validated).
    material_spec : dict
        The full material spec dictionary (already validated).
    mvol_ne, mvol_pe : MolarVolumeModel
        Pre-constructed molar volume models.
    Q0_SEI_NE : float
        Derived initial SEI charge [A*s].
    Q0_LLI_NE : float
        Derived initial LLI on NE [A*s] (equals Q0_SEI_NE).
    """

    def _v(field_name: str) -> float:
        return params_spec[field_name]["value"]

    # X_LAM values are stored as scalars, returned as constant lambdas
    x_lam_pe_val = _v("X_LAM_PE")
    x_lam_ne_val = _v("X_LAM_NE")

    return AgingModel(
        sei=SEIParameters(
            k_cal=_v("k_SEI_cal"),
            k_cyc=_v("k_SEI_cyc"),
            Ea=_v("E_a_SEI"),
            alpha_f=_v("alpha_f_SEI"),
        ),
        plating=PlatingParameters(
            k_LP=_v("k_LP"),
            alpha_LP=_v("alpha_LP"),
            V_LP_eq=_v("V_LP_eq"),
        ),
        lam_pe=LAMParameters(
            k_cal=_v("k_LAM_PE_cal"),
            k_cyc=_v("k_LAM_PE_cyc"),
            gamma=_v("gamma_PE"),
        ),
        lam_ne=LAMParameters(
            k_cal=_v("k_LAM_NE_cal"),
            k_cyc=_v("k_LAM_NE_cyc"),
            gamma=_v("gamma_NE"),
        ),
        resistance_aging=ResistanceAgingParameters(
            R_SEI=_v("R_SEI"),
            R_NE_0=_v("R_NE_0"),
        ),
        mvol_ne=mvol_ne,
        mvol_pe=mvol_pe,
        Q0_LLI_PE=_v("Q0_LLI_PE"),
        Q0_LLI_NE=Q0_LLI_NE,
        Q0_LAM_PE=_v("Q0_LAM_PE"),
        Q0_LAM_NE=_v("Q0_LAM_NE"),
        Q0_SEI_NE=Q0_SEI_NE,
        Q0_PLA_NE=_v("Q0_PLA_NE"),
        X_LAM_PE=lambda X_pe, _v=x_lam_pe_val: _v,
        X_LAM_NE=lambda X_ne, _v=x_lam_ne_val: _v,
        acceleration_factor=1.0,
    )


def build_resistance_closures(
    r_luts: ResistanceLUTs,
    material_spec: dict,
    params_spec: dict,
) -> Tuple[
    Callable[[float, float, float, float], float],
    Callable[[float, float, float, float], float],
    Callable[[float, float, float, float], float],
]:
    """Construct resistance closure functions from the LUT and specs.

    Currently supports only resistance_mode="ncr18650b_default".
    Future modes can be dispatched here.

    Returns (Rs_fn, R1_fn, R2_fn), each with signature (T, X_ne, X_pe, I) -> float.
    """
    mode = params_spec["resistance_mode"]

    if mode == "ncr18650b_default":
        return _ncr18650b_default_closures(r_luts, material_spec)
    else:
        raise ValueError(
            f"Unknown resistance_mode '{mode}'. "
            f"Currently supported: ['ncr18650b_default']."
        )


def _ncr18650b_default_closures(
    r_luts: ResistanceLUTs,
    material_spec: dict,
) -> Tuple[
    Callable[[float, float, float, float], float],
    Callable[[float, float, float, float], float],
    Callable[[float, float, float, float], float],
]:
    """Build resistance closures matching the original panasonic_ncr18650b.py."""
    CN_Ah = material_spec["C_nominal_Ah"]["value"]
    CN_As = CN_Ah * 3600.0

    def Rs_fn(T, X_ne, X_pe, I):
        c_rate = np.clip(-I * 3600.0 / CN_As, -4.0, 4.0)
        return (1.0 / CN_Ah) * r_luts.interp_Rs(c_rate, 0.0)

    def R1_fn(T, X_ne, X_pe, I):
        c_rate = -I * 3600.0 / CN_As
        return (1.0 / CN_Ah) * r_luts.interp_RNE(c_rate, X_ne)

    def R2_fn(T, X_ne, X_pe, I):
        c_rate = -I * 3600.0 / CN_As
        return (1.0 / CN_Ah) * r_luts.interp_RPE(c_rate, X_pe)

    return Rs_fn, R1_fn, R2_fn
