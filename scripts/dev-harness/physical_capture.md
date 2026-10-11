# Physical capture through the real Flutter app

**Experimental: full physical recovery/upload is unqualified.** The 2026-09-22
session reached rendered onboarding but the capture entry failed before an
accepted WAL sequence. Use the stage/runtime journals to diagnose that entry;
do not treat a signed build or the offline verifier as hardware acceptance.
For verified offline tools and measured scope, start with [the agent guide](IPHONE_HARNESS.md).

`app/integration_test/physical_capture_main.dart` is an AOT app entry point,
not a Flutter widget test and not a replacement for `mobile-session live`.
It calls the shipping `app.main`, resolves its actual `CaptureProvider`, and
uses the production services, bridge, recorder, WAL writer and upload client.
No fake capture dependency, fake Firebase token gateway, or synthetic audio
frame injection is installed. Existing live-session admission is unchanged.

The separately signed app is intended to measure the included capture path. It does not
qualify the ordinary app's distribution signature, push, HealthKit, widgets,
watch extension, Apple sign-in, or other excluded capabilities. The generated
build must retain microphone/Bluetooth consent strings and the audio and BLE
background modes. Installing the ordinary Omi bundle is prohibited.

## Build admission

The entry point requires these compile defines:

```
OMI_PHYSICAL_QUALIFICATION=true
OMI_APP_PROFILE=local_dev
OMI_API_BASE_URL=http://<literal-private-address>:<session-port>/
OMI_FIREBASE_AUTH_EMULATOR_HOST=<literal-private-address>
OMI_FIREBASE_AUTH_EMULATOR_PORT=<auth-port>
OMI_PHYSICAL_FIXTURE_UID=omi-physical-fixture-<run>
OMI_PHYSICAL_CAPTURE_SECONDS=20
```

Use flavor `dev` and profile mode for cold, untethered relaunch. The native
bundle identifier must contain `.capture-qualification.`. The read-only
`omi/physical_qualification` channel verifies the bundle and these three
explicit false Info.plist flags before app-owned networking:

- `FirebaseMessagingAutoInitEnabled`
- `FirebaseCrashlyticsCollectionEnabled`
- `FirebaseDataCollectionDefaultEnabled`

The isolated native build excludes external telemetry plugins. The Dart opt-in
disables their callers, uses private health checks, and rejects nonempty
PostHog/Intercom credentials. A destination allowlist contains Dart HttpClient
requests to the exact API and emulator host/port; it rejects proxies and
redirect destinations outside that set. This is not a general native socket
firewall. The build's native dependency exclusions and endpoint configuration
remain required. Native Firebase Auth stays connected to the genuine local
emulator, with the synthetic UID checked on every boot.

For wearable capture, use a new qualification bundle, fixture UID and API port
with `OMI_PHYSICAL_CAPTURE_SOURCE=wearable`. The production DeviceService scans
and reports `wearable_candidates` to the authenticated collector, containing
a fresh `scan_id` and `{peripheral_id,name,rssi}` records filtered to the actual
Omi service classification. Zero or multiple candidates fail; RSSI never chooses
an arbitrary wearable. The host can approve the sole already-authorized Omi
without asking the user again. Its control response is:

```
{"command":"select_wearable","fixture_uid":"<this fixture>",
 "run_id":"<this collector run>","scan_id":"<this app scan>",
 "peripheral_id":"<sole reported UUID>"}
```

The app requires that exact fixture, fresh scan and sole UUID before calling
the actual `ensureConnection(force:true)`. Both the production connection state
and a native `isConnected()` check must succeed before `wearable_connected` and
`streamDeviceRecording`. The UUID comes from this bundle's native discovery;
a separate probe's identifier is not assumed transferable. An optional explicit
`OMI_PHYSICAL_WEARABLE_ID` remains available when the correct UUID is already
known, but must still match the sole fresh Omi candidate.

Without a wearable source or ID define, the app calls `streamRecording` through
the real phone microphone service. Both choose live stream mode to exercise
the Flutter WAL path; batch fallback is rejected for the phone lane. Durable
capture state records source and fixture UID, and refuses recovery under a
different source or principal. Use separate bundles for separate runs so the
completed phone recording remains untouched.

## Host/device sequence

1. Run the real Auth emulator and the private fixture API. Keep `/v1/health`
   reachable but `/v4/listen` unavailable. This models an unavailable streaming
   backend while the network is reachable; it is not an airplane-mode test.
2. Install only the separate qualification bundle. Host automation handles
   initial consent prompts and can background/lock during the `capturing`
   event. Play the authorized audio fixture for quality checks independently.
3. On first boot, the entry point signs in, starts capture, records for the
   configured duration, stops normally, and finalizes the real WAL. Reporting
   cannot extend the recording window; a failed report, mode rejection, or
   partial-start error still attempts stop and records cleanup failures. It copies
   `Documents/wals.json` and the selected audio files into
   `Documents/physical_capture/before/`, saves the selection in
   `Documents/physical_capture_state.json`, and reports `awaiting_termination`.
4. The host records the bundle, process start identity and observed exit,
   terminates this app, then relaunches the same artifact. An app restart or
   emitted event alone is not host evidence of process death.
5. The new process loads the real on-disk WAL inventory and requires exact
   audio hashes/statuses to match the previous snapshot. It copies the
   `recovered/` evidence and waits for the authenticated host control endpoint
   to return `{"command":"upload"}`.
6. The app uses the production per-WAL upload and job reconciler. The fixture
   API accepts multipart audio at `/v2/sync-local-files`, hashes the received
   file parts, returns HTTP 202 with a job ID, and holds the job queued until
   the `uploaded` event. The local file must remain present in `uploaded/`.
   The fixture then returns `completed`; the real reconciler must mark the WAL
   synced before the app copies `completed/` evidence.

All `/physical-capture/events` and `/physical-capture/control` calls carry
the real synthetic emulator bearer identity. Events contain hashes/byte counts,
not audio or credentials. The collector owns upload permission. It must never
declare STT/audio-quality success from a synthetic completed job.

This sequence verifies recovery of finalized local recordings. It does not
claim survival of an unflushed in-memory tail from a mid-write kill, automatic
iOS restoration after a user force-quit, or background delivery without
separate observed lifecycle and frame evidence. The ordinary capture code
still owns its timers and write policy.

## Offline evidence check

`python3 scripts/dev-harness/physical_capture_verify.py <manifest.json>` checks
copied artifacts only. Success is `artifact_consistency_passed` and always
`hardware_qualified:false`. The actual device operation receipts, source/build
provenance, bridge execution, background timing, and audio-quality measurements
must accompany it before making a hardware claim.

The manifest uses schema `physical-capture-recovery-v1`, fields `flavor`,
`profile`, `bundle_id`, `source_sha` (40 hex), `dirty_input_sha256` (64 hex),
`artifact` (relative path), `artifact_sha256`, `api_base_url`,
`auth_emulator_url`, `synthetic_uid`, `wal_ids`, `lifecycle`, `server_receipt`,
and `before`, `recovered`, `uploaded`, `completed` (relative copied Documents
directories). Each directory includes the production `wals.json` and selected
nonempty `.bin` files; audio is never committed to Git.

The lifecycle JSON records `bundle_id`, distinct `before_process` and
`after_process` identities, `observed_exit:true`, and strictly increasing integer
timestamps `persisted_at_ms`, `terminated_at_ms`, `relaunched_at_ms`,
`recovered_at_ms`, `uploaded_at_ms`, `completed_at_ms`. These are host evidence,
not values to infer from state filenames. The server receipt records
`api_base_url`, `synthetic_uid`, `http_status:202`, `status:completed`,
and exact selected `files` with `filename`, `bytes`, `sha256`, and `job_id`.
Different per-WAL uploads may have different jobs. A single top-level `job_id`
is also accepted when all files genuinely belong to that one batch job.

Hermetic oracle tests: `python3 scripts/dev-harness/physical_capture_test.py`.
Network guard tests: from `app/`, run
`flutter test test/unit/physical_qualification_test.dart`.
