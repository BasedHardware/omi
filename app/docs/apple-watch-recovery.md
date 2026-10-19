# Apple Watch audio custody and recovery

Status: proposed implementation for #20479; not a released or physically qualified recovery guarantee.

## Existing behavior and incident boundary

The legacy Watch app sends 1.5-second PCM chunks over WatchConnectivity without
an original audio file. iPhone Offline Sync inventories phone WALs, not the
WatchConnectivity queue. Zero WALs cannot establish that no Watch audio remains.
PR #21072 removed the iPhone's whole-session in-memory copy. It does not add
Watch persistence, survive the receiver's recording-state gate after Stop or
relaunch, or establish recovery of the reported eleven-hour session.

## Pipeline

The live transcript channel stays in place. An independent custody path saves
PCM before live routing into the existing native batch format: 320-byte PCM16
frames, each with a four-byte little-endian length. A session UUID and segment
ordinal prevent collisions between starts in the same second. One-minute
segments bound transfer size to 1,944,000 bytes; start times come from the
original session plus sample position, never delivery time.

`WatchRecordingStore` serializes writes, seals, receipt handling and retries with
one recursive lock. AVAudioEngine conversion runs on the audio callback with
immutable converter inputs; published state and WatchConnectivity callbacks hop
to the main actor. Each callback carries its original archive session token so
old callbacks cannot write into a later recording. Fsync runs every 1.5 seconds
and at seal. Process restart recovers complete frames and an offset-matched
sub-frame tail; torn originals are kept for diagnosis. Sudden power loss may
lose the most recent 1.5 seconds. Capture refuses new writes below 200 MB free,
stops on storage failure, and shows an error. Interruption and missing-frame
checks retire the recording indicator instead of leaving a timer running after
capture has stopped.

The writer copies only its sub-frame tail after consumption: advancing a Data
slice must not retain the whole session's backing allocation. Capture writes,
validation, recovery and digest reads drain their Foundation temporary buffers
within bounded autorelease pools. The native CI guard exercises 90 minutes of
unaligned callbacks plus validation/receipt cleanup with peak RSS below 128 MB.

Interrupted segments recover independently: a corrupt or oversized partial
cannot disable capture or access to healthy recordings. Originals remain on
disk and the Watch reports saved audio needing recovery. If a sealed copy
already exists, the partial is removed only when their digests match.

WatchConnectivity transfers finalized files, with at most four outstanding.
The source remains on the Watch after OS transfer completion. The iPhone's
`didReceive file` handler synchronously validates framing and account ownership,
copies/fsyncs into `batchAudioDir`, then persists a receipt before acknowledging
its SHA-256 digest. The handler works after Stop and process restart without
starting a microphone or bypassing the live recording-state gate. A matching
receipt allows Watch cleanup only after the OS transfer has finished.

The iPhone receipt includes capture ownership and outlives audio processing or
user deletion. Repeated deliveries acknowledge the original receipt without
resurrecting a removed backup. Conflicting bytes or metadata fail closed. The
Dart recordings scanner requires a committed receipt before listing a Watch
backup, so it cannot process a file in the publication-to-receipt interval or
adopt it into another account. Account context is refreshed through the existing
Watch host and carried on immediate start commands. An unbound Watch asks the
user to open Omi on iPhone before capture; queued files owned by a different
account stay on Watch until that account is available.
Only files belonging to the current account enter the transfer queue. Retry
backoff uses monotonic uptime, and least-recently attempted files go first so
missing receipts for a few files cannot starve a long recording's later segments.

## User workflow

Saved recovery copies appear in the existing local Recordings list. They can be
played or processed through its existing upload/job-confirmation pipeline. They
are manual, including when auto-sync is enabled: automatically retranscribing
successful live audio would create duplicate conversations. They remain local
until the user chooses processing or deletion. Originals may span several
one-minute copies; this change does not promise one eleven-hour conversation.
The shared sync coordinator treats a single selected Watch recovery segment as
an explicit keep choice, just like phone Transcribe Later. It restores retained
rule-discarded speech before enrichment; automatic and mixed/bulk sync policy
is unchanged. Silence still produces no conversation.

The Watch shows when saved audio awaits transfer and offers Retry transfer.
Opening the Watch app, session activation, reachability changes and a periodic
retry also resume the queue. Both the iPhone app and its Watch companion need
the new release. Legacy streamed chunks and pre-upgrade recordings cannot be
retroactively reconstructed by this protocol. The format is already supported,
but the Process Now keep rule requires deploying the shared sync backend image
to the processing services as well as releasing both mobile companions.

## Implementation and rollout checklist

- [x] Keep the stateless live relay; no whole-session iPhone buffer.
- [x] Persist before live routing; seal, rotate and recover interrupted writes.
- [x] Session-fence callbacks and stop false recording state on capture failure.
- [x] Retain Watch files until a durable, matching iPhone receipt.
- [x] Accept background files independently of live recording state.
- [x] Deduplicate receipts across restart, processing and deletion.
- [x] Bind ownership before listing, playing, polling or uploading backups.
- [x] Surface pending transfer and an explicit retry on Watch.
- [x] Isolate damaged partials, preserve conflicting originals and fairly retry
  current-account transfers without blocking later segments.
- [x] Preserve explicit Process Now keep intent for Watch recovery speech.
- [ ] Qualify physical paired devices with screen off, phone terminated, phone
  unavailable, disk pressure, account switch, Stop before transfer and at least
  11h06m of capture. Compare sample counts/digests, memory, battery and transfer
  completion, and verify playback/Process Now on iPhone.
- [x] After merging current main, re-verify project membership: `WatchRecordingStore.swift`
  compiles once into Runner, RunnerRayBanDat and omiWatchApp, and `SafeFoundationSinks.swift`
  has no duplicate build entries (`watch_recording_recovery_test.rb` checks the store count).
- [ ] Complete full iPhone build/CI review and merge.
- [ ] Deploy the sync processing backend (fresh/backfill workers and inline hosts)
  before releasing the iOS build that contains the paired iPhone and Watch apps;
  an older backend ignores the explicit Process Now keep rule, so recovered Watch
  speech can fall back to the automatic discard policy.
- [ ] Release the signed iPhone app with its Watch companion.
- [ ] Verify this customer's old server records, crash diagnostics and queued
  legacy transfers using private account ID and exact recording times.
- [ ] Confirm customer recovery or explicitly document which audio could not be
  found. Keep #20479 open until this investigation is resolved.

Do not advise reinstall, reset, unpairing or storage deletion while original
recovery is pending. A new prevention fix does not prove old audio is recoverable.
Apple requires synchronous handling of received temporary file URLs and physical
paired-device testing for WatchConnectivity file delivery:
https://developer.apple.com/documentation/watchconnectivity/wcsessiondelegate/session(_:didreceive:)
