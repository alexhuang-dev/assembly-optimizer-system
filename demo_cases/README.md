# Assembly Optimizer Demo Cases

These JSON files are ready-made payloads for API, LangGraph, and Langflow demos.

Use them with:

- `POST /analyze`
- `POST /multiagent/runs`

## Recommended Demo Order

1. `01_baseline_normal_cold_press.json`
2. `02_warning_thermal_route.json`
3. `03_critical_short_length_overload.json`
4. `04_critical_service_interference_loss.json`
5. `05_warning_heavy_fit_high_stress.json`
6. `06_critical_fit_reselection.json`
7. `07_history_step1_baseline.json`
8. `08_history_step2_followup.json`

## Expected Behavior

| File | Purpose | Expected status | Expected method |
|---|---|---|---|
| `01_baseline_normal_cold_press.json` | Stable baseline | `overall_status=normal` / `risk=normal` | `cold_press` |
| `02_warning_thermal_route.json` | Press capacity pushes the process toward heating | `overall_status=normal` / `risk=warning` | `thermal_assembly` |
| `03_critical_short_length_overload.json` | Short contact length and high load | `overall_status=critical` / `risk=critical` | `thermal_assembly` |
| `04_critical_service_interference_loss.json` | Service temperature removes effective interference | `overall_status=critical` / `risk=critical` | `thermal_assembly` |
| `05_warning_heavy_fit_high_stress.json` | Heavy fit and thin hub stress warning | `overall_status=warning` / `risk=warning` | `thermal_assembly` |
| `06_critical_fit_reselection.json` | Cold press and moderate heating are both uncomfortable | `overall_status=critical` / `risk=critical` | `fit_reselection` |
| `07_history_step1_baseline.json` | First step of history comparison pair | `overall_status=warning` / `risk=warning` | `cold_press` |
| `08_history_step2_followup.json` | Same part worsens after baseline | `overall_status=critical` / `risk=critical` | `thermal_assembly` |

## History Demo

`07` and `08` are a pair:

- They use the same `part_id`.
- Run `07` first.
- Run `08` second.
- The second response should show `history_comparison.has_previous = true`.

To avoid old local history affecting a demo, pass a temporary config:

```json
{
  "history_db_path": "data/demo_history/history_pair.db",
  "output_dir": "data/demo_history/reports"
}
```
