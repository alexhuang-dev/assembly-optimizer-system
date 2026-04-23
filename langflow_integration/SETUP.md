# Langflow Setup For Assembly Optimizer

Langflow is an optional visual demo layer. The backend remains the source of truth for physical calculation, Harness validation, policy gating, HITL, and dispatch artifacts.

## Recommended Import

Use:

```text
langflow_integration/assembly_optimizer_multiagent_import_ready_flow.json
```

This import-ready flow is wired for:

- `POST /analyze`
- `POST /multiagent/runs`
- `POST /multiagent/runs/{thread_id}/resume`
- `GET /multiagent/runs/{thread_id}`

## Optional Custom Component

The source component is:

```text
langflow_integration/assembly_optimizer_component.py
```

Paste it into Langflow custom components, or place it in the directory your Langflow instance uses for local components.

## Start Backend

```powershell
powershell -ExecutionPolicy Bypass -File .\start_stack.ps1
```

Default backend:

```text
http://127.0.0.1:8010
```

## Supported Operations

- `analyze`
  - Calls `POST /analyze`
  - Use for deterministic press-fit analysis.
- `multiagent_run`
  - Calls `POST /multiagent/runs`
  - Starts LangGraph orchestration and may return a HITL interrupt package.
- `multiagent_resume`
  - Calls `POST /multiagent/runs/{thread_id}/resume`
  - Use after a reviewer approves or rejects a paused run.
- `multiagent_state`
  - Calls `GET /multiagent/runs/{thread_id}`
  - Reads the latest stored graph state.

## Demo Sequence

1. Start the backend.
2. Import `assembly_optimizer_multiagent_import_ready_flow.json`.
3. Set `Operation = multiagent_run`.
4. Paste a higher-risk payload such as `tests/golden/case_002_thermal.json`.
5. Run the flow.
6. If the output status is `waiting_for_approval`, copy `thread_id`.
7. Set `Operation = multiagent_resume`.
8. Paste the `thread_id`.
9. Set `Approval Decision = approve` or `reject`.
10. Run again to continue from the checkpoint.

## Optional LLM Settings

The gateway exposes these fields:

- `LLM Enabled`
- `LLM Provider`
- `LLM Model`
- `LLM API Base URL`
- `LLM API Key`
- `LLM Temperature`
- `LLM Max Tokens`

Leave LLM disabled for deterministic offline demos. Use `provider = mock` for offline specialist enrichment.

Example config:

```json
{
  "llm": {
    "enabled": true,
    "provider": "mock",
    "model": "industrial-mock"
  }
}
```

For a live OpenAI-compatible endpoint, provide your own local secret. Do not commit keys:

```json
{
  "llm": {
    "enabled": true,
    "provider": "openai_compatible",
    "model": "<model-name>",
    "api_base_url": "https://api.openai.com/v1",
    "api_key": "<provider-api-key>",
    "temperature": 0.0,
    "max_tokens": 700
  }
}
```

## Gateway Headers

If you put the backend behind a local proxy, auth gateway, or cloud tunnel, fill:

- `API Key`
- `API Key Header`
- `Headers JSON`

Examples:

```json
{"X-API-Key": "local-demo-key"}
```

or:

```text
API Key Header = Authorization
API Key = <gateway-token>
```

The component will send:

```text
Authorization: Bearer <gateway-token>
```

## What Langflow Should Do

- Collect or transform user-friendly input.
- Call the backend.
- Narrate engineering results.
- Present recommendation, risk, report paths, and HITL package.
- Let a reviewer decide whether to resume a paused run.

## What Langflow Should Not Do

- Recompute contact pressure or safety factor.
- Override Harness failures with free-form text.
- Bypass the backend policy gate.
- Dispatch anything directly to equipment.
