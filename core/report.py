from __future__ import annotations

import html
import json
from pathlib import Path


def _report_paths(output_dir: Path, run_id: str) -> tuple[Path, Path]:
    return output_dir / f"report_{run_id}.json", output_dir / f"report_{run_id}.html"


def write_report(output_dir: Path, run_id: str, payload: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, html_path = _report_paths(output_dir, run_id)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    calc_result = payload["analysis_result"]
    recommendation = payload["agent_recommendation"]
    risk_eval = payload["risk_eval"]
    harness_eval = payload["harness_eval"]

    html_path.write_text(
        f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Assembly Optimizer Report {html.escape(run_id)}</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 32px; color: #1f2937; background: #f8fafc; }}
    .card {{ background: white; border: 1px solid #dbe2ea; border-radius: 12px; padding: 20px; margin-bottom: 18px; }}
    h1, h2 {{ margin-top: 0; }}
    code {{ background: #eff6ff; padding: 2px 6px; border-radius: 6px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #e5e7eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Assembly Process Parameter Report</h1>
    <p>Run ID: <code>{html.escape(run_id)}</code></p>
    <p>Fit: <strong>{html.escape(calc_result["fit_code"])}</strong></p>
    <p>Overall status: <strong>{html.escape(calc_result["overall_status"])}</strong></p>
  </div>

  <div class="card">
    <h2>Core Metrics</h2>
    <table>
      <tr><th>Assembly contact pressure</th><td>{calc_result["contact_pressure_mpa"]["assembly"]} MPa</td></tr>
      <tr><th>Service contact pressure</th><td>{calc_result["contact_pressure_mpa"]["service"]} MPa</td></tr>
      <tr><th>Press force</th><td>{calc_result["capacities"]["press_force_kn"]} kN</td></tr>
      <tr><th>Holding torque</th><td>{calc_result["capacities"]["torque_capacity_nm"]} Nm</td></tr>
      <tr><th>Hub safety factor</th><td>{calc_result["stress"]["hub_safety_factor"]}</td></tr>
      <tr><th>Recommended hub temperature</th><td>{calc_result["thermal"]["recommended_hub_temperature_c"]} C</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>Recommendation</h2>
    <p><strong>{html.escape(recommendation["primary_method"])}</strong></p>
    <p>{html.escape(recommendation["summary"])}</p>
    <p>Alternative fit: {html.escape(str(recommendation["alternative_fit_code"]))}</p>
  </div>

  <div class="card">
    <h2>Risk</h2>
    <p>Level: <strong>{html.escape(risk_eval["level"])}</strong></p>
    <p>{html.escape(risk_eval["summary"])}</p>
  </div>

  <div class="card">
    <h2>Harness</h2>
    <p>Passed: <strong>{html.escape(str(harness_eval["passed"]))}</strong> | Score: {harness_eval["score"]}</p>
  </div>
</body>
</html>
""".strip(),
        encoding="utf-8",
    )
    return {
        "json_report_path": str(json_path),
        "html_report_path": str(html_path),
    }


def load_report(output_dir: Path, run_id: str) -> tuple[Path, Path]:
    json_path, html_path = _report_paths(output_dir, run_id)
    return json_path, html_path
