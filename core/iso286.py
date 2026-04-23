from __future__ import annotations

from .config import FIT_LIBRARY


def get_fit_definition(fit_code: str) -> dict:
    if fit_code not in FIT_LIBRARY:
        supported = ", ".join(sorted(FIT_LIBRARY))
        raise ValueError(f"Unsupported fit code '{fit_code}'. Supported fits: {supported}")
    definition = FIT_LIBRARY[fit_code]
    return {
        "fit_code": fit_code,
        "family": definition["family"],
        "interference_um": definition["interference_um"],
    }


def get_nominal_interference_um(fit_code: str) -> float:
    fit = get_fit_definition(fit_code)
    min_um, max_um = fit["interference_um"]
    return round((min_um + max_um) / 2.0, 3)


def list_supported_fits() -> list[str]:
    return sorted(FIT_LIBRARY)

