from __future__ import annotations

import math


def hub_geometry_factor(nominal_diameter_mm: float, hub_outer_diameter_mm: float) -> float:
    if hub_outer_diameter_mm <= nominal_diameter_mm:
        raise ValueError("hub_outer_diameter_mm must be greater than nominal_diameter_mm")
    inner_sq = nominal_diameter_mm ** 2
    outer_sq = hub_outer_diameter_mm ** 2
    return (outer_sq + inner_sq) / (outer_sq - inner_sq)


def contact_pressure_mpa(
    interference_um: float,
    nominal_diameter_mm: float,
    hub_outer_diameter_mm: float,
    shaft_elastic_modulus_gpa: float,
    hub_elastic_modulus_gpa: float,
    shaft_poisson_ratio: float,
    hub_poisson_ratio: float,
) -> float:
    if interference_um <= 0:
        return 0.0

    interference_m = interference_um / 1_000_000.0
    nominal_diameter_m = nominal_diameter_mm / 1000.0

    shaft_compliance = (1.0 - shaft_poisson_ratio**2) / (shaft_elastic_modulus_gpa * 1_000_000_000.0)
    hub_compliance = ((1.0 - hub_poisson_ratio**2) / (hub_elastic_modulus_gpa * 1_000_000_000.0)) * hub_geometry_factor(
        nominal_diameter_mm, hub_outer_diameter_mm
    )
    total_compliance = nominal_diameter_m * (shaft_compliance + hub_compliance)
    pressure_pa = interference_m / total_compliance
    return round(pressure_pa / 1_000_000.0, 3)


def hub_hoop_stress_mpa(contact_pressure_mpa_value: float, nominal_diameter_mm: float, hub_outer_diameter_mm: float) -> float:
    return round(contact_pressure_mpa_value * hub_geometry_factor(nominal_diameter_mm, hub_outer_diameter_mm), 3)


def hub_von_mises_mpa(contact_pressure_mpa_value: float, nominal_diameter_mm: float, hub_outer_diameter_mm: float) -> float:
    hoop = hub_hoop_stress_mpa(contact_pressure_mpa_value, nominal_diameter_mm, hub_outer_diameter_mm)
    radial = -contact_pressure_mpa_value
    equivalent = math.sqrt(max((hoop**2) - (hoop * radial) + (radial**2), 0.0))
    return round(equivalent, 3)


def safety_factor(yield_strength_mpa: float, equivalent_stress_mpa: float) -> float | None:
    if equivalent_stress_mpa <= 0:
        return None
    return round(yield_strength_mpa / equivalent_stress_mpa, 3)
