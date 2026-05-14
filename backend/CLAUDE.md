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
- **Lane 2 — Executors** (`utils/executors.py`): 7 purpose-specific thread pools. Never ad-hoc `Thread`/`ThreadPoolExecutor`.
  - **Async dispatch rules** (choose the right primitive):
    - `await run_blocking(executor, fn)` — sync/CPU-bound work where the caller needs the result before continuing.
    - `start_background_task(coro, name=...)` — async fire-and-forget work (pipelines, post-processing). Tracks the task, logs exceptions, cleans up references. Never use bare `asyncio.create_task()` for production background work.
    - `submit_with_context(executor, fn)` — short sync fire-and-forget only (precache, small cleanups). Never for pipelines that hold a slot >10s.
  - **Long-running pipelines must be async coordinators.** Each blocking step uses `await run_blocking(pool, fn)`, borrowing a thread only for that step. Never hold a thread pool slot across await points or for >60s.
  - **Pool assignment** (match work type to pool):
    - `critical_executor` (8w) — auth gates only: `_verify_ws_auth`, `validate_byok_websocket`, `check_rate_limit`, `is_hard_restricted`, session/code Redis ops in `auth.py`
    - `db_executor` (16w) — Firestore/Redis CRUD, vector DB queries
    - `llm_executor` (4w) — LLM API calls (`get_llm().invoke()`, `get_app_result()`, persona generation)
    - `stripe_executor` (4w) — Stripe API calls
    - `sync_executor` (12w) — sync endpoint pipeline work
    - `postprocess_executor` (8w) — post-conversation processing, coordinator functions
    - `storage_executor` (32w) — GCS uploads/downloads, audio chunk I/O
  - **Deadlock prevention — 4 rules:**
    1. **Worker threads are leaf operations only.** Never `.result()` on another pool from inside a worker thread. If pool A thread submits to pool B and calls `.result()`, and vice versa, both pools deadlock.
    2. **Orchestration stays in async code.** The async handler coordinates via `await run_blocking(pool, fn)` — sequentially or with `asyncio.gather`. The event loop never blocks, pools stay independent.
    3. **Coordinators must not share a pool with their children.** If a function fans out work to `storage_executor` and waits on `.result()`, that function must run on a different pool (e.g., `postprocess_executor`), never on `storage_executor` itself — otherwise all threads become coordinators and children can't run.
    4. **Long-running coordinators need async orchestration or sized pools.** If a coordinator holds a thread pool slot for >10s, it must either use async coordination (`asyncio.create_task` + `await run_blocking(...)`) or run on a pool sized for `hold_time × peak_concurrency`. Prefer async coordination for any coordinator with hold time >60s — thread slots occupied by sleeping coordinators waste memory and starve other work.
  - **Audit command:** `grep -rn '\.result()' --include="*.py" | grep -v tests/ | grep -v __pycache__` — every hit must be a leaf operation or a coordinator on a different pool from its children.
  - **Pool observability:** `get_executor_metrics()` returns active count, queue depth, and utilization % for all pools. `log_executor_health()` runs every 60s, warns when any pool exceeds 70% utilization. Wired in `main.py` startup event.
- **Lane 3 — Lint**: `python scripts/lint_async_blockers.py` catches `requests.*`, `time.sleep()`, `Thread().start()` in async code. Run before committing.
- **Shutdown**: `close_all_clients()` + `shutdown_executors()` wired in `main.py` and `pusher/main.py`.

## WebSocket Concurrency (Long-Lived Connections)

WebSocket handlers in `transcribe.py` and `pusher.py` manage 5-11 concurrent tasks per connection. These rules prevent ghost connections, memory leaks, and gauge drift.

### Task lifecycle: supervisor with `asyncio.wait(FIRST_COMPLETED)`

Never `asyncio.gather()` the receive task with background tasks — a hung bg task blocks cleanup forever. Never bare `await receive_task` either — a crashed bg task goes unnoticed for hours.

Use `asyncio.wait(FIRST_COMPLETED)` to detect **both** client disconnect **and** bg task failures immediately:

```python
bg_main_tasks = []
try:
    GAUGE.inc()
    receive_task = asyncio.create_task(receive_loop(), name=f"ws:{uid}:receive")
    bg_main_tasks = [
        asyncio.create_task(bg1(), name=f"ws:{uid}:bg1"),
        asyncio.create_task(bg2(), name=f"ws:{uid}:bg2"),
    ]
    # Supervisor: exits on disconnect OR bg crash
    done, _ = await asyncio.wait({receive_task, *bg_main_tasks}, return_when=asyncio.FIRST_COMPLETED)
    # Log bg failures, re-raise receive errors
    for task in done:
        if task is not receive_task and not task.cancelled():
            exc = task.exception()
            if exc: logger.error(f"BG task {task.get_name()} crashed: {exc}")
    if receive_task in done and not receive_task.cancelled():
        exc = receive_task.exception()
        if exc: raise exc
    # Cancel receive if bg crash triggered exit
    if not receive_task.done():
        receive_task.cancel()
    # Drain remaining bg tasks with timeout
    remaining = [t for t in bg_main_tasks if not t.done()]
    if remaining:
        try:
            await asyncio.wait_for(asyncio.gather(*remaining, return_exceptions=True), timeout=BG_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            for t in remaining:
                if not t.done(): t.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)
finally:
    all_to_cancel = [t for t in bg_main_tasks if not t.done()]
    for t in all_to_cancel: t.cancel()
    if all_to_cancel: await asyncio.gather(*all_to_cancel, return_exceptions=True)
    GAUGE.dec()
```

### Receive timeouts

Every `websocket.receive()` / `websocket.receive_bytes()` must be wrapped in `asyncio.wait_for(..., timeout=WS_RECEIVE_TIMEOUT)`. Dead TCP connections (mobile killed, network drop) block indefinitely without this.

### Gauge placement

`GAUGE.inc()` inside the `try` body, `GAUGE.dec()` in the `finally` — always paired, never separated by code that can raise. Initialize `bg_main_tasks = []` BEFORE the `try` so the `finally` can reference it.

### Task tracking and naming

Every `asyncio.create_task()` must: (1) include `name=f"ws:{uid}:{task_name}"` for production debugging, (2) be tracked for cancellation via `spawn()` (adds to `bg_tasks`) or `bg_main_tasks`. Untracked/unnamed tasks leak on disconnect and are invisible in logs.

### Executor bounds

`critical_executor` (8 workers) and `storage_executor` (16 workers) have bounded pools. The default executor (`None`) is unbounded — avoid it for user-triggered work. If you must use it (e.g., to avoid deadlock with `critical_executor`), document why and consider the thread count under load.

### Process-scoped dict cleanup

Module-level dicts (`proactive_noti_sent_at`, caches) grow forever if cleanup is lazy-only. Add TTL-based eviction or cap size with `maxlen`.

## Common Gotchas

1. **Python 3.11 only** — no 3.12+ syntax (nested same-type quotes in f-strings break the Docker build)
2. **Never `time.sleep()` in async** — use `asyncio.sleep()`. For blocking work: `await run_blocking(executor, fn)` with the appropriate pool
3. **Sync `requests` in async is silent poison** — no error raised, just blocks the entire event loop. All connections freeze, health checks fail, HPA can't scale.
4. **Semaphores are event-loop-bound** — `http_client.py` handles this via `(loop_id, name)` keying. Don't create raw `asyncio.Semaphore` outside that module.
5. **Webhook timeout = 30s** — partner integrations depend on this window. Don't change `httpx.Timeout(30.0, connect=2.0)`.
6. **WAL files must be opus-encoded** — opus decoder silently errors on raw PCM but returns HTTP 200
7. **Firestore collection group queries** need explicit indexes — 500 with no useful error
8. **Mutable WebSocket state races** — snapshot `nonlocal` variables before spawning async work
9. **Silent fire-and-forget drops** — functions gating on connection state must log when dropping work
10. **Queue caps for user data** — `private_cloud_queue` uses `deque(maxlen=20)` to prevent OOM kills (sized for 30 conns/pod); dropping oldest chunk is better than killing the pod and losing ALL data for ALL users
11. **`langdetect` unreliable on short text** — don't use on <20 chars or gate paid API calls on interim streaming text
12. **DG keepalive vs response timeout** — `keep_alive()` prevents DG's 10s idle timeout but NOT 1011 response timeout after all audio is processed. Post-session 1011 is benign.
