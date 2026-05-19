# Omi Local Backend

This is the lean local-first daemon scaffold for Omi Desktop. It is separate from
`desktop/Backend-Rust` so the local daemon can build and run without Omi cloud
credentials, Firebase, Firestore, Redis, GCS, pusher, paywall, or agent-proxy
dependencies.

## Run Locally

For a complete user-test walkthrough, including desktop launch environment and
transcript import, see `docs/local-mvp-runbook.md`.

Primary desktop local-mode user-test command:

```bash
cd desktop
OMI_DESKTOP_BACKEND_MODE=local \
OMI_LOCAL_DAEMON_SUPERVISE=1 \
OMI_LOCAL_DAEMON_URL=http://127.0.0.1:8765 \
OMI_PYTHON_API_URL=http://omi-cloud-invalid:9001 \
OMI_DESKTOP_API_URL=http://omi-rust-invalid:9002 \
./run.sh
```

This targets only the development app bundle and supervises the local daemon if
`/health` is not already reachable.

```bash
cd desktop/local-backend
cargo run
```

The daemon listens on `127.0.0.1:8765` by default and stores local data under the
platform app data directory.

Configuration is environment-based:

```bash
OMI_LOCAL_BACKEND_HOST=127.0.0.1 \
OMI_LOCAL_BACKEND_PORT=8777 \
OMI_LOCAL_BACKEND_DATA_DIR=/tmp/omi-local-backend \
cargo run
```

Verify the health endpoint:

```bash
curl http://127.0.0.1:8765/health
```

The response includes the service name, local mode, package version, bind
address, and resolved data directory.

## MVP HTTP API

The local daemon exposes JSON endpoints for the desktop MVP:

- `GET /health`, `GET /version`, `GET /profile/status`
- `GET|POST /v1/conversations`
- `GET|PATCH|DELETE /v1/conversations/:id`
- `POST /v1/conversations/:id/transcript-segments`
- `POST /v1/conversations/:id/finalize-transcript`
- `GET /v1/search/conversations?q=<text>`
- `GET|POST /v1/memories`
- `GET|PATCH|DELETE /v1/memories/:id`
- `GET|POST /v1/action-items`
- `GET|PATCH|DELETE /v1/action-items/:id`
- `GET|PUT /v1/profile`
- `GET|PUT /v1/settings`
- `GET /v1/processing-jobs`
- `GET /v1/processing-jobs/:id`
- `GET /v1/processing-jobs/status`
- `POST /v1/processing-jobs/process-next`

Finalizing transcript ingestion currently enqueues a local `finalize_transcript`
processing job. Later processing workers can consume the same durable
`processing_jobs` rows and update queued/running/completed/failed state.

## Differences From The Cloud API

The local daemon is intentionally unauthenticated on loopback for the MVP. It
does not require Firebase ID tokens, does not return paywall errors, does not
create GCS signed URLs, and does not depend on Redis, Firestore, pusher, or
agent-proxy coordination.

Local responses use explicit JSON errors with `source: "local_daemon"`. Profile
status reports `authenticated: false` because local-first mode does not imply an
Omi cloud account. Cloud IDs and sync fields are retained in storage models so a
future sync adapter can map local records to cloud records without making cloud
state the source of truth.

## Local-First Capability Boundaries

Desktop local daemon mode uses `DesktopBackendEnvironment.Capability` as the
capability matrix for deciding what UI/API flows may call into cloud-bound
services. In local daemon mode:

- Available: local conversation data, local transcript ingestion, local search,
  local memories, local action items, local settings, and optional Firebase
  sign-in as an account-only feature.
- Unavailable: managed agent VM provisioning/sync, Omi backend provider proxies,
  hosted transcription endpoints, public sharing links, Omi cloud sync,
  subscriptions/payments/quotas, and Crisp support messaging.

Unavailable capabilities fail before building a request to Omi-hosted services.
Local conversation CRUD/search/settings flows continue to use the configured
loopback daemon URL and do not require Firebase auth.

Signed-in local daemon mode keeps the signed-in identity for UI/account context,
but it does not run cloud startup sync. App launch, activation, Settings load,
profile-name edits, assistant settings sync, backend API-key fetch, subscription
refresh, quota refresh, managed agent VM setup, and Crisp support polling are
skipped, answered from local defaults, or fail before network. Assistant/chat
features that depend on the Omi Gemini/Anthropic/provider proxy remain
unavailable until direct local provider support is added for that surface.

Hosted transcription endpoints are intentionally unavailable in local daemon
mode. Direct live STT parity is not part of this MVP unless a future direct
provider path is added. For user testing, import transcript text or JSON
fixtures through the supported helper. Desktop local mode blocks hosted live
capture before network and leaves stopped local sessions for the retry/import
finalize path instead of calling Python force-process.

```bash
desktop/local-backend/tools/import_transcript.py /path/to/transcript.txt
```

The helper creates a conversation, appends transcript segments, finalizes
ingestion, waits for local processing, verifies search, and prints read/search
commands for the imported conversation. Stable client conversation, memory, and
action-item IDs are idempotent: exact replay returns the existing row, while a
conflicting replay returns HTTP 409.

Local processing uses deterministic fallback unless an OpenAI-compatible
provider is configured through structured `PUT /v1/settings` JSON; see the
runbook for local-stub set and clear commands.

## Architecture And E2E Validation

The durable MVP architecture note and validation checklist live in
`docs/architecture.md`.

Run the local daemon API smoke test:

```bash
desktop/local-backend/tools/e2e_smoke.sh
```

The smoke starts the daemon on a temporary loopback port, creates and updates a
conversation, appends/finalizes transcript segments, waits for fallback
processing, checks job status, restarts the daemon, and verifies persisted
conversation/search output without Omi cloud credentials.
