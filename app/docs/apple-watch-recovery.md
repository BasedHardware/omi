# Apple Watch audio custody and recovery

Status: durable custody merged in #22059, current Home policy merged in #23288,
and control cleanup proposed in draft #23280. Public release and physical Watch
qualification are not established by these merge states.

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

Current main uses the shared custody ledger described in
[CUSTODY.md](../lib/services/wals/CUSTODY.md). Watch recovery copies enter Offline
Sync as automatic WAL work. Home lists only explicit user-held recordings, such
as Transcribe Later; it does not list every Watch minute copy. The previous
manual-only Watch backup policy has been superseded by #23288. Copies without
sufficient live coverage upload automatically. Deduplication can remove a copy
only after the ledger proves server-reachable coverage; locally durable but
unconfirmed live audio is not deletion proof. The durable iPhone receipt remains
so a later retransmission is acknowledged without recreating the backup.

Explicit Process Now keeps the user's intent through the shared processing
pipeline. Silence can still produce no conversation. Original files may span
many one-minute parts; this protocol does not promise one eleven-hour
conversation. Neither a zero-pending phone inventory nor the new custody flow
establishes recovery of an older missing recording.

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
- [x] Complete full iPhone build/CI review and merge for #22059 (merged
  2026-10-20); physical paired-device acceptance remains separate.
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


## Visible Stop and microphone cleanup (#23275, PR #23280)

The active Watch control is a labelled native Stop recording button. It stays
visible while recovery transfers wait; Retry transfer remains a separate action.
At accessibility text sizes the Stop title uses the full button width so words
remain readable. The 40 mm layout fits both controls; the stopped-state Record
target is 44 pt when recovery status is present so Retry also fits. The stopped
state offers Record and retains saved-audio status. Recovery status never gates the recording control.

The recorder validates its original start attempt after permission before
activating AVAudioSession. Stop retires that attempt, removes the installed tap,
stops the engine, releases converter resources and deactivates the audio session.
Failed startup takes the same cleanup path and seals any admitted archive.
Late permission answers cannot activate capture after cancellation or adopt a
newer start. Audio-session and permission closures are native I/O seams; their
production defaults preserve the real AVFoundation calls.

Home recovery presentation is owned by the shared custody pipeline merged in
[#23288](https://github.com/BasedHardware/omi/pull/23288), rather than a second
provider scanner or a Watch grouping projection. Watch minute copies are
ordinary automatic WAL work and appear in Offline Sync; Home shows only
explicit user-held recordings. Proven redundant Watch copies follow the
existing server-reachable coverage policy in [CUSTODY.md](../lib/services/wals/CUSTODY.md).
The earlier proposed Home grouping has been removed after integrating current
main, so it cannot conflict with that pipeline or change its retention policy.

This follow-up adds no backend/firmware/API contract and requires an iPhone
release with its Watch companion after merge. A merged custody change is not
proof that the corresponding public store binary has shipped.

### Controls and microphone checklist

- [x] Native Watch target compiles and the 40 mm render shows Stop and Retry.
- [x] Seven real view-model lifecycle cases pass in the Watch simulator with
  synthetic permission/audio-session I/O; no microphone is opened by the probe.
- [x] Native custody/presentation/relay regressions pass (24 tests).
- [x] Integrate main's canonical custody pipeline without adding a second
  Home projection or changing file retention and upload ownership.
- [x] Previous head passes analyzer ratchet, 23 selected journeys and 30
  preflight checks; current-main analyzer ratchet also passes.
- [x] Additional simulator inspection catches and fixes the 40 mm stopped-state
  Retry clipping; active/error/accessibility text states retain a visible Stop.
- [x] Previous head `9811d2d534` passes full app checks (7,092 passed,
  four skipped), the separate 138 protected contracts, and remote iOS compile,
  Dart/analyzer, generated-file and static checks. These precede the current
  main integration and are not final-head verification for it.
- [x] Physical iPhone 16 Pro, iOS 27.0.1: separate Personal Team-signed QA host
  runs the unchanged production recorder/view/store with real AVFoundation.
  The bounded 70.46-second run crosses a minute boundary, stops, reports one
  successful audio-session deactivation and no deactivation errors, validates
  retained frames, and finds unchanged file sizes after two seconds. Result UTC:
  2026-10-23T03:50:31Z. A prior QA part remains in the sandbox; the reported three
  parts are not all attributed to this run. This is an iPhone-host result, not a
  Watch, physical Stop-button tap, microphone-indicator or transfer qualification.
  The battery adapter is a no-op; no production app/account or backend is used.
- [x] Subsequent physical-iPhone manual Stop run reports valid stable files and
  zero deactivation errors (result UTC: 2026-10-23T03:56:27Z). Aryan confirms:
  "Timer stops; microphone indicator disappears." This qualifies the visible
  control only in the iPhone QA host, not on physical watchOS.
- [ ] Repeat affected checks and final CI after current-main integration and
  removal of the superseded Home grouping.
- [ ] Keep the PR in draft until physical paired-device acceptance and required
  final checks pass. The simulator does not support WatchConnectivity file
  transfers; a harness receipt roundtrip is not an OS-delivery acceptance test.
- [ ] Merge, then release the signed iPhone app with the updated Watch companion.
- [ ] Qualify on paired hardware: Stop must remove the microphone indicator with
  the phone reachable and unavailable, during pending transfers and after screen
  off/resume. Confirm saved parts still transfer and the iPhone shows a Home
  view without one-minute backup rows; original retained audio remains accessible
  in Offline Sync. Simulator closure tests and screenshots do not establish
  physical microphone, radio or background behavior.

Reproduce the native policy probe in the CocoaPods Ruby environment:
`ruby app/ios/test/watch_recording_controls_probe.rb --device <booted-watch-uuid>
--output <temporary-output-directory>`. It compiles the actual production view,
recorder and store with the synthetic app under `app/ios/test/fixtures/`.
The earlier synthetic iPhone grouping fixture has been retired with its superseded
projection. Actual Home and native-intake verification uses the shared custody
pipeline's existing contracts and simulator fixture.
