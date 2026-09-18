# Omi Plugins

This directory contains three distinct things:

## 1. `omi-plugin-sdk/` — shared SDK (models only)

`omi-plugin-sdk` is a small Python package that owns the Omi webhook
payload models (`omi_plugin_sdk.models`: `Conversation`, `TranscriptSegment`,
`ActionItem`, ...). It is intentionally models-only — auth/webhook/FastAPI
helpers were removed in July 2026.

SDK installation differs by consumer:

- **Legacy monolith** (`plugins/main.py`, `plugins/Dockerfile`): installs the
  SDK through `plugins/requirements.txt`, which pins `./omi-plugin-sdk`.
- **Independently deployed `omi-*-app/` services**: each has its own
  `requirements.txt` and installs the SDK by relative path (`../omi-plugin-sdk`)
  from within its own directory — not via `plugins/requirements.txt`.

## 2. `omi-*-app/` — independently deployed plugin services (28)

Each `omi-<name>-app/` directory (notion, github, slack, dropbox, whoop, ...)
is a self-contained FastAPI service with its own `main.py`, dependency file,
and deploy descriptor (Dockerfile / Procfile / railway.toml). They are
deployed independently of each other and of the monolith.

## 3. Legacy monolith — `main.py` + `Dockerfile`

`plugins/main.py` is the old all-in-one plugin API (`uvicorn main:app`, built
by `plugins/Dockerfile`, deployed manually via
`.github/workflows/gcp_plugins.yml` — workflow_dispatch only). It is kept
only because that Cloud Run deploy target still exists; do not add new
business logic to it. Its live routers: `basic/` (conversation_created,
mentor), `oauth/`, `zapier/`, `chatgpt/`, `subscription/`, `notifications/`,
`iq_rating/`, and `_multion/` (the last legacy integration, dormant).
`templates/` holds the setup-flow HTML it serves; `.env.template` lists its
environment variables.

- History and keep/retire decision: see `LEGACY_MONOLITH.md`.
- Migration audit (historical): see `PLUGIN_REFACTOR_AUDIT.md`.

## Other directories

- `models.py` — root compatibility shim over `omi_plugin_sdk.models`.
- `scripts/check_plugin_imports.py` — imports every `omi-*-app/main.py` and
  builds their OpenAPI schemas (contract check for isolated-root builds).
- `instructions/` — per-app instruction/asset content served to the mobile
  app.
- `hume-ai/`, `composio/`, `uber_call/` — standalone services hosted outside
  the monorepo's deploy workflows.
- `logos/`, `import/` — static assets and import tooling.
