"""
model_versions
==============
Mechanism model version registry for the cell type abstraction layer.

Each mechanism model version (e.g. mmeka2025) is implemented as a submodule
that provides two functions:

- ``assemble_aging_model(params_spec, material_spec) -> AgingModel``
- ``build_resistance_closures(resistance_lut, material_spec, params_spec)
     -> (Rs_fn, R1_fn, R2_fn)``

The registry maps version strings to these entry points.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from . import mmeka2025

# Each entry: {"assemble": callable, "resistance": callable}
MODEL_VERSION_REGISTRY: Dict[str, Dict[str, Callable]] = {
    "mmeka2025": {
        "assemble": mmeka2025.assemble_aging_model,
        "resistance": mmeka2025.build_resistance_closures,
    },
}


def get_model_version(version_str: str) -> Dict[str, Callable]:
    """Return the registered entry points for the given model version.

    Raises ValueError if the version is not registered.
    """
    if version_str not in MODEL_VERSION_REGISTRY:
        registered = ", ".join(sorted(MODEL_VERSION_REGISTRY.keys()))
        raise ValueError(
            f"Unknown model version '{version_str}'. "
            f"Registered versions: [{registered}]. "
            f"To add a new version, create a submodule in "
            f"libquiv_aging/model_versions/ and register it in __init__.py."
        )
    return MODEL_VERSION_REGISTRY[version_str]
