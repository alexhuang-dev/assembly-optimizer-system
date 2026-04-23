from __future__ import annotations

from typing import Any

from agents.decision import assess_route_options, recommend_assembly
from agents.risk import evaluate_risk
from multiagent.llm import StructuredLLMClient


SEVERITY_ORDER = {
    "normal": 0,
    "acceptable": 0,
    "warning": 1,
    "critical": 2,
}


def _more_severe(left: str, right: str) -> str:
    left_norm = str(left or "normal").strip().lower()
    right_norm = str(right or "normal").strip().lower()
    return left_norm if SEVERITY_ORDER.get(left_norm, 0) >= SEVERITY_ORDER.get(right_norm, 0) else right_norm


def _guess_failure_mode(baseline: dict[str, Any]) -> str:
    reasons = set(baseline.get("reasons", []))
    if "service_interference_lost" in reasons:
        return "thermal_release"
    if "torque_capacity_below_demand" in reasons:
        return "micro_slip_or_rotation"
    if "axial_capacity_below_demand" in reasons:
        return "axial_pullout"
    if "hub_safety_factor_below_1" in reasons or "hub_safety_factor_below_2" in reasons:
        return "hub_plasticity_or_yield"
    return "no_dominant_failure_mode"


def _mock_risk_assessment(
    calc_result: dict[str, Any],
    baseline: dict[str, Any],
    world_model_result: dict[str, Any] | None,
    history_result: dict[str, Any] | None,
) -> dict[str, Any]:
    dominant_risk = (world_model_result or {}).get("dominant_risk", "deterministic_margin")
    history_flag = bool((history_result or {}).get("has_previous"))
    return {
        "risk_level": baseline["level"],
        "primary_failure_mode": _guess_failure_mode(baseline),
        "key_concern": (
            "historical degradation in matching scenarios"
            if history_flag
            else f"current dominant modeled risk is {dominant_risk}"
        ),
        "confidence": 0.92 if baseline["level"] == "normal" else 0.84,
        "rationale": (
            "Deterministic margins remain comfortable and no major contradiction was found."
            if baseline["level"] == "normal"
            else "Deterministic margins indicate one or more weak points that deserve engineering review."
        ),
    }


def _normalize_risk_assessment(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_level": str(raw.get("risk_level") or raw.get("level") or "warning").strip().lower(),
        "primary_failure_mode": str(raw.get("primary_failure_mode") or "unspecified").strip(),
        "key_concern": str(raw.get("key_concern") or raw.get("concern") or "").strip(),
        "confidence": float(raw.get("confidence") or 0.0),
        "rationale": str(raw.get("rationale") or raw.get("summary") or "").strip(),
    }


def _mock_decision_assessment(
    baseline: dict[str, Any],
    risk_result: dict[str, Any],
    history_result: dict[str, Any] | None,
) -> dict[str, Any]:
    has_history = bool((history_result or {}).get("has_previous"))
    return {
        "primary_method": baseline["primary_method"],
        "summary": (
            "Historical evidence supports the current route and no additional route escalation is required."
            if has_history and risk_result["level"] == "normal"
            else baseline["summary"]
        ),
        "key_tradeoff": (
            "lower installation effort versus preserving enough in-service margin"
            if baseline["primary_method"] == "thermal_assembly"
            else "repeatable press trace versus cycle time"
        ),
        "operator_watch_item": (
            "Watch the heating profile and temperature soak consistency."
            if baseline["primary_method"] == "thermal_assembly"
            else "Watch the real press-force signature against the expected envelope."
        ),
        "confidence": 0.9 if risk_result["level"] == "normal" else 0.82,
        "alternative_fit_code": baseline.get("alternative_fit_code"),
    }


def _normalize_decision_assessment(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_method": str(raw.get("primary_method") or raw.get("method") or "engineering_review").strip().lower(),
        "summary": str(raw.get("summary") or raw.get("rationale") or "").strip(),
        "key_tradeoff": str(raw.get("key_tradeoff") or "").strip(),
        "operator_watch_item": str(raw.get("operator_watch_item") or raw.get("watch_item") or "").strip(),
        "confidence": float(raw.get("confidence") or 0.0),
        "alternative_fit_code": raw.get("alternative_fit_code"),
    }


def _method_allowed(candidate: str, baseline: dict[str, Any], route_options: dict[str, Any]) -> bool:
    if candidate == "cold_press":
        return route_options["cold_press_feasible"]
    if candidate == "thermal_assembly":
        return route_options["thermal_assembly_feasible"]
    if candidate == "fit_reselection":
        return True
    return candidate == baseline["primary_method"]


def _mock_constitutional_audit(
    calc_result: dict[str, Any] | None,
    risk_result: dict[str, Any],
    process_result: dict[str, Any],
    harness_report: dict[str, Any],
    policy_result: dict[str, Any],
    approval_record: dict[str, Any] | None,
    execution_result: dict[str, Any] | None,
) -> dict[str, Any]:
    issues: list[str] = []
    if risk_result["level"] == "critical" and process_result["primary_method"] == "cold_press":
        issues.append("Cold press recommendation is inconsistent with a critical merged risk level.")
    if policy_result.get("requires_approval") and (execution_result or {}).get("status") == "published":
        if not approval_record or approval_record.get("decision") != "approve":
            issues.append("Published dispatch is missing an approval record.")
    if harness_report.get("blocking_issues"):
        issues.append("Harness still reports blocking issues.")
    return {
        "passed": not issues,
        "issues": issues,
        "verdict": "No additional contradiction found." if not issues else "Conflicts found between specialist outputs and governance state.",
        "confidence": 0.88,
    }


def _normalize_constitutional_audit(raw: dict[str, Any]) -> dict[str, Any]:
    issues = raw.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    return {
        "passed": bool(raw.get("passed", not issues)),
        "issues": [str(item) for item in issues if str(item).strip()],
        "verdict": str(raw.get("verdict") or "").strip(),
        "confidence": float(raw.get("confidence") or 0.0),
    }


def llm_enhanced_risk_assessment(
    calc_result: dict[str, Any],
    world_model_result: dict[str, Any] | None,
    history_result: dict[str, Any] | None,
    llm_client: StructuredLLMClient,
) -> dict[str, Any]:
    baseline = evaluate_risk(calc_result)
    llm_assessment: dict[str, Any] | None = None
    llm_error: str | None = None

    if llm_client.available:
        try:
            if llm_client.is_mock:
                llm_assessment = _mock_risk_assessment(calc_result, baseline, world_model_result, history_result)
            else:
                system_prompt = (
                    "You are a senior press-fit and mechanical assembly risk specialist. "
                    "Base your reasoning on the deterministic facts provided. "
                    "Do not invent measurements. Return only JSON."
                )
                user_prompt = f"""
Evaluate this interference-fit scenario.

Deterministic facts:
- fit_code: {calc_result['fit_code']}
- overall_status: {calc_result['overall_status']}
- hub_safety_factor: {calc_result['stress']['hub_safety_factor']}
- torque_margin: {calc_result['margins']['torque_margin']}
- axial_margin: {calc_result['margins']['axial_margin']}
- service_interference_um: {calc_result['effective_interference_um']['service']}
- dominant_world_model_risk: {(world_model_result or {}).get('dominant_risk')}
- historical_has_previous: {(history_result or {}).get('has_previous')}
- deterministic_reasons: {baseline['reasons']}

Return JSON with:
{{
  "risk_level": "normal|warning|critical",
  "primary_failure_mode": "...",
  "key_concern": "...",
  "confidence": 0.0,
  "rationale": "..."
}}
"""
                llm_assessment = _normalize_risk_assessment(
                    llm_client.invoke_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0, max_tokens=400)
                )
        except Exception as exc:  # pragma: no cover - exercised in integration only
            llm_error = str(exc)

    if llm_assessment is None:
        return {
            **baseline,
            "rule_baseline": baseline,
            "llm_assessment": None,
            "source": "rules_only",
            "primary_failure_mode": _guess_failure_mode(baseline),
            "key_concern": baseline["warnings"][0] if baseline["warnings"] else "No dominant concern identified.",
            "confidence": 0.78,
            "llm_error": llm_error,
        }

    llm_assessment = _normalize_risk_assessment(llm_assessment)
    merged_level = _more_severe(baseline["level"], llm_assessment["risk_level"])
    merged_summary = llm_assessment["rationale"] or baseline["summary"]
    return {
        "level": merged_level,
        "reasons": baseline["reasons"],
        "warnings": baseline["warnings"],
        "summary": merged_summary,
        "rule_baseline": baseline,
        "llm_assessment": llm_assessment,
        "source": "llm_plus_rules" if not llm_client.is_mock else "mock_plus_rules",
        "primary_failure_mode": llm_assessment["primary_failure_mode"] or _guess_failure_mode(baseline),
        "key_concern": llm_assessment["key_concern"] or (baseline["warnings"][0] if baseline["warnings"] else ""),
        "confidence": llm_assessment["confidence"] or 0.8,
        "llm_error": llm_error,
    }


def llm_enhanced_process_recommendation(
    calc_result: dict[str, Any],
    operating: dict[str, Any],
    risk_result: dict[str, Any],
    history_result: dict[str, Any] | None,
    llm_client: StructuredLLMClient,
) -> dict[str, Any]:
    baseline = recommend_assembly(calc_result, operating)
    route_options = assess_route_options(calc_result, operating)
    llm_assessment: dict[str, Any] | None = None
    llm_error: str | None = None

    if llm_client.available:
        try:
            if llm_client.is_mock:
                llm_assessment = _mock_decision_assessment(baseline, risk_result, history_result)
            else:
                system_prompt = (
                    "You are a senior assembly process planner. "
                    "Use the deterministic constraints below and return only JSON. "
                    "You may be more conservative than the baseline route, but you may not violate deterministic feasibility."
                )
                user_prompt = f"""
Plan the assembly route.

Deterministic facts:
- fit_code: {calc_result['fit_code']}
- overall_status: {calc_result['overall_status']}
- hub_safety_factor: {calc_result['stress']['hub_safety_factor']}
- torque_margin: {calc_result['margins']['torque_margin']}
- axial_margin: {calc_result['margins']['axial_margin']}
- press_force_kn: {calc_result['capacities']['press_force_kn']}
- equipment_force_limit_kn: {operating['equipment_force_limit_kn']}
- required_heating_delta_c: {calc_result['thermal']['required_heating_delta_c']}
- baseline_method: {baseline['primary_method']}
- baseline_alternative_fit: {baseline.get('alternative_fit_code')}
- risk_level: {risk_result['level']}
- historical_has_previous: {(history_result or {}).get('has_previous')}

Return JSON with:
{{
  "primary_method": "cold_press|thermal_assembly|fit_reselection",
  "summary": "...",
  "key_tradeoff": "...",
  "operator_watch_item": "...",
  "confidence": 0.0,
  "alternative_fit_code": null
}}
"""
                llm_assessment = _normalize_decision_assessment(
                    llm_client.invoke_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0, max_tokens=450)
                )
        except Exception as exc:  # pragma: no cover - exercised in integration only
            llm_error = str(exc)

    if llm_assessment is None:
        return {
            **baseline,
            "rule_baseline": baseline,
            "llm_assessment": None,
            "source": "rules_only",
            "key_tradeoff": "No LLM process reasoning enabled.",
            "operator_watch_item": baseline["next_actions"][0] if baseline["next_actions"] else "",
            "confidence": 0.76,
            "llm_error": llm_error,
        }

    llm_assessment = _normalize_decision_assessment(llm_assessment)
    candidate_method = llm_assessment["primary_method"] or baseline["primary_method"]
    if not _method_allowed(candidate_method, baseline, route_options):
        candidate_method = baseline["primary_method"]

    final_result = dict(baseline)
    final_result["primary_method"] = candidate_method
    if candidate_method == "thermal_assembly":
        final_result["recommended_hub_temperature_c"] = calc_result["thermal"]["recommended_hub_temperature_c"]
        final_result["recommended_press_force_kn"] = None
    elif candidate_method == "cold_press":
        final_result["recommended_press_force_kn"] = round(calc_result["capacities"]["press_force_kn"], 3)
        final_result["recommended_hub_temperature_c"] = None
    else:
        final_result["recommended_press_force_kn"] = None
        final_result["recommended_hub_temperature_c"] = None
        final_result["alternative_fit_code"] = llm_assessment["alternative_fit_code"] or baseline.get("alternative_fit_code")

    final_result["summary"] = llm_assessment["summary"] or baseline["summary"]
    final_result["rule_baseline"] = baseline
    final_result["llm_assessment"] = llm_assessment
    final_result["source"] = "llm_plus_rules" if not llm_client.is_mock else "mock_plus_rules"
    final_result["key_tradeoff"] = llm_assessment["key_tradeoff"]
    final_result["operator_watch_item"] = llm_assessment["operator_watch_item"]
    final_result["confidence"] = llm_assessment["confidence"] or 0.8
    final_result["llm_error"] = llm_error
    return final_result


def llm_world_model_summary(
    calc_result: dict[str, Any] | None,
    world_model_baseline: dict[str, Any],
    memory_events: list[dict[str, Any]],
    llm_client: StructuredLLMClient,
) -> dict[str, Any] | None:
    if not calc_result or not llm_client.available:
        return None
    if llm_client.is_mock:
        dominant = world_model_baseline["dominant_risk"]
        trend = "stable" if not memory_events else "needs_attention"
        return {
            "trend": trend,
            "forecast_status": world_model_baseline["predicted_states"][-1]["status"],
            "memory_signal": f"Recent memory events tracked: {len(memory_events)}",
            "dominant_risk": dominant,
            "confidence": 0.82,
        }
    try:  # pragma: no cover - exercised in integration only
        system_prompt = (
            "You are a digital twin forecasting assistant for mechanical assembly. "
            "Use deterministic probabilities and recent memory journal events to summarize trend direction. "
            "Return only JSON."
        )
        user_prompt = f"""
Forecast the next-state risk for this scenario.

Deterministic world model:
- dominant_risk: {world_model_baseline['dominant_risk']}
- failure_probabilities: {world_model_baseline['failure_probabilities']}
- predicted_states: {world_model_baseline['predicted_states']}

Mechanical margins:
- hub_safety_factor: {calc_result['stress']['hub_safety_factor']}
- torque_margin: {calc_result['margins']['torque_margin']}
- axial_margin: {calc_result['margins']['axial_margin']}

Recent memory events:
{memory_events}

Return JSON:
{{
  "trend": "improving|stable|worsening|needs_attention",
  "forecast_status": "normal|warning|critical",
  "memory_signal": "...",
  "dominant_risk": "...",
  "confidence": 0.0
}}
"""
        raw = llm_client.invoke_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0, max_tokens=350)
        return {
            "trend": str(raw.get("trend") or "stable"),
            "forecast_status": str(raw.get("forecast_status") or world_model_baseline["predicted_states"][-1]["status"]),
            "memory_signal": str(raw.get("memory_signal") or "").strip(),
            "dominant_risk": str(raw.get("dominant_risk") or world_model_baseline["dominant_risk"]),
            "confidence": float(raw.get("confidence") or 0.0),
        }
    except Exception:
        return None


def llm_constitutional_audit(
    calc_result: dict[str, Any] | None,
    risk_result: dict[str, Any],
    process_result: dict[str, Any],
    harness_report: dict[str, Any],
    policy_result: dict[str, Any],
    approval_record: dict[str, Any] | None,
    execution_result: dict[str, Any] | None,
    llm_client: StructuredLLMClient,
) -> dict[str, Any]:
    rule_issues: list[str] = []
    if execution_result and execution_result.get("status") in {"published", "already_published"} and policy_result.get("requires_approval"):
        if not approval_record or approval_record.get("decision") != "approve":
            rule_issues.append("A dispatchable action requiring approval was executed without an approval record.")
    if harness_report.get("blocking_issues"):
        rule_issues.extend(str(item) for item in harness_report["blocking_issues"])

    llm_audit: dict[str, Any] | None = None
    llm_error: str | None = None
    if llm_client.available:
        try:
            if llm_client.is_mock:
                llm_audit = _mock_constitutional_audit(
                    calc_result, risk_result, process_result, harness_report, policy_result, approval_record, execution_result
                )
            else:  # pragma: no cover - exercised in integration only
                system_prompt = (
                    "You are an independent constitutional audit model for an industrial assembly workflow. "
                    "Your only job is to find contradictions or governance violations. Return only JSON."
                )
                user_prompt = f"""
Audit this assembly decision package for contradictions.

Deterministic calculation:
{calc_result}

Risk specialist:
{risk_result}

Process specialist:
{process_result}

Harness report:
{harness_report}

Policy state:
{policy_result}

Approval record:
{approval_record}

Execution result:
{execution_result}

Return JSON:
{{
  "passed": true,
  "issues": [],
  "verdict": "...",
  "confidence": 0.0
}}
"""
                llm_audit = _normalize_constitutional_audit(
                    llm_client.invoke_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0, max_tokens=450)
                )
        except Exception as exc:
            llm_error = str(exc)

    llm_issues = llm_audit["issues"] if llm_audit else []
    issues = rule_issues + [issue for issue in llm_issues if issue not in rule_issues]
    passed = not issues and (llm_audit["passed"] if llm_audit else True)
    return {
        "passed": passed,
        "issues": issues,
        "verdict": (
            llm_audit["verdict"]
            if llm_audit and llm_audit.get("verdict")
            else ("No contradiction found." if not issues else "Contradictions detected.")
        ),
        "rule_audit": {
            "passed": not rule_issues,
            "issues": rule_issues,
        },
        "llm_audit": llm_audit,
        "source": "llm_plus_rules" if llm_audit and not llm_client.is_mock else ("mock_plus_rules" if llm_audit else "rules_only"),
        "llm_error": llm_error,
    }
