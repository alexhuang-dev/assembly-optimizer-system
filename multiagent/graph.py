from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agents.decision import assess_route_options
from core.assembly import build_run_id, build_scenario_key, calculate_press_fit
from core.history import compare_with_previous, fetch_previous_run
from core.iso286 import get_fit_definition, list_supported_fits
from multiagent.llm import StructuredLLMClient
from multiagent.runtime import (
    MultiAgentRuntimeConfig,
    append_memory_events,
    build_action_key,
    dispatch_instruction_plan,
    fetch_recent_memory_events,
)
from multiagent.specialists import (
    llm_constitutional_audit,
    llm_enhanced_process_recommendation,
    llm_enhanced_risk_assessment,
    llm_world_model_summary,
)


class MultiAgentState(TypedDict):
    request_payload: dict[str, Any]
    runtime_config: dict[str, Any]
    thread_id: str
    run_id: str
    scenario_key: str

    calculation_error: str | None
    assembly_result: dict[str, Any] | None
    world_model_result: dict[str, Any]

    selected_experts: list[str]
    expert_confidence: dict[str, float]

    standards_result: dict[str, Any] | None
    risk_result: dict[str, Any] | None
    process_result: dict[str, Any] | None
    history_result: dict[str, Any] | None

    harness_passed: bool
    harness_report: dict[str, Any]
    risk_level: str
    decision_package: dict[str, Any]
    policy_result: dict[str, Any]

    approval_record: dict[str, Any] | None
    execution_plan: dict[str, Any] | None
    execution_result: dict[str, Any] | None

    xai_trace: Annotated[list[str], operator.add]
    knowledge_updates: Annotated[list[dict[str, Any]], operator.add]
    audit_log: Annotated[list[str], operator.add]

    constitutional_passed: bool
    constitutional_report: dict[str, Any]


def _probability_from_margin(margin: float | None) -> float:
    if margin is None:
        return 0.02
    if margin <= 1.0:
        return 0.9
    if margin <= 1.1:
        return 0.72
    if margin <= 1.2:
        return 0.48
    if margin <= 1.3:
        return 0.26
    if margin <= 1.5:
        return 0.16
    if margin <= 2.0:
        return 0.08
    return 0.03


def _world_model_status(probability: float) -> str:
    if probability >= 0.6:
        return "critical"
    if probability >= 0.3:
        return "warning"
    return "normal"


def initialize_context_node(state: MultiAgentState) -> dict[str, Any]:
    payload = state["request_payload"]
    scenario_key = build_scenario_key(payload)
    return {
        "run_id": build_run_id(payload),
        "scenario_key": scenario_key,
        "audit_log": [f"[Init] Thread={state['thread_id']} Scenario={scenario_key}"],
    }


def calculation_node(state: MultiAgentState) -> dict[str, Any]:
    payload = state["request_payload"]
    try:
        calc_result = calculate_press_fit(payload)
        return {
            "assembly_result": calc_result,
            "calculation_error": None,
            "xai_trace": [f"[Calculation] Fit={calc_result['fit_code']} Status={calc_result['overall_status']}"],
            "audit_log": ["[Calculation] Deterministic press-fit analysis completed"],
        }
    except Exception as exc:
        return {
            "assembly_result": None,
            "calculation_error": str(exc),
            "audit_log": [f"[Calculation] Failed: {exc}"],
        }


def build_graph(runtime_config: MultiAgentRuntimeConfig) -> StateGraph:
    llm_client = StructuredLLMClient(runtime_config.llm)

    def world_model_node(state: MultiAgentState) -> dict[str, Any]:
        calc_result = state.get("assembly_result")
        memory_events = fetch_recent_memory_events(runtime_config.operations_db_path, state["scenario_key"], limit=6)
        if not calc_result:
            baseline = {
                "failure_probabilities": {"analysis_failure": 1.0},
                "predicted_states": [{"horizon": "now", "status": "critical"}],
                "dominant_risk": "analysis_failure",
                "memory_context": memory_events,
            }
            return {
                "world_model_result": baseline,
                "audit_log": ["[World Model] Fallback critical state because calculation failed"],
            }

        margins = calc_result["margins"]
        safety_factor = calc_result["stress"]["hub_safety_factor"]
        heating_delta_c = calc_result["thermal"]["required_heating_delta_c"]

        slip_risk = _probability_from_margin(margins["torque_margin"])
        axial_risk = _probability_from_margin(margins["axial_margin"])
        yield_risk = _probability_from_margin(safety_factor)
        heating_risk = 0.75 if heating_delta_c > 220.0 else 0.35 if heating_delta_c > 140.0 else 0.08

        probabilities = {
            "slip_risk": slip_risk,
            "axial_release_risk": axial_risk,
            "hub_yield_risk": yield_risk,
            "thermal_process_risk": round(heating_risk, 3),
        }
        dominant_risk = max(probabilities, key=probabilities.get)
        predicted_states = [
            {"horizon": "assembly", "status": _world_model_status(max(slip_risk, yield_risk))},
            {"horizon": "service", "status": _world_model_status(max(probabilities.values()))},
        ]
        baseline = {
            "failure_probabilities": probabilities,
            "predicted_states": predicted_states,
            "dominant_risk": dominant_risk,
            "memory_context": memory_events,
        }
        llm_forecast = llm_world_model_summary(calc_result, baseline, memory_events, llm_client)
        world_model_result = {
            **baseline,
            "llm_forecast": llm_forecast,
            "source": "llm_plus_rules" if llm_forecast and not llm_client.is_mock else ("mock_plus_rules" if llm_forecast else "rules_only"),
        }
        trace = f"[World Model] Dominant risk={dominant_risk}"
        if llm_forecast:
            trace += f" Trend={llm_forecast['trend']}"
        return {
            "world_model_result": world_model_result,
            "xai_trace": [trace],
            "audit_log": ["[World Model] Scenario forecast computed from deterministic margins and memory context"],
        }

    def router_node(state: MultiAgentState) -> dict[str, Any]:
        calc_result = state.get("assembly_result")
        world_model = state["world_model_result"]
        payload = state["request_payload"]

        selected = {"risk_agent", "process_agent"}
        confidence = {"risk_agent": 0.9, "process_agent": 0.88}

        if calc_result is None:
            selected.add("standards_agent")
            confidence["standards_agent"] = 0.95
        else:
            fit_family = calc_result["fit_family"]
            if fit_family in {"heavy_press_fit", "shrink_fit"}:
                selected.add("standards_agent")
                confidence["standards_agent"] = 0.86

            max_probability = max(world_model.get("failure_probabilities", {}).values(), default=0.0)
            if max_probability >= 0.2 or payload["geometry"].get("part_id"):
                selected.add("history_agent")
                confidence["history_agent"] = 0.8 if max_probability >= 0.2 else 0.72

        ordered = sorted(selected)
        return {
            "selected_experts": ordered,
            "expert_confidence": confidence,
            "audit_log": [f"[Router] Selected experts={ordered}"],
        }

    def standards_agent_node(state: MultiAgentState) -> dict[str, Any]:
        if "standards_agent" not in state.get("selected_experts", []):
            return {}

        payload = state["request_payload"]
        fit_code = payload["geometry"]["fit_code"]
        supported = fit_code in list_supported_fits()
        result = {
            "fit_code": fit_code,
            "supported": supported,
            "fit_definition": get_fit_definition(fit_code) if supported else None,
            "notes": (
                "Fit is within the curated ISO 286 library used by this system."
                if supported
                else "Fit is not present in the supported ISO 286 library."
            ),
        }
        return {
            "standards_result": result,
            "xai_trace": [f"[Standards] Fit={fit_code} Supported={supported}"],
            "audit_log": ["[Standards] Standards validation completed"],
        }

    def risk_agent_node(state: MultiAgentState) -> dict[str, Any]:
        if "risk_agent" not in state.get("selected_experts", []):
            return {}

        calc_result = state.get("assembly_result")
        if not calc_result:
            result = {
                "level": "critical",
                "reasons": ["calculation_error"],
                "warnings": ["Deterministic calculation failed, so the scenario cannot be released."],
                "summary": "Calculation failed and requires engineering review.",
                "rule_baseline": None,
                "llm_assessment": None,
                "source": "rules_only",
                "primary_failure_mode": "analysis_failure",
                "key_concern": "Deterministic calculation failed.",
                "confidence": 1.0,
            }
        else:
            result = llm_enhanced_risk_assessment(
                calc_result=calc_result,
                world_model_result=state.get("world_model_result"),
                history_result=state.get("history_result"),
                llm_client=llm_client,
            )

        return {
            "risk_result": result,
            "xai_trace": [f"[Risk] Level={result['level']} Source={result['source']}"],
            "audit_log": ["[Risk] Risk specialist completed"],
        }

    def process_agent_node(state: MultiAgentState) -> dict[str, Any]:
        if "process_agent" not in state.get("selected_experts", []):
            return {}

        calc_result = state.get("assembly_result")
        if not calc_result:
            result = {
                "primary_method": "engineering_review",
                "recommended_press_force_kn": None,
                "recommended_hub_temperature_c": None,
                "alternative_fit_code": None,
                "summary": "Calculation failed, so no automated assembly route can be recommended.",
                "next_actions": ["Review input geometry, fit code, and material assumptions before release."],
                "rule_baseline": None,
                "llm_assessment": None,
                "source": "rules_only",
                "key_tradeoff": "No route recommendation available.",
                "operator_watch_item": "Review deterministic inputs before any release action.",
                "confidence": 1.0,
            }
        else:
            result = llm_enhanced_process_recommendation(
                calc_result=calc_result,
                operating=state["request_payload"]["operating"],
                risk_result=state.get("risk_result") or {"level": "warning"},
                history_result=state.get("history_result"),
                llm_client=llm_client,
            )

        return {
            "process_result": result,
            "xai_trace": [f"[Process] Method={result['primary_method']} Source={result['source']}"],
            "audit_log": ["[Process] Process specialist completed"],
        }

    def history_agent_node(state: MultiAgentState) -> dict[str, Any]:
        if "history_agent" not in state.get("selected_experts", []):
            return {}

        previous_run = fetch_previous_run(runtime_config.history_db_path, scenario_key=state["scenario_key"])
        scenario_memory = fetch_recent_memory_events(runtime_config.operations_db_path, state["scenario_key"], limit=8)
        if not previous_run or not state.get("assembly_result"):
            result = {
                "has_previous": False,
                "previous_run": previous_run,
                "comparison": {"has_previous": False},
                "memory_events": scenario_memory,
            }
        else:
            result = {
                "has_previous": True,
                "previous_run": previous_run,
                "comparison": compare_with_previous(state["assembly_result"], previous_run),
                "memory_events": scenario_memory,
            }

        return {
            "history_result": result,
            "xai_trace": [f"[History] Has previous={result['has_previous']} Memory events={len(scenario_memory)}"],
            "audit_log": ["[History] Scenario-grouped history lookup completed"],
        }

    def harness_node(state: MultiAgentState) -> dict[str, Any]:
        blocking_issues: list[str] = []
        warnings: list[str] = []

        calc_result = state.get("assembly_result")
        standards = state.get("standards_result")
        process = state.get("process_result") or {}
        risk = state.get("risk_result") or {"level": "critical", "reasons": ["missing_risk_result"], "warnings": []}
        world_model = state.get("world_model_result") or {}
        history = state.get("history_result") or {"has_previous": False}

        if state.get("calculation_error"):
            blocking_issues.append(f"Deterministic calculation failed: {state['calculation_error']}")

        if standards and not standards["supported"]:
            blocking_issues.append(f"Unsupported fit code: {standards['fit_code']}")

        if calc_result and process:
            route_options = assess_route_options(calc_result, state["request_payload"]["operating"])
            method = process["primary_method"]
            if method == "cold_press" and not route_options["cold_press_feasible"]:
                blocking_issues.append("Cold press was recommended even though deterministic route checks say it is not feasible.")
            if method == "thermal_assembly" and not route_options["thermal_assembly_feasible"]:
                blocking_issues.append("Thermal assembly was recommended even though the heating envelope exceeds the configured safety bound.")
            if method == "fit_reselection" and process.get("alternative_fit_code") is None:
                warnings.append("Fit reselection was recommended without a concrete alternative fit code.")

        max_failure_prob = max(world_model.get("failure_probabilities", {}).values(), default=0.0)
        if max_failure_prob >= 0.6:
            warnings.append(f"World model dominant probability is high ({max_failure_prob:.1%}).")

        llm_forecast = world_model.get("llm_forecast") or {}
        if llm_forecast.get("trend") in {"worsening", "needs_attention"}:
            warnings.append(f"World model trend is {llm_forecast['trend']}.")

        if history.get("has_previous"):
            comparison = history["comparison"]
            if comparison.get("safety_factor_delta", 0) < -0.25:
                warnings.append("Safety factor has degraded materially versus the previous matching scenario.")
            if comparison.get("torque_margin_delta", 0) < -0.1:
                warnings.append("Torque margin is materially worse than the previous matching scenario.")

        if risk.get("llm_error"):
            warnings.append(f"Risk LLM unavailable, fell back to deterministic reasoning: {risk['llm_error']}")
        if process.get("llm_error"):
            warnings.append(f"Process LLM unavailable, fell back to deterministic reasoning: {process['llm_error']}")

        risk_level = risk["level"]
        if blocking_issues:
            effective_risk = "critical"
        elif risk_level == "critical" or max_failure_prob >= 0.6:
            effective_risk = "high"
        elif risk_level == "warning" or warnings:
            effective_risk = "high"
        else:
            effective_risk = "low"

        decision_package = {
            "summary": f"Assembly scenario {state['scenario_key']} evaluated as {effective_risk}",
            "scenario_key": state["scenario_key"],
            "run_id": state["run_id"],
            "analysis_result": calc_result,
            "world_model_result": world_model,
            "standards_result": standards,
            "risk_result": risk,
            "process_result": process,
            "history_result": history,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "xai_trace": state.get("xai_trace", []),
            "llm_runtime": state["runtime_config"].get("llm", {}),
        }

        report = {
            "passed": not blocking_issues,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "effective_risk": effective_risk,
            "selected_experts": state.get("selected_experts", []),
        }
        return {
            "harness_passed": not blocking_issues,
            "harness_report": report,
            "risk_level": effective_risk,
            "decision_package": decision_package,
            "audit_log": [f"[Harness] Risk={effective_risk} Blocking={len(blocking_issues)} Warnings={len(warnings)}"],
        }

    def policy_gate_node(state: MultiAgentState) -> Command[Literal["hitl_node", "planner_node", "memory_update"]]:
        process = state.get("process_result") or {}
        method = process.get("primary_method", "engineering_review")
        report = state.get("harness_report") or {}
        risk_level = state.get("risk_level", "high")

        if report.get("blocking_issues"):
            policy = {
                "action": "block_execution",
                "reason": "blocking_issues_present",
                "requires_approval": False,
            }
            return Command(
                update={
                    "policy_result": policy,
                    "execution_result": {
                        "status": "blocked_by_policy",
                        "reason": report["blocking_issues"],
                    },
                    "audit_log": ["[Policy] Execution blocked before planning"],
                },
                goto="memory_update",
            )

        if risk_level == "low" and method == "cold_press":
            policy = {
                "action": "auto_dispatch",
                "reason": "low_risk_cold_press",
                "requires_approval": False,
            }
            return Command(
                update={
                    "policy_result": policy,
                    "audit_log": ["[Policy] Auto-dispatch approved"],
                },
                goto="planner_node",
            )

        if method in {"cold_press", "thermal_assembly"}:
            policy = {
                "action": "request_human_approval",
                "reason": f"{risk_level}_risk_or_non_default_route",
                "requires_approval": True,
            }
            return Command(
                update={
                    "policy_result": policy,
                    "audit_log": ["[Policy] Human approval required before dispatch"],
                },
                goto="hitl_node",
            )

        policy = {
            "action": "block_execution",
            "reason": f"method_{method}_is_not_dispatchable",
            "requires_approval": False,
        }
        return Command(
            update={
                "policy_result": policy,
                "execution_result": {
                    "status": "blocked_by_policy",
                    "reason": [f"Method {method} is not dispatchable without engineering redesign."],
                },
                "audit_log": ["[Policy] Method blocked from execution dispatch"],
            },
            goto="memory_update",
        )

    def hitl_node(state: MultiAgentState) -> Command[Literal["planner_node", "memory_update"]]:
        package = dict(state.get("decision_package", {}))
        package["policy_result"] = state.get("policy_result")

        human_response = interrupt(
            {
                "type": "human_approval_required",
                "thread_id": state["thread_id"],
                "decision_package": package,
                "message": f"Review assembly scenario {state['scenario_key']}",
            }
        )

        decision = "reject"
        comment = ""
        if isinstance(human_response, dict):
            decision = str(human_response.get("decision", "reject")).lower()
            comment = str(human_response.get("comment", ""))

        approval_record = {
            "decision": decision,
            "comment": comment,
            "approved": decision == "approve",
        }

        if decision == "approve":
            return Command(
                update={
                    "approval_record": approval_record,
                    "audit_log": [f"[HITL] Approved: {comment or 'no comment'}"],
                },
                goto="planner_node",
            )

        return Command(
            update={
                "approval_record": approval_record,
                "execution_result": {
                    "status": "rejected_by_human",
                    "reason": comment or "Manual reviewer rejected the instruction package.",
                },
                "audit_log": [f"[HITL] Rejected: {comment or 'no comment'}"],
            },
            goto="memory_update",
        )

    def planner_node(state: MultiAgentState) -> dict[str, Any]:
        process = state.get("process_result") or {}
        calc_result = state.get("assembly_result")
        risk = state.get("risk_result") or {}
        if not calc_result or not process:
            return {
                "execution_plan": None,
                "audit_log": ["[Planner] No execution plan generated because calculation or process result is missing"],
            }

        method = process["primary_method"]
        if method == "cold_press":
            parameters = {
                "fit_code": calc_result["fit_code"],
                "press_force_kn": calc_result["capacities"]["press_force_kn"],
                "torque_capacity_nm": calc_result["capacities"]["torque_capacity_nm"],
                "axial_capacity_n": calc_result["capacities"]["axial_capacity_n"],
            }
        elif method == "thermal_assembly":
            parameters = {
                "fit_code": calc_result["fit_code"],
                "recommended_hub_temperature_c": calc_result["thermal"]["recommended_hub_temperature_c"],
                "required_heating_delta_c": calc_result["thermal"]["required_heating_delta_c"],
                "service_temperature_delta_c": calc_result["thermal"]["service_temperature_delta_c"],
            }
        else:
            parameters = {
                "fit_code": calc_result["fit_code"],
                "alternative_fit_code": process.get("alternative_fit_code"),
                "engineering_summary": process.get("summary"),
            }

        execution_plan = {
            "plan_type": "assembly_instruction_package",
            "method": method,
            "scenario_key": state["scenario_key"],
            "run_id": state["run_id"],
            "parameters": parameters,
            "risk_level": risk.get("level"),
            "primary_failure_mode": risk.get("primary_failure_mode"),
            "operator_watch_item": process.get("operator_watch_item"),
            "next_actions": process.get("next_actions", []),
        }
        execution_plan["action_key"] = build_action_key(execution_plan)
        return {
            "execution_plan": execution_plan,
            "xai_trace": [f"[Planner] Action key={execution_plan['action_key']}"],
            "audit_log": [f"[Planner] Built execution plan for method={method}"],
        }

    def execute_node(state: MultiAgentState) -> dict[str, Any]:
        plan = state.get("execution_plan")
        if not plan:
            return {
                "execution_result": {
                    "status": "no_dispatch",
                    "reason": "No execution plan was available.",
                },
                "audit_log": ["[Execute] No dispatch because no plan exists"],
            }

        result = dispatch_instruction_plan(
            db_path=runtime_config.operations_db_path,
            dispatch_dir=runtime_config.dispatch_dir,
            thread_id=state["thread_id"],
            execution_plan=plan,
        )
        return {
            "execution_result": result,
            "audit_log": [f"[Execute] Dispatch status={result['status']}"],
        }

    def memory_update_node(state: MultiAgentState) -> dict[str, Any]:
        events: list[dict[str, Any]] = []

        if state.get("risk_result"):
            events.append({"type": "risk_eval", "content": state["risk_result"]})
        if state.get("process_result"):
            events.append({"type": "process_recommendation", "content": state["process_result"]})
        if state.get("execution_result"):
            events.append({"type": "execution_result", "content": state["execution_result"]})
        if state.get("constitutional_report"):
            events.append({"type": "constitutional_audit", "content": state["constitutional_report"]})

        event_count = append_memory_events(
            db_path=runtime_config.operations_db_path,
            thread_id=state["thread_id"],
            scenario_key=state["scenario_key"],
            events=events,
        )
        return {
            "knowledge_updates": events,
            "audit_log": [f"[Memory] Persisted {event_count} events to the memory journal"],
        }

    def constitutional_node(state: MultiAgentState) -> dict[str, Any]:
        report = llm_constitutional_audit(
            calc_result=state.get("assembly_result"),
            risk_result=state.get("risk_result") or {"level": "critical"},
            process_result=state.get("process_result") or {"primary_method": "engineering_review"},
            harness_report=state.get("harness_report") or {},
            policy_result=state.get("policy_result") or {},
            approval_record=state.get("approval_record"),
            execution_result=state.get("execution_result"),
            llm_client=llm_client,
        )
        return {
            "constitutional_passed": report["passed"],
            "constitutional_report": report,
            "audit_log": [f"[Constitutional] {'passed' if report['passed'] else 'failed'}: {report['issues']}"],
        }

    builder = StateGraph(MultiAgentState)

    builder.add_node("initialize_context", initialize_context_node)
    builder.add_node("calculation", calculation_node)
    builder.add_node("world_model", world_model_node)
    builder.add_node("router", router_node)
    builder.add_node("standards_agent", standards_agent_node)
    builder.add_node("risk_agent", risk_agent_node)
    builder.add_node("process_agent", process_agent_node)
    builder.add_node("history_agent", history_agent_node)
    builder.add_node("harness", harness_node)
    builder.add_node("policy_gate", policy_gate_node)
    builder.add_node("hitl_node", hitl_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("execute_node", execute_node)
    builder.add_node("memory_update", memory_update_node)
    builder.add_node("constitutional", constitutional_node)

    builder.add_edge(START, "initialize_context")
    builder.add_edge("initialize_context", "calculation")
    builder.add_edge("calculation", "world_model")
    builder.add_edge("world_model", "router")

    builder.add_edge("router", "standards_agent")
    builder.add_edge("router", "risk_agent")
    builder.add_edge("router", "process_agent")
    builder.add_edge("router", "history_agent")

    builder.add_edge("standards_agent", "harness")
    builder.add_edge("risk_agent", "harness")
    builder.add_edge("process_agent", "harness")
    builder.add_edge("history_agent", "harness")

    builder.add_edge("harness", "policy_gate")
    builder.add_edge("planner_node", "execute_node")
    builder.add_edge("execute_node", "memory_update")
    builder.add_edge("memory_update", "constitutional")
    builder.add_edge("constitutional", END)

    return builder
