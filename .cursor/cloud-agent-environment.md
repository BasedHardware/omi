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

This is the best way to validate backend changes end-to-end on this VM (real routers, auth, encryption, middleware against the fakes). It is the same harness CI runs (`.github/workflows/backend-hermetic-e2e.yml`). Verified here: **103 passed, 3 skipped**. Add new hermetic scenarios under `backend/testing/e2e/`; fixtures and the `client`/`auth_headers` fixtures live in `backend/testing/e2e/conftest.py` (dev auth is `Authorization: Bearer dev-token` → uid `123`).

## Unit tests (known pre-existing failures on `main`)

`bash test.sh` runs each file in its own pytest process under `set -e`, so it **halts at the first failing file**. On current `main` that is `tests/unit/test_speaker_sample.py` (pre-existing: it patches `deepgram_prerecorded_from_bytes`, renamed to `prerecorded_from_bytes`). Async-heavy files also fail because `pytest-asyncio` is **not** in the lock and no `asyncio_mode` is configured. Run files individually (`pytest tests/unit/test_x.py`) to validate; ~129/172 unit-test files pass in isolation. Do **not** run the whole `tests/unit` dir in one pytest process — cross-file mock contamination causes mass false failures (the per-file isolation in `test.sh` is intentional).

## Running the backend live (manual API calls)

Only needed when the hermetic harness isn't enough (e.g. poking endpoints with `curl`). Unlike the harness, a live `uvicorn` process has no fakes injected, so it needs the import-time clients satisfied. `backend/.env` is pre-seeded for this (gitignored, persists via snapshot): Firestore emulator (`FIRESTORE_EMULATOR_HOST=127.0.0.1:8085`, `GOOGLE_CLOUD_PROJECT=demo-omi`), a dummy `GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json` so the GCS client constructs, placeholder `OPENAI_API_KEY`/`TYPESENSE_*`, `ENCRYPTION_SECRET`, `ADMIN_KEY=local_dev_admin_key`, and **Pinecone left unset** so `database/vector_db.py` takes its `index = None` no-op path. If `backend/.env` is missing, recreate it from `.env.template` plus those values, and regenerate `google-credentials.json` as any syntactically valid service-account JSON (a generated RSA key — Firestore I/O goes to the emulator, not real GCP).

The committed repo-root `firebase.json` already pins the Firestore emulator to `127.0.0.1:8085` (match `FIRESTORE_EMULATOR_HOST` to it), so no `firebase.json` needs to be created:

```bash
redis-server --daemonize yes
firebase emulators:start --only firestore --project demo-omi   # uses repo-root firebase.json (firestore :8085)
cd backend && source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

Auth: `Authorization: Bearer local_dev_admin_key<uid>` (the `<uid>` is taken verbatim), or set `LOCAL_DEVELOPMENT=true` and use `Bearer dev-token` → uid `123`. Verified hello-world: `POST /v3/memories` then `GET /v3/memories` round-trips through the emulator.

Features needing real external services (Deepgram STT, LLM chat, GCS audio, Pinecone/Typesense search) fail at **call time** with placeholders — that's expected, not an env bug. Supply real keys / `SERVICE_ACCOUNT_JSON` to exercise them.
