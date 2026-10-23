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
   fails if any other file under `lib/` does. It also forbids direct `uploadLocalFilesV2`,
   `fetchSyncJobStatus`, and the custody endpoint path outside the ledger and HTTP-client namespace.
2. **Delete only on confirmation.** A custody file is deleted only when its upload job completes,
   when the live transcript covers it (`confirmSessionTranscription`), when the user deletes it,
   or when a Watch copy is proven redundant (invariant 5).
   With PostHog `custody_capture_committed_release` explicitly true, exact server `capture_committed`
   source-frame receipts replace the live transcript heuristic. Unknown/false keeps the heuristic.
   Receipt ranges are journaled durably per owner even in shadow; comparisons emit
   `event=refactor_shadow lane=L5 check=custody_release outcome=agree|disagree`. The union must cover
   the entire WAL in its capture root, mono channel, clock epoch and (when supplied) recording session.
   Gaps, foreign owners, missing ordinals and in-flight/manual/on-device WALs never release.
   A release marks server-confirmed synced retention; only the existing retention policy deletes bytes.
3. **Owner before anything.** A WAL's `ownerUid` is set before it is listed, played, uploaded or
   deleted. Watch copies take the owner from their iPhone receipt. Other native files take the
   signed-in uid at intake, the same as every other producer. Once registered, the ledger
   keeps that owner across account changes. During upgrade, an existing legacy owners-file stamp
   is preserved (including parked foreign-account WALs). A malformed owners file stays intact:
   potentially legacy-stamped files are deferred, with telemetry on each deferral. Intake continues
   for receipt-owned Watch files and non-Watch files whose native creation timestamp AND file mtime
   are newer than the owners file mtime; these cannot have a legacy stamp. Overflow uses the same
   resolver. New ownership is never assigned while signed out.
4. **Idempotent intake.** Registering the same native file twice is a no-op, keyed by file name.
   A file already uploaded under the old path (its job id in the legacy `localRecordingJobs`
   sidecar) is registered as `uploaded` with that job id, so the shared poller finishes it rather
   than uploading it again. Malformed jobs are quarantined once in
   `localRecordingJobsCorrupt`, with telemetry; intake proceeds with an empty job map.
5. **Watch copies are not a second transcript.** The ledger keeps a live-coverage journal: the
   wall-clock ranges of Watch audio that the phone received live and made durable in custody.
   A copy is deleted only with ≥ 95% server-reachable coverage: durable live WALs stamped with a
   `conversationId`, confirmed with `syncedAt > 0`, or `miss` WALs queued for the drain. Transport-only
   `synced` WALs (`syncedAt == 0`, no conversation) prove only local durability. If combined durable
   coverage reaches 95% but server-reachable coverage does not, keep the copy without uploading or
   deleting and re-judge on subsequent scans. After `unboundWatchReceiptTimeout` (30 minutes from
   the iPhone receipt mtime), admit it for automatic upload if still unbound. Uncovered copies upload
   automatically with no session binding. The iPhone receipt stays after deletion so retransmission
   remains acknowledged. Kill switch: PostHog `watch_copy_dedupe_off`; when true, unknown, or unreadable,
   keep and upload. Only an explicitly resolved false enables dedupe. Journal v2 tracks durable and
   server-reachable ranges separately, owner-scoped, merged, with a seven-day TTL; old unclassified
   journals provide no deletion proof. Ranges are written only after audio and index are durable;
   conversation stamping promotes durable Watch ranges before transcript cleanup can remove them.
   Watch live frames are retained even after socket sends (a send is not server confirmation).
   Before judging a new Watch receipt, intake checkpoints the live Watch tail without ending its
   capture session: the 60-second receipt can precede the ordinary 105-second disk flush.
6. **Home shows only what waits for the user.** Home lists `holdForUser` recordings only, one row
   per file, including accepted jobs in the processing state. A manual recording keeps its hold
   until the job completes (or the synchronous result completes); failure leaves the hold in place
   for another explicit retry. Acceptance wakes the shared coordinator to reconcile even when
   automatic uploading is disabled. This replaces acceptance-time release to preserve Home recovery. Everything else is visible on the Sync page, as every other custody WAL already is.

Native batch directory and WAL documents directory must match. A mismatch (for example a stale
absolute path after an iOS update moves the app container) emits `Native Custody Observed /
directory_mismatch`, repoints `batchAudioDir` at the documents directory, and scans there.

Chunked on-device transcript exports freeze their prepared segments, language, duration and optional
projection in the same owner-scoped WAL index before sending the first chunk. A restart reuses
that immutable input instead of running speech recognition again and changing an accepted chunk.
The outbox remains on failure and clears only with the durable conversation result. Flag:
`clients_from_segments_chunks`; guard: `unit/on_device_runner_test.dart` restart test.

## Server contract used

`POST /v2/sync-local-files` with the existing parameters (`conversation_id`,
`recording_session_id`, `audio_start_seconds`/`audio_end_seconds`, capture evidence and geolocation
headers). The server binds by `recording_session_id`, otherwise to the conversation closest in
time, otherwise it creates one. No backend change is needed.

`capture_committed` listen events are consumed by `capture_committed_custody.dart`;
`CaptureCommittedJournal` records each receipt before applying it. `confirmSessionTranscription`
compares exact receipts with the old coverage decision in shadow. The opt-in is identity-fenced and
off unless explicitly true. S1 source frame ordinals already in the ledger are sent by
`captureEvidenceUploadHeader` on both batch and single safety-WAL uploads; legacy/unpositioned
WALs omit claims rather than deriving them from wall clock. Batch must apply L1 coverage before
the legacy coverage trim is deleted (plan C, C11).

## Guards

| Invariant | Behavioral guard under `app/test/` |
|---|---|
| 1 | `unit/local_recordings_auto_upload_test.dart` (lib source scan) |
| 2 | `unit/l5_capture_committed_test.dart`, `unit/wal_upload_resilience_test.dart`, WAL reconcile/retention tests, `unit/watch_custody_dedupe_test.dart`, `unit/native_completion_surface_test.dart` |
| 3 | `unit/local_recordings_owner_test.dart` |
| 4 | `unit/local_recordings_auto_upload_test.dart`, `unit/sync_poll_storm_test.dart` |
| 5 | `unit/watch_custody_dedupe_test.dart` |
| 6 | `widgets/phone_custody_home_render_test.dart` (real conversations page) |
