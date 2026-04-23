from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from .config import SCHEMA_VERSION
from .iso286 import get_fit_definition, get_nominal_interference_um
from .stress import contact_pressure_mpa, hub_von_mises_mpa, safety_factor
from .thermal import effective_interference_um, required_heating_delta_c, roughness_loss_um, service_interference_um


def _capacity_margin(capacity: float, demand: float) -> float | None:
    if demand <= 0:
        return None
    return round(capacity / demand, 3)


def _overall_status(safety_factor_value: float | None, torque_margin: float | None, axial_margin: float | None) -> str:
    constrained = [value for value in (safety_factor_value, torque_margin, axial_margin) if value is not None]
    if not constrained:
        return "normal"
    minimum = min(constrained)
    if minimum < 1.0:
        return "critical"
    if minimum < 1.5:
        return "warning"
    return "normal"


def _format_scenario_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):g}"
    return str(value)


def build_run_id(payload: dict) -> str:
    fingerprint = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{timestamp}_{fingerprint}"


def build_scenario_key(payload: dict) -> str:
    geometry = payload["geometry"]
    part_id = geometry.get("part_id")
    if part_id:
        return f"part:{part_id}|fit:{geometry['fit_code']}"

    fields = (
        ("fit", geometry["fit_code"]),
        ("d", geometry["nominal_diameter_mm"]),
        ("D", geometry["hub_outer_diameter_mm"]),
        ("L", geometry["contact_length_mm"]),
    )
    return "|".join(f"{name}:{_format_scenario_value(value)}" for name, value in fields)


def calculate_press_fit(payload: dict) -> dict:
    geometry = payload["geometry"]
    materials = payload["materials"]
    operating = payload["operating"]

    fit = get_fit_definition(geometry["fit_code"])
    raw_nominal_um = get_nominal_interference_um(geometry["fit_code"])
    raw_min_um, raw_max_um = fit["interference_um"]

    nominal_diameter_mm = geometry["nominal_diameter_mm"]
    hub_outer_diameter_mm = geometry["hub_outer_diameter_mm"]
    contact_length_mm = geometry["contact_length_mm"]

    roughness_loss_value_um = roughness_loss_um(geometry["shaft_roughness_um"], geometry["bore_roughness_um"])
    assembly_interference_um = effective_interference_um(
        raw_nominal_um, geometry["shaft_roughness_um"], geometry["bore_roughness_um"]
    )
    service_delta_c = operating["working_temperature_c"] - operating["assembly_temperature_c"]
    service_interference_value_um = service_interference_um(
        assembly_interference_um,
        materials["shaft_thermal_expansion"],
        materials["hub_thermal_expansion"],
        nominal_diameter_mm,
        service_delta_c,
    )

    pressure_assembly_mpa = contact_pressure_mpa(
        assembly_interference_um,
        nominal_diameter_mm,
        hub_outer_diameter_mm,
        materials["shaft_elastic_modulus_gpa"],
        materials["hub_elastic_modulus_gpa"],
        materials["shaft_poisson_ratio"],
        materials["hub_poisson_ratio"],
    )
    pressure_service_mpa = contact_pressure_mpa(
        service_interference_value_um,
        nominal_diameter_mm,
        hub_outer_diameter_mm,
        materials["shaft_elastic_modulus_gpa"],
        materials["hub_elastic_modulus_gpa"],
        materials["shaft_poisson_ratio"],
        materials["hub_poisson_ratio"],
    )

    nominal_diameter_m = nominal_diameter_mm / 1000.0
    contact_length_m = contact_length_mm / 1000.0

    axial_capacity_n = (
        operating["service_friction_coefficient"] * pressure_service_mpa * 1_000_000.0 * math.pi * nominal_diameter_m * contact_length_m
    )
    torque_capacity_nm = (
        operating["service_friction_coefficient"]
        * pressure_service_mpa
        * 1_000_000.0
        * math.pi
        * nominal_diameter_m**2
        * contact_length_m
        / 2.0
    )
    press_force_n = (
        operating["press_friction_coefficient"] * pressure_assembly_mpa * 1_000_000.0 * math.pi * nominal_diameter_m * contact_length_m
    )

    equivalent_stress_mpa = hub_von_mises_mpa(pressure_assembly_mpa, nominal_diameter_mm, hub_outer_diameter_mm)
    safety_factor_value = safety_factor(materials["hub_yield_strength_mpa"], equivalent_stress_mpa)

    torque_margin = _capacity_margin(torque_capacity_nm, operating["transmitted_torque_nm"])
    axial_margin = _capacity_margin(axial_capacity_n, operating["axial_force_n"])
    equipment_force_margin = _capacity_margin(operating["equipment_force_limit_kn"] * 1000.0, press_force_n)

    heating_delta_c = required_heating_delta_c(
        assembly_interference_um,
        operating["desired_installation_clearance_um"],
        materials["hub_thermal_expansion"],
        nominal_diameter_mm,
    )

    overall_status = _overall_status(safety_factor_value, torque_margin, axial_margin)

    return {
        "schema_version": SCHEMA_VERSION,
        "fit_code": geometry["fit_code"],
        "fit_family": fit["family"],
        "overall_status": overall_status,
        "raw_interference_um": {
            "min": round(raw_min_um, 3),
            "max": round(raw_max_um, 3),
            "nominal": round(raw_nominal_um, 3),
        },
        "roughness_loss_um": roughness_loss_value_um,
        "effective_interference_um": {
            "assembly": assembly_interference_um,
            "service": service_interference_value_um,
        },
        "contact_pressure_mpa": {
            "assembly": pressure_assembly_mpa,
            "service": pressure_service_mpa,
        },
        "capacities": {
            "axial_capacity_n": round(axial_capacity_n, 3),
            "torque_capacity_nm": round(torque_capacity_nm, 3),
            "press_force_kn": round(press_force_n / 1000.0, 3),
        },
        "stress": {
            "hub_von_mises_mpa": equivalent_stress_mpa,
            "hub_safety_factor": safety_factor_value,
        },
        "thermal": {
            "required_heating_delta_c": heating_delta_c,
            "recommended_hub_temperature_c": round(operating["assembly_temperature_c"] + heating_delta_c, 3),
            "service_temperature_delta_c": round(service_delta_c, 3),
        },
        "margins": {
            "torque_margin": torque_margin,
            "axial_margin": axial_margin,
            "equipment_force_margin": equipment_force_margin,
        },
    }
