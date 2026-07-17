# Backend (Python) — Developer Guide

Inherits all rules from the root `../AGENTS.md`. This file adds backend-specific development guidance.

## Setup

Python 3.11 is required (not 3.12+ — Dockerfile pins 3.11). Backend local dev pins the exact interpreter in `.python-version` and uses `uv` for reproducible dependency sync. Also needs FFmpeg, Opus (`opuslib`), Redis (optional).

```bash
cp .env.template .env          # Fill in required values (see .env.template for full list)
./scripts/sync-python-deps.sh  # creates .venv from .python-version + pylock.toml
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8080
```

**Env stages** (`OMI_ENV_STAGE`): `local` (emulator harness, `.env.local-dev`), `offline` (fake providers, `.env.offline`), `dev` (remote dev GCP, `.env.dev`), `prod` (reference only, `.env.prod`). `load_backend_env()` loads the stage file then `backend/.env` overrides. Templates: `backend/.env.*.template`. Harness: `PROVIDER_MODE=offline make dev-up` or `OMI_ENV_STAGE=offline`.

When intentionally changing backend Python dependencies, edit the relevant `requirements*.txt` input file and refresh the lock:

```bash
./scripts/update-python-lock.sh
```

By default, the lock refresh preserves already-locked package versions so unrelated transitive upgrades do not sneak into infrastructure changes. Set `PYLOCK_UPGRADE=1` only when intentionally refreshing dependency versions.

Key env vars: `OPENAI_API_KEY` (LLM calls — not `OPENAI_ADMIN_KEY` which is billing-only), `HOSTED_PARAKEET_API_URL` and `MODULATE_API_KEY` (serving STT), `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` (local harness chat/realtime via Rust desktop backend), `ENCRYPTION_SECRET` (required for tests), `REDIS_DB_HOST` (cache/rate-limiting, fail-open without it), `ADMIN_KEY` (local dev auth bypass via token `ADMIN_KEY<uid>`), `SERVICE_ACCOUNT_JSON` (Firestore/GCS credentials).

Chat SSE deadlines: `AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS` (default `25`), `AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS` (default `20`), `AGENT_STREAM_MAX_DURATION_SECONDS` (default `150`), and `AGENT_STREAM_CANCEL_GRACE_SECONDS` (default `2`) bound silent setup/producer work and keep valid long tool calls observable. Values must be positive.

LLM gateway resilience: `OMI_LLM_GATEWAY_CONNECT_TIMEOUT_SECONDS` (default `3`), `OMI_LLM_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS` (default `15`), `OMI_LLM_GATEWAY_CIRCUIT_FAILURE_THRESHOLD` (default `2`), and `OMI_LLM_GATEWAY_CIRCUIT_COOLDOWN_SECONDS` (default `30`) bound the optional gateway hop. Gateway-first callers use the shared process-local circuit and may fall back only before stream output. Never restore a production `OMI_LLM_GATEWAY_URL` static IP: the backend deployment derives it after `verify-llm-gateway-serving.py` validates the ready Kubernetes workload, ingress/ILB attachment, and Cloud Run VPC smoke route.

## Directory Structure

```
backend/
  main.py                 # FastAPI entry, middleware, 45+ router registrations
  models/                 # Pydantic request/response schemas (22 files: conversation, memory, app, chat, user subscription, etc.)
  database/               # All persistence — 25+ domain modules
    _client.py            #   Firestore singleton + document_id_from_seed utility
    redis_db.py           #   Cache, rate limiting (Lua scripts), pub/sub, locks, geolocation
    helpers.py            #   Decorators: data protection levels, encryption/decryption on read/write
    conversations.py      #   Conversations with encrypted segments, photos, processing status
    memories.py           #   User facts/learnings with categories, visibility, encryption
    users.py              #   Profiles, subscriptions, people/contacts, private cloud sync settings
    apps.py               #   Custom apps/personas, reviews, payment (Stripe), usage history
    action_items.py       #   Tasks with due dates, completion status
    vector_db.py          #   Pinecone integration for semantic search
    knowledge_graph.py    #   Neo4j entity relationships
    fair_use.py           #   Usage limits and soft-cap tracking
    ...                   #   + folders, goals, phone_calls, daily_summaries, trends, imports, etc.
  routers/                # FastAPI route handlers — 42 files, one per feature domain
    transcribe.py         #   /v4/listen WebSocket — core audio streaming + transcription pipeline (2900 LOC)
    chat.py               #   /v2/messages — AI chat with tool use, voice messages, file uploads
    conversations.py      #   /v1/conversations — CRUD, merge, search, action items, photos
    memories.py           #   /v3/memories — CRUD, visibility, semantic search
    apps.py               #   App marketplace, personas, reviews, payment (2000 LOC)
    sync.py               #   /v1/sync — mobile client data sync (1500 LOC)
    auth.py               #   Google/Apple OAuth callbacks, session management
    users.py              #   Profile, subscription, settings (1200 LOC)
    task_integrations.py  #   Todoist, Microsoft Tasks sync (1200 LOC)
    mcp.py, mcp_sse.py    #   Model Context Protocol server endpoints
    ...                   #   + action_items, goals, knowledge_graph, payment, integrations, etc.
  utils/                  # Business logic — 60+ files (never import from routers/)
    llm/                  #   LLM orchestration (14 files): chat processing, conversation post-processing,
                          #   memory extraction, persona management, proactive notifications, goal tracking,
                          #   app generation, fair-use classification, usage tracking
      clients.py          #     Model instances: OpenAI (gpt-4.1-mini, o4-mini), Anthropic (claude-sonnet-4-6),
                          #     OpenRouter (gemini-flash), with prompt caching and usage callbacks
    stt/                  #   Speech-to-text (7 files): Parakeet/Modulate streaming, VAD gating, speech profiles,
                          #   pre-recorded batch transcription, speaker embeddings
    conversations/        #   Conversation lifecycle (6 files): ingestion, memory extraction, action items,
                          #   merge, post-processing, search
    retrieval/            #   RAG pipeline (25+ files): agentic RAG via Claude with 18 tool types —
                          #   action items, calendar, Gmail, Apple Health, conversations, memories,
                          #   screen activity, files, Perplexity web search, notifications, etc.
    other/                #   Storage (GCS), auth dependencies, timeout middleware, Hume emotion detection
    log_sanitizer.py      #   sanitize() / sanitize_pii() — required for all logging
    encryption.py         #   AES-256-GCM per-user encryption (HKDF-SHA256 key derivation)
    fair_use.py           #   Rolling speech-hour tracking via Redis minute buckets, soft-cap enforcement
    prompts.py            #   LLM prompt templates for memory extraction, categorization, etc.
    translation.py        #   Multi-language translation coordination
    speaker_identification.py  # Speaker diarization + person matching against speech profiles
  pusher/                 # Subservice: real-time data distribution hub (separate Docker)
                          #   - Receives audio + transcripts from backend-listen via binary WebSocket protocol
                          #   - Routes transcripts to integrations/webhooks in 1s batches
                          #   - Streams audio to ML services and developer webhooks (4s accumulation)
                          #   - Runs LLM-powered conversation analysis (memories, action items, insights)
                          #   - Batches + uploads audio to private cloud storage (60s batches, 3 retries)
                          #   - Queues speaker sample extraction (120s age minimum)
                          #   - 5 concurrent background tasks per WebSocket connection
  llm_gateway/            # Subservice: internal Omi-managed LLM auto-lane gateway
  diarizer/              # Subservice: speaker audio analysis (separate Docker, GPU/CUDA)
                          #   - POST /v1/diarization — speaker boundary detection (pyannote/speaker-diarization)
                          #   - POST /v1/embedding — speaker vector extraction (pyannote/embedding)
                          #   - POST /v2/embedding — alt speaker vectors (wespeaker-voxceleb-resnet34-LM)
  agent-proxy/           # Subservice: WebSocket bridge between mobile app and user's agent VM
                          #   - Firebase auth → Firestore VM lookup → GCE lifecycle (start/reset/health)
                          #   - Bidirectional message pump with keepalive (120s)
                          #   - Chat history injection (last 10 messages on first query)
                          #   - Optional AES-256-GCM message encryption
  nllb_translation/      # Subservice: self-hosted NLLB translation (separate Docker, GPU/CUDA)
                          #   - POST /v1/translate — batch sentence translation (NLLB-200 + CTranslate2)
                          #   - Prometheus metrics at /metrics, health at /health, readiness at /ready
                          #   - Fallback to Google Cloud Translation V3 when NLLB is unavailable
  modal/                 # Serverless GPU services (deployed on Modal) + Cloud Run Jobs
                          #   - Speaker identification: matches segments to speech profiles (SpeechBrain, T4 GPU)
                          #   - VAD: voice activity detection (pyannote/voice-activity-detection)
                          #   - notifications-job: hourly push notifications + X sync (Cloud Run Job)
                          #   - memory-maintenance-job: canonical ST→LT maintenance (Cloud Run Job)
  tests/unit/            # 50+ unit tests (no external service deps)
  tests/integration/     # Integration tests (need Redis, Firebase, API keys)
  scripts/run-unit-ci.sh # Full CI unit-test contract
  test.sh                # Selected-suite executor used by the shared contract
  test-preflight.sh      # Env validator (Python, pytest, packages, Redis)
```

## Service Map

```
Shared: Firestore, Redis

backend (main.py)
  ├── ws ──► pusher (pusher/)
  ├── ──────► diarizer (diarizer/)
  ├── ──────► vad (modal/)
  ├── ──────► parakeet (parakeet/)
  ├── ──────► modulate (managed API)
  ├── ──────► nllb-translation (nllb_translation/)
  └── ──────► llm-gateway (llm_gateway/main.py)

pusher
  ├── ──────► diarizer (diarizer/)
  └── ──────► parakeet / modulate (STT)

agent-proxy (agent-proxy/main.py)
  └── ws ──► user agent VM (private IP, port 8080)

backend-sync (main.py, Cloud Run)
  ├── ──────► Cloud Tasks queue `sync-jobs` ──► POST /v2/sync-jobs/run (OIDC, same service; fresh lane)
  ├── ──────► Cloud Tasks queue `sync-backfill` ──► backend-sync-backfill POST /v2/sync-jobs/run (OIDC; historical lane)
  ├── ──────► Cloud Tasks queue `audio-merge` ──► POST /v2/audio-merge-jobs/run (OIDC, same service)
  └── ──────► Cloud Tasks queue `account-deletion` ──► POST /v1/users/account-deletion-wipes/run (OIDC, same service)

notifications-job (modal/job.py)  [cron]
memory-maintenance-job (modal/memory_maintenance_job.py)  [cron]
agent-vm-reaper (backend/charts/agent-vm-reaper)  [cron]
```

Helm charts: `backend/charts/{agent-proxy,agent-vm-reaper,backend-listen,backend-secrets,diarizer,llm-gateway,monitoring,nllb-translation,parakeet,pusher,vad}/`.

Serving STT provider/surface policy and canonical model order are owned exclusively by `config/stt_provider_policy.py`; deployment values are validated against it.

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings (`utils/stt/speaker_embedding.py`). Calls vad for voice activity detection and speaker identification (`utils/stt/vad.py`, `utils/stt/speech_profile.py`). Calls Parakeet or Modulate for STT (`HOSTED_PARAKEET_API_URL`, `MODULATE_API_KEY`, `utils/stt/streaming.py`). Calls NLLB translation when `HOSTED_TRANSLATION_API_URL` is set and NLLB is selected (`utils/translation.py`).
- **hosted MCP OAuth** (`routers/mcp_sse.py`) — Provider-neutral OAuth for `/v1/mcp/sse`. Configure public or confidential clients with `MCP_OAUTH_CLIENTS_JSON`; allowlist the exact connector callback URI from the provider. The temporary `MCP_OAUTH_CHATGPT_*` envs still define the legacy confidential ChatGPT test client, and `MCP_OAUTH_PUBLIC_*` can expose a no-secret PKCE public client. Also set `MCP_AUTHORIZATION_SERVER_URL`, optional `MCP_RESOURCE_URL`, and token TTL env vars.
- **llm-gateway** (`llm_gateway/main.py`) — Internal FastAPI service for Omi-managed LLM auto lanes. Called by backend with service auth for `omi:auto:*` chat-completions routes; not exposed to clients.
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Calls diarizer and the configured Parakeet/Modulate STT provider for speaker sample extraction (`utils/speaker_identification.py` → `utils/speaker_sample.py`).
- **agent-proxy** (`agent-proxy/main.py`) — GKE. WebSocket proxy at `wss://agent.omi.me/v1/agent/ws`. Validates Firebase ID token, looks up `agentVm` in Firestore, proxies bidirectionally to VM's `ws://<ip>:8080/ws`.
- **diarizer** (`diarizer/main.py`) — GPU. Speaker embeddings at `/v2/embedding`. Called by backend and pusher (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — GPU. `/v1/vad` and `/v1/speaker-identification`. Called by backend only.
- **parakeet** (`parakeet/`) — GPU STT service for streaming and pre-recorded transcription. Called by backend when `HOSTED_PARAKEET_API_URL` is set and Parakeet is selected.
- **modulate** — Managed STT provider for configured languages. Called by backend when `MODULATE_API_KEY` is configured and Modulate is selected.
- **nllb-translation** (`nllb_translation/`) — GPU translation service. Called by backend when `HOSTED_TRANSLATION_API_URL` is set and NLLB is selected.
- **backend-sync** (`main.py`, same image as backend) — Cloud Run admission service for `/v2/sync-local-files`. The server classifies whole batches: recordings no more than six hours old enter `sync-jobs` (fresh), while older or untrusted batches enter `sync-backfill` and the scale-to-zero **backend-sync-backfill** worker. Fresh keeps its bounded inline fallback; backfill never falls into fresh/inline capacity. Backfill defaults to one in-flight job per UID, four processed speech hours per UID/day, 555 processed speech hours globally/day, a 30-day lookback, and four queue workers. Live fair-use reads only `realtime + sync_fresh`; `sync_backfill` is separately metered. A 45-day Firestore content ledger protects transcription and usage side effects across job expiry and re-upload. Audio playback merges (`/v1/sync/audio/*`) follow the same pattern via queue `audio-merge` building 30-day MP3 artifacts under `playback/` (`AUDIO_MERGE_DISPATCH_MODE`) — per-part files plus one dense per-conversation `conversation.mp3` whose spans manifest + audio_files fingerprint are stamped on the conversation doc (`conversation_audio`); a fingerprint mismatch after late chunks re-enqueues the build. In production, account deletion requires `ACCOUNT_DELETION_DISPATCH_MODE=cloud_tasks` and complete Cloud Tasks bindings to enqueue opaque job IDs to queue `account-deletion`, which posts `/v1/users/account-deletion-wipes/run`; startup rejects inline or incomplete configuration, reconciliation only re-dispatches tasks so the OIDC handler is the sole wipe executor, and the post-deploy queue-drain window accepts the former sync OIDC audience only for legacy UID payloads. API success is returned only after the deletion marker is persisted and the wipe task is durably enqueued.
- **notifications-job** (`modal/job.py`) — Cron job, reads Firestore/Redis, sends push notifications and runs X connector sync. It has no canonical maintenance flags or Typesense secrets; its deploy workflow removes only those retired bindings and preserves unrelated notification/X-sync env.
- **memory-maintenance-job** (`modal/memory_maintenance_job.py`) — Cloud Run Job and sole host for canonical ST→LT maintenance (TTL → consolidation → promotion). Manual deploy via `.github/workflows/gcp_memory_maintenance_job.yml`; auto-dev on push to `main` via `gcp_memory_maintenance_job_auto_dev.yml`. Enablement is a multi-var contract (`MEMORY_MODE`, `MEMORY_ENABLED_USERS`, cron/fast-track/consolidation flags) enforced by `backend/scripts/validate-backend-runtime-env.py`; prod stays `MEMORY_MODE=off` until Gate 3.
- **monitoring** (`backend/charts/monitoring/`) — Prometheus, Grafana, Loki, Alloy, alerts, and HPA metric adapters for backend services.
- **agent-vm-reaper** (`backend/charts/agent-vm-reaper/`) — CronJob that deletes stale `omi-agent-*` GCE VMs left by desktop agent sandboxes.
- **backend-secrets** (`backend/charts/backend-secrets/`) — ExternalSecret and SecretStore resources that sync backend runtime secrets into GKE namespaces.

Backend runtime env contract: keep `backend/deploy/runtime_env.yaml` aligned with GKE Helm values and Cloud Run runtime env; run `backend/scripts/pre-deploy-check.sh` after backend runtime env or deploy workflow changes. The `llm_gateway` manifest section owns the release, ingress, and static-address identity; a reserved address alone is never an endpoint contract. Gateway-mode promotion requires the control-plane gate plus `probe-llm-gateway-from-cloud-run.sh` before Cloud Run revisions are created.

Firestore index boundary: backend deploy workflows run `reconcile_firestore_indexes.py --check-only` against `RUNTIME_GCP_PROJECT_ID` in an isolated approved-source job using dedicated read-only credentials. Manual deploys must keep `firestore.indexes.json` identical to `main` and deploy the exact checked candidate SHA. A failed gate writes and locally revalidates a short-lived, redacted create-only proposal before upload; backend deployment must never mutate the serving schema.

Keep this map up to date. When adding, removing, or changing inter-service calls, update this section. If a PR changes audio streaming, transcription, conversation lifecycle, speaker identification, or the listen/pusher WebSocket protocol — update `docs/doc/developer/backend/listen_pusher_pipeline.mdx` in the same PR.

## Import Rules

All imports at module top level — never inside functions. Strict hierarchy:

```
database/  →  utils/  →  routers/  →  main.py
```

Higher imports from lower, never reverse. Cross-importing between routers will break. Code paths are shared across backend, pusher, and diarizer — trace imports before assuming a change only affects one service.

Runtime-selected providers must keep model-token parsing and required environment bindings in a pure `config/` module. Read mutable env at the call boundary rather than snapshotting it during import, and construct SDK clients lazily. For pre-recorded STT, `config/prerecorded_stt.py` is the single source of truth used by both `utils/stt/pre_recorded.py` and the deploy manifest validator; adding a provider or model token requires updating that contract and its runtime/deploy tests together.

## Database

**Firestore** (primary store): use `get_firestore_client()` from `database._client` at call time, and add optional keyword-only `firestore_client` parameters on converted database helpers so tests can inject fake clients. `db` remains a legacy lazy compatibility proxy only; do not use it in new code. Never construct Firestore clients at import time. Collection group queries need explicit indexes (will 500 with no useful error). Segments are encrypted at rest — direct Firestore reads return opaque blobs. Feature gating via user fields: e.g., translation requires `users/{uid}.language` non-empty — silently disabled if missing.

**Redis** (cache/rate-limiting/locks): `from database import redis_db` — **fail-open** (all errors caught and logged, requests proceed). Rate limiting via Lua scripts. `try_acquire_listen_lock(uid)` prevents duplicate WS connections.

## Auth

HTTP endpoints: `uid: str = Depends(get_current_user_uid)` from `utils.other.endpoints`.

WebSocket endpoints: use `WebSocketException(code=1008)`, **not** `HTTPException` — HTTPException exits ASGI without handshake, causing LB 5xx.

Rate limiting: `Depends(auth.with_rate_limit(get_current_user_uid, "policy_name"))` — policies in `utils/rate_limit_config.py`.

## Logging Security

Never log raw sensitive data. Use `sanitize()` and `sanitize_pii()` from `utils.log_sanitizer`.

- `sanitize()` for `response.text`, API responses, error bodies.
- `sanitize_pii()` for names, emails, user text.
- Keep UIDs, IPs, status codes visible for debugging.
- Never put raw `response.text` in exception messages.

## Error Composition & Memory

- **Composition errors** — step helpers raise a typed error caught once at the composition boundary. Do not add assigned-call `isinstance(...): return` flow control; `.github/scripts/check_isinstance_return_ratchet.py` ratchets existing occurrences.
- **Memory management** — `del` byte arrays after processing, `.clear()` dicts/lists holding data.

## Testing

```bash
bash test-preflight.sh   # Verify env
bash test.sh             # Run all tests (CI source of truth)
npm run test:listen-lifecycle:emulator  # Real Firestore transaction contention for listen cleanup/content
```

**Tests are selector-driven.** `scripts/run-unit-ci.sh` is the full GitHub Actions contract: it selects changed-file tests on PRs, runs preflight and type-checking, then invokes `test.sh`; main CI uses it with `--all`. Local pre-push intentionally keeps its own 40-file cap and runs changed test files when a broad selector exceeds that budget. Do not make the hook call the CI runner: bounded push latency protects the normal development loop. Local `test.sh` runs the selected set from `tests/unit/`, `tests/services/`, and `tests/routers/` via `scripts/select_backend_unit_tests.py`. Tests that need live services (Redis, Firebase, real API keys) go in `tests/integration/`, which is not part of selector auto-discovery; note in the PR how you ran them.

**Runtime image contracts.** `runtime_images.json` registers each deployed Python image, its Dockerfile, build context, entrypoints, and deployment workflows. Run `make runtime-image-source-closure` to verify final-stage first-party source closure and that every registered deployment workflow smokes its declared Dockerfile; it is the fast pre-push and CI gate. `make runtime-image-smoke SERVICE=pusher` builds one image, checks every reachable third-party module is installed offline, then imports the registered isolated entrypoint. PR CI builds every registry-selected CPU image; deployment workflows build, smoke, then publish. GPU images use the same dependency-presence probe after their deployment build but defer full import until model initialization is lazy. Do not add a hand-maintained image-layout test or workflow mapping; add the service to the registry instead.

**OpenAPI contract runner** — OpenAPI contract checks use `backend/scripts/openapi_runner.sh`, which syncs the pinned `backend/openapi-requirements.txt` runner env and prewarms `tiktoken`; CI and `scripts/pre-push` must use this same path.

**Released app-client compatibility** — `docs/api-reference/app-client-openapi.json` is a compatibility boundary, not only a generated snapshot. PR CI compares it directionally with the merge-base via `scripts/check_app_client_openapi_compatibility.py`: requests accepted by the released contract must remain accepted, and new responses must remain decodable by released clients. Additive optional request fields and response fields are allowed. Do not allowlist breaking changes; retain a deprecated boundary field/parameter or version the endpoint.

**Test isolation / import purity** — never mutate `sys.modules` at module scope in tests; production modules must not construct clients or do IO at import time. Sanctioned seams: `monkeypatch.setattr` on a lazy-held singleton, FastAPI `app.dependency_overrides`. Enforced by `python scripts/check_module_stub_pollution.py` and `python scripts/scan_import_time_side_effects.py`. Full prescription: `backend/docs/test_isolation.md`.

**Firestore transaction fakes** — a fake at this service boundary must enforce its ordering and constraint semantics. Use `tests.unit.fixtures.strict_firestore_transaction.StrictFirestore` for transaction tests that need document-reference reads plus `set`/`update`: it rejects reads after the first write, the production rule that #9739's lenient fake missed. If an incident requires queries, deletes, retry, or contention behavior, first cover it with the Firestore emulator; extend the fixture only for a proven hermetic guard.

Pre-mock heavy deps before importing the module under test. Use `patch.object(target_module, "func")` not string-based `patch("module.func")` — the string form silently patches the wrong reference if the function was already imported. When modules construct objects at import time, use lazy getters to avoid triggering heavy init in tests.

### Memory continuity gauntlet gates

Do not confuse these gates — a green live gauntlet does **not** prove hermetic
pipeline invariants, and hermetic tests do **not** prove deployed-backend continuity.

| Gate | What it covers | What it does **not** cover |
| --- | --- | --- |
| **Hermetic pipeline E2E** (`testing/e2e/test_canonical_memory_pipeline.py`) | capture→consolidate→promote→read, archive excluded from default reads, surface default-access matrix, projection fail-closed without legacy bleed | Deployed revision identity, prod IAM/index deltas, live LLM consolidation |
| **Gauntlet `--self-check`** | Required files, `canonical_memory_pipeline` workflow registration, suite/nonce wiring in `memory-continuity-gauntlet.py` | Any memory write or HTTP probe |
| **Live gauntlet** (`memory-continuity-gauntlet.sh` with `ADMIN_KEY` + reachable backend) | Structural `/v3/memories` probes per suite on a running backend | Full Gate 2 synthetic matrix or Gate 3 prod activation |
| **Gate 2 dev-cloud proof** (`v3_dev_cloud_proof.py` + deployed branch revision) | Multi-user synthetic matrix, indexes, IAM, auth, rollback on dev-cloud | Local hermetic fakes; not production activation |
| **Gate 3 production proof** (`docs/rollout/memory-v3-proof-order.md`) | Prod-specific deltas after Gate 2 GO + independent review | Substitute for hermetic pipeline E2E or gauntlet self-check |

CI runs `python3 backend/scripts/memory-continuity-gauntlet.py --self-check` only.
Live suites record `NOT_RUN` when credentials/backend are unavailable — never fake `GO`.

## Self-Testing a Change (run the real path)

A passing unit test is not the same as exercising the endpoint. Before putting a change in a PR:

1. **Serve locally**: `./scripts/dev-serve.sh` (per-worktree port) or `uvicorn main:app --port 8080`. No GCP credentials? Use the offline harness — `PROVIDER_MODE=offline make dev-up` from the repo root (fake providers, no external services).
2. **Authenticate without a client**: set `ADMIN_KEY` in `.env`, then call endpoints as any uid with `Authorization: Bearer <ADMIN_KEY><uid>` (the key concatenated with the uid).
3. **Hit the changed endpoints** with curl and read the server logs — verify the behavior changed as intended, not just that the route returns 200.
4. **Record the commands and output** in the PR description (root `AGENTS.md` → Definition of Done).

## Formatting

```bash
black --line-length 120 --skip-string-normalization <files>
```

`--skip-string-normalization` is critical — without it, black flips all quotes and diffs explode.

## Async I/O (3-Lane Architecture)

Never block the event loop — it freezes health checks, HPA scaling, and all concurrent connections.

- **Lane 1 — Async HTTP** (`utils/http_client.py`): Shared `httpx.AsyncClient` pools with semaphore-bounded concurrency. Never `requests.*` or sync `httpx.*` in async code.
  - Clients: `get_webhook_client()`, `get_maps_client()`, `get_auth_client()`, `get_stt_client()`
  - Semaphores: always wrap calls — `async with get_webhook_semaphore(): await client.post(...)`
  - Circuit breakers: `get_webhook_circuit_breaker(url)` for external targets — call `cb.record_success()`/`cb.record_failure()`
  - Lifecycle: lazy singletons, closed at shutdown via `close_all_clients()`
- **Lane 2 — Executors** (`utils/executors.py`): 7 purpose-specific thread pools. Never ad-hoc `Thread`/`ThreadPoolExecutor`.
  - **Async dispatch rules** (choose the right primitive):
    - `await run_blocking(executor, fn)` — sync/CPU-bound work where the caller needs the result before continuing.
    - `start_background_task(coro, name=...)` — async fire-and-forget work (pipelines, post-processing). Tracks the task, logs exceptions, cleans up references. Never use bare `asyncio.create_task()` for production background work.
    - `submit_with_context(executor, fn)` — short sync fire-and-forget only (precache, small cleanups). Never for pipelines that hold a slot >10s.
  - **Long-running pipelines must be async coordinators.** Each blocking step uses `await run_blocking(pool, fn)`, borrowing a thread only for that step. Never hold a thread pool slot across await points or for >60s.
  - **Pool assignment** (match work type to pool):
    - `critical_executor` (8w) — auth gates only: `_verify_ws_auth`, `validate_byok_websocket`, `check_rate_limit`, `is_hard_restricted`, session/code Redis ops in `auth.py`
    - `db_executor` (24w) — Firestore/Redis CRUD, vector DB queries
    - `llm_executor` (6w) — LLM API calls (`get_llm().invoke()`, `get_app_result()`, persona generation, KG rebuild with cap 4)
    - `stripe_executor` (4w) — Stripe API calls
    - `sync_executor` (16w) — sync endpoint pipeline work, parent calls that fan out to storage_executor
    - `postprocess_executor` (24w) — post-conversation processing, coordinator functions
    - `storage_executor` (128w) — GCS uploads/downloads, audio chunk I/O (fan-out gated by semaphores: 32 global chunks, 8 per-call window, 4 concurrent precache files)
  - **Deadlock prevention — 4 rules:**
    1. **Worker threads are leaf operations only.** Never `.result()` on another pool from inside a worker thread. If pool A thread submits to pool B and calls `.result()`, and vice versa, both pools deadlock.
    2. **Orchestration stays in async code.** The async handler coordinates via `await run_blocking(pool, fn)` — sequentially or with `asyncio.gather`. The event loop never blocks, pools stay independent.
    3. **Coordinators must not share a pool with their children.** If a function fans out work to `storage_executor` and waits on `.result()`, that function must run on a different pool (e.g., `postprocess_executor`), never on `storage_executor` itself — otherwise all threads become coordinators and children can't run.
    4. **Long-running coordinators need async orchestration or sized pools.** If a coordinator holds a thread pool slot for >10s, it must either use async coordination (`asyncio.create_task` + `await run_blocking(...)`) or run on a pool sized for `hold_time × peak_concurrency`. Prefer async coordination for any coordinator with hold time >60s — thread slots occupied by sleeping coordinators waste memory and starve other work.
  - **Audit command:** `grep -rn '\.result()' --include="*.py" | grep -v tests/ | grep -v __pycache__` — every hit must be a leaf operation or a coordinator on a different pool from its children.
  - **Pool observability:** `get_executor_metrics()` returns active count, queue depth, and utilization % for all pools. `log_executor_health()` runs every 60s, warns when any pool exceeds 70% utilization. Wired in `main.py` startup event.
- **Lane 3 — Lint**: `python scripts/scan_async_blockers.py --dirs routers utils` catches blocking calls in async routes and helpers.
  The scanner follows direct calls through module-local sync helpers transitively, so moving blocking I/O behind a wrapper is not an escape; offload the helper at the async boundary with `run_blocking`.
  Run from `backend/` before committing. From the repository root, use `python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils`.
- **Shutdown**: `close_all_clients()` + `shutdown_executors()` wired in `main.py` and `pusher/main.py`.

## WebSocket Concurrency (Long-Lived Connections)

WS handlers in `transcribe.py` and `pusher.py` manage 5-11 concurrent tasks per connection. Use `utils/async_tasks.py` utilities — never raw `asyncio.gather()` or bare `await receive_task`.

- **Supervision**: `supervise_tasks()` wraps `asyncio.wait(FIRST_COMPLETED)` — detects both client disconnect and bg task crashes immediately. Classify tasks as finite (can complete during session) or lifetime (completion = session ending).
- **Drain**: `drain_tasks()` cancels remaining bg tasks with bounded timeout, force-cancels stragglers via `asyncio.wait` (not `asyncio.gather`, which hangs if a task suppresses CancelledError).
- **Fan-out**: `gather_safe()` replaces `asyncio.gather(return_exceptions=True)` — semaphore-bounded concurrency, per-item exception logging, typed `GatherResult[T]` return.
- **Interruptible sleep**: `wait_for_event(event, seconds)` replaces `asyncio.sleep()` in polling loops — wakes instantly on disconnect via per-connection `asyncio.Event`. Never bare `asyncio.sleep()` in WS task loops.
- **Receive timeouts**: every `websocket.receive()` must be wrapped in `asyncio.wait_for(..., timeout=WS_RECEIVE_TIMEOUT)`.
- **Gauge placement**: `GAUGE.inc()` inside `try` body, `GAUGE.dec()` in `finally`. Init `bg_main_tasks = []` before `try`.
- **Task naming**: `create_named_task()` for WS-scoped tasks (tracked in task_set for supervise/drain). Use `start_background_task()` from `utils/executors.py` for fire-and-forget work that outlives the handler.
- **Prometheus labels**: static low-cardinality only (e.g. "pusher", "listen") — never uid/session_id.
- **Module-level dicts**: add TTL-based eviction or cap size — they grow forever otherwise.

## Common Gotchas

1. **Python 3.11 only** — no 3.12+ syntax (nested same-type quotes in f-strings break the Docker build)
2. **Never `time.sleep()` in async** — use `asyncio.sleep()`. For blocking work: `await run_blocking(executor, fn)` with the appropriate pool
3. **Sync `requests` in async is silent poison** — no error raised, just blocks the entire event loop. All connections freeze, health checks fail, HPA can't scale.
4. **Semaphores are event-loop-bound** — `http_client.py` handles this via `(loop_id, name)` keying. Don't create raw `asyncio.Semaphore` outside that module.
5. **Webhook timeout = 30s** — partner integrations depend on this window. Don't change `httpx.Timeout(30.0, connect=2.0)`.
6. **Sync WAL codec is filename-driven** — `decode_files_to_wav` routes on the filename codec token (`utils/sync/files.py`): `_pcm16_`/`_pcm8_` → PCM decoder, otherwise opus. PCM is fully supported; the real gotcha is a mislabeled/missing codec token silently decodes as the wrong codec (garbage audio, still HTTP 200) — name the codec correctly in the filename
7. **Firestore collection group queries** need explicit indexes — 500 with no useful error
8. **Mutable WebSocket state races** — snapshot `nonlocal` variables before spawning async work
9. **Silent fire-and-forget drops** — functions gating on connection state must log when dropping work
10. **New fallbacks** — call `utils.observability.fallback.record_fallback` (see `docs/agents/fallback-telemetry.md`); do not invent a new `*_fallback_total` Counter
11. **Queue caps for user data** — `private_cloud_queue` uses `deque(maxlen=20)` to prevent OOM kills (sized for 30 conns/pod); dropping oldest chunk is better than killing the pod and losing ALL data for ALL users
12. **`langdetect` unreliable on short text** — don't use on <20 chars or gate paid API calls on interim streaming text
13. **DG keepalive vs response timeout** — `keep_alive()` prevents DG's 10s idle timeout but NOT 1011 response timeout after all audio is processed. Post-session 1011 is benign.
