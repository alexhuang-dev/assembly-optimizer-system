from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.types import Command

from multiagent.graph import MultiAgentState, build_graph
from multiagent.runtime import (
    MultiAgentRuntimeConfig,
    build_thread_id,
    create_checkpointer,
    ensure_operations_db,
    resolve_multiagent_runtime_config,
)


@dataclass
class WorkflowResult:
    thread_id: str
    status: str
    state: dict[str, Any]
    interrupts: list[dict[str, Any]]


def _normalize_interrupts(result: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in result.get("__interrupt__", []):
        value = getattr(item, "value", item)
        if isinstance(value, dict):
            normalized.append(value)
        else:
            normalized.append({"value": value})
    return normalized


class AssemblyMultiAgentService:
    def __init__(self, runtime_config: MultiAgentRuntimeConfig):
        self.runtime_config = runtime_config
        ensure_operations_db(runtime_config.operations_db_path)
        self._checkpoint_connection, checkpointer = create_checkpointer(runtime_config.checkpoint_db_path)
        self._graph = build_graph(runtime_config).compile(checkpointer=checkpointer)

    def close(self) -> None:
        self._checkpoint_connection.close()

    def _graph_config(self, thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _initial_state(self, payload: dict[str, Any], thread_id: str) -> MultiAgentState:
        return {
            "request_payload": payload,
            "runtime_config": {
                "history_db_path": str(self.runtime_config.history_db_path),
                "output_dir": str(self.runtime_config.output_dir),
                "checkpoint_db_path": str(self.runtime_config.checkpoint_db_path),
                "operations_db_path": str(self.runtime_config.operations_db_path),
                "dispatch_dir": str(self.runtime_config.dispatch_dir),
                "llm": self.runtime_config.llm.public_dict(),
            },
            "thread_id": thread_id,
            "run_id": "",
            "scenario_key": "",
            "calculation_error": None,
            "assembly_result": None,
            "world_model_result": {},
            "selected_experts": [],
            "expert_confidence": {},
            "standards_result": None,
            "risk_result": None,
            "process_result": None,
            "history_result": None,
            "harness_passed": False,
            "harness_report": {},
            "risk_level": "high",
            "decision_package": {},
            "policy_result": {},
            "approval_record": None,
            "execution_plan": None,
            "execution_result": None,
            "xai_trace": [],
            "knowledge_updates": [],
            "audit_log": [],
            "constitutional_passed": False,
            "constitutional_report": {},
        }

    def _build_result(self, thread_id: str, invoke_result: dict[str, Any]) -> WorkflowResult:
        snapshot = self._graph.get_state(self._graph_config(thread_id))
        status = "waiting_for_approval" if snapshot.next else "completed"
        return WorkflowResult(
            thread_id=thread_id,
            status=status,
            state=dict(snapshot.values),
            interrupts=_normalize_interrupts(invoke_result),
        )

    def invoke(self, payload: dict[str, Any], thread_id: str | None = None) -> WorkflowResult:
        scenario_seed = payload["geometry"].get("fit_code", "unknown-fit")
        thread_id = thread_id or build_thread_id(scenario_seed)
        invoke_result = self._graph.invoke(self._initial_state(payload, thread_id), self._graph_config(thread_id))
        return self._build_result(thread_id, invoke_result)

    def resume(self, thread_id: str, decision: str, comment: str = "") -> WorkflowResult:
        invoke_result = self._graph.invoke(
            Command(resume={"decision": decision, "comment": comment}),
            self._graph_config(thread_id),
        )
        return self._build_result(thread_id, invoke_result)

    def get_state(self, thread_id: str) -> WorkflowResult:
        snapshot = self._graph.get_state(self._graph_config(thread_id))
        status = "waiting_for_approval" if snapshot.next else "completed"
        return WorkflowResult(
            thread_id=thread_id,
            status=status,
            state=dict(snapshot.values),
            interrupts=[],
        )


def create_multiagent_service(overrides: dict[str, Any] | None = None) -> AssemblyMultiAgentService:
    return AssemblyMultiAgentService(resolve_multiagent_runtime_config(overrides))
