# Backend (Python) — Developer Guide

Inherits all rules from the root `../CLAUDE.md`. This file adds backend-specific development guidance.

## Setup

### Prerequisites
Python 3.11 (not 3.12+ — Dockerfile pins 3.11), FFmpeg, Opus (`opuslib`), Redis (optional)

### Quick Start
```bash
cp .env.template .env          # Fill in required values
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

### Key Env Vars
| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | LLM calls (not `OPENAI_ADMIN_KEY` — that's for billing) |
| `DEEPGRAM_API_KEY` | Yes | Speech-to-text |
| `ENCRYPTION_SECRET` | Yes (for tests) | AES-256-GCM key derivation |
| `REDIS_DB_HOST` | Recommended | Cache + rate limiting (fail-open without it) |
| `ADMIN_KEY` | For local dev | Bypass Firebase auth with token `ADMIN_KEY<uid>` |
| `SERVICE_ACCOUNT_JSON` | For GCS/Firestore | JSON content or `GOOGLE_APPLICATION_CREDENTIALS` path |

See `.env.template` for the full list.

## Directory Structure

```
backend/
  main.py              # FastAPI entry, middleware, router registration
  models/              # Pydantic BaseModel definitions
  database/            # All persistence (Firestore, Redis, Pinecone, Neo4j)
    _client.py         #   Firestore singleton
    redis_db.py        #   Cache, rate limiting, pub/sub
  routers/             # FastAPI route handlers (one file per feature)
    transcribe.py      #   /v4/listen WebSocket — audio streaming
    chat.py            #   /v1/messages — AI chat
    memories.py        #   /v3/memories — CRUD + search
  utils/               # Domain utilities (never import from routers/)
    llm/clients.py     #   LLM model instances (OpenAI, Anthropic, OpenRouter)
    stt/               #   Speech-to-text pipeline (Deepgram, VAD)
    other/endpoints.py #   Auth dependencies, rate limiting
    log_sanitizer.py   #   sanitize() / sanitize_pii()
    encryption.py      #   AES-256-GCM per-user encryption
  pusher/              # Subservice: conversation processor (separate Docker)
  diarizer/            # Subservice: speaker identification (GPU)
  agent-proxy/         # Subservice: WebSocket bridge to user agent VMs
  tests/unit/          # Unit tests (no external deps)
  tests/integration/   # Integration tests (need Redis, Firebase, API keys)
  test.sh              # Test runner — source of truth for CI
  test-preflight.sh    # Env validator
```

## Import Rules

All imports at module top level — never inside functions. Strict hierarchy:

```
database/  →  utils/  →  routers/  →  main.py
  (lower)                              (higher)
```

Higher imports from lower, never reverse. Cross-importing between routers will break. Shared code paths exist across backend, pusher, and backend-listen — trace imports before assuming a change only affects one service.

## Database

### Firestore (primary store)
```python
from database._client import db
docs = db.collection('users').document(uid).collection('memories').stream()
db.collection('users').document(uid).set(data, merge=True)
```
- Collection group queries need explicit Firestore indexes — will 500 with no helpful error
- Segments are encrypted at rest — direct reads return opaque blobs; use REST API with auth for decrypted data
- Feature gating via user fields: e.g., translation requires `users/{uid}.language` non-empty — silently disabled if missing

### Redis (cache, rate limiting, locks)
```python
from database import redis_db
redis_db.set_generic_cache(path, data, ttl=60)
data = redis_db.get_generic_cache(path)  # Returns None on miss or error
```
- **Fail-open**: All Redis errors caught and logged; requests proceed without caching/rate-limiting
- Rate limiting: Lua scripts for atomic increment + window check
- Locks: `try_acquire_listen_lock(uid)` prevents duplicate WS connections

## Auth

### HTTP Endpoints
```python
from utils.other.endpoints import get_current_user_uid

@router.get('/v3/memories')
def get_memories(uid: str = Depends(get_current_user_uid)):
    ...
```

### WebSocket Endpoints
```python
# Use WebSocketException, NOT HTTPException
# HTTPException exits ASGI without handshake → 5xx instead of clean close
raise WebSocketException(code=1008, reason="Invalid token")
```

### Rate Limiting
```python
uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:send_message"))
# Policies in utils/rate_limit_config.py
```

## Testing

```bash
bash test-preflight.sh   # Verify env (Python, pytest, packages, Redis)
bash test.sh             # Run all tests — this is what CI runs
```

**New test files must be added to `test.sh`** or they won't run in CI.

### Mock Patterns
```python
# Pre-mock heavy deps BEFORE importing the module under test
import types, sys
from unittest.mock import MagicMock

_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

# NOW import the module
from utils import fair_use as fair_use_mod
```

Use `patch.object(target_module, "func")` not string-based `patch("module.func")` — the string form silently patches the wrong reference if the function was already imported by the target module.

When modules construct objects at import time, use lazy getters to avoid triggering heavy initialization in tests.

## Formatting

```bash
black --line-length 120 --skip-string-normalization <files>
```

`--skip-string-normalization` is critical — without it, black flips all quotes and the diff explodes.

## Common Gotchas

1. **Python 3.11 only**: No 3.12+ syntax (e.g., nested same-type quotes in f-strings break in the Docker build)
2. **Never `time.sleep()` in async handlers**: Blocks the uvicorn event loop. Use `asyncio.sleep()`. For blocking work (LLM calls, heavy processing), use `asyncio.to_thread()` + semaphore
3. **WAL files must be opus-encoded**: Opus decoder silently errors on raw PCM but returns HTTP 200 — sync tests pass for the wrong reason. Use opus `.bin` with 4-byte LE length-prefixed frames
4. **Firestore collection group queries**: Need explicit indexes — will 500 with no useful error in logs
5. **Mutable WebSocket state races**: Snapshot `nonlocal` variables before spawning async work — mutable closures + rollover events cause race conditions
6. **Silent fire-and-forget drops**: Functions gating on connection state must log when dropping work (speaker samples, etc.)
7. **Unbounded queues for user data**: `deque(maxlen=N)` silently drops audio. Data-safety queues must stay unbounded
8. **`langdetect` unreliable on short text**: Don't use on <20 chars or gate paid API calls on interim streaming text
