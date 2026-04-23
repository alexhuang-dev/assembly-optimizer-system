from __future__ import annotations


def roughness_loss_um(shaft_roughness_um: float, bore_roughness_um: float) -> float:
    return round(5.0 * ((shaft_roughness_um + bore_roughness_um) / 2.0), 3)


def effective_interference_um(raw_interference_um: float, shaft_roughness_um: float, bore_roughness_um: float) -> float:
    return round(max(raw_interference_um - roughness_loss_um(shaft_roughness_um, bore_roughness_um), 0.0), 3)


def required_heating_delta_c(
    effective_interference_um: float,
    desired_installation_clearance_um: float,
    hub_thermal_expansion: float,
    nominal_diameter_mm: float,
) -> float:
    growth_per_degree_um = hub_thermal_expansion * nominal_diameter_mm * 1000.0
    if growth_per_degree_um <= 0:
        return 0.0
    total_clearance_um = max(effective_interference_um, 0.0) + max(desired_installation_clearance_um, 0.0)
    return round(total_clearance_um / growth_per_degree_um, 3)


def service_interference_um(
    assembly_interference_um: float,
    shaft_thermal_expansion: float,
    hub_thermal_expansion: float,
    nominal_diameter_mm: float,
    service_temperature_delta_c: float,
) -> float:
    drift_um = (shaft_thermal_expansion - hub_thermal_expansion) * nominal_diameter_mm * 1000.0 * service_temperature_delta_c
    return round(max(assembly_interference_um + drift_um, 0.0), 3)

