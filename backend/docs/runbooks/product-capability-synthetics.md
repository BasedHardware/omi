# Product-capability synthetics

Use this suite after backend/runtime incidents to verify user-facing capability paths, not only process health.

## Run locally

```bash
python3 backend/scripts/product_capability_synthetics.py
```

Default mode is safe for local agents:

- uses fake sentinel tokens only
- uses the LLM gateway fake provider
- uses hermetic e2e local fixtures for conversation processing and listen custom-STT
- does not read production user data
- does not require production provider credentials

To check a local or staging backend metadata surface too:

```bash
OMI_SYNTHETIC_BACKEND_URL=http://127.0.0.1:8000 \
  python3 backend/scripts/product_capability_synthetics.py
```

The Python backend health route traced from code is `GET /v1/health`.

For machine-readable output only:

```bash
python3 backend/scripts/product_capability_synthetics.py --json-only
```

## Statuses

- `PASS`: the check ran and the capability contract held.
- `FAIL`: the check ran and the capability contract broke.
- `SKIP_NO_CREDENTIALS`: reserved for future checks that require an explicit safe credential or token.
- `NOT_RUN`: prerequisites were not supplied or local fixture checks were disabled.

Any `FAIL` makes the suite exit non-zero. `NOT_RUN` is not a pass claim; read each check summary before using the report as release evidence.

## Current checks

- `backend_health`: optional HTTP probe for `GET /v1/health`.
- `llm_gateway_chat_fake_provider`: in-process service-auth and OpenAI-compatible chat smoke with a fake provider.
- `conversation_processing_local_fixture`: hermetic e2e conversation lifecycle path with deterministic action-item and memory fixture output.
- `mcp_oauth_metadata`: optional HTTP probe for MCP OAuth discovery metadata.
- `listen_protocol_local_fixture`: hermetic e2e custom-STT listen websocket protocol and persistence check.

## Secret safety

The runner redacts bearer tokens, Omi MCP/OAuth tokens, OpenAI-style keys, client secrets, generic API keys, and token fields from output. Do not pass production user identifiers, production bearer tokens, or provider credentials to this script.
