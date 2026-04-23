from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agents.decision import recommend_assembly
from agents.risk import evaluate_risk
from core.assembly import build_run_id, build_scenario_key, calculate_press_fit
from core.config import resolve_runtime_config
from core.history import compare_with_previous, count_runs, ensure_history_db, fetch_previous_run, fetch_recent_runs, save_run
from core.iso286 import list_supported_fits
from core.report import load_report, write_report
from harness.checks import run_checks
from multiagent import create_multiagent_service


class GeometryInput(BaseModel):
    nominal_diameter_mm: float = Field(..., gt=0)
    hub_outer_diameter_mm: float = Field(..., gt=0)
    contact_length_mm: float = Field(..., gt=0)
    fit_code: str
    part_id: str | None = Field(default=None, min_length=1)
    shaft_roughness_um: float = Field(1.6, ge=0)
    bore_roughness_um: float = Field(1.6, ge=0)


class MaterialInput(BaseModel):
    shaft_elastic_modulus_gpa: float = Field(..., gt=0)
    hub_elastic_modulus_gpa: float = Field(..., gt=0)
    shaft_poisson_ratio: float = Field(..., ge=0, lt=0.5)
    hub_poisson_ratio: float = Field(..., ge=0, lt=0.5)
    shaft_yield_strength_mpa: float = Field(..., gt=0)
    hub_yield_strength_mpa: float = Field(..., gt=0)
    shaft_thermal_expansion: float = Field(..., gt=0)
    hub_thermal_expansion: float = Field(..., gt=0)


class OperatingInput(BaseModel):
    transmitted_torque_nm: float = Field(..., ge=0)
    axial_force_n: float = Field(0.0, ge=0)
    working_temperature_c: float = 20.0
    assembly_temperature_c: float = 20.0
    desired_installation_clearance_um: float = Field(15.0, ge=0)
    press_friction_coefficient: float = Field(0.12, gt=0)
    service_friction_coefficient: float = Field(0.15, gt=0)
    equipment_force_limit_kn: float = Field(100.0, gt=0)


class AnalyzeRequest(BaseModel):
    geometry: GeometryInput
    materials: MaterialInput
    operating: OperatingInput
    config: dict[str, Any] | None = None


class MultiAgentRunRequest(BaseModel):
    geometry: GeometryInput
    materials: MaterialInput
    operating: OperatingInput
    config: dict[str, Any] | None = None
    thread_id: str | None = None


class MultiAgentResumeRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = ""
    config: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    config = resolve_runtime_config()
    ensure_history_db(config["history_db_path"])
    config["output_dir"].mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Assembly Optimizer API", version="1.0.0", lifespan=lifespan)


def _query_config(history_db_path: str | None = None, output_dir: str | None = None) -> dict:
    overrides: dict[str, str] = {}
    if history_db_path:
        overrides["history_db_path"] = history_db_path
    if output_dir:
        overrides["output_dir"] = output_dir
    return resolve_runtime_config(overrides)


@app.get("/health")
def health(
    history_db_path: str | None = Query(default=None),
    output_dir: str | None = Query(default=None),
) -> dict:
    config = _query_config(history_db_path=history_db_path, output_dir=output_dir)
    return {
        "ready": True,
        "history_db_path": str(config["history_db_path"]),
        "output_dir": str(config["output_dir"]),
        "run_count": count_runs(config["history_db_path"]),
        "supported_fits": list_supported_fits(),
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    payload = request.model_dump(mode="python")
    config = resolve_runtime_config(payload.get("config"))

    run_id = build_run_id(payload)
    scenario_key = build_scenario_key(payload)
    calc_result = calculate_press_fit(payload)
    risk_eval = evaluate_risk(calc_result)
    recommendation = recommend_assembly(calc_result, payload["operating"])
    harness_eval = run_checks(calc_result, risk_eval, recommendation, payload)
    previous_run = fetch_previous_run(config["history_db_path"], scenario_key=scenario_key)
    history_comparison = compare_with_previous(calc_result, previous_run)

    response_payload = {
        "run_id": run_id,
        "scenario_key": scenario_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_result": calc_result,
        "agent_recommendation": recommendation,
        "risk_eval": risk_eval,
        "harness_eval": harness_eval,
        "history_comparison": history_comparison,
        "alert_payload": {
            "level": risk_eval["level"],
            "reasons": risk_eval["reasons"],
            "primary_method": recommendation["primary_method"],
        },
    }

    report_paths = write_report(config["output_dir"], run_id, response_payload)
    response_payload["report_paths"] = report_paths

    save_run(
        config["history_db_path"],
        {
            "run_id": run_id,
            "created_at": response_payload["created_at"],
            "fit_code": calc_result["fit_code"],
            "primary_method": recommendation["primary_method"],
            "risk_level": risk_eval["level"],
            "scenario_key": scenario_key,
            "safety_factor": calc_result["stress"]["hub_safety_factor"],
            "torque_margin": calc_result["margins"]["torque_margin"],
            "press_force_kn": calc_result["capacities"]["press_force_kn"],
            "payload": response_payload,
        },
    )

    return response_payload


@app.get("/history")
def history(
    limit: int = Query(default=20, ge=1, le=100),
    history_db_path: str | None = Query(default=None),
) -> dict:
    config = _query_config(history_db_path=history_db_path)
    return {
        "items": fetch_recent_runs(config["history_db_path"], limit=limit),
    }


@app.get("/report/{run_id}")
def report(
    run_id: str,
    format: str = Query(default="json"),
    output_dir: str | None = Query(default=None),
) -> Any:
    config = _query_config(output_dir=output_dir)
    json_path, html_path = load_report(config["output_dir"], run_id)
    target = html_path if format == "html" else json_path
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Report not found for run_id={run_id}")
    if format == "html":
        return FileResponse(Path(target))
    return Path(target).read_text(encoding="utf-8")


@app.post("/multiagent/runs")
def multiagent_run(request: MultiAgentRunRequest) -> dict:
    payload = request.model_dump(mode="python", exclude_none=True)
    config_override = payload.pop("config", None)
    thread_id = payload.pop("thread_id", None)

    service = create_multiagent_service(config_override)
    try:
        result = service.invoke(payload, thread_id=thread_id)
    finally:
        service.close()

    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "interrupts": result.interrupts,
        "state": result.state,
    }


@app.post("/multiagent/runs/{thread_id}/resume")
def multiagent_resume(thread_id: str, request: MultiAgentResumeRequest) -> dict:
    service = create_multiagent_service(request.config)
    try:
        result = service.resume(thread_id=thread_id, decision=request.decision, comment=request.comment)
    finally:
        service.close()

    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "interrupts": result.interrupts,
        "state": result.state,
    }


@app.get("/multiagent/runs/{thread_id}")
def multiagent_state(thread_id: str, checkpoint_db_path: str | None = Query(default=None)) -> dict:
    overrides = {"checkpoint_db_path": checkpoint_db_path} if checkpoint_db_path else None
    service = create_multiagent_service(overrides)
    try:
        result = service.get_state(thread_id=thread_id)
    finally:
        service.close()

    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "state": result.state,
    }
