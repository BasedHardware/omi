# Hermetic Backend E2E Harness

A manually runnable integration test suite that imports the **real omi FastAPI backend** and exercises selected routes against **faked or disabled external dependencies**. It is intended as a local dogfood harness first; there is no CI wiring yet.

Current dogfood status:

```text
42 passed, 6 skipped
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

This first version proves the backend can boot hermetically and that selected CRUD / legacy-shape compatibility paths can execute without real Firestore, Redis, Pinecone, Typesense, Google ADC, or production API keys.

| Scenario | Status | Notes |
|---|---:|---|
| CRUD golden path | ✅ Green | Conversations are seeded directly because `POST /v1/conversations` processes an existing in-progress conversation; action items and memories use real create/update/delete routes. |
| Conversation processing shape | ⚠️ Partial / explicit skips | Seed/read and state-transition coverage runs. Full LLM-backed reprocessing/action-item/memory extraction tests are skipped until deterministic LLM clients are wired. |
| Failure / edge modes | ✅ Partial | Invalid input and edge-case coverage runs. Redis-unavailable, LLM 500, and STT timeout cases are explicitly skipped or deferred until per-test failure fakes are wired. |
| Legacy shape compatibility | ✅ Green | Exercises legacy conversation/memory shapes and deterministic fake-store repeated writes. It does not execute production migration scripts. |

## What is faked or disabled

| Dependency | v1 behavior | Why |
|---|---|---|
| Firestore | `fake-firestore` `MockFirestore` | In-memory datastore backing the real database modules. |
| Redis | `fakeredis` | In-memory Redis replacement. |
| Google ADC | `google.auth.default` returns anonymous credentials | Prevents real credential lookup at import time. |
| Pinecone | `PINECONE_API_KEY` removed | `database/vector_db.py` only skips Pinecone when the env var is absent. |
| Typesense | Dummy host/port/API key | Lets import-time Typesense client construction succeed; v1 tests do not perform keyword search. |
| Google Translate | Anonymous Google credentials | Allows import-time client construction; v1 tests do not call live translation. |
| Storage | Local temp-dir helper only; not globally patched | Available for tests that explicitly use `fakes.storage`; v1 routes should not call real GCS. |
| LLM/STT/VAD/embeddings | Fake modules scaffolded, not fully wired into all backend clients yet | Kept as v2 work where scenarios need real outbound HTTP/WS assertions. |

## What's real

- FastAPI app import via `main.app`
- Routers, middleware, auth dependency, Pydantic request/response validation
- Database modules and model serialization/deserialization
- Firestore query/update/delete code paths, backed by `MockFirestore`
- Redis client construction and delegated fakeredis operations

## Running individual scenarios

```bash
# Scenario 1: CRUD / data shape
bash backend/testing/e2e/run.sh -k "test_crud"

# Scenario 2: conversation processing shape
bash backend/testing/e2e/run.sh -k "test_conversation_processing"

# Scenario 3: failure / edge modes
bash backend/testing/e2e/run.sh -k "test_failure_modes"

# Scenario 4: legacy shape compatibility
bash backend/testing/e2e/run.sh -k "test_migration_safety"
```

## Architecture

```text
run.sh
  └── pytest testing/e2e/
        ├── conftest.py                    # env, auth, fake setup, TestClient
        ├── fakes/
        │   ├── firestore.py                # MockFirestore + seed/read helpers
        │   ├── redis.py                    # FakeRedis + redis.Redis patch
        │   ├── llm.py                      # deterministic LLM fake scaffold
        │   ├── stt.py                      # Deepgram fake scaffold; WS TODO
        │   ├── embeddings.py               # VAD/diarization/embedding fake scaffold
        │   └── storage.py                  # temp-dir storage helper
        ├── fixtures/
        │   ├── conversations.json
        │   ├── memories.json
        │   └── action_items.json
        ├── test_crud.py
        ├── test_conversation_processing.py
        ├── test_failure_modes.py
        └── test_migration_safety.py
```

## Test lifecycle

1. Set hermetic env vars before importing backend modules.
2. Patch Google auth before any Firestore/Translate client construction.
3. Build in-memory Firestore/Redis fakes.
4. Disable dotenv loading so local `.env` files cannot rehydrate real credentials.
5. Patch Firestore/Redis client constructors before `import main`.
6. Import the real FastAPI app and wrap it with `TestClient`.
7. Clear fake Firestore/Redis state around each test.
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
- [ ] Capture outbound webhooks with `responses` or an HTTP test server.
- [ ] Add real no-op vector/search fakes if Pinecone/Typesense query assertions become in-scope.
- [ ] Run under Python 3.11 in CI-like environments; the local dogfood run used the repo `.venv` Python.

## Dependencies

- omi backend dependencies from `requirements.txt`
- e2e-only dependencies from `testing/e2e/requirements.txt`
