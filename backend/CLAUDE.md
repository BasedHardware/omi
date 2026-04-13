# Backend (Python) — Developer Guide

Inherits all rules from the root `../CLAUDE.md`. This file adds backend-specific development guidance.

## Setup

Python 3.11 required (not 3.12+ — Dockerfile pins 3.11). Also needs FFmpeg, Opus (`opuslib`), Redis (optional).

```bash
cp .env.template .env          # Fill in required values (see .env.template for full list)
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

Key env vars: `OPENAI_API_KEY` (LLM calls — not `OPENAI_ADMIN_KEY` which is billing-only), `DEEPGRAM_API_KEY` (STT), `ENCRYPTION_SECRET` (required for tests), `REDIS_DB_HOST` (cache/rate-limiting, fail-open without it), `ADMIN_KEY` (local dev auth bypass via token `ADMIN_KEY<uid>`), `SERVICE_ACCOUNT_JSON` (Firestore/GCS credentials).

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
    stt/                  #   Speech-to-text (7 files): Deepgram streaming, VAD gating, speech profiles,
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
  diarizer/              # Subservice: speaker audio analysis (separate Docker, GPU/CUDA)
                          #   - POST /v1/diarization — speaker boundary detection (pyannote/speaker-diarization)
                          #   - POST /v1/embedding — speaker vector extraction (pyannote/embedding)
                          #   - POST /v2/embedding — alt speaker vectors (wespeaker-voxceleb-resnet34-LM)
  agent-proxy/           # Subservice: WebSocket bridge between mobile app and user's agent VM
                          #   - Firebase auth → Firestore VM lookup → GCE lifecycle (start/reset/health)
                          #   - Bidirectional message pump with keepalive (120s)
                          #   - Chat history injection (last 10 messages on first query)
                          #   - Optional AES-256-GCM message encryption
  modal/                 # Serverless GPU services (deployed on Modal)
                          #   - Speaker identification: matches segments to speech profiles (SpeechBrain, T4 GPU)
                          #   - VAD: voice activity detection (pyannote/voice-activity-detection)
                          #   - Cron: hourly notification job
  tests/unit/            # 50+ unit tests (no external service deps)
  tests/integration/     # Integration tests (need Redis, Firebase, API keys)
  test.sh                # Test runner — source of truth for CI
  test-preflight.sh      # Env validator (Python, pytest, packages, Redis)
```

## Import Rules

All imports at module top level — never inside functions. Strict hierarchy:

```
database/  →  utils/  →  routers/  →  main.py
```

Higher imports from lower, never reverse. Cross-importing between routers will break. Code paths are shared across backend, pusher, and diarizer — trace imports before assuming a change only affects one service.

## Database

**Firestore** (primary store): `from database._client import db` — sync client. Collection group queries need explicit indexes (will 500 with no useful error). Segments are encrypted at rest — direct Firestore reads return opaque blobs. Feature gating via user fields: e.g., translation requires `users/{uid}.language` non-empty — silently disabled if missing.

**Redis** (cache/rate-limiting/locks): `from database import redis_db` — **fail-open** (all errors caught and logged, requests proceed). Rate limiting via Lua scripts. `try_acquire_listen_lock(uid)` prevents duplicate WS connections.

## Auth

HTTP endpoints: `uid: str = Depends(get_current_user_uid)` from `utils.other.endpoints`.

WebSocket endpoints: use `WebSocketException(code=1008)`, **not** `HTTPException` — HTTPException exits ASGI without handshake, causing LB 5xx.

Rate limiting: `Depends(auth.with_rate_limit(get_current_user_uid, "policy_name"))` — policies in `utils/rate_limit_config.py`.

## Testing

```bash
bash test-preflight.sh   # Verify env
bash test.sh             # Run all tests (CI source of truth)
```

**New test files must be added to `test.sh`** or they won't run in CI.

Pre-mock heavy deps before importing the module under test. Use `patch.object(target_module, "func")` not string-based `patch("module.func")` — the string form silently patches the wrong reference if the function was already imported. When modules construct objects at import time, use lazy getters to avoid triggering heavy init in tests.

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
- **Lane 2 — Executors** (`utils/executors.py`): `critical_executor` (8 workers) and `storage_executor` (4 workers). Never ad-hoc `Thread`/`ThreadPoolExecutor`. Use `loop.run_in_executor(critical_executor, fn)`.
  - Deadlock rule: coordinators that fan out to `critical_executor` must run in default executor (`None`)
- **Lane 3 — Lint**: `python scripts/lint_async_blockers.py` catches `requests.*`, `time.sleep()`, `Thread().start()` in async code. Run before committing.
- **Shutdown**: `close_all_clients()` + `shutdown_executors()` wired in `main.py` and `pusher/main.py`.

## Common Gotchas

1. **Python 3.11 only** — no 3.12+ syntax (nested same-type quotes in f-strings break the Docker build)
2. **Never `time.sleep()` in async** — use `asyncio.sleep()`. For blocking work: `loop.run_in_executor(critical_executor, fn)`
3. **Sync `requests` in async is silent poison** — no error raised, just blocks the entire event loop. All connections freeze, health checks fail, HPA can't scale.
4. **Semaphores are event-loop-bound** — `http_client.py` handles this via `(loop_id, name)` keying. Don't create raw `asyncio.Semaphore` outside that module.
5. **Webhook timeout = 30s** — partner integrations depend on this window. Don't change `httpx.Timeout(30.0, connect=2.0)`.
6. **WAL files must be opus-encoded** — opus decoder silently errors on raw PCM but returns HTTP 200
7. **Firestore collection group queries** need explicit indexes — 500 with no useful error
8. **Mutable WebSocket state races** — snapshot `nonlocal` variables before spawning async work
9. **Silent fire-and-forget drops** — functions gating on connection state must log when dropping work
10. **Unbounded queues for user data** — `deque(maxlen=N)` silently drops audio; data-safety queues must stay unbounded
11. **`langdetect` unreliable on short text** — don't use on <20 chars or gate paid API calls on interim streaming text
12. **DG keepalive vs response timeout** — `keep_alive()` prevents DG's 10s idle timeout but NOT 1011 response timeout after all audio is processed. Post-session 1011 is benign.
