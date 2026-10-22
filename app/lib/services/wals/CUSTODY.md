# Audio custody on the phone: one ledger, one uploader

Status: contract for the unified-custody change (David, 2026-10-22). It supersedes the separate
"Transcribe Later" upload path in `providers/local_recordings_provider.dart`.

## The rule

Every byte of captured audio that the server has not confirmed lives in exactly one place: the WAL
ledger owned by `LocalWalSyncImpl` (`wals.json` + the `.bin` files beside it). Every upload goes
through that ledger's drain (`SyncUploadGate`, `SyncJobPoller`). Nothing else on the phone uploads
audio, polls sync jobs, or decides when audio may be deleted.

There are exactly three audio paths:

| Path | What | Code |
|---|---|---|
| Live | frames streamed to `/v4/listen` | `services/sockets`, `services/capture` |
| Custody | audio the server has not confirmed, uploaded to `/v2/sync-local-files` | `services/wals` (this folder) |
| On-device | transcripts made on the phone from custody audio, posted to `from-segments` | `services/on_device` (a consumer of custody WALs marked `onDeviceOnly`) |

## Producers (who may add audio to custody)

All producers hand finished, durable files to the ledger through `LocalWalSync.addExternalWal`
after `ensureStorageAdmission`. None of them uploads, polls or deletes on its own.

| Producer | Files | Upload policy | Binding |
|---|---|---|---|
| Live safety copy | frames from the capture session | auto | `recordingSessionId` stamped at creation |
| Pendant ring / multi-file / SD / flash drains | chunks written by `persistDeviceChunk` | auto | server binds by time and device |
| Native recordings (`native_recording_intake.dart`) | `audio_omibatch*` files written by iOS/Android native code | see below | see below |

Native recordings, by marker (the marker is parsed in exactly one place, `BatchRecordingInfo`):

| Marker | Written when | Policy |
|---|---|---|
| `omibatch`, `omibatchphone` | the user chose Transcribe Later | `holdForUser`: never auto-uploaded; the user transcribes it from Home |
| `omibatchphoneauto` | the phone mic had no network | auto |
| `omibatchlimitless` | Limitless flash drained in batch mode | auto (it may be the only copy) |
| `omibatchwatch` | Apple Watch recovery copy, one per minute | dropped when the live safety copy already covers it; otherwise auto |
| `omibatchoverflow` | on-device overflow | admitted by `services/on_device/on_device_overflow_intake.dart` as `onDeviceOnly` custody |

Overflow discovery runs before native migration retires the legacy owners file, and also in
`OnDeviceRunner` (foreground and background). This replaces the old dependency on the Home
provider's scan: keeping that dependency would strand overflow once Home becomes a ledger view.

## Invariants (each has a test)

1. **One uploader.** Only `LocalWalSyncImpl` calls `SyncUploadGate.upload`. A lint-style test
   fails if any other file under `lib/` does.
2. **Delete only on confirmation.** A custody file is deleted only when its upload job completes,
   when the live transcript covers it (`confirmSessionTranscription`), when the user deletes it,
   or when a Watch copy is proven redundant (invariant 5).
3. **Owner before anything.** A WAL's `ownerUid` is set before it is listed, played, uploaded or
   deleted. Watch copies take the owner from their iPhone receipt. Other native files take the
   signed-in uid at intake, the same as every other producer. Once registered, the ledger
   keeps that owner across account changes. During upgrade, an existing legacy owners-file stamp
   is preserved (including parked foreign-account WALs); a malformed owners file defers migration
   rather than reassigning private audio. New ownership is never assigned while signed out.
4. **Idempotent intake.** Registering the same native file twice is a no-op, keyed by file name.
   A file already uploaded under the old path (its job id in the legacy `localRecordingJobs`
   sidecar) is registered as `uploaded` with that job id, so the shared poller finishes it rather
   than uploading it again.
5. **Watch copies are not a second transcript.** The ledger keeps a live-coverage journal: the
   wall-clock ranges of Watch audio that the phone received live and made durable in custody.
   A Watch copy that the journal covers to ≥ 95% is redundant: it is acknowledged (its iPhone
   receipt stays, so retransmission cannot bring it back) and deleted without upload. Kill switch:
   PostHog flag `watch_copy_dedupe_off`; when set, unknown, or unreadable, every Watch copy is kept
   and uploaded. Only an explicitly resolved false enables dedupe. Journal ranges are owner-scoped,
   merged and expire after seven days; they are written only after the live WAL and index are durable.
   Watch live frames are retained even after socket sends (a send is not server confirmation).
   Before judging a new Watch receipt, intake checkpoints the live Watch tail without ending its
   capture session: the 60-second receipt can precede the ordinary 105-second disk flush.
6. **Home shows only what waits for the user.** Home lists `holdForUser` recordings only, one row
   per file. Everything else is visible on the Sync page, as every other custody WAL already is.

## Server contract used

`POST /v2/sync-local-files` with the existing parameters (`conversation_id`,
`recording_session_id`, `audio_start_seconds`/`audio_end_seconds`, capture evidence and geolocation
headers). The server binds by `recording_session_id`, otherwise to the conversation closest in
time, otherwise it creates one. No backend change is needed.

Follow-up for the backend architecture plan (not in this change): a `capture_committed` websocket
event and a coverage query, so the client can release live-covered custody by the server's word
instead of the transcript-coverage heuristic, and the batch pipeline must apply S1 coverage before
the legacy coverage trim is deleted (plan C, C11).

## Guards

| Invariant | Behavioral guard under `app/test/` |
|---|---|
| 1 | `unit/local_recordings_auto_upload_test.dart` (lib source scan) |
| 2 | `unit/wal_upload_resilience_test.dart`, WAL reconcile/retention tests, `unit/watch_custody_dedupe_test.dart`, `unit/native_completion_surface_test.dart` |
| 3 | `unit/local_recordings_owner_test.dart` |
| 4 | `unit/local_recordings_auto_upload_test.dart`, `unit/sync_poll_storm_test.dart` |
| 5 | `unit/watch_custody_dedupe_test.dart` |
| 6 | `widgets/phone_custody_home_render_test.dart` (real conversations page) |
