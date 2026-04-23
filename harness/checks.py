from __future__ import annotations

from agents.decision import assess_route_options


def run_checks(calc_result: dict, risk_eval: dict, recommendation: dict, request_payload: dict) -> dict:
    checks = []

    geometry = request_payload["geometry"]
    materials = request_payload["materials"]
    operating = request_payload["operating"]
    route_options = assess_route_options(calc_result, operating)

    checks.append(
        {
            "name": "physical_reasonableness",
            "passed": (
                calc_result["effective_interference_um"]["assembly"] > 0
                and (calc_result["stress"]["hub_safety_factor"] or 0) > 1.0
                and geometry["hub_outer_diameter_mm"] > geometry["nominal_diameter_mm"]
            ),
            "details": {
                "effective_interference_um": calc_result["effective_interference_um"]["assembly"],
                "hub_safety_factor": calc_result["stress"]["hub_safety_factor"],
            },
        }
    )

    if recommendation["primary_method"] == "cold_press":
        ai_consistency = route_options["cold_press_feasible"]
    elif recommendation["primary_method"] == "thermal_assembly":
        ai_consistency = route_options["thermal_assembly_feasible"]
    else:
        ai_consistency = recommendation["alternative_fit_code"] is not None or risk_eval["level"] == "critical"

    checks.append(
        {
            "name": "recommendation_consistency",
            "passed": ai_consistency,
            "details": {
                "primary_method": recommendation["primary_method"],
                "press_force_kn": calc_result["capacities"]["press_force_kn"],
                "equipment_force_limit_kn": operating["equipment_force_limit_kn"],
                "required_heating_delta_c": calc_result["thermal"]["required_heating_delta_c"],
                "cold_press_feasible": route_options["cold_press_feasible"],
                "thermal_assembly_feasible": route_options["thermal_assembly_feasible"],
                "torque_margin": route_options["torque_margin"],
                "hub_safety_factor": route_options["safety_factor"],
            },
        }
    )

    checks.append(
        {
            "name": "standards_and_material_fields",
            "passed": (
                geometry["fit_code"] in {"H7/k6", "H7/m6", "H7/p6", "H7/s6", "H7/u6"}
                and materials["shaft_elastic_modulus_gpa"] > 0
                and materials["hub_elastic_modulus_gpa"] > 0
                and materials["hub_yield_strength_mpa"] > 0
            ),
            "details": {
                "fit_code": geometry["fit_code"],
            },
        }
    )

    passed_count = sum(1 for item in checks if item["passed"])
    score = round(passed_count / len(checks), 3)
    return {
        "passed": passed_count == len(checks),
        "score": score,
        "checks": checks,
    }
