# Security Notes

This project is an engineering decision-support system. It does not include real PLC, MES, ERP, SCADA, or actuator integration.

## Secrets

Do not commit:

- `.env`
- API keys
- model provider tokens
- gateway credentials
- production database files
- generated reports containing proprietary part data

The repository includes `.env.example` with empty placeholders only.

## Runtime Data

Generated runtime files live under `data/` by default and are ignored by Git except `data/.gitkeep`.

Ignored examples:

- SQLite history databases
- LangGraph checkpoint databases
- dispatch JSON artifacts
- generated report JSON/HTML files
- local temporary folders

## LLM Provider Keys

The optional LLM specialist layer reads keys from environment variables or request config. The API response exposes only `has_api_key` and header names, not the raw key.

Recommended local variables:

```text
ASSEMBLY_LLM_API_KEY=<provider-api-key>
ASSEMBLY_LLM_EXTRA_HEADERS={}
```

## Industrial Execution Boundary

The system emits JSON instruction packages for review. It does not directly command equipment.

Before connecting to production systems, add:

- authentication and authorization for API endpoints
- operator identity and approval logging
- network segmentation review
- command allowlists
- rate limits and replay protection
- plant-specific safety interlocks

## Reporting A Vulnerability

For now, keep security issues private and report them directly to the repository owner.
