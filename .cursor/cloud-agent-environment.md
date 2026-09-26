# Cursor Cloud agent environment (Linux x86 VM)

Guidance for AI agents running in a Cursor Cloud VM. Linked from `AGENTS.md`.

## What runs here

Only the **Python backend** (`backend/`) is exercised on this VM. The macOS desktop app, iOS/Android builds, and firmware **cannot** be built or run here (they need macOS/Xcode, the Android SDK, or embedded hardware).

Preinstalled in the snapshot: `uv` (global), `redis-server`, `firebase-tools` (Firestore emulator), Java 21, FFmpeg, Node. The startup update script refreshes `backend/.venv` from `backend/pylock.toml` (idempotent `uv pip sync`). To use the venv: `cd backend && source .venv/bin/activate`.

## Preferred: hermetic E2E harness (no credentials)

The backend constructs Firestore, GCS, OpenAI, Pinecone, and Typesense clients **at import time**, so it normally won't even import without those services/keys. The repo ships a fully hermetic harness that imports the **real** FastAPI app with in-process fakes (`fake_firestore`, `fakeredis`, fake GCS), `LOCAL_DEVELOPMENT=true` auth, and an outbound-network guard — no credentials, no emulator, nothing to start:

```bash
cd backend && source .venv/bin/activate
bash testing/e2e/run.sh -q --tb=short
```

This is the best way to validate backend changes end-to-end on this VM (real routers, auth, encryption, middleware against the fakes). It is the same harness CI runs (`.github/workflows/backend-hermetic-e2e.yml`), so that workflow's latest run is the current pass/skip baseline. Add new hermetic scenarios under `backend/testing/e2e/`; fixtures and the `client`/`auth_headers` fixtures live in `backend/testing/e2e/conftest.py` (dev auth is `Authorization: Bearer dev-token` → uid `123`).

## Unit tests

`bash test.sh` runs each unit-test file in its **own pytest process**, several at a time (`BACKEND_PYTEST_WORKERS`, defaulting to one per CPU). A failing file does not stop the run — the script collects each file's status, reports **all** failing files at the end, and prints a `BACKEND_UNIT_TEST_FILE_LIST=... bash test.sh` command to re-run just those. `BACKEND_PYTEST_FILE_ISOLATION=0` switches to a single pytest invocation, still xdist-parallel unless you also set `BACKEND_PYTEST_XDIST=0`.

Do **not** run the whole `tests/unit` dir in one pytest process — many files mutate `sys.modules` at import time, so cross-file contamination causes mass false failures. The per-file isolation is deliberate containment, not a workaround; `backend/docs/test_isolation.md` is the authority on why, carries the current count, and tracks the migration toward single-process safety.

`BACKEND_PYTEST_PARALLEL_SESSION=1` is an experiment, not a shortcut: it keeps a process per file only for `backend/tests/.module_stub_legacy_allowlist` and runs the rest in one xdist session. It does not work on this tree yet — that allowlist only names files whose `sys.modules` writes are statically visible, and collecting the remainder together produces mass import errors, a protobuf segfault, or an OOM kill. Leave it off until the import-purity migration lands.

## Running the backend live (manual API calls)

Only needed when the hermetic harness isn't enough (e.g. poking endpoints with `curl`). Unlike the harness, a live `uvicorn` process has no fakes injected, so it needs the import-time clients satisfied. `backend/.env` is pre-seeded for this (gitignored, persists via snapshot): Firestore emulator (`FIRESTORE_EMULATOR_HOST=127.0.0.1:8081`, `GOOGLE_CLOUD_PROJECT=demo-omi`), a dummy `GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json` so the GCS client constructs, placeholder `OPENAI_API_KEY`/`TYPESENSE_*`, `ENCRYPTION_SECRET`, `ADMIN_KEY=local_dev_admin_key`, and **Pinecone left unset** so `backend/database/vector_db.py` takes its `index = None` no-op path. If `backend/.env` is missing, recreate it from `.env.template` plus those values, and regenerate `google-credentials.json` as any syntactically valid service-account JSON (a generated RSA key — Firestore I/O goes to the emulator, not real GCP).

```bash
redis-server --daemonize yes
firebase emulators:start --only firestore --project demo-omi   # needs a firebase.json pinning firestore to :8081
cd backend && source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

Auth: `Authorization: Bearer local_dev_admin_key<uid>` (the `<uid>` is taken verbatim), or set `LOCAL_DEVELOPMENT=true` and use `Bearer dev-token` → uid `123`. Verified hello-world: `POST /v3/memories` then `GET /v3/memories` round-trips through the emulator.

Features needing real external services (Deepgram STT, LLM chat, GCS audio, Pinecone/Typesense search) fail at **call time** with placeholders — that's expected, not an env bug. Supply real keys / `SERVICE_ACCOUNT_JSON` to exercise them.
