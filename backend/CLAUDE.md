# Backend (Python) — Operational Playbook

Inherits all rules from the root `../CLAUDE.md`. This file adds backend-specific operational guidance.

## Directory Structure

```
backend/
  main.py                  # FastAPI entry point, middleware, 45+ router registrations
  models/                  # Pydantic BaseModel definitions (shared across services)
  database/                # All persistence: Firestore, Redis, Pinecone, Neo4j
    _client.py             #   Firestore singleton (google.cloud.firestore.Client)
    redis_db.py            #   Redis: caching, rate limiting (Lua scripts), pub/sub
    memories.py            #   Example domain module (conversations.py, users.py, etc.)
  routers/                 # FastAPI route handlers (one file per feature domain)
    transcribe.py          #   /v4/listen WebSocket — main audio streaming endpoint
    chat.py                #   /v1/messages — AI chat with tool use
    memories.py            #   /v3/memories — CRUD + search
    auth.py                #   Google/Apple OAuth callbacks, session management
  utils/                   # Domain utilities (never import from routers/)
    llm/                   #   LLM client instances, prompt caching, usage tracking
      clients.py           #     Model instances (OpenAI, Anthropic, OpenRouter)
    stt/                   #   Speech-to-text pipeline (Deepgram streaming, VAD gating)
    other/                 #   Auth dependencies, storage, timeout middleware
      endpoints.py         #     get_current_user_uid(), rate limit enforcement
    log_sanitizer.py       #   sanitize() / sanitize_pii() — required for all logging
    encryption.py          #   AES-256-GCM per-user encryption (HKDF-SHA256 key derivation)
  charts/                  # Kubernetes Helm charts for all services
  tests/
    unit/                  # 50+ unit tests (no external service dependencies)
    integration/           # Integration tests (need Redis, Firebase, API keys)
  pusher/                  # Subservice: conversation processor (separate Docker/requirements)
  diarizer/                # Subservice: speaker identification (GPU, pyannote.audio)
  agent-proxy/             # Subservice: WebSocket bridge to user agent VMs
  modal/                   # GPU services: VAD, speaker ID (runs on Modal)
  Dockerfile               # Multi-stage build (Python 3.11 + liblc3)
  requirements.txt         # 250+ dependencies
  test.sh                  # Test runner — source of truth for CI
  test-preflight.sh        # Environment validator (Python, pytest, env vars, Redis)
  .env.template            # All env vars with descriptions
```

## Service Architecture

| Service | Runtime | Entry Point | Purpose |
|---------|---------|-------------|---------|
| **backend-listen** | GKE (`prod-omi-backend` namespace) | `main.py` | REST API + WebSocket, 45 routers |
| **pusher** | Cloud Run | `pusher/main.py` | Audio stream processing, calls diarizer + Deepgram |
| **diarizer** | Cloud Run | `diarizer/main.py` | Speaker embeddings (GPU) |
| **agent-proxy** | Cloud Run | `agent-proxy/main.py` | WebSocket bridge: mobile <-> user agent VMs |
| **vad** | Modal | `modal/` | Voice activity detection (GPU) |
| **notifications-job** | Modal (cron) | `modal/job.py` | Scheduled push notifications |

### Service Dependencies
```
backend-listen --> Redis (pub/sub, rate limiting, caching)
backend-listen --> Deepgram (streaming STT)
backend-listen --> pusher (via external LB, 30s idle timeout on WS)
backend-listen --> diarizer (speaker embeddings)
pusher ---------> diarizer + Deepgram (independent connections)
agent-proxy ----> user GCE VMs (private IP, port 8080)
```

Shared code paths exist across backend, pusher, and backend-listen — trace imports before assuming a change only affects one service.

## Database Layer

| Store | Purpose | Access Pattern |
|-------|---------|----------------|
| **Firestore** | Primary persistent store | `from database._client import db` — sync client, collection/document API |
| **Redis** | Cache, rate limiting, pub/sub, locks | `from database import redis_db` — fail-open (errors logged, not raised) |
| **Pinecone** | Vector embeddings (memory/conversation search) | Via `utils/` — semantic similarity queries |
| **Neo4j** | Knowledge graph (entity relationships) | Via `utils/` — Cypher queries |

### Firestore Patterns
```python
# Read
docs = db.collection('users').document(uid).collection('memories').stream()

# Write
db.collection('users').document(uid).set(data, merge=True)

# Collection group queries need explicit Firestore indexes — will 500 without them (no helpful error)
```

### Redis Patterns
- Caching: `set_generic_cache(path, data, ttl)` / `get_generic_cache(path)` — returns None on miss or error
- Rate limiting: Lua script in `check_rate_limit()` — atomic increment + window check
- Locks: `try_acquire_listen_lock(uid)` — prevents duplicate WS connections
- **Fail-open**: All Redis errors are caught and logged; requests proceed without caching/rate-limiting

### Data Protection
- Encryption uses AES-256-GCM with per-user keys derived via HKDF-SHA256 from `ENCRYPTION_SECRET`
- Firestore segments are encrypted at rest — direct Firestore reads return opaque blobs; use the REST API with auth to get decrypted data
- Some features are gated by Firestore user fields (e.g., translation requires `users/{uid}.language` to be non-empty — silently disabled if missing)

## Auth Patterns

### HTTP Endpoints
```python
from utils.other.endpoints import get_current_user_uid

@router.get('/v3/memories')
def get_memories(uid: str = Depends(get_current_user_uid)):
    # uid extracted from "Bearer <firebase_token>" header
```

### WebSocket Endpoints
```python
# IMPORTANT: Use WebSocketException, NOT HTTPException
# HTTPException exits ASGI without handshake → LB returns 5xx instead of clean close
raise WebSocketException(code=1008, reason="Invalid token")
```

### Rate Limiting
```python
# Applied via dependency injection
uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:send_message"))

# Policies defined in utils/rate_limit_config.py
# RATE_LIMIT_BOOST env var (float, default 1.0) scales all limits
# RATE_LIMIT_SHADOW_MODE (bool) logs violations without blocking
```

### Local Development
- Set `ADMIN_KEY=dev_key_123` in `.env` — enables token format `ADMIN_KEY<uid>` to bypass Firebase verification
- `ADMIN_KEY` is set on GKE backend-listen but empty on Cloud Run services — admin endpoints silently fail on Cloud Run

## Testing

### Running Tests
```bash
bash test-preflight.sh   # Verify environment (Python, pytest, packages, env vars, Redis)
bash test.sh             # Run all tests — this is what CI runs
```

### Critical Rule
New test files **must be added to `test.sh`** or they won't run in CI. Easy to forget — reviewers check this.

### Test Patterns
```python
# Pre-mock heavy dependencies BEFORE importing the module under test
import types, sys
from unittest.mock import MagicMock

_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

# NOW import the module
from utils import fair_use as fair_use_mod
```

### Mock Best Practice
Use `patch.object(target_module, "func")` over string-based `patch("module.func")`. The string form silently patches the wrong reference if the function was already imported by the target module.

### What's Mocked vs Real
- **Mocked**: Firestore, external APIs (Deepgram, OpenAI), Firebase Auth
- **Real (if available)**: Redis (gracefully skipped if unavailable)
- Integration tests in `tests/integration/` need credentials + running services

## Local Development

### Prerequisites
Python 3.11, GCloud SDK, FFmpeg, Opus (`opuslib`), Redis (optional but recommended)

### Quick Start
```bash
cp .env.template .env          # Fill in required values
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

### Port-Forwards for Subservices
Local dev needs port-forwards for diarizer/VAD:
```bash
kubectl port-forward svc/dev-omi-diarizer <port>
```
Without them, backend tries `host.docker.internal:18881` which fails silently.

### Key Env Vars
| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | LLM calls (not `OPENAI_ADMIN_KEY` — that's for billing API) |
| `DEEPGRAM_API_KEY` | Yes | Speech-to-text |
| `ENCRYPTION_SECRET` | Yes (for tests) | AES-256-GCM key derivation |
| `REDIS_DB_HOST` | Recommended | Cache + rate limiting (fail-open without) |
| `ADMIN_KEY` | For local dev | Bypass Firebase auth: `ADMIN_KEY<uid>` |
| `SERVICE_ACCOUNT_JSON` | For GCS/Firestore | JSON content or `GOOGLE_APPLICATION_CREDENTIALS` path |

See `.env.template` for the full list.

## Formatting

```bash
black --line-length 120 --skip-string-normalization <files>
```

The `--skip-string-normalization` flag is critical — without it, black flips single quotes to double quotes and the diff explodes.

## Common Gotchas

1. **Python 3.11 only**: Dockerfile runs 3.11 — no 3.12+ syntax (e.g., nested same-type quotes in f-strings will break)
2. **`time.sleep()` blocks uvicorn**: Use `asyncio.sleep()` always; `time.sleep()` in an async handler blocks the entire event loop
3. **WAL files must be opus-encoded**: Backend opus decoder errors silently on raw PCM but returns HTTP 200 — sync tests pass for the wrong reason. Use opus `.bin` with 4-byte LE length-prefixed frames
4. **GKE namespace is `prod-omi-backend`** (not `prod`): Wrong namespace = silent failures in kubectl/logging queries
5. **Cloud Logging for backend-listen**: Use `resource.type="k8s_container"` + `container_name="backend-listen"` + `namespace_name="prod-omi-backend"` — `cloud_run_revision` returns nothing
6. **Pusher WS idle timeout**: External LB has 30s idle timeout — silence >30s kills the WebSocket, no retry/fallback
7. **Firestore collection group queries**: Need explicit indexes — will 500 without them, no helpful error in logs
8. **`private_cloud_sync_enabled` defaults True**: Speaker ID runs for all users even without speech profiles
