# v1.0.0 - Production-Oriented Foundation

This release promotes the assembly optimizer from a private foundation snapshot to a documented production-oriented project.

## What Changed

- Polished the repository release surface to match the first project style:
  - English README
  - Chinese README
  - release notes
  - security notes
  - `.env.example`
- Updated FastAPI metadata to version `1.0.0`.
- Removed stale Langflow flow artifacts that still contained references to the gear SPC project.
- Kept the current supported Langflow entry focused on the multi-agent gateway flow.
- Documented the system boundary: deterministic physics and Harness own the facts; LangGraph agents organize specialist reasoning and HITL.
- Verified local test suite.
- Verified local smoke tests for deterministic and multi-agent API paths.

## Current Capabilities

- Deterministic press-fit physics:
  - ISO 286 curated fit support
  - effective interference
  - contact pressure
  - press-in force
  - holding torque
  - hub stress and safety factor
  - thermal assembly temperature
  - service-temperature interference drift
- LangGraph orchestration:
  - world model risk projection
  - MoE-style expert routing
  - standards, risk, process, and history specialists
  - Harness validation
  - policy gate
  - HITL approval
  - dispatch artifact publication
  - memory journal
  - constitutional audit
- Optional LLM specialist layer:
  - OpenAI-compatible live provider
  - offline mock provider
  - deterministic fallback when LLM is disabled or unavailable

## Validation

Local checks:

```text
pytest tests -q
10 passed
```

Smoke checks:

```text
smoke_test.ps1
smoke_test_multiagent.ps1
passed
```

Security hygiene:

- no `.env` tracked
- no SQLite databases tracked
- no generated reports tracked
- no API keys or GitHub tokens found in tracked files
- `data/` ignored except `data/.gitkeep`

## Known Limitations

- GitHub Actions workflow is not included yet because the current publishing token does not have `workflow` scope.
- The repository remains a decision-support backend, not a direct equipment controller.
- The ISO fit library is intentionally curated and should be expanded before deep production use.
- Real API authentication should be added before exposing the backend beyond localhost or a trusted network.

## 中文说明

这个版本把装配工艺参数优化系统整理成一个可以正式展示和继续迭代的工程项目。

主要变化：

- 补齐中英文 README、发布说明、安全说明和 `.env.example`。
- API 版本更新为 `1.0.0`。
- 移除残留的旧 Langflow 文件，避免出现其他项目的过期名称和端口配置。
- 保留当前正确的 multi-agent Langflow gateway flow。
- 明确工业边界：物理计算和 Harness 负责事实，agent 负责专家协作和决策包组织。
- 本地测试和 smoke test 均已通过。
