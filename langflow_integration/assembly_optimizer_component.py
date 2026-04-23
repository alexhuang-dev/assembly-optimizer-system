from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from lfx.custom.custom_component.component import Component
from lfx.io import MultilineInput, Output, StrInput
from lfx.schema.data import Data


class AssemblyOptimizerComponent(Component):
    display_name = "Assembly Optimizer Gateway"
    description = "Call the assembly optimizer backend for classic analysis or industrial multi-agent orchestration."
    icon = "activity"
    documentation = "http://127.0.0.1:8010/docs"

    inputs = [
        StrInput(
            name="operation",
            display_name="Operation",
            info="Supported values: analyze, multiagent_run, multiagent_resume, multiagent_state",
            value="multiagent_run",
            required=True,
        ),
        MultilineInput(
            name="request_json",
            display_name="Request JSON",
            info="Paste the full analyze/multi-agent request JSON here. Leave empty if you provide a file path.",
            value="",
            required=False,
            input_types=["Message"],
        ),
        StrInput(
            name="request_file_path",
            display_name="Request File Path",
            info="Optional local JSON file path. Used when Request JSON is empty.",
            value="",
            required=False,
        ),
        StrInput(
            name="thread_id",
            display_name="Thread ID",
            info="Optional for multiagent_run. Required for multiagent_resume and multiagent_state.",
            value="",
            required=False,
        ),
        StrInput(
            name="approval_decision",
            display_name="Approval Decision",
            info="Used for multiagent_resume. Supported values: approve, reject",
            value="approve",
            required=False,
        ),
        StrInput(
            name="approval_comment",
            display_name="Approval Comment",
            info="Optional comment for multiagent_resume.",
            value="",
            required=False,
        ),
        MultilineInput(
            name="config_json",
            display_name="Config JSON",
            info="Optional runtime config overrides merged into the backend request config field.",
            value="",
            required=False,
        ),
        StrInput(
            name="llm_enabled",
            display_name="LLM Enabled",
            info="Set true to enable LLM specialists. Supported values: true, false.",
            value="false",
            required=True,
        ),
        StrInput(
            name="llm_provider",
            display_name="LLM Provider",
            info="Supported values: mock, openai_compatible",
            value="openai_compatible",
            required=True,
        ),
        StrInput(
            name="llm_model",
            display_name="LLM Model",
            info="Model name for the LLM specialist layer.",
            value="",
            required=False,
        ),
        StrInput(
            name="llm_api_base_url",
            display_name="LLM API Base URL",
            info="Base URL for the LLM provider, for example https://api.openai.com/v1",
            value="https://api.openai.com/v1",
            required=False,
        ),
        StrInput(
            name="llm_api_key",
            display_name="LLM API Key",
            info="Optional LLM API key. Stored in the request config.llm.api_key field.",
            value="",
            required=False,
        ),
        StrInput(
            name="llm_temperature",
            display_name="LLM Temperature",
            info="Temperature for specialist reasoning.",
            value="0.0",
            required=True,
        ),
        StrInput(
            name="llm_max_tokens",
            display_name="LLM Max Tokens",
            info="Max tokens per specialist call.",
            value="700",
            required=True,
        ),
        MultilineInput(
            name="headers_json",
            display_name="Headers JSON",
            info="Optional extra HTTP headers. Example: {\"X-API-Key\": \"demo-key\"}",
            value="",
            required=False,
        ),
        StrInput(
            name="api_key",
            display_name="API Key",
            info="Optional convenience field. When set, it is added to the configured header below.",
            value="",
            required=False,
        ),
        StrInput(
            name="api_key_header",
            display_name="API Key Header",
            info="Header name for the API Key field. Defaults to X-API-Key. Use Authorization if your gateway expects Bearer tokens.",
            value="X-API-Key",
            required=True,
        ),
        StrInput(
            name="api_url",
            display_name="API URL",
            value="http://127.0.0.1:8010",
            required=True,
        ),
        StrInput(
            name="timeout_seconds",
            display_name="Timeout Seconds",
            value="300",
            required=True,
        ),
    ]

    outputs = [
        Output(display_name="Gateway Response", name="analysis", type_=Data, method="build_analysis"),
        Output(display_name="Core Metrics", name="core_metrics", type_=Data, method="build_core_metrics"),
        Output(display_name="Recommendation", name="recommendation", type_=Data, method="build_recommendation"),
        Output(display_name="Risk", name="risk", type_=Data, method="build_risk"),
        Output(display_name="Harness", name="harness", type_=Data, method="build_harness"),
        Output(display_name="History Comparison", name="history_comparison", type_=Data, method="build_history"),
        Output(display_name="Report Paths", name="report_paths", type_=Data, method="build_report_paths"),
        Output(display_name="Multi-Agent Summary", name="multiagent_summary", type_=Data, method="build_multiagent_summary"),
        Output(display_name="Multi-Agent State", name="multiagent_state", type_=Data, method="build_multiagent_state"),
        Output(display_name="Decision Package", name="decision_package", type_=Data, method="build_decision_package"),
        Output(display_name="Policy", name="policy", type_=Data, method="build_policy"),
        Output(display_name="Execution", name="execution", type_=Data, method="build_execution"),
        Output(display_name="Interrupts", name="interrupts", type_=Data, method="build_interrupts"),
    ]

    _response_cache: dict[str, Any] | None = None

    def _load_request(self) -> dict[str, Any]:
        raw_text = str(self.request_json or "").strip()
        if raw_text:
            return json.loads(raw_text)

        file_path = str(self.request_file_path or "").strip()
        if not file_path:
            return {}

        path = Path(file_path)
        if not path.exists():
            raise ValueError("Request File Path does not exist.")

        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                return json.loads(path.read_text(encoding=encoding))
            except UnicodeDecodeError:
                continue

        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))

    def _parse_json(self, raw: str) -> dict[str, Any] | None:
        text = str(raw or "").strip()
        if not text:
            return None
        return json.loads(text)

    def _normalized_operation(self) -> str:
        operation = str(self.operation or "analyze").strip().lower()
        supported = {"analyze", "multiagent_run", "multiagent_resume", "multiagent_state"}
        if operation not in supported:
            raise ValueError(f"Unsupported operation '{operation}'. Supported: {sorted(supported)}")
        return operation

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        parsed = self._parse_json(self.headers_json)
        if parsed:
            headers.update({str(key): str(value) for key, value in parsed.items()})

        api_key = str(self.api_key or "").strip()
        api_key_header = str(self.api_key_header or "X-API-Key").strip()
        if api_key:
            if api_key_header.lower() == "authorization" and not api_key.lower().startswith("bearer "):
                headers[api_key_header] = f"Bearer {api_key}"
            else:
                headers[api_key_header] = api_key
        return headers

    def _prepare_request_body(self, payload: dict[str, Any]) -> dict[str, Any]:
        config_override = self._parse_json(self.config_json)
        config_override = dict(config_override or {})

        llm_enabled = str(self.llm_enabled or "false").strip().lower() in {"1", "true", "yes", "on", "enabled"}
        llm_payload = {
            "enabled": llm_enabled,
            "provider": str(self.llm_provider or "").strip(),
            "model": str(self.llm_model or "").strip(),
            "api_base_url": str(self.llm_api_base_url or "").strip(),
            "api_key": str(self.llm_api_key or "").strip(),
            "temperature": float(self.llm_temperature or 0.0),
            "max_tokens": int(float(self.llm_max_tokens or 700)),
        }
        if llm_enabled or llm_payload["model"] or llm_payload["api_key"]:
            merged_llm = dict(config_override.get("llm") or {})
            merged_llm.update({key: value for key, value in llm_payload.items() if value != ""})
            config_override["llm"] = merged_llm

        if not config_override:
            return payload

        merged = dict(payload.get("config") or {})
        merged.update(config_override)
        payload = dict(payload)
        payload["config"] = merged
        return payload

    def _call_api(self) -> dict[str, Any]:
        if self._response_cache is not None:
            return self._response_cache

        operation = self._normalized_operation()
        payload = self._prepare_request_body(self._load_request())
        timeout_seconds = float(self.timeout_seconds or 300)
        base_url = str(self.api_url).rstrip("/")
        headers = self._headers()

        if operation == "analyze":
            response = requests.post(
                f"{base_url}/analyze",
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
        elif operation == "multiagent_run":
            thread_id = str(self.thread_id or "").strip()
            if thread_id:
                payload = dict(payload)
                payload["thread_id"] = thread_id
            response = requests.post(
                f"{base_url}/multiagent/runs",
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
        elif operation == "multiagent_resume":
            thread_id = str(self.thread_id or "").strip()
            if not thread_id:
                raise ValueError("Thread ID is required for multiagent_resume.")
            body = {
                "decision": str(self.approval_decision or "approve").strip().lower(),
                "comment": str(self.approval_comment or ""),
            }
            config_override = self._parse_json(self.config_json)
            if config_override:
                body["config"] = config_override
            response = requests.post(
                f"{base_url}/multiagent/runs/{thread_id}/resume",
                json=body,
                headers=headers,
                timeout=timeout_seconds,
            )
        else:
            thread_id = str(self.thread_id or "").strip()
            if not thread_id:
                raise ValueError("Thread ID is required for multiagent_state.")
            params = {}
            config_override = self._parse_json(self.config_json)
            if config_override and config_override.get("checkpoint_db_path"):
                params["checkpoint_db_path"] = config_override["checkpoint_db_path"]
            response = requests.get(
                f"{base_url}/multiagent/runs/{thread_id}",
                params=params,
                headers=headers,
                timeout=timeout_seconds,
            )

        response.raise_for_status()
        self._response_cache = response.json()
        self.status = self._response_cache
        return self._response_cache

    def _analysis_payload(self) -> dict[str, Any]:
        payload = self._call_api()
        return payload.get("analysis_result") or payload.get("state", {}).get("assembly_result") or {}

    def _state_payload(self) -> dict[str, Any]:
        payload = self._call_api()
        return payload.get("state") or {}

    def build_analysis(self) -> Data:
        return Data(data=self._call_api())

    def build_core_metrics(self) -> Data:
        analysis = self._analysis_payload()
        return Data(
            data={
                "fit_code": analysis.get("fit_code"),
                "overall_status": analysis.get("overall_status"),
                "contact_pressure_mpa": analysis.get("contact_pressure_mpa"),
                "capacities": analysis.get("capacities"),
                "stress": analysis.get("stress"),
                "thermal": analysis.get("thermal"),
                "margins": analysis.get("margins"),
            }
        )

    def build_recommendation(self) -> Data:
        payload = self._call_api()
        recommendation = payload.get("agent_recommendation")
        if recommendation is None:
            recommendation = self._state_payload().get("process_result")
        return Data(data={"recommendation": recommendation})

    def build_risk(self) -> Data:
        payload = self._call_api()
        risk_eval = payload.get("risk_eval")
        if risk_eval is None:
            risk_eval = self._state_payload().get("risk_result")
        return Data(data={"risk_eval": risk_eval})

    def build_harness(self) -> Data:
        payload = self._call_api()
        harness_eval = payload.get("harness_eval")
        if harness_eval is None:
            state = self._state_payload()
            harness_eval = {
                "passed": state.get("harness_passed"),
                "report": state.get("harness_report"),
            }
        return Data(data={"harness_eval": harness_eval})

    def build_history(self) -> Data:
        payload = self._call_api()
        history_comparison = payload.get("history_comparison")
        if history_comparison is None:
            history_comparison = self._state_payload().get("history_result")
        return Data(data={"history_comparison": history_comparison})

    def build_report_paths(self) -> Data:
        payload = self._call_api()
        report_paths = payload.get("report_paths")
        if report_paths is None:
            report_paths = self._state_payload().get("report_paths")
        return Data(data={"report_paths": report_paths})

    def build_multiagent_summary(self) -> Data:
        payload = self._call_api()
        state = payload.get("state") or {}
        return Data(
            data={
                "thread_id": payload.get("thread_id"),
                "status": payload.get("status"),
                "scenario_key": state.get("scenario_key"),
                "run_id": state.get("run_id"),
                "risk_level": state.get("risk_level"),
                "policy_result": state.get("policy_result"),
                "constitutional_passed": state.get("constitutional_passed"),
            }
        )

    def build_multiagent_state(self) -> Data:
        return Data(data={"state": self._state_payload()})

    def build_decision_package(self) -> Data:
        return Data(data={"decision_package": self._state_payload().get("decision_package")})

    def build_policy(self) -> Data:
        return Data(data={"policy_result": self._state_payload().get("policy_result")})

    def build_execution(self) -> Data:
        return Data(data={"execution_result": self._state_payload().get("execution_result")})

    def build_interrupts(self) -> Data:
        return Data(data={"interrupts": self._call_api().get("interrupts", [])})
