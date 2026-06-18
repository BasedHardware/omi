# Hermetic Backend E2E Harness

A manually runnable integration test suite that imports the **real omi FastAPI backend** and exercises selected routes against **faked or disabled external dependencies**. It is intended as a local dogfood harness first; there is no CI wiring yet.

Current dogfood status:

```text
68 passed, 6 skipped, 41 warnings
```

The run installs a local-only socket guard before importing backend code. Any non-local DNS/socket attempt raises an assertion, so real API calls fail the harness instead of silently leaking.

Run it with:

```bash
bash backend/testing/e2e/run.sh
```

Install e2e-only dependencies once with:

```bash
cd backend
python -m pip install -r testing/e2e/requirements.txt
```

`run.sh` verifies these dependencies are present but does not install them dynamically, so the test entrypoint itself does not reach PyPI before pytest imports the socket guard.

## Scope of v1

This version proves the backend can boot hermetically and that selected core CRUD, user/account, storage, webhook, task-integration, listen-routing, retrieval/search, deterministic processing-seam, and legacy-shape paths can execute without real Firestore, Redis, GCS, Pinecone, Typesense, Google ADC, or production API keys.

| Scenario | Status | Notes |
|---|---:|---|
| CRUD golden path | ✅ Green | Conversations are seeded directly because `POST /v1/conversations` processes an existing in-progress conversation; action items and memories use real create/update/delete routes. |
| Deterministic conversation-processing seam | ✅ Partial | Reprocess route, auth, model serialization, Firestore update, memory readback, and action-item queryability run with the provider-heavy processing function replaced by deterministic output. Full LLM-client wiring remains v2. |
| Listen/STT route seam | ✅ Partial | `/v4/web/listen` websocket auth/query parsing/custom-STT dispatch is covered with a fake stream handler; custom-STT suggested transcript events also run through the real listen websocket loop into client emission and decrypted conversation readback. Full Deepgram-compatible streaming fake remains v2. |
| Storage / speech profile | ✅ Green | `google.cloud.storage.Client` is patched to a temp-dir fake; speech-profile presence, signed URL, sample list, and delete paths run through real routes/helpers. |
| Webhooks | ✅ Partial | Developer webhook config/status routes, disabled no-op behavior, realtime delivery payload, non-2xx failure health recording, timeout/exception health recording, and threshold auto-disable are covered with `httpx.MockTransport`. Marketplace app webhook retry/circuit-breaker behavior remains v2. |
| Task integrations | ✅ Partial | CRUD/default list paths plus connected/disconnected/no-token and Todoist success, provider 500, 401 disconnect, and timeout failure paths are covered. Task creation uses deterministic integration lookup due a fake-firestore single-doc lookup/delete limitation on this nested subcollection shape. |
| User/auth/profile/account | ✅ Green | Auth guard, profile, onboarding, language/transcription prefs, people CRUD, notification/assistant settings, AI profile, and BYOK activation/deactivation routes are covered. |
| Retrieval/search | ✅ Partial | Memory, action-item, conversation summary, and transcript-chunk retrieval routes run through real public APIs with Firestore-backed records and a deterministic in-memory replacement for Pinecone/OpenAI embeddings at the `database.vector_db` client seam. Full Pinecone/Typesense service compatibility remains out of scope. |
| Failure / edge modes | ✅ Partial | Invalid input and edge-case coverage runs. Redis-unavailable, LLM 500, and STT timeout cases are explicitly skipped or deferred until per-test failure fakes are wired. |
| Legacy shape compatibility | ✅ Green | Exercises legacy conversation/memory shapes and deterministic fake-store repeated writes. It does not execute production migration scripts. |

## What is faked or disabled

| Dependency | v1 behavior | Why |
|---|---|---|
| Firestore | `fake-firestore` `MockFirestore` | In-memory datastore backing the real database modules. |
| Redis | `fakeredis` | In-memory Redis replacement. |
| Google Cloud Storage | `google.cloud.storage.Client` patched to a filesystem-backed fake | Enables storage-backed routes without GCS credentials/network. |
| Google ADC | `google.auth.default` returns anonymous credentials | Prevents real credential lookup at import time. |
| Pinecone | `PINECONE_API_KEY` removed globally; targeted retrieval/search tests monkeypatch `database.vector_db.index` to a deterministic in-memory fake | Keeps app import hermetic while allowing route-level vector upsert/query/delete assertions without real Pinecone. |
| Typesense | Dummy host/port/API key | Lets import-time Typesense client construction succeed; retrieval/search tests rely on vector results and fail-open keyword search rather than real Typesense compatibility. |
| Google Translate | Anonymous Google credentials | Allows import-time client construction; v1 tests do not call live translation. |
| LLM/STT/VAD/embeddings | Fake modules scaffolded; route and custom-STT suggested-transcript seams covered where deterministic patching is practical | Kept as v2 work where scenarios need real outbound HTTP/WS/provider assertions. |
| Webhook/task external HTTP | `httpx.MockTransport` in targeted tests | Captures outbound payloads without network. |

## What's real

- FastAPI app import via `main.app`
- Routers, middleware, auth dependency, websocket route entrypoints, Pydantic request/response validation
- Database modules and model serialization/deserialization
- Firestore query/update/delete code paths, backed by `MockFirestore`
- Redis client construction and delegated fakeredis operations
- Storage helper code paths, backed by temp-dir fake GCS

## Running individual scenarios

```bash
# CRUD / data shape
bash backend/testing/e2e/run.sh -k "test_crud"

# Conversation processing and state seams
bash backend/testing/e2e/run.sh -k "conversation_processing"

# Listen/STT websocket route seam
bash backend/testing/e2e/run.sh -k "listen_stt"

# Storage-backed speech profile routes
bash backend/testing/e2e/run.sh -k "storage_speech_profile"

# Webhook and task integration seams
bash backend/testing/e2e/run.sh -k "webhooks or task_integrations"

# Retrieval/search seams
bash backend/testing/e2e/run.sh -k "search or retrieval or embedding or vector"

# User/auth/profile/account routes
bash backend/testing/e2e/run.sh -k "user_auth_profile"

# Failure / edge modes
bash backend/testing/e2e/run.sh -k "test_failure_modes"

# Legacy shape compatibility
bash backend/testing/e2e/run.sh -k "test_migration_safety"
```

## Architecture

```text
run.sh
  └── pytest testing/e2e/
        ├── conftest.py                         # env, auth, fake setup, TestClient
        ├── fakes/
        │   ├── firestore.py                    # MockFirestore + seed/read helpers
        │   ├── redis.py                        # FakeRedis + redis.Redis patch
        │   ├── storage.py                      # filesystem-backed fake GCS client
        │   ├── vector_search.py                # deterministic embeddings + in-memory Pinecone-like index
        │   ├── llm.py                          # deterministic LLM fake scaffold
        │   ├── stt.py                          # deterministic custom-STT event helper; Deepgram WS TODO
        │   └── embeddings.py                   # VAD/diarization/embedding fake scaffold
        ├── fixtures/
        │   ├── conversations.json
        │   ├── memories.json
        │   └── action_items.json
        ├── test_crud.py
        ├── test_conversation_processing.py
        ├── test_conversation_processing_deterministic.py
        ├── test_failure_modes.py
        ├── test_harness_guards.py
        ├── test_listen_stt.py
        ├── test_migration_safety.py
        ├── test_retrieval_search.py
        ├── test_storage_speech_profile.py
        ├── test_task_integrations.py
        ├── test_user_auth_profile.py
        └── test_webhooks.py
```

## Test lifecycle

1. Set hermetic env vars before importing backend modules.
2. Patch Google auth before any Firestore/Translate client construction.
3. Build in-memory Firestore/Redis fakes and temp-dir fake GCS.
4. Disable dotenv loading so local `.env` files cannot rehydrate real credentials.
5. Patch Firestore/Redis/Storage client constructors before `import main`.
6. Import the real FastAPI app and wrap it with `TestClient`.
7. Clear fake Firestore/Redis/Storage state around each test.
8. Seed data where the backend has no generic create endpoint.
9. Run route-level assertions through the real app.

## Adding tests

Prefer real public routes. If no route exists for setup (for example, arbitrary conversation creation), seed via `fakes.firestore.seed_*` and then exercise the route under test.

```python
from fakes.firestore import seed_conversation


def test_read_seeded_conversation(client, auth_headers, sample_conversation_data):
    seed_conversation("123", sample_conversation_data)

    resp = client.get(
        f"/v1/conversations/{sample_conversation_data['id']}",
        headers=auth_headers,
    )

    assert resp.status_code == 200
```

## Current limitations / v2 work

- [ ] Implement Deepgram streaming WebSocket fake for `/v4/listen` / pusher scenarios.
- [ ] Wire deterministic LLM endpoints into all OpenAI/Anthropic/OpenRouter clients used by processing code.
- [ ] Add per-test HTTP failure injection for LLM 500 / timeout scenarios.
- [ ] Add real Redis-unavailable fail-open tests; v1 uses fakeredis-backed paths.
- [ ] Execute production migration scripts against fake fixtures if migration-script coverage is needed.
- [ ] Add marketplace app webhook retry/circuit-breaker tests beyond the developer realtime transcript failure/auto-disable paths.
- [ ] Improve fake-firestore support for nested task-integration single-doc lookup/delete so the task creation route no longer needs deterministic lookup patching.
- [ ] Expand retrieval/search beyond the deterministic in-memory vector seam to cover real Typesense keyword behavior and closer Pinecone response compatibility if those service contracts become in-scope.
- [ ] Run under Python 3.11 in CI-like environments; the local dogfood run used the repo `.venv` Python.

## Dependencies

- omi backend dependencies from `requirements.txt`
- e2e-only dependencies from `testing/e2e/requirements.txt`
