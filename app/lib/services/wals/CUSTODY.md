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
   or when a Watch copy is proven redundant (invariant 5), or under the narrowly scoped
   [stranded-orphan exception](#stranded-orphan-reclaim) to INV-CAP-1. Undo on Home's recording bar is a user
   delete: `LocalWalSyncImpl.discardRecording` (`wal_discard.dart`) drops the live tail and the
   WALs of that one recording session, never another recording's. A WAL of it that is uploading
   is not interrupted; it is never picked for upload again and is deleted once that upload settles.
   With PostHog `custody_durable_audio_release` explicitly true, the phone releases an Omi
   safety WAL into synced retention after writer-proved original and manifest receipts cover
   every source ordinal and the independent per-frame digest audit matches the local bytes.
   `audio_custody` supplies independent proof. A `capture_committed` range contributes only
   where explicitly bound to committed original-audio evidence. Legacy transcript-only
   receipts remain readable. The socket owner, device capture root, mono channel, clock epoch
   and supplied recording session must match. A server recording rollover can retain the
   phone session only through an explicit client-session binding on the writer receipt.
   Custom STT sockets do not negotiate receipt release. Gaps, conflicts and unknown mappings keep
   the repair path open. Receipt ranges are journaled durably per owner in shadow and serve.
   In-flight, manual and on-device WALs are excluded. The WAL index must persist synced
   retention successfully. Only the existing retention policy deletes bytes. The existing
   saved-transcript confirmation for a captured Live Custom STT session continues to honor
   the user's upload choice. Unknown/false keeps the existing confirmation behavior.
   `WAL Custody Audit` records aggregate per-frame audit agreement, disagreement, unknown
   proof and persisted receipt releases by build.
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

## Exclusive live conversation cuts

A conversation close uses `finalizeAndSnapshotSession` followed by `stampConversationSnapshot`,
not a later time-range scan. Admission synchronously seals the current frame buffer and reserves
eligible WAL object identities before queued disk I/O. Reserved memory rows cannot extend with
subsequent ingress, and unresolved earlier cuts cannot be claimed by a later conversation. Tokens
are bound to one ledger, owner and account generation; reconstructed rows or another ledger do
not inherit their authority. Generic lifecycle/checkpoint finalization remains separate.

A stamp establishes lineage, not transcript coverage. Existing coverage/receipt confirmation and
retention rules still decide whether a copy leaves Pending. Uncertain Process Now results remain
unlinked and recoverable. `unit/conversation_wal_snapshot_test.dart` covers queue barriers,
post-cut ingress, same-second cuts, owner changes and durable source coordinates; the capture
architecture documents the per-conversation close lifecycle.

## Server contract used

`POST /v2/sync-local-files` with the existing parameters (`conversation_id`,
`recording_session_id`, `audio_start_seconds`/`audio_end_seconds`, capture evidence and geolocation
headers). The server binds by `recording_session_id`, otherwise to the conversation closest in
time, otherwise it creates one. No backend change is needed.

The authenticated mono Listen socket opts in to `audio_custody`. Both receipt types enter
`CaptureCommittedJournal` through the WAL buffer queue. The phone audits each proposed release
against the local length-prefixed frames before applying synced retention. S1 source frame ordinals already in the ledger are sent by
`captureEvidenceUploadHeader` on both batch and single safety-WAL uploads; legacy/unpositioned
WALs omit claims rather than deriving them from wall clock. Batch must apply L1 coverage before
the legacy coverage trim is deleted (plan C, C11).

## Guards

| Invariant | Behavioral guard under `app/test/` |
|---|---|
| 1 | `unit/local_recordings_auto_upload_test.dart` (lib source scan) |
| 2 | `unit/l5_capture_committed_test.dart`, `unit/local_wal_sync_test.dart` (discardRecording), `unit/wal_upload_resilience_test.dart`, WAL reconcile/retention tests, `unit/watch_custody_dedupe_test.dart`, `unit/native_completion_surface_test.dart` |
| 3 | `unit/local_recordings_owner_test.dart` |
| 4 | `unit/local_recordings_auto_upload_test.dart`, `unit/sync_poll_storm_test.dart` |
| 5 | `unit/watch_custody_dedupe_test.dart` |
| 6 | `widgets/phone_custody_home_render_test.dart` (real conversations page) |

## Upload refusals and attention

HTTP 503 `record_capture_pending` asks the app to retain the submitted WALs.
The upload gate applies the response body's `retry_after_seconds` to that recording,
using the WAL upload group (conversation, session, batch family, location).
The body can defer that recording for up to 30 minutes. Local backoff and the
legacy Retry-After header fallback stay bounded to five minutes. WALs without a session
ID are paced by the submitted file names. The wait survives an app restart for
the signed-in account. Automatic and single-file
uploads both respect it. Subsequent sync passes can send the WAL when the
deadline passes, and acceptance clears the backoff.

HTTP 400/413 is feedback for Omi, not a per-recording user repair. The ledger
stores only a closed reason token, HTTP status, first refusal time and last
attempt time. Daily attempts stop seven days after the first refusal, except
`invalid_capture_time`: that reason retries daily during the first week, then
no more than once every seven days indefinitely until accepted. A weekly probe
bounds recurring full-file traffic while allowing a later server rollout to
recover retained audio: at most five full-file probes per rolling 30 days after
the first week (roughly 4–5 times the file size, plus request overhead). Other
reasons keep their existing expiry. Audio and both stored clocks stay intact; after seven days the aggregate still counts the row
as reported. Restart and connectivity wakes respect the same persisted last
attempt. Legacy refused rows start their window at the first recovery attempt.
Each attempt uses one file, under the existing 25-refusal-per-drain cap. Valid
audio keeps priority, with a separate unknown-clock batch after at most 36 valid
batch attempts. This shared budget is checkpointed on waiting WALs in the same owner
index before each valid attempt and resets after an unknown batch enters the
gate, so restarts cannot erase it and unknown backlog cannot monopolize uploads.
Local-only and held custody stay closed to automatic uploads, including refusal
recovery. A held recording may retry a recoverable refusal through Home's
explicit Process now action; the hold and stored clocks stay intact. Deterministic
`too_large`/`too_many_parts` refusals retain their existing no-retry guards.
No install migration, clock reset, or receipt is needed: an unheld old
invalid-date refusal automatically becomes eligible on its next weekly due date.
`OMI_INVALID_CAPTURE_TIME_RECOVERY_OFF=true` restores the seven-day expiry for
this reason without changing any stored state (compile-time, default false).

A framed file of at most four bytes has no audio payload and completes as a
no-op. Larger files, including tiny compressed speech, always retain normal
server decoding/VAD. Refusals emit the registered `WAL Upload Refused` event with
bounded reason and status. `SyncProvider.refusalSummary` exposes count, seconds,
reported count and `userActionCanHelp=false`; refused rows do not enter user
attention or offer Retry. Original audio remains in the full inventory.

The Catching up dates cover the latest contiguous pending run on one local day.
Old uploaded handles contribute dates only after a recent authoritative pending
reply. Completion acknowledges custody; confirmed absence requeues intact audio
through the existing deduplicated upload path. Missing/transient reads alone do
not imply success or renew a pending span. All backlog counts remain available.

Guard: `test/unit/sync_attention_policy_test.dart` and
`test/providers/sync_provider_needs_attention_retry_test.dart`.

## Offline Sync cleanup acceptance (#24783)

- [x] Saved Custom STT coverage uses the recorded session mode, independent of later preferences.
- [x] Covered phone copies enter synced retention; partial, held, on-device and unlinked audio remains recoverable.
- [x] Targeted/grouped and bulk cleanup check selected identities, report retained/unconfirmed entries, and refresh after partial failure.
- [x] Unsupported pending flash-page cleanup retains the row and reports failure; processed-page ACK errors propagate.
- [x] Legacy positional indexes are invalidated after attempted deletion without treating a rejected command as success.
- [x] Regression coverage: `capture_transcript_coverage_test`, `l5_capture_committed_test`, `offline_sync_recording_blocks_test`, and device deletion protocol suites.
- [ ] App release containing the verified fix (tracked separately from source merge).

## Reauthentication recovery (#24777)

The ledger outlives the authentication screen. After Home mounts for an authenticated
session, its explicit local-recordings refresh scans native migration receipts, then
reconciles active, parked and retired inventory for that owner. Only afterward does
Offline Sync refresh its view. Ordinary inventory reads never restore retired rows:
sign-out clears providers before clearing the old UID, so read-time restoration can
republish the retiring account. Refresh work captures the session generation and UID
before awaiting disk access; a successor session cannot adopt that work.

Existing batch rows resolve their legacy/Watch owner before admission. Ambiguous
ownership remains parked with the source audio and migration evidence intact. The
legacy job receipt and quarantine preference survive sign-out; a migrated uploaded
row retains its job ID and hold so the shared reconciler delivers its result without
another upload. Recovery does not change automatic-upload or local-only choices.

- [x] Same-owner cold start and in-session reauthentication restore parked inventory.
- [x] Foreign accounts and unresolved batch ownership remain hidden and recoverable.
- [x] Accepted legacy jobs survive preference clearing and resume as processing.
- [x] Regression suites exercise real WAL persistence, retained bytes and repeated intake.
- [x] Native iOS simulator persistence/reauthentication verification with disposable PCM audio, real preferences and index.
- [ ] Store release and original-customer recording recovery, tracked separately from source verification.

## End-of-recording marker

`CaptureEndDetector` (`app/lib/services/capture/capture_end.dart`) keeps the last time the on-phone VAD heard
speech and reports an end on an explicit stop (`user_initiated`), a lost or removed pendant (`disconnect`), or
when the server-provided silence timer runs out (`silence_backstop`). `CaptureEndReporter` posts it to
`/v2/sync-capture-end` and again when the recording's last sealed file is accepted, so the final copy says no
file is pending. The reporter is an observer: audio up to the end that is still being written or published counts as
pending (`MobileBatchBuffer.pendingJournalCount`), so it waits for the capture lifecycle and never drives it.
This observer reads retained journals from disk, including failed append/seal/publish operations and prior
processes. Losing a writer or replaying a journal cannot erase pending evidence. A retained journal stops
counting only when the ledger reports server acceptance for that file and the current byte length matches
the accepted length; an accepted prefix cannot hide later appends. Unreadable metadata over-counts; an
unreadable directory omits the marker. The index separately counts every unproven row, including transport-only
`synced` copies and terminal refusals. Counts may overlap while registering/replaying; only delay is allowed.
An observation is bound to its account and WAL generation before queuing and rechecked after disk reads:
logout cannot turn an emptied active index into an old recording's zero. This adds no startup index save.
A process-wide append revision also invalidates an observation if capture writes during its asynchronous
disk read; the end stays queued for a later accepted-file wake. Retained torn originals remain pending.
The marker is latency information only. It never seals, uploads, deletes or releases a WAL,
and no custody rule above reads it: a marker that is lost, refused or switched off (PostHog
`upload_end_marker_off`) leaves the server's ordinary wait in place. It is held in memory, so an app killed
before the resend simply takes that wait.

## Standard mobile batch live-ring proof

Automatic Standard batch retains the original BLE header and device at its
routing boundary. Only a complete accepted append observes the shared live
packet counter; a refusal falls through untouched to ordinary capture. A file
never spans two ring incarnations or live sessions. Missing, reordered and
fragmented packets keep the existing fail-closed behavior.

`batch_live_session` is a unique session identity, not a persisted integer BLE
epoch. `live_device_id`, `live_ring_id` and the contiguous live ordinal interval
bind its phone samples to the pendant. At each existing one-second audio fsync,
the journal atomically checkpoints that exact prefix. Seal fsyncs and checkpoints
before publishing. Replay parses and fsyncs complete bytes, preserves at most the
checkpointed ordinal prefix, and persists the recovered WAL index before it can
publish custody. Bytes after the checkpoint remain recoverable without invented
ordinals; a short or inconsistent prefix loses its proof.

Validated mark boundaries are persisted separately as mapping evidence under the
original session identity. They carry no reclaim authority by themselves. The
same mark-pair/contiguous-union implementation combines them with exact indexed
WAL references, including ordinary fallback chunks. Reconnect can complete an
old session proof only against the same ring incarnation, existing phone bytes
and persisted index; old ordinals never enter the new session's tracker. The
custody validator reads the index without journal discovery. Owner/generation
checks still fence publication and commands, and an unproven oldest prefix still
blocks every newer range.

Default-on kill switch: build with `--dart-define=OMI_BATCH_RING_PROOF_OFF=true`
to retain today's batch behavior: no batch counter observation, live metadata,
mapping restoration or new reclaim proof. Audio, upload choice, retry caps,
legacy firmware, Custom STT routing and ordinary live custody are unchanged.
Regression guard: `test/services/wals/batch_ring_proof_test.dart` (also executed
with the real compile-time switch off).

## Orphan audio recovery (stage 1, INV-CAP-1)

Stage 1 never deletes or rewrites audio or sidecars. Its adoption proof does not
license deletion: a local ring receipt, empty index or transport label cannot
supply server confirmation. The separate [stranded-orphan reclaim](#stranded-orphan-reclaim)
exception applies only to complete-census, entirely unreferenced audio with both
clocks older than 67 days (`orphanReclaimAgeSeconds`), under David’s explicit ruling.

The ledger's explicit foreground resume/15-minute recovery pass runs only after
startup admission finishes; headless workers skip it. While live audio is arriving
(a frame in the last minute) the pass runs at most every two hours instead, because
its census walks every Documents file on the UI isolate (`orphanRecoveryDue`); it
still runs, and the delay only defers adoption, never audio retention. The shared read-only
inventory census runs outside the capture queue and includes active, retired,
foreign, main, backup, temporary and quarantined rows, batch journals, native
owner receipts, `.wal-live-receipts` sidecars, legacy jobs/preferences, ring
checkpoint/download refs and capture-committed journals (including temporary
files). A sidecar reserves only its managed basename; missing or unreadable
sidecars leave that audio visible as receiptless, never eligible for adoption
or reclaim. The directory scan examines at most 128 ordinary entries, skips
`staging` and `retired` before the budget, and reports truncation separately.
Unscanned managed names remain receiptless. Unexpected or invalid sidecar
entries are diagnostic and do not invalidate unrelated census results; a sidecar
reserves its basename only after validation and an unchanged-file check.
Receipt publication syncs its containing directories before audio bytes are
written; every audio file is flushed before index admission, and receiptless
audio also syncs the documents directory. A failed barrier leaves that WAL in
memory and emits `WAL Write Receipt` with `directory_sync_failed`. If a
receiptless audio write completed but its directory barrier failed, the file is
removed and the WAL remains unindexed: without a durable owner-bound receipt,
that file cannot be safely retained or admitted. Storage-blocked pendant intake
is bounded at 2,000 buffered frames and reports subsequent drops. After three
consecutive native directory-sync failures, the process opens a fail-fast
circuit. Later custody writes stay in memory while native barrier probes retry
with exponential backoff from 30 seconds up to 30 minutes; disk admission
resumes only after a probe succeeds. Native directory sync runs off the UI
thread. When pending receipts
exist, deleted-account cleanup captures persisted main, backup, temporary and
quarantine index references before account-purge index rewrites, then reuses
that snapshot after WAL readiness. It reads at most 128 receipt entries per
batch and releases the index-writer lock between batches. Pages refresh the
snapshot under the lock only after an index revision change, retaining earlier
references across refreshes; incomplete reference checks retain the audio and
are reported. Empty receipt directories do not trigger an index-reference scan.
Unreadable, invalid, changed or unresolved index, journal, preference or consent
sources prevent adoption. Wrong-typed or quarantined
legacy preference inputs also make the census incomplete; recovery and support
export share one raw, read-only preference snapshot. That snapshot is compared
again at admission. Consent reads never repair unknown types to cloud defaults:
non-string STT settings, wrong-typed policy booleans and archived consent preserve
a hold. Ring checkpoints must match the known version and full range/reference
schema, including batch-session chunks and download receipts; unknown keys,
versions or skipped malformed entries block certainty. Ring receipts reserve
local files; capture receipts are read for owner history, never inferred as a
file-bound server receipt for a rowless orphan.

The local-only classifier assigns working (`.part`, `.torn`, `omibatch*`,
`omimobilebatch*`), receiptless_managed, unparseable, owner_unknown, expired or
recoverable. Receiptless managed audio is retained and excluded from recovery
and reclaim. A complete
mono filename and strict complete length-prefixed frames establish capture time
and duration. Automatic recovery requires a plausible capture time within 58
days (`orphanRecoveryWindowSeconds`), leaving two days inside the server's 60-day
production admission window (`serverSyncLookbackSeconds`, mirroring
`SYNC_BACKFILL_MAX_AGE_SECONDS` since #25677). A dev build against a 30-day dev
server adopts 30–58-day orphans that the server then refuses; the row stays held
as `outsideRecoveryWindow` and its audio is retained, so that mismatch only costs
a refused request. Older audio
stays on disk. Unknown, missing or foreign owners in any custody source, including legacy
pending-file/job preferences, prevent
single-owner proof; at least one index/memory row must prove the current owner.
A capture journal's owner hash must match the current UID. No inference from
filenames or the currently signed-in account overrides historical ownership.

David's superseding ruling (2026-11-17): recovered rows enter plain `miss`
for automatic upload only with single-owner proof, no `onDeviceOnly` or
`holdForUser` row in any current, backup, temporary or quarantined generation
or live/retired/foreign memory bucket, and an account preference permitting cloud
upload. Otherwise `holdForUser=true`. An unavailable history snapshot fails closed to a hold. Optional legacy WAL
policy fields retain the same false defaults as `Wal.fromJson`; a missing/null
optional flag does not assert local-only history. Present non-null invalid flag
types are treated conservatively as local-only. Unknown storage enums, malformed file-path types and disk rows without a nonempty path make the census incomplete; they cannot erase a possible reference. Offline auto-sync off, any durable Custom STT choice (including the pinned
on-device choice), malformed/unknown STT settings, keep-everything-on-device, save-live-hours, active
on-device overflow or the selected local capture route all preserve the hold.
The raw Custom STT document must match the current serialized schema, including
nullable text, port, transport, string maps and response schema fields. Unknown
keys, wrong types or invalid structured values hold even when provider is Omi
and send-raw is true; no coercing parser can silently manufacture cloud consent.
Preferences, memory policy and the kill switch are checked again after budget I/O at admission.
The ruling is recorded in the lane evidence `ruling-2026-11-17-orphans.md`. The hold also overrides the daily
`uploadRejected` retry lane after a refused manual request; a refusal cannot
create automatic consent. `holdForUser` (rather than
`onDeviceOnly`, which blocks `syncWal` even for an explicit action) is the
existing user-controlled path: `LocalRecordingsProvider` lists held rows in
Home, `RecordingListItem` opens the recording sheet, and its Process now and
confirmed Delete actions call the provider's `upload`/`delete`. No new UI is
needed. New recovered rows persist `recovered_orphan=true`; their WAL id is a
stable hash of the original basename, keeping same-second/fractional/collision
files separate in playback/share caches and upload attempts. Source filenames,
device and capture time stay intact. Existing rows retain their legacy ids. Recovery publishes `heldRevision` after its batched save so an open
recordings view refreshes. Manual upload uses the existing ledger/uploader;
if the server rejects a later attempt past its lookback, the existing
`outsideRecoveryWindow` status is persisted, the held row stays visible as
failed, and every audio byte remains retained until explicit user deletion.

At most 200 oldest eligible files enter `miss` custody per pass, at most 400 per
rolling 24 hours, and pending rows across all buckets never rise above 720.
Timestamped reservations fsync to a device-local budget file before row admission; a crash/failure may spend budget
without adoption, conservatively delaying the next pass. A torn budget blocks
adoption; logout cannot clear this budget with account preferences. Each nonempty pass
makes one index save. Generation, foreground, admission, kill switch, references,
source metadata, file size and mtime/ctime are rechecked before committing rows.
An unsuccessful save rolls back unpublished rows by object identity within the
same session; a later pass can retry them. The daily reservation remains spent,
and audio remains untouched. Only successful publication advances `heldRevision`.
Configured directories outside Documents are classified but retained in place,
and excluded before reserving pass/daily budget so they cannot starve eligible
Documents files.
No census or audio decoding runs inside the capture queue. The first census
validates every file's framing; later foreground passes reuse a process-local
positive frame-count cache only when path, size, mtime and ctime are unchanged.
Zero/failed reads are never cached, so transient I/O failure can recover on a
later pass; malformed files are conservatively re-read. Every pass
still performs the full reference/ownership/stat census and recomputes age and
classification. Known Limitless random/sequence, collision and estimated-clock
filename suffixes are parsed without changing the source name; the recovered
row preserves `clockRun`. The server's supported trailing `_uN` collision form
is accepted; a nonce between `clke` and timestamp stays unparseable/retained
because uploading that original name would lose its clock partition.
Age is read again immediately before each admission,
after budget I/O, and a capture outside the current 28-day window is retained.
This cache is derived data, never custody/deletion proof; only
entries in the latest orphan corpus survive, and stop/account reset clears it.
Diagnostics count actual frame-reader calls and cache hits.
Support exports reuse the opaque ledger framing snapshot when available, while
still refreshing reference, owner, stat and age evidence. Only aggregate results
are serialized; the cache never enters diagnostics or telemetry.
Cold scans after a restart still read the corpus; no device-scale timing or memory claim is made. Commit metadata
checks are bounded to 512 other sources plus the 128-entry receipt budget (640
total) and five directories; larger source sets retain everything for a later
supported pass. The automatic drain excludes
held pending rows; a clean-phone plain `miss` follows the existing automatic
drain. Normal server confirmation and retention govern uploaded copies.

PostHog `orphan_audio_recovery_off` is a kill switch: only true stops recovery;
unknown/false keeps it on. This is safe to default on because adoption preserves
all bytes, owner uncertainty retains, local-only history/choices preserve a
hold, and held rows cannot automatically upload. Local caps bound the backlog;
existing server backfill pacing bounds processed-speech cost. This stage makes no storage
reclamation or duplicate-processing outcome claim. `Orphan Audio Recovery` is
one typed aggregate event per pass: class/age counts and bytes, adopted count,
cap/change/reference, commit-time expiry and outside-Documents skips, and a bounded fence result. The diagnostics export's
`local_recording_inventory.orphan_classification` uses the same summary and
never exports paths, basenames, account IDs or per-file entries.
`Orphan Audio Receiptless Custody` separately aggregates receiptless managed
count/bytes, managed-receipt-missing skips, phase, scan truncation and census
completeness for recovery and reclaim; receiptless files count as managed-receipt
skips in both phases and are excluded from age buckets because their capture
metadata is not trusted. It exports no paths, basenames or owners.

Guard: `test/unit/wal_orphan_recovery_test.dart`; startup admission's existing
no-orphan-discovery contract remains separately guarded by
`test/unit/wal_startup_admission_test.dart`.

Consent/custody preference quarantine is an observation of the current store,
not a permanent historical marker: the shared preference-quarantine subsystem
prunes archives after seven days. While an archive exists, it holds consent or
invalidates reference completeness. After pruning, the defined current setting
defaults apply; this pass adds no durable unknown-consent marker. Indexed local-only
or held rows still preserve phone-wide history regardless of preference pruning.

Unreadable index quarantine is custody evidence, not disposable diagnostics.
It intentionally prevents adoption until repaired; do not prune it merely to
make a census complete. More than 640 sources or five directories defers the
bounded commit.
Unknown-owner files are retained, not assigned to the current account or
surfaced as its held rows; `owner_unknown` remains an aggregate diagnostic.

## Stranded orphan reclaim

David's 2026-11-17 ruling item 2 (recorded in chat in
`omi-workspace/data/run-2026-11-17-pendant-diag/ruling-2026-11-17-orphans.md`)
is the authority for the [INV-CAP-1 exception](../../../../product/invariants/pendant-audio-retention.md#explicit-exception-stranded-orphan-audio-older-than-67-days).
Only `LocalWalSyncImpl`'s `wal_orphan_reclaim.dart` may apply it, foreground-only,
after admission. Existing paced recovery wakes invoke reclaim after recovery settles;
there is no startup census, separate timer, uploader or UI.

A complete #25573 census reserves every file named by every current/backup/tmp/quarantined
index generation, live/retired/foreign/held memory row, live receipt sidecar, ring
checkpoint/download receipt, batch journal, native owner receipt and legacy file/job
preference. Working `.part`,
`.torn`, `omibatch` and `omimobilebatch` files stay intact. The filename capture time
and mtime must both be strictly older than 67 days: the 60-day server lookback plus the
7-day `margin_days` of `backend/deploy/storage-lifecycle/retention_contract.json`, so reclaim
never deletes audio the server would still admit or recovery could still adopt. All three
ages derive from `serverSyncLookbackSeconds` in `orphan_audio_classifier.dart`, and a test
fails if the reclaim age is not strictly beyond the recovery window plus that margin. The
2026-11-17 ruling set 45 days on a 30-day lookback; David's 2026-11-18 decision (item 2,
`omi-workspace/data/run-2026-11-18-support-packet/decisions.md`) replaces that premise.
Ambiguous clocks and files outside
Documents stay intact. The deletion predicate is independent of single-owner adoption
proof: multiple accounts do not prohibit reclaim, but any account's reference does.

The census runs off the capture queue. A pass considers at most 200 candidates, in
five-file buffer-queue turns with a yield between turns. Each turn checks session
UID/generation, admission, headless/foreground state, raw legacy preferences, every
source/directory stamp, fresh memory references and file type/size/mtime/ctime.
Legacy pending-file basenames remain reserved across directory/container aliases,
so path-string differences cannot grant deletion. More
than 640 sources/five directories defers. Sources remain immutable; only the Documents
directory stamp is advanced synchronously after our own unlinks. One batch intent is flushed asynchronously before entering the capture queue;
a fresh final revalidation has no await through unlink. Completion
is flushed asynchronously after leaving the queue.

Device-local `Documents/orphan_audio_reclaim/tombstones.json` is a flushed, atomically
replaced ring of the latest 200 attempts (hashed local file/stamp key, bytes, mtime,
attempt time and pending/completed state). It survives account changes and is never
exported. A non-blocking advisory OS lock serializes cooperating processes; the foreground
singleton coalesces calls and headless engines skip reclaim. OS locks do not
serialize isolates in the same process; malformed/oversized
journals stop the pass. Capture-committed lists use the canonical receipt parser
and reject malformed rows or unknown fields before the census can be complete. An interrupted temp never grants permission. Intent is
persisted before either unlink; sidecar is removed before audio, so an interruption
after audio unlink leaves no geolocation sidecar. A pending entry does not authorize
replay: a fresh census and unchanged-file fences are always required. Repeating the
same identity replaces its attempt; absent files do nothing. Completed history ages
out by the 200-attempt bound; uninstall removes the device-local journal.

`orphan_audio_reclaim_off` follows the destructive Watch kill-switch pattern: only
resolved false permits deletion; true, unknown and unreadable retain. It initially
retains until the mobile custody lead enables David's device, then the fleet by
2026-11-24 (within one week). Expand only if census unreferenced count falls by exactly
the deleted count and missing-recording reports do not rise. Setting true stops new
reclaim; deleted bytes cannot be restored. This PR does not create or enable the flag.

`Orphan Audio Reclaim` emits aggregate files/bytes deleted, bounded skip reasons and
pass result; no filenames, paths, owners or tombstones. The account-deletion
`wal_orphan_purge` event sets `reference_scan_incomplete` when a bounded index scan
or purge-snapshot refresh cannot establish complete references, while retaining
uncertain audio. Missing events are unknown,
not zero deletions. Device timing, actual reclaimed space and ramp outcomes require
physical-device acceptance. Guard: `test/unit/wal_orphan_reclaim_test.dart`.
