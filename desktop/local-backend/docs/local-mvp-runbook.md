# Local MVP User-Test Runbook

This runbook starts the local daemon and imports transcript data without Omi
hosted backend services. It is the supported MVP path for testing local
conversation storage, transcript ingestion, processing fallback, and search.

## Prerequisites

- macOS with Xcode command line tools installed.
- Rust toolchain with `cargo`.
- Python 3 for the import helper.
- `curl` for health and API checks.
- For desktop app testing: the normal desktop development prerequisites from
  `desktop/README.md` and `desktop/run.sh`.

No Firebase, Omi Python backend, Rust cloud backend, Redis, Firestore, GCS,
pusher, or agent-proxy credentials are required for the local daemon path.

## Automated Local-Only Self-Test

Run the unattended MVP check from the repo root:

```bash
desktop/local-backend/tools/local_only_self_test.sh
```

The self-test creates an isolated temp data directory, starts the local daemon
on a free loopback port, verifies health/profile/settings, conversation
create/read/update/delete, transcript append/finalize, search, processing
status, restart persistence, and then runs `APIClientRoutingTests` to assert
local-mode desktop actions stay on the local daemon without Firebase auth or
Omi-hosted backend requests. It prints a concise pass/fail summary at the end.

## Primary Desktop Launch

For user-test runs, use one command from the repo root. This launches the
development app bundle only (`Omi Dev.app` / `com.omi.desktop-dev`), checks the
local daemon health endpoint, starts `desktop/local-backend` if needed, and
keeps Omi-hosted backend URLs deliberately invalid so accidental cloud routing
is obvious:

```bash
cd desktop
OMI_DESKTOP_BACKEND_MODE=local \
OMI_LOCAL_DAEMON_SUPERVISE=1 \
OMI_LOCAL_DAEMON_URL=http://127.0.0.1:8765 \
OMI_PYTHON_API_URL=http://omi-cloud-invalid:9001 \
OMI_DESKTOP_API_URL=http://omi-rust-invalid:9002 \
./run.sh
```

Required environment:

- `OMI_DESKTOP_BACKEND_MODE=local` selects the local daemon profile.
- `OMI_LOCAL_DAEMON_SUPERVISE=1` lets `desktop/run.sh` start the daemon when
  `/health` is not already reachable.

Recommended test-boundary environment:

- `OMI_LOCAL_DAEMON_URL=http://127.0.0.1:8765` makes the daemon URL explicit.
- `OMI_PYTHON_API_URL=http://omi-cloud-invalid:9001` makes accidental Python
  backend calls fail locally.
- `OMI_DESKTOP_API_URL=http://omi-rust-invalid:9002` makes accidental cloud Rust
  backend calls fail locally.

Optional daemon environment:

- `OMI_LOCAL_BACKEND_DATA_DIR=/tmp/omi-local-mvp` isolates SQLite data.
- `OMI_LOCAL_BACKEND_PORT=<port>` chooses a free loopback port. Keep
  `OMI_LOCAL_DAEMON_URL` in sync with it.
- `OMI_LOCAL_DAEMON_LOG=/tmp/omi-local-backend-dev.log` changes the supervised
  daemon log path.
- `OMI_CLEAN_STALE_CLONES=1` enables the broad home-directory cleanup for stale
  `Omi Dev.app` clones. Local daemon mode skips that scan by default so the
  primary launch command reaches the daemon preflight quickly.

Do not use this launcher to manage `/Applications/omi.app`.

## Manual Daemon Launch

For API-only testing or when you do not want `desktop/run.sh` to supervise the
daemon, start it manually from the repo root:

```bash
cd desktop/local-backend
OMI_LOCAL_BACKEND_DATA_DIR=/tmp/omi-local-mvp \
OMI_LOCAL_BACKEND_PORT=8765 \
cargo run
```

Verify health from another terminal:

```bash
curl http://127.0.0.1:8765/health
```

Expected signals:

- `service` is `omi-local-backend`.
- `mode` is `local`.
- `data_dir` points at the daemon data directory.

If health does not respond, check that the daemon terminal is still running and
that no other process is already using the selected port.

To keep using a manually managed daemon, start it first and launch the desktop
app with the same local-mode environment:

```bash
cd desktop
OMI_DESKTOP_BACKEND_MODE=local \
OMI_LOCAL_DAEMON_URL=http://127.0.0.1:8765 \
OMI_PYTHON_API_URL=http://omi-cloud-invalid:9001 \
OMI_DESKTOP_API_URL=http://omi-rust-invalid:9002 \
./run.sh
```

## Confirm Local Mode In The App

The Conversations header shows a `Local` chip when the app is using local daemon
mode. Settings → About also includes a Backend Mode card with the selected
daemon URL, auth requirement, `/health` result, data directory, and whether
processing is using deterministic fallback or an OpenAI-compatible provider.

Cloud-only folder and public share controls are hidden in local mode. Merge and
folder API calls fail locally before building an Omi-hosted request if they are
reached from another surface.

## Import Transcript Data

Hosted transcription endpoints are intentionally disabled in local daemon mode.
Direct live STT parity is not part of the current MVP unless a future direct
provider path is added. For local MVP testing, import or append transcript text
and then finalize processing.

Create a plain text fixture:

```bash
cat >/tmp/omi-local-transcript.txt <<'EOF'
We reviewed the local-first desktop MVP and confirmed it can store transcript
segments without Firebase or Firestore.

The next action is to test local search and processing status from the desktop
app.
EOF
```

Import it:

```bash
desktop/local-backend/tools/import_transcript.py /tmp/omi-local-transcript.txt
```

The helper:

- creates a local conversation through `POST /v1/conversations`
- appends transcript segment rows through
  `POST /v1/conversations/:id/transcript-segments`
- finalizes ingestion through `POST /v1/conversations/:id/finalize-transcript`
- waits for the local processing job to complete
- verifies search finds the imported transcript text
- prints the conversation ID plus read and search `curl` commands

For retry tests, pass a stable `--conversation-id` and run the same command
again. The helper reuses the existing conversation, exact duplicate transcript
segments return the existing row, and finalize returns an already active or
current completed processing job instead of piling up duplicate queued work. A
different segment body at an existing `segment_index` returns HTTP 409.

JSON fixtures are also supported. The file may be a list of segment strings, a
list of segment objects, or an object with conversation fields plus `segments`
or `transcript_segments`:

```json
{
  "title": "Local MVP Fixture",
  "overview": "Imported for a local daemon user test",
  "segments": [
    {
      "speaker_label": "Alex",
      "text": "Local daemon mode keeps transcript data on this machine.",
      "start_ms": 0,
      "end_ms": 2400
    },
    {
      "speaker_label": "Sam",
      "text": "Search should find this imported fixture without cloud credentials.",
      "start_ms": 2400,
      "end_ms": 5200
    }
  ]
}
```

Useful helper options:

```bash
desktop/local-backend/tools/import_transcript.py fixture.json \
  --base-url http://127.0.0.1:8765 \
  --title "User Test Import" \
  --search-query "imported fixture"
```

## Read And Search Imported Conversations

Use the commands printed by the import helper, or run them directly:

```bash
curl http://127.0.0.1:8765/v1/conversations/<conversation-id>
curl 'http://127.0.0.1:8765/v1/search/conversations?q=local+first'
curl http://127.0.0.1:8765/v1/processing-jobs/status
```

After finalization, the conversation status should become `processed`. Search
results should include the imported conversation when the query appears in the
title, overview, or transcript text.

## Local Provider Configuration

Processing works without provider keys by using deterministic fallback. To force
that path, clear provider settings:

```bash
curl -X PUT http://127.0.0.1:8765/v1/settings \
  -H 'content-type: application/json' \
  -d '{"ai_provider": null, "provider": null}'
```

To test a direct OpenAI-compatible provider without editing source code, store
the provider configuration in the local daemon settings:

```bash
curl -X PUT http://127.0.0.1:8765/v1/settings \
  -H 'content-type: application/json' \
  -d '{
    "ai_provider": {
      "kind": "openai_compatible",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4o-mini",
      "api_key": "'"$OPENAI_API_KEY"'"
    }
  }'
```

Inspect the active settings:

```bash
curl http://127.0.0.1:8765/v1/settings
```

Provider keys remain in the local daemon SQLite settings table and are sent
directly to the configured provider, not to Omi-hosted backend services.

## What Works Without Omi-Hosted Services

- Local daemon startup on loopback.
- SQLite-backed conversation create/read/update/delete.
- Transcript segment append and finalize.
- Local fallback processing for title and overview.
- Local full-text search over conversation and transcript text.
- Local memories, action items, profile, and settings endpoints.
- Desktop routing for local MVP flows without Firebase auth.

## What Still Needs Provider Keys Or Cloud Mode

- Live hosted transcription and Deepgram/Omi transcription endpoints require
  cloud mode today.
- Omi backend provider proxies, quota checks, subscriptions, payments, public
  sharing, Crisp support, managed agent VMs, and cloud sync require cloud mode.
- Remote AI provider calls from the local daemon require explicit local provider
  settings/API keys. Without them, processing uses deterministic fallback output.
- Fully offline local LLM/STT support is outside the current MVP.

## Known Environment Blockers

- `curl /health` cannot connect: the daemon is not running, the port is wrong,
  or another process is bound to the port. Restart with
  `OMI_LOCAL_BACKEND_PORT=<free-port>` and update `OMI_LOCAL_DAEMON_URL`.
- `cargo run` fails before listening: inspect the daemon terminal output for
  Rust build errors or data directory permission errors.
- Import helper reports HTTP 404 for local routes: verify `--base-url` points to
  the local daemon, not the cloud backend.
- Import helper times out waiting for processing: run
  `curl http://127.0.0.1:8765/v1/processing-jobs/status` and check the daemon
  log for processing errors.
- Desktop still calls cloud endpoints: confirm the app was launched with
  `OMI_DESKTOP_BACKEND_MODE=local` and that `OMI_LOCAL_DAEMON_URL` includes the
  daemon port.
- Desktop launch/auth callback issues in custom test builds: keep the app name
  and bundle suffix aligned as described in the repo desktop agent rules.
