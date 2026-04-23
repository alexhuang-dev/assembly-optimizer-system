from __future__ import annotations


def evaluate_risk(calc_result: dict) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []

    safety_factor = calc_result["stress"]["hub_safety_factor"]
    torque_margin = calc_result["margins"]["torque_margin"]
    axial_margin = calc_result["margins"]["axial_margin"]

    if safety_factor is not None and safety_factor < 1.0:
        reasons.append("hub_safety_factor_below_1")
        warnings.append("Hub stress exceeds the elastic safety envelope.")
    elif safety_factor is not None and safety_factor < 2.0:
        reasons.append("hub_safety_factor_below_2")
        warnings.append("Safety factor is usable but does not leave much process margin.")

    if torque_margin is not None and torque_margin < 1.0:
        reasons.append("torque_capacity_below_demand")
        warnings.append("Holding torque is below the transmitted torque requirement.")
    elif torque_margin is not None and torque_margin < 1.25:
        reasons.append("torque_margin_below_1_25")
        warnings.append("Torque margin is narrow under service conditions.")

    if axial_margin is not None and axial_margin < 1.0:
        reasons.append("axial_capacity_below_demand")
        warnings.append("Axial retention capacity is below the requested load.")
    elif axial_margin is not None and axial_margin < 1.25:
        reasons.append("axial_margin_below_1_25")
        warnings.append("Axial retention margin is narrow.")

    if calc_result["effective_interference_um"]["service"] <= 0:
        reasons.append("service_interference_lost")
        warnings.append("The fit opens up at service temperature.")

    if any(reason.endswith("below_demand") or reason.endswith("below_1") or reason == "service_interference_lost" for reason in reasons):
        level = "critical"
    elif reasons:
        level = "warning"
    else:
        level = "normal"

    summary = {
        "normal": "The current fit is mechanically acceptable with comfortable margin.",
        "warning": "The current fit is usable, but one or more margins are tight and should be reviewed.",
        "critical": "The current fit is not safe enough for direct release and needs redesign or process change.",
    }[level]

    return {
        "level": level,
        "reasons": reasons,
        "warnings": warnings,
        "summary": summary,
    }

