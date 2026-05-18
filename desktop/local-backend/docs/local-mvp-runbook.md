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

## Start The Local Daemon

From the repo root:

```bash
cd desktop/local-backend
cargo run
```

The daemon listens on `127.0.0.1:8765` by default. To keep test data isolated:

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

## Launch Desktop In Local Daemon Mode

The desktop app selects local mode through environment variables:

```bash
cd desktop
OMI_DESKTOP_BACKEND_MODE=local \
OMI_LOCAL_DAEMON_URL=http://127.0.0.1:8765 \
OMI_PYTHON_API_URL=http://omi-cloud-invalid:9001 \
OMI_DESKTOP_API_URL=http://omi-rust-invalid:9002 \
./run.sh
```

The invalid cloud URLs make accidental cloud routing obvious during a user test.
Local conversation, transcript, memory, action item, settings, and search flows
should use `OMI_LOCAL_DAEMON_URL`.

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
