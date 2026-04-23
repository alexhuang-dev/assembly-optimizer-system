from __future__ import annotations

import json
from pathlib import Path

from multiagent import create_multiagent_service


def _load_case(name: str) -> dict:
    path = Path(__file__).parent / "golden" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _service(tmp_path: Path):
    return create_multiagent_service(
        {
            "history_db_path": str(tmp_path / "history.db"),
            "output_dir": str(tmp_path / "reports"),
            "checkpoint_db_path": str(tmp_path / "multiagent_checkpoints.db"),
            "operations_db_path": str(tmp_path / "multiagent_ops.db"),
            "dispatch_dir": str(tmp_path / "dispatch"),
        }
    )


def test_multiagent_low_risk_auto_dispatch(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        result = service.invoke(_load_case("case_001_nominal.json"))
    finally:
        service.close()

    assert result.status == "completed"
    assert result.state["policy_result"]["action"] == "auto_dispatch"
    assert result.state["execution_result"]["status"] == "published"
    assert Path(result.state["execution_result"]["dispatch_path"]).exists()
    assert result.state["constitutional_passed"] is True


def test_multiagent_high_risk_requires_hitl_then_resume(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        started = service.invoke(_load_case("case_002_thermal.json"))
        assert started.status == "waiting_for_approval"
        assert started.interrupts
        assert started.state["policy_result"]["action"] == "request_human_approval"

        resumed = service.resume(started.thread_id, decision="approve", comment="Maintenance planner approved thermal route")
    finally:
        service.close()

    assert resumed.status == "completed"
    assert resumed.state["approval_record"]["decision"] == "approve"
    assert resumed.state["execution_result"]["status"] == "published"
    assert resumed.state["constitutional_passed"] is True


def test_multiagent_mock_llm_enrichment(tmp_path: Path) -> None:
    service = create_multiagent_service(
        {
            "history_db_path": str(tmp_path / "history.db"),
            "output_dir": str(tmp_path / "reports"),
            "checkpoint_db_path": str(tmp_path / "multiagent_checkpoints.db"),
            "operations_db_path": str(tmp_path / "multiagent_ops.db"),
            "dispatch_dir": str(tmp_path / "dispatch"),
            "llm": {
                "enabled": True,
                "provider": "mock",
                "model": "industrial-mock",
            },
        }
    )
    try:
        result = service.invoke(_load_case("case_001_nominal.json"))
    finally:
        service.close()

    assert result.status == "completed"
    assert result.state["risk_result"]["source"] == "mock_plus_rules"
    assert result.state["risk_result"]["llm_assessment"] is not None
    assert result.state["process_result"]["source"] == "mock_plus_rules"
    assert result.state["process_result"]["llm_assessment"] is not None
    assert result.state["world_model_result"]["llm_forecast"] is not None
    assert result.state["constitutional_report"]["source"] == "mock_plus_rules"
