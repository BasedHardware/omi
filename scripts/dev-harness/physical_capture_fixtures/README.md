# Physical capture synthetic fixtures

**Experimental physical workflow.** Fixture protocol tests pass, but the full
real-app recovery/upload sequence has not passed on hardware. See
[status and measured layers](../IPHONE_HARNESS.md).

This explicit standalone API supports testing the real app's capture, local persistence,
and HTTP acknowledgment lifecycle. It does **not** implement the Omi backend,
transcription, or the live-session broker and does not produce session-evidence-v1.
Firebase Authentication uses the genuine Firebase CLI Auth emulator with demo
project `demo-omi-local`. Each API accepts only its explicitly configured fixture
UID. The supported microphone and wearable identities are distinct; neither needs
production credentials or cloud services.

Choose a fresh external state directory and verify the current private address
and unused ports before starting services:

```sh
export CAPTURE_HOST="$(ipconfig getifaddr en0)"
export CAPTURE_STATE="$(mktemp -d /tmp/omi-physical-capture.XXXXXX)"
python3 - <<'PYCONFIG'
import json, os
from pathlib import Path
config = {"emulators": {
    "auth": {"host": os.environ["CAPTURE_HOST"], "port": 19099},
    "ui": {"enabled": False},
    "hub": {"host": "127.0.0.1", "port": 19440},
    "logging": {"host": "127.0.0.1", "port": 19450},
    "singleProjectMode": True,
}}
(Path(os.environ["CAPTURE_STATE"]) / "firebase.json").write_text(json.dumps(config))
PYCONFIG
```

Start each service in its own owned foreground session. Start Firebase from the
external state directory so its debug logs stay out of the repository:

```sh
firebase emulators:start --only auth --project demo-omi-local --config "$CAPTURE_STATE/firebase.json"
```

From the product worktree, start the microphone API (default fixture UID):

```sh
python3 scripts/dev-harness/physical_capture_fixtures/server.py --synthetic-only --host "$CAPTURE_HOST" --receipts "$CAPTURE_STATE/mic"
python3 -m unittest discover -s scripts/dev-harness/physical_capture_fixtures -p 'test_*.py'
```

Verify the current private host address and unused ports before each run. Keep both
processes in owned foreground sessions. Use a fresh external receipts directory
per qualification run; never commit runtime output. API defaults to port 18765,
Auth to 19099. API refuses wildcard/public binds. A matching private interface is
required for phone access. The only outbound API call is ID-token lookup against
that same private host's Auth emulator, with proxies and redirects disabled. Health and fixture custom-token minting
are bootstrap endpoints; capture events, control, and uploads require the fixture
principal's emulator ID token.

The app POSTs metadata to `/physical-capture/events`. A `recovered` event plus independent host approval permits
uploads; prior upload attempts return 503. After independently checking process
death and copied-file equality, the host writes `host-upload-approved.json` into
the receipt directory with exactly the `command` value `upload` and the
`fixture_uid` and `run_id` copied from that API's current `run.json`.
No remote endpoint can issue this approval. Each API start mints a new run ID,
so stale approval files and jobs cannot authorize the new run. Multipart `/v2/sync-local-files` returns
202 only after a hash/byte-count receipt is flushed and fsynced. Job polling stays
queued until the app emits `uploaded`, then returns synthetic completion with no
memories. No uploaded audio is persisted: multipart parsing occurs in bounded
memory (32 MiB request maximum, 64 files maximum). `/v4/listen` returns 503 so the
real stream's offline WAL path runs. Unknown routes return errors.

Receipt files contain only metadata, filenames, byte counts, hashes, timestamps,
and synthetic acknowledgment identifiers. These are independent fixture receipts,
not proof of transcription or production backend durability. Authentication
emulator state is ephemeral, and control state resets on API restart. Restart both
processes and choose a new receipt directory for another qualification.

Each completed job poll produces `completed-<job_id>.json` with per-file
`filename`, `bytes`, `sha256`, and `job_id`. Concatenate their `files` arrays
for the device verifier only after checking every expected job completed.

## Wearable isolation and exact selection

Start an independent API with `--port 18766 --fixture-uid
omi-physical-fixture-wearable-20260922` and a separate receipts directory. It can
share the same Auth emulator; it accepts only its own fixture principal. Never
restart or reuse the microphone API's state when beginning wearable work.

Authenticated `wearable_candidates` events contain `scan_id` and `candidates`
(`peripheral_id`, `name`, integer `rssi`). Selection requires exactly one candidate
from the latest scan. The host writes `host-wearable-selected.json` in the wearable
receipts directory, containing exactly:

```json
{"command":"select_wearable","fixture_uid":"omi-physical-fixture-wearable-20260922","run_id":"CURRENT_RUN","scan_id":"LATEST_SCAN","peripheral_id":"EXACT_SOLE_CANDIDATE"}
```

Authenticated control requests receive that command only when every value
matches. A newer scan invalidates an earlier selection. `wearable_connected`
events must match the approved scan and peripheral. Selection does not approve
upload: recovery still requires the independent `host-upload-approved.json` with
the wearable principal and current run ID. BLE metadata is recorded; audio is not.

The server stamps its current run ID into each saved event. The host collector
requires that ID and the API/auth endpoint identity from `run.json`; file
timestamps alone are not event provenance.

Host collection: [physical_capture_collect.md](../physical_capture_collect.md).
