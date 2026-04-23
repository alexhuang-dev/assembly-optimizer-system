from __future__ import annotations

FIT_UPGRADE = {
    "H7/k6": "H7/m6",
    "H7/m6": "H7/p6",
    "H7/p6": "H7/s6",
    "H7/s6": "H7/u6",
    "H7/u6": None,
}

FIT_DOWNGRADE = {
    "H7/u6": "H7/s6",
    "H7/s6": "H7/p6",
    "H7/p6": "H7/m6",
    "H7/m6": "H7/k6",
    "H7/k6": None,
}


def assess_route_options(calc_result: dict, operating: dict) -> dict:
    safety_factor = calc_result["stress"]["hub_safety_factor"] or 0.0
    press_force_kn = calc_result["capacities"]["press_force_kn"]
    equipment_force_limit_kn = operating["equipment_force_limit_kn"]
    heating_delta_c = calc_result["thermal"]["required_heating_delta_c"]
    torque_margin = calc_result["margins"]["torque_margin"]

    cold_press_feasible = (
        press_force_kn <= equipment_force_limit_kn
        and safety_factor >= 1.5
        and (torque_margin is None or torque_margin >= 1.15)
    )
    thermal_assembly_feasible = heating_delta_c <= 220.0

    return {
        "cold_press_feasible": cold_press_feasible,
        "thermal_assembly_feasible": thermal_assembly_feasible,
        "press_force_kn": press_force_kn,
        "equipment_force_limit_kn": equipment_force_limit_kn,
        "heating_delta_c": heating_delta_c,
        "safety_factor": safety_factor,
        "torque_margin": torque_margin,
    }


def _fit_adjustment(calc_result: dict) -> str | None:
    fit_code = calc_result["fit_code"]
    torque_margin = calc_result["margins"]["torque_margin"]
    safety_factor = calc_result["stress"]["hub_safety_factor"]

    if torque_margin is not None and torque_margin < 1.1:
        return FIT_UPGRADE.get(fit_code)
    if safety_factor is not None and safety_factor < 1.5:
        return FIT_DOWNGRADE.get(fit_code)
    return None


def recommend_assembly(calc_result: dict, operating: dict) -> dict:
    route_options = assess_route_options(calc_result, operating)
    safety_factor = route_options["safety_factor"]
    press_force_kn = route_options["press_force_kn"]
    heating_delta_c = route_options["heating_delta_c"]
    torque_margin = calc_result["margins"]["torque_margin"]
    axial_margin = calc_result["margins"]["axial_margin"]

    if route_options["cold_press_feasible"]:
        primary_method = "cold_press"
        explanation = "Cold press is feasible because the required force stays inside the machine envelope and the stress margin is acceptable."
    elif route_options["thermal_assembly_feasible"]:
        primary_method = "thermal_assembly"
        explanation = "Thermal assembly is preferred because it reduces the mechanical assembly load while keeping the fit geometry unchanged."
    else:
        primary_method = "fit_reselection"
        explanation = "Neither direct cold press nor a moderate thermal route looks comfortable, so the fit should be reselected."

    suggestions = []
    if primary_method == "cold_press":
        suggestions.append("Use controlled lubrication and monitor the real press-force trace during validation runs.")
    if primary_method == "thermal_assembly":
        suggestions.append("Use hub heating and hold the shaft near ambient temperature to preserve predictable interference gain.")
    if torque_margin is not None and torque_margin < 1.25:
        suggestions.append("Increase contact length or move to a stronger fit class if transmitted torque is production-critical.")
    if axial_margin is not None and axial_margin < 1.25:
        suggestions.append("Add an axial retention feature if pull-out load is a major design driver.")
    if safety_factor < 2.0:
        suggestions.append("Validate hub material strength or increase hub outer diameter before release.")

    alternative_fit = _fit_adjustment(calc_result)

    return {
        "primary_method": primary_method,
        "recommended_press_force_kn": round(press_force_kn, 3) if primary_method == "cold_press" else None,
        "recommended_hub_temperature_c": calc_result["thermal"]["recommended_hub_temperature_c"]
        if primary_method == "thermal_assembly"
        else None,
        "alternative_fit_code": alternative_fit,
        "summary": explanation,
        "next_actions": suggestions,
    }
