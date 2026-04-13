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

### Lane 1 — Async HTTP (`utils/http_client.py`)

Shared `httpx.AsyncClient` pools for all outbound HTTP. Each client has tuned timeouts and connection limits:

| Client | Get via | Timeout | Max conn | Semaphore | Use case |
|--------|---------|---------|----------|-----------|----------|
| webhook | `get_webhook_client()` | 30s (2s connect) | 64 | `get_webhook_semaphore()` (64) | Developer webhooks, integrations |
| maps | `get_maps_client()` | 10s (2s connect) | 8 | `get_maps_semaphore()` (8) | Google Maps geocoding |
| auth | `get_auth_client()` | 10s (2s connect) | 20 | `get_auth_semaphore()` (20) | OAuth token exchange |
| stt | `get_stt_client()` | 300s (5s connect) | 8 | `get_stt_semaphore()` (8) | Pre-recorded STT, ML services |

**Rules:**
- Never `requests.*` in async — it blocks the event loop for the entire request duration.
- Never `httpx.get()`/`httpx.post()` (sync httpx) in async — same problem. Always `await client.get()`.
- Always wrap calls in the matching semaphore: `async with get_webhook_semaphore(): ...` — prevents unbounded fan-out.
- Webhooks have per-URL circuit breakers (`get_webhook_circuit_breaker(url)`) — 5 failures → 30s open → half-open probe. Call `cb.record_success()` / `cb.record_failure()` after each request.
- Audio byte webhooks use latest-wins dropping (`latest_wins_start(uid)` / `latest_wins_check(uid, version)`) — if a newer audio chunk arrives before the old one is sent, the old one is silently dropped.
- Clients are lazy singletons — created on first use, closed at shutdown via `close_all_clients()`.

**Adding a new outbound HTTP target:**
1. Add a new `_foo_client` + `get_foo_client()` in `http_client.py` with appropriate timeouts and pool size.
2. Add a `get_foo_semaphore()` with a concurrency limit matching the pool size.
3. Add the client to `close_all_clients()`.
4. Use it: `async with get_foo_semaphore(): client = get_foo_client(); response = await client.get(...)`.

### Lane 2 — Executors (`utils/executors.py`)

Two shared `ThreadPoolExecutor` instances for offloading blocking work from the event loop:

| Executor | Workers | Use case |
|----------|---------|----------|
| `critical_executor` | 8 | process_conversation, memory extraction, action items, webhook delivery, vector ops |
| `storage_executor` | 4 | Audio precaching, GCS uploads/downloads |

**Rules:**
- Never create ad-hoc `Thread()` or `ThreadPoolExecutor()` — use the shared executors.
- Never `Thread().start()` + `.join()` — it blocks the calling thread (and the event loop if called from async).
- Use `loop.run_in_executor(critical_executor, fn)` for CPU/blocking work from async code.
- **Deadlock rule**: Functions submitted to `critical_executor` must NOT themselves submit to `critical_executor`. If a coordinator fans out to `critical_executor`, the coordinator must run in the default executor (`None`), not in `critical_executor`.
- Shutdown: `shutdown_executors()` is registered via `atexit` and also wired in `main.py`.

### Lane 3 — Lint (`scripts/lint_async_blockers.py`)

AST-based linter that catches blocking patterns inside async functions:
- `requests.get/post/...` → use `httpx.AsyncClient`
- `httpx.get/post/...` (sync) → use `httpx.AsyncClient`
- `time.sleep()` → use `asyncio.sleep()`
- `Thread().start()` → use `run_in_executor()`

```bash
python scripts/lint_async_blockers.py           # scan all backend code
python scripts/lint_async_blockers.py --strict   # non-zero exit on violations (CI mode)
python scripts/lint_async_blockers.py utils/     # scan specific directory
```

Run before committing any async code changes. Skips test files and `__pycache__`.

### Shutdown

Both `close_all_clients()` (Lane 1) and `shutdown_executors()` (Lane 2) are wired to FastAPI `shutdown` event in `main.py` and `pusher/main.py`. This ensures HTTP connection pools are drained and executor threads are stopped on graceful shutdown.

### Migration patterns (from sync to async)

When converting sync code to use this architecture:

1. **`requests.post(url, ...)` → `await client.post(url, ...)`**: Replace `import requests` with client getter. Wrap in semaphore. Add circuit breaker for external targets. The function must become `async def`.
2. **`Thread(target=fn).start()` + `thread.join()` → `await loop.run_in_executor(critical_executor, fn)`**: The executor handles thread lifecycle. No more orphaned threads on exception.
3. **`time.sleep(n)` → `await asyncio.sleep(n)`**: Or for blocking work that needs a real sleep: `await loop.run_in_executor(None, time.sleep, n)`.
4. **`asyncio.run(coro)` in sync endpoint → just `await coro`**: If the caller is already async, don't nest event loops. If the caller is sync (rare), `asyncio.run()` creates a temporary loop — the semaphore cache handles this via loop-ID keying.

### Learnings and pitfalls (from PR #6377)

- **Back pressure is essential**: Without semaphores, async HTTP fans out to all concurrent WebSocket connections simultaneously. 1000 users × 1 webhook each = 1000 simultaneous outbound connections. Semaphores cap this.
- **Circuit breakers prevent cascade failures**: A single slow/down webhook target can exhaust the connection pool. Per-URL circuit breakers isolate the damage — one broken webhook doesn't affect others.
- **Sync `requests` inside async is silent poison**: It doesn't raise an error — it just blocks the entire event loop thread for the duration of the HTTP call. All other connections freeze. Health checks fail. HPA can't scale. This is the #1 pattern to eliminate.
- **`asyncio.Semaphore` is event-loop-bound**: A semaphore created in one event loop can't be used in another. Sync FastAPI endpoints use `asyncio.run()` which creates a new loop each call. The semaphore cache in `http_client.py` handles this by keying on `(loop_id, name)`.
- **Coordinator deadlock is subtle**: If function A runs in `critical_executor` and submits function B to `critical_executor`, and all 8 workers are busy running function A instances, function B never starts → deadlock. Fix: run coordinators in default executor.
- **Webhook timeout must match previous behavior**: When migrating from `requests.post(timeout=30)` to httpx, the timeout must be preserved — partner integrations depend on the 30s window.

## Common Gotchas

1. **Python 3.11 only** — no 3.12+ syntax (nested same-type quotes in f-strings break the Docker build)
2. **Never `time.sleep()` in async handlers** — blocks event loop. Use `asyncio.sleep()`. For blocking work: `loop.run_in_executor(critical_executor, fn)`
3. **WAL files must be opus-encoded** — opus decoder silently errors on raw PCM but returns HTTP 200, so sync tests pass for the wrong reason
4. **Firestore collection group queries** need explicit indexes — 500 with no useful error
5. **Mutable WebSocket state races** — snapshot `nonlocal` variables before spawning async work
6. **Silent fire-and-forget drops** — functions gating on connection state must log when dropping work
7. **Unbounded queues for user data** — `deque(maxlen=N)` silently drops audio; data-safety queues must stay unbounded
8. **`langdetect` unreliable on short text** — don't use on <20 chars or gate paid API calls on interim streaming text
9. **Coordinator deadlock** — functions submitting to `critical_executor` must not themselves run in `critical_executor` — use default executor (`None`)
10. **DG keepalive vs response timeout** — `SafeDeepgramSocket` sends `keep_alive()` every 5s idle to prevent DG's 10s connection timeout. But DG 1011 "did not provide a response" is a server-side *response* timeout, not connection idle — `keep_alive()` cannot prevent it after all audio is processed. Post-session 1011 is benign; mid-stream 1011 is a real failure.
11. **Webhook timeout backward compatibility** — `httpx.Timeout(30.0, connect=2.0)` preserves the previous `requests.post(timeout=30)` behavior. Changing this will break partner integrations that rely on the 30s window.
