# Local MVP User-Test Runbook

This runbook starts the local daemon and imports transcript data without Omi
hosted backend services. It is the supported MVP path for testing local
conversation storage, transcript ingestion, processing fallback, and search.

## Prerequisites

- macOS with Xcode command line tools installed.
- Rust toolchain with `cargo`.
- Python 3 for the import helper.
- `curl` for health and API checks.
- Homebrew **`webp`** for the desktop Swift build (`CWebP` / screen capture):
  `brew install webp` (verify with `pkg-config --exists libwebp`).
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

### One command from repo root (recommended)

`make serve-local` starts the local daemon and desktop dev app in a tmux session
(`omi-hybrid-local`): top pane runs `cargo run` in `desktop/local-backend`, bottom
pane runs `desktop/run.sh` in hybrid local mode. Teardown: `make down-local`.

```bash
make serve-local    # attach or switch tmux client to omi-hybrid-local
make down-local     # stop tmux session, daemon, and Omi Dev.app
```

If you are already inside another tmux session, `make serve-local` switches your
client to `omi-hybrid-local` (it does not nest sessions). To start without
attaching:

```bash
OMI_HYBRID_LOCAL_ATTACH=0 make serve-local
tmux attach -t omi-hybrid-local
```

The first desktop build can take several minutes while SwiftPM resolves
packages; `run.sh` waits if another `swift-build` is already running on the
machine.

**Troubleshooting `make serve-local`:**

- You still see a different tmux session (for example `local-supergemma`): run
  `tmux attach -t omi-hybrid-local` or `tmux switch-client -t omi-hybrid-local`.
- Bottom pane stuck on `Waiting for other SwiftPM instance`: another
  `swift-build` is running (often Firebase/GRDB package resolve). Wait for it to
  finish or stop that build, then re-run `make serve-local`.
- Daemon port in use after a crash: `make down-local`, then `make serve-local`.
- Verify daemon only: `curl http://127.0.0.1:8765/health` should return
  `"service":"omi-local-backend"`.
- Hybrid providers: `make serve-local` and `desktop/run.sh` (local mode) run
  `desktop/local-backend/tools/seed_hybrid_defaults.sh` when the daemon is healthy,
  seeding `post_transcript`, `proactive`, and `chat` model slots to a local
  OpenAI-compatible account if those slots lack provider accounts. Override with
  `OMI_HYBRID_DEFAULT_CHAT_BASE_URL`, `OMI_HYBRID_DEFAULT_CHAT_MODEL`, and
  `OMI_HYBRID_DEFAULT_PROVIDER_ACCOUNT_ID`.

### Manual `run.sh` launch

For user-test runs without tmux, use one command from the repo root. This launches
the development app bundle only (`Omi Dev.app` / `com.omi.desktop-dev`), checks the
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

- Live transcription in local daemon mode uses on-device Apple Speech when hybrid direct STT is enabled.
  `./run.sh` injects `OMI_HYBRID_DIRECT_STT_ENABLED=1` into the bundled app `.env` for local daemon mode by default (and sets the same in the launcher environment). Disable with `OMI_HYBRID_DIRECT_STT_ENABLED=0` if you need to turn it off.

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

Hybrid local mode does **not** require Apple/Google sign-in for daily use. The app
enters an on-device guest session automatically (`local-hybrid-guest`). Cloud
sign-in remains optional for account UI only; OAuth uses the Python backend and
will not work when `OMI_PYTHON_API_URL` is set to an invalid host (intentional
for hybrid testing).

**Settings → Plan and Usage** shows a **Local** plan (not cloud Free/Neo tiers).
Use that section to configure a local provider account and task slots: Chat,
Post-transcript processing, Proactive assistants, optional Vision, STT/local
transcription, and Memory search: Local wiki. Keys are stored in the local daemon
SQLite database on this Mac. Memory search uses local wiki/FTS search and does
not require `embedding_provider` or vector embeddings for this profile. Cloud
subscription, usage quotas, and the Advanced “BYOK free forever” flow are hidden
in local mode.

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

The desktop app refuses hosted live capture before opening a WebSocket when
`OMI_DESKTOP_BACKEND_MODE=local`. Stopping a capture session in local mode does
not call Python force-process; any locally stored session data is left for the
local retry/import/finalize path with a log entry.

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
different conversation payload for an existing `id`, or a different segment body
at an existing `segment_index`, returns HTTP 409.

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

See [hybrid-provider-settings.md](hybrid-provider-settings.md) for the full
provider-policy schema, default slots, legacy setting-key bridge, and
`POST /v1/provider-policy/test-slot/{slot}`.

Processing works without provider keys by using deterministic fallback. To force
that path, clear the typed provider policy and legacy provider settings:

```bash
curl -X PUT http://127.0.0.1:8765/v1/settings \
  -H 'content-type: application/json' \
  -d '{"provider_policy": null, "ai_provider": null, "provider": null, "chat_provider": null, "vision_provider": null}'
```

To test a direct OpenAI-compatible provider without editing source code, point
the provider configuration at a local stub or a user-managed endpoint. For local
MVP validation, prefer a loopback stub so the test cannot reach hosted Omi or
OpenAI services by accident:

```bash
curl -X PUT http://127.0.0.1:8765/v1/provider-policy \
  -H 'content-type: application/json' \
  -d '{
    "version": 1,
    "provider_accounts": [{
      "id": "local-openai-compatible",
      "kind": "openai_compatible",
      "base_url": "http://127.0.0.1:43210/v1",
      "api_key": "local-test-key",
      "display_name": "Local stub",
      "capabilities": {
        "chat_completions": true,
        "json_mode": true,
        "tool_calls": false,
        "vision": false,
        "speech_to_text": false
      },
      "subscription_integration": null
    }],
    "model_slots": {
      "chat": {
        "provider_account_id": "local-openai-compatible",
        "model_id": "local-stub",
        "options": {"json_mode": false, "tool_support": false}
      },
      "post_transcript": {
        "provider_account_id": "local-openai-compatible",
        "model_id": "gpt-5.4-mini",
        "options": {"json_mode": true, "tool_support": false}
      },
      "proactive": {
        "provider_account_id": "local-openai-compatible",
        "model_id": "gpt-5.4-mini",
        "options": {"json_mode": true, "tool_support": false}
      },
      "memory_search": {
        "provider_account_id": null,
        "model_id": "local_wiki",
        "options": {}
      }
    }
  }'
```

Inspect and validate the active policy:

```bash
curl http://127.0.0.1:8765/v1/provider-policy
curl http://127.0.0.1:8765/v1/provider-policy/resolve/post_transcript
curl -X POST http://127.0.0.1:8765/v1/provider-policy/test-slot/memory_search -d '{}'
```

Provider keys remain in the local daemon SQLite settings table and are sent
directly to the configured provider, not to Omi-hosted backend services.

## What Works Without Omi-Hosted Services

- Local daemon startup on loopback.
- SQLite-backed conversation create/read/update/delete.
- Transcript segment append and finalize.
- Local post-transcript processing through the `post_transcript` slot, with
  deterministic fallback metadata when no provider account is configured.
- Local full-text search over conversation and transcript text.
- Local memories, action items, profile, and settings endpoints.
- Desktop routing for local MVP flows without Firebase auth.
- Signed-in local daemon sessions keep account UI state without cloud startup
  sync: launch/activation do not fetch cloud conversations, assistant settings,
  backend API keys, subscription state, quotas, profile data, managed agent VM
  state, or Crisp support messages.

## What Still Needs Provider Keys Or Cloud Mode

- Live hosted transcription and Deepgram/Omi transcription endpoints require
  cloud mode today.
- Omi backend provider proxies, quota checks, subscriptions, payments, public
  sharing, Crisp support, managed agent VMs, and cloud sync require cloud mode.
- Proactive assistant and chat paths that currently depend on Omi-hosted
  Gemini/Anthropic/provider proxy endpoints are disabled in local daemon mode
  unless the path has direct local provider configuration.
- Remote AI provider calls from the local daemon require an explicit provider
  account and model slot in `/v1/provider-policy` or compatible legacy settings.
  Without a resolved `post_transcript` slot provider, processing uses
  deterministic fallback output and records the fallback reason in job metadata.
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
- `swift build` fails with `cannot change to .../firebase-ios-sdk-...: No such file
  or directory`: Swift Package Manager has a missing or partial git mirror for
  `firebase-ios-sdk` (or `GRDB.swift`) in
  `~/Library/Caches/org.swift.swiftpm/repositories/`. This is unrelated to local
  daemon mode — the desktop app still resolves Firebase for auth even in local
  mode. Stop competing builds, clear the broken mirrors, pre-resolve, then
  re-run `./run.sh`:

  ```bash
  pkill -f 'swift-build|swift-package' 2>/dev/null || true
  rm -rf ~/Library/Caches/org.swift.swiftpm/repositories/firebase-ios-sdk-*
  rm -rf ~/Library/Caches/org.swift.swiftpm/repositories/GRDB.swift-*
  cd desktop
  xcrun swift package resolve --package-path Desktop
  ```

  The first resolve can take several minutes. Do not interrupt it; a partial clone
  leaves SPM pointing at a cache path that does not exist yet.
