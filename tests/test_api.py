from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app


def _load_case(name: str) -> dict:
    path = Path(__file__).parent / "golden" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_api_round_trip(tmp_path: Path) -> None:
    payload = _load_case("case_001_nominal.json")
    payload["config"] = {
        "history_db_path": str(tmp_path / "history.db"),
        "output_dir": str(tmp_path / "reports"),
    }

    with TestClient(app) as client:
        response = client.post("/analyze", json=payload)
        assert response.status_code == 200

        body = response.json()
        assert body["analysis_result"]["fit_code"] == "H7/p6"
        assert body["harness_eval"]["passed"] is True

        history = client.get("/history", params={"history_db_path": str(tmp_path / "history.db")})
        assert history.status_code == 200
        assert len(history.json()["items"]) == 1

        report = client.get(
            f"/report/{body['run_id']}",
            params={"output_dir": str(tmp_path / "reports"), "format": "json"},
        )
        assert report.status_code == 200
        assert body["run_id"] in report.text


def test_health_respects_runtime_overrides(tmp_path: Path) -> None:
    history_db_path = tmp_path / "custom-history.db"
    output_dir = tmp_path / "custom-reports"

    with TestClient(app) as client:
        response = client.get(
            "/health",
            params={
                "history_db_path": str(history_db_path),
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["history_db_path"] == str(history_db_path)
    assert body["output_dir"] == str(output_dir)


def test_history_comparison_uses_matching_scenario_only(tmp_path: Path) -> None:
    same_scenario = _load_case("case_001_nominal.json")
    different_scenario = _load_case("case_002_thermal.json")
    config = {
        "history_db_path": str(tmp_path / "history.db"),
        "output_dir": str(tmp_path / "reports"),
    }
    same_scenario["config"] = dict(config)
    different_scenario["config"] = dict(config)

    with TestClient(app) as client:
        first = client.post("/analyze", json=same_scenario)
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["history_comparison"]["has_previous"] is False

        second = client.post("/analyze", json=different_scenario)
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["scenario_key"] != first_body["scenario_key"]
        assert second_body["history_comparison"]["has_previous"] is False

        third = client.post("/analyze", json=same_scenario)
        assert third.status_code == 200
        third_body = third.json()
        assert third_body["run_id"] != first_body["run_id"]
        assert third_body["history_comparison"]["has_previous"] is True
        assert third_body["history_comparison"]["previous_scenario_key"] == third_body["scenario_key"]


def test_multiagent_api_accepts_mock_llm_config(tmp_path: Path) -> None:
    payload = _load_case("case_001_nominal.json")
    payload["config"] = {
        "history_db_path": str(tmp_path / "history.db"),
        "output_dir": str(tmp_path / "reports"),
        "checkpoint_db_path": str(tmp_path / "checkpoints.db"),
        "operations_db_path": str(tmp_path / "operations.db"),
        "dispatch_dir": str(tmp_path / "dispatch"),
        "llm": {
            "enabled": True,
            "provider": "mock",
            "model": "industrial-mock",
        },
    }

    with TestClient(app) as client:
        response = client.post("/multiagent/runs", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["state"]["risk_result"]["source"] == "mock_plus_rules"
        assert body["state"]["process_result"]["source"] == "mock_plus_rules"
        assert body["state"]["constitutional_report"]["source"] == "mock_plus_rules"
