# Plugin Refactor Audit for #8559

Date: 2026-06-29

## Summary

- Added neutral Python SDK at `plugins/omi-plugin-sdk` (`omi-plugin-sdk`, import `omi_plugin_sdk`).
- Canonical Omi webhook models now live in `omi_plugin_sdk.models`.
- `backend/models/structured.py` imports the SDK when it is available and keeps a backend-local compatibility fallback for backend images that copy only `backend/`.
- Legacy monolith is kept because `.github/workflows/gcp_plugins.yml` still builds `plugins/Dockerfile` and starts `plugins/main.py`.

## Shared Model Surfaces

| Surface | Before | After |
| --- | --- | --- |
| `Structured`, `ActionItem`, `Event` | Duplicated in backend, root `plugins/models.py`, Dropbox, and future-use app model blocks | Single implementation in `plugins/omi-plugin-sdk/src/omi_plugin_sdk/models.py`; backend/root/plugin files re-export |
| Dropbox webhook parsing | Local `ActionItem`/`Structured` definitions drifted from backend | `plugins/omi-dropbox-app/models.py` imports SDK `Conversation`, so `action_items` parse via SDK |
| Root plugin monolith models | Local webhook model implementation | Compatibility imports from SDK plus root-only proactive notification models |

## Deploy and Dependency Matrix

| Target | Entrypoint | Deploy descriptor | SDK dependency mode | Notes |
| --- | --- | --- | --- | --- |
| Legacy monolith | `plugins/main.py` | `.github/workflows/gcp_plugins.yml` -> `plugins/Dockerfile`; Datadog variant exists | `plugins/requirements.txt` installs `./omi-plugin-sdk`; root Dockerfiles copy SDK before install | Active deploy evidence found; kept as legacy |
| `omi-dropbox-app` | `main.py` | `Procfile`, `railway.toml` | `requirements.txt` installs `../omi-plugin-sdk` | Migrated webhook parsing and `EndpointResponse`; requires repo checkout with SDK sibling |
| `omi-linear-app` | `main.py` | `Procfile`, `railway.toml` | `requirements.txt` installs `../omi-plugin-sdk` | Future-use Omi webhook models are SDK re-exports; business models remain local |
| `omi-hive-app` | `main.py` | `Procfile`, `railway.toml` | `requirements.txt` installs `../omi-plugin-sdk` | Future-use Omi webhook models are SDK re-exports; business models remain local |
| `omi-shopify-app` | `main.py` | `Procfile`, `railway.toml` | `requirements.txt` installs `../omi-plugin-sdk` | Future-use Omi webhook models are SDK re-exports; business models remain local |
| `omi-shipbob-app` | `main.py` | `Procfile`, `railway.toml` | `requirements.txt` installs `../omi-plugin-sdk` | Future-use Omi webhook models are SDK re-exports; business models remain local |
| Other `plugins/omi-*-app` Python apps | `main.py` where present | `Procfile`/`railway.toml`/Dockerfile as listed in app folders | No SDK dependency added unless the app imports SDK-backed models | No duplicated `Structured` implementation found |

## Storage, Auth, and Webhook Helpers

- Added SDK primitives in `auth.py`, `webhook.py`, and `fastapi.py`.
- These are intentionally small. They do not change OAuth token storage, Redis keys, volume paths, or app-specific business logic.

## Dependency Risk

The migrated Railway/Nixpacks apps use `../omi-plugin-sdk`. This is valid when builds run from a repository checkout where `plugins/omi-plugin-sdk` is a sibling of the app directory. If any service is configured with an isolated root directory that excludes sibling folders, dependency installation will fail. No destructive migration or deletion was done until that deploy mode is verified.

Backend images are different: `backend/Dockerfile` copies only `backend/`, so `backend/models/structured.py` keeps a fallback compatibility implementation when `omi_plugin_sdk` is not installed. Local full-repo runs import the SDK implementation.

## Legacy Monolith Decision

Keep `plugins/main.py`, `plugins/_mem0`, `plugins/_multion`, `plugins/Dockerfile`, and `plugins/Dockerfile.datadog`.

Deletion is blocked by active deploy evidence: `.github/workflows/gcp_plugins.yml` builds `plugins/Dockerfile`, which copies `plugins/` and starts `uvicorn main:app`. See `plugins/LEGACY_MONOLITH.md`.
