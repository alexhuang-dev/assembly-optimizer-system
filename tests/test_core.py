from __future__ import annotations

import json
from pathlib import Path

from agents.decision import recommend_assembly
from agents.risk import evaluate_risk
from core.assembly import calculate_press_fit
from harness.checks import run_checks


def _load_case(name: str) -> dict:
    path = Path(__file__).parent / "golden" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_nominal_case_prefers_cold_press() -> None:
    payload = _load_case("case_001_nominal.json")
    calc_result = calculate_press_fit(payload)
    risk_eval = evaluate_risk(calc_result)
    recommendation = recommend_assembly(calc_result, payload["operating"])
    harness_eval = run_checks(calc_result, risk_eval, recommendation, payload)

    assert calc_result["fit_code"] == "H7/p6"
    assert 35.0 <= calc_result["contact_pressure_mpa"]["assembly"] <= 60.0
    assert calc_result["stress"]["hub_safety_factor"] is not None
    assert calc_result["stress"]["hub_safety_factor"] > 2.0
    assert recommendation["primary_method"] == "cold_press"
    assert harness_eval["passed"] is True


def test_heavier_case_prefers_thermal_route() -> None:
    payload = _load_case("case_002_thermal.json")
    calc_result = calculate_press_fit(payload)
    risk_eval = evaluate_risk(calc_result)
    recommendation = recommend_assembly(calc_result, payload["operating"])

    assert calc_result["fit_code"] == "H7/s6"
    assert calc_result["capacities"]["press_force_kn"] > payload["operating"]["equipment_force_limit_kn"]
    assert recommendation["primary_method"] == "thermal_assembly"
    assert risk_eval["level"] in {"warning", "critical"}


def test_harness_rejects_cold_press_when_torque_margin_is_too_tight() -> None:
    payload = _load_case("case_001_nominal.json")
    calc_result = calculate_press_fit(payload)
    calc_result["margins"]["torque_margin"] = 1.1
    risk_eval = evaluate_risk(calc_result)
    recommendation = {
        "primary_method": "cold_press",
        "alternative_fit_code": None,
    }

    harness_eval = run_checks(calc_result, risk_eval, recommendation, payload)
    consistency_check = next(item for item in harness_eval["checks"] if item["name"] == "recommendation_consistency")

    assert consistency_check["passed"] is False
    assert harness_eval["passed"] is False
