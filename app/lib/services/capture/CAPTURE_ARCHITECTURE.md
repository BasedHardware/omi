# Capture Coordinator Architecture

`capture_coordinator.dart` is the single ownership authority for capture in the
app. Phone microphone capture, pendant (BLE device) capture, and Omi calls can
never own capture concurrently: every ownership decision is a pure reducer
transition over an explicit phase model, and every side effect is an ordered,
awaited port call or staged body.

Related documents:

- `OWNERSHIP.md` — the C1 seam contract and injectable fakes.
- `CAPTURE_POLICY.md` — the durable capture-policy (mute) admission contract.
- `capture_session_owner.dart` — generation/foreground/recovery authority.
  The coordinator deliberately does **not** duplicate it: `CaptureSessionOwner`
  stays the fence for stale callbacks and app-lifecycle recovery.

## State model

`CaptureCoordinatorState` is immutable. Every transition produces a new value
via `copyWith`; `suspended` and a `CaptureTransition`'s `effects` are frozen
with `List.unmodifiable` at construction.

### `CapturePhase`

Exactly one phase is active at a time:

| Phase | Meaning |
|---|---|
| `idle` | No source owns capture. |
| `pendantLive` / `pendantPaused` | Connected pendant streaming in realtime mode; paused is the user device-mute. |
| `pendantBatchLive` / `pendantBatchPaused` | Pendant in Transcribe Later; the native writer owns the audio under the shared policy. |
| `phoneLive` | Phone mic live: `PhoneMicSource` + WAL + socket. |
| `phonePaused` | Phone mic released; **socket and recording id are kept** (see invariants). |
| `phoneBatchLive` / `phoneBatchPaused` | Phone mic Transcribe Later; native recorder writes `.bin` directly. Paused drops packets into the same file. |
| `callActive` | An Omi call holds the channel; the previous owner is suspended. |
| `audioInterrupted` | OS audio interruption over a live phone session. The phone stays owner; native recovers. |

### `ActiveCaptureSession`

The session a phase runs: `source`, `mode` (`live`/`batch`), `sessionKey`
(fresh per ownership session, from the monotonic `sessionSeq`), `recordingId`
(the client conversation id, folded in once minted), and the device identity
when pendant-owned.

### `SuspendedCapture` — LIFO stack

Typed suspension entries: `source`, `wasPaused`, `reason`
(`SuspendReason.phone` / `SuspendReason.call`), `recordingId`, device identity
and mode. `suspended` is a stack; resume pops the most recent pendant entry.
A pendant suspended for the phone processes its conversation **before** the
phone session opens; a pendant suspended for a call preserves its conversation
id and only resumes if the user had not paused it.

If the phone stops or finishes while a call is still active, its phone-reason
suspension converts to a call suspension: `wasPaused`, device identity and
mode are preserved, but the session identity is cleared — the phone takeover
already ended that conversation — so the call-end resume mints a fresh
recording id. A call suspension that was never taken over keeps its session
identity and resumes without a roll. A call that *starts* over a held
phone-reason debt (`awaitingPhoneResume`) does none of that: it only flags
`callActive`, the phone debt and its awaiting marker are untouched, the call
end releases `callActive` without popping them, a `PhoneStartRequested` while
the call holds is refused outright (`result: false`), and a
`DeviceStartRequested` during the hold refreshes the pendant's identity
without resuming audio — only an explicit later phone start/stop resolves the
debt. Repeated
call-start or reconnect events
while a call already holds add no debt, a repeated pendant start under an
owner only refreshes the suspended entry's device identity, and a suspension
with no live taker is dropped rather than stranded on idle.

### Flags

- `connectedDevice` — last pendant identity reported by the device provider.
- `callActive` — event mirror of the Omi call state.
- `micInterrupted` — native phone-mic interruption mirror, kept separate from
  `phase` so a paused session stays paused across interruptions.
- `mutedBeforePhone` — policy a phone recording started under; restored on a
  user stop so stopping the phone never leaves the next source paused.
- `awaitingPhoneResume` — marks a pendant suspension debt that a
  `PhoneStopRequested(userStop, resumeSuspendedPendant: false)` deliberately
  kept for the known next phone start/stop cycle (the speech-profile
  temporary-stop flow). Serialized and strictly parsed; preserved across
  unrelated settings, call, and device-identity notifications; cleared by the
  next admitted phone start, a normal stop/finish that consumes the debt, a
  pendant disconnect, or launch sanitization. A phone start that fails over
  this held debt fails closed *with the original debt and flag kept* — the
  retry stays possible — instead of stranding the pendant; failures of
  unrelated transitions still fail closed fully.
- `lastFailure` — diagnostics for the fail-closed commit.

## Events

`CaptureEvent` is the only way in. Public `CaptureController` APIs and every
listener callback dispatch events; nothing else mutates ownership.

User/API intents: `PhoneStartRequested`, `PhoneStopRequested`,
`FinishRequested`, `PauseCaptureRequested`, `ResumeCaptureRequested`,
`OfflineMuteToggled`, `DeviceStartRequested`, `DeviceStopRequested`,
`DeviceUpdated`, `PhoneBatchStartRequested`, `DevicePauseRequested`,
`DeviceResumeRequested`, `BatchModeSetRequested`,
`TranscriptionSettingsChanged`, `RecordProfileChanged`,
`OnboardingBatchChanged`.

External signals: `CallStateChanged`, `MicInterruptionChanged`,
`NativeMicStalled`, `AppForegrounded`, `SocketClosed`, `SocketConnected`,
`SocketError`, `KeepAliveTick`, `LaunchRecovery`.

## Effects and ports

The pure reducer is public and independently callable:
`transitionCapture(state, event, env)` returns a `CaptureTransition` with
immutable `state` and `effects`, so deterministic tests can exercise every
transition without instantiating ports. Effects are executed in order, each
awaited, against `CaptureEffectPorts` — one method per primitive:

| Port | Production wiring |
|---|---|
| `writePolicy(muted)` | `_setCaptureMuted` durable admission write; returns `PolicyWriteOutcome` and a superseded policy aborts the rest of the transition. |
| `stopBleStream` / `startBleStream` | `_closeBleStream` / `_initiateDeviceAudioStreaming`. |
| `openSocket(spec)` / `closeSocket(reason)` | `_initiateWebsocket` / `_socket?.stop`. |
| `startNativeMic(mode)` / `stopNativeMic()` | live → `_resumeMicRecording`; batch → `_startPhoneMicBatchBody`; stop → `_phoneMic.stop()`. |
| `setNativeWriterGate(source, admitted)` | `CaptureNativeWriterGate` interface. **Interface only**: no native per-source gate exists, so production uses `NoopCaptureNativeWriterGate` and batch handoffs stay refused rather than silently unsafe. |
| `finalizeWal` | `_wal.getSyncs().phone.finalizeCurrentSession()`. |
| `rollSession(identity)` | `_rollCaptureSession`. |
| `mintRecordingId(sessionKey, source)` | completes the previous telemetry id (`session_roll`) then `_recordingTelemetry.prepare`; returns the fresh id folded into the session. |
| `checkPhonePermission()` | OS microphone permission request, run once as the first effect of any phone start; its result is handed to the start stage so the body never prompts a second time. |
| `clearPhonePermissionGrant()` | Resets the prefetched grant (`_prefetchedMicPermission`). Called in `_run`'s `finally` after every transition — a denied, superseded, or failed start never leaks a grant into the next event. |
| `readSnapshot` / `persistSnapshot` | shared-preferences snapshot store; persist is the last step of a safe transition, skipped when the encoding is unchanged. |
| `runStage(stage)` | the staged-migration seam, below. |

`BleStreamStart`, `WalFinalize`, and `WalSessionRoll` are defined effects with
dispatch arms, but **no reducer currently emits them** — pendant stream opening
and WAL finalize/roll still happen inside staged bodies. The arms exist so the
port contract is complete when those bodies decompose; they must not be treated
as live paths. `NativeWriterGate` *is* emitted, into a no-op gate (see
invariants). `currentRecordingId` was removed from the port seam: minted ids
come only from `MintRecording`, and staged bodies no longer mint on their own.

## Staged migration seam

Composite transition bodies that are not yet decomposed into port calls run as
`CaptureStage`s through `runStage`, in reducer order, inside the same dispatch.
They are the legacy side-effect bodies extracted to private controller methods
— never a queued public API (which would deadlock).

Moved to pure reducer + ports: phase/ownership decisions, suspension stack,
policy writes, socket open/close ordering, BLE stream **stop** ordering,
native mic start/stop ordering, recording-id minting, snapshot persistence.
BLE stream *opens* and WAL finalize/roll are **not** reducer-emitted yet —
they still run inside stage bodies (`_initiateDeviceAudioStreaming`,
`finalizeCurrentSession`, `_rollCaptureSession`), so the "ordering" guarantee
for them is the staged-ownership guard, not the effect list. C1 compatibility
exceptions remain: `updateRecordingDevice` publishes only the synchronous
display identity (`_recordingDevice`) for provider readers before its queued
`DeviceUpdated` runs — the session-generation roll and offline bookkeeping
stay inside the queued `UpdateRecordingDeviceStage`. Because display identity
moves eagerly while the roll waits on the queue, a same-id disconnect/reconnect
pair can land *inside* a held event's await: the token still reads current and
the device id matches. `_deviceIdentityRevision` closes that window — it bumps
synchronously on every `updateRecordingDevice` notification (and again at the
queued identity commit) and is captured/rechecked across awaits in the pendant
socket/BLE open paths (`_reconnectDeviceCaptureBody`,
`_ensureDeviceSocketConnection` codec + STT resolver,
`_transcriptionSettingsChangedBody`, `_initiateDeviceAudioStreaming` before any
native config or BLE subscription, and the `_initiateWebsocket` →
`_openTranscriptionSocket` → `_publishTranscriptionSocket` chain whenever the
attempt began pendant-owned). A stale attempt stops only its own socket — never
the installed one. The revision fence covers *opens*: inside an
already-installed BLE bytes subscription the per-frame admission is narrower —
frames are dropped only when the controller is disposed, the policy revision
moved, or the recording device *id* actually changed — so a same-id device
refresh or metadata normalization never starves a stream it cannot invalidate.
A *different*-device identity change mid-open can leave the old
characteristic's subscription installed until `_closeBleStream` runs; the
installed frame guards already drop its bytes by device id and policy, so the
residual subscription never reaches a new socket's traffic.

One strictly test-only compatibility lane exists on top of that fence:
`reconnectActiveCaptureForTesting` dispatches `KeepAliveTick(testingProbe: true)`.
Concurrent probes coalesce onto the first in-flight probe's dispatch future
(`_testingProbe`), so overlapping callers observe one reconnect. The probe
carries `testingProbe` through `ReconnectDeviceStage` into
`_reconnectDeviceCaptureBody`, where — and only there — a pre-coordinator
fixture that attests `RecordingState.deviceRecord` while the committed phase is
still `idle` is admitted alongside `pendantLive`; `callActive`, any phone
ownership, and a live pendant suspension still refuse even under the probe. The
method also holds `_testingReconnectProbeDepth > 0` for its duration, and only
while that depth is held *and* the committed phase is `idle` (no coordinator
owner — the pre-coordinator fixture world) does `updateRecordingDevice` retire
the session generation synchronously, so the contract test can assert
`isCurrent(before) == false` before the queued `DeviceUpdated` runs. Under a
committed pendant/phone/call session the queued roll stays the only retirement —
the revision fence alone blocks the stale continuation. Production never sets
the depth, never probes, and never rolls synchronously: real keepalive ticks,
transcription-settings reconnects, and call paths always require committed
`pendantLive` plus a current generation; `onClosed` still mutates
three flags at callback time — `_keepAliveEpoch++` invalidates any keepalive
reconnect attempt in flight for the now-dead socket (a tick can fire between
the close callback and the queued `SocketClosed`, so the epoch must move
before dispatch), `_socketCloseQueued` lets `keepAliveScheduledForTesting`
observe a queued close without pumping the event queue (existing
reconnect-test contract), and `_transcriptServiceReady = false` drops
readiness immediately because the keepalive tick and reconnect gates read it
synchronously while the dead socket object may still be non-null. Everything
else — status reset, wedge completion, interrupted-state publish, snackbar,
reconnect-pending mark, `_startKeepAliveServices` — runs inside
`_socketClosedBody` under dispatch. `onConnected` is fully queued: the
interrupted→record/deviceRecord restore and the mic restart live in
`_socketConnectedBody`, guarded by staged live ownership. None of these paths
opens a capture source; their remaining bookkeeping belongs in the
coordinator admission fence during the next seam extraction.

### Synchronous surfaces that remain outside the reducer

| Surface | What it still does synchronously | Why it stays |
|---|---|---|
| Mic `onRecording`/`onStop`/`onInitializing` callbacks | Mirror native mic state into `recordingState` (admission re-checked via `_admitsCapture`). | They are native state *mirrors*, not ownership decisions; the coordinator owns start/stop ordering. |
| `_setCaptureMuted` pause mark | Writes `RecordingState.pause` inside the `writePolicy` port, only after the durable write is confirmed unsuperseded. | Same-execution ordering is required so a superseded write never leaves a phantom pause mark. |
| `changeAudioRecordProfile` | Reopens the transcription socket with new codec params. | Called only inside stage bodies; never emits `SocketOpen` itself. |
| `startNewOfflineRecording` | Sets `batchCutRequested` + resets offline-session bookkeeping. | A native-writer marker preference, not an ownership change; the batch session stays owner. |
| `dispose` | `_rollCaptureSession('disposed')`, telemetry complete, keepalive cancel, socket unsubscribe. | Dispose denies new dispatches; teardown is outside the event contract. |
| `systemAudioRecord` keepalive lane | Read by `_shouldReconnectTranscriptionSocket`/reconnect bodies. | macOS system-audio lane shares the socket but is not coordinator-owned yet. |
| `setBackgroundModeEnabled` | Writes native-streaming prefs directly. | Preference/config management; does not start or stop a capture owner. |
| `recordingState` ownership reads | Reconnect gates (`_shouldReconnectTranscriptionSocket`, `_reconnectDeviceCaptureBody`) consult the legacy mirror alongside the staged phase. | Compatibility while the mirror still feeds UI; guarded by staged phase checks. |
| `onClosed` sync flags | `_keepAliveEpoch++`, `_socketCloseQueued`, `_transcriptServiceReady = false`. | Documented above — the callback-time window a queued event cannot close. |
| Stage-internal socket/BLE/WAL | `_initiateWebsocket`, `_initiateDeviceAudioStreaming`, `finalizeCurrentSession`, `_rollCaptureSession` run inside `RunStage` bodies behind staged-ownership guards. | The defined `BleStreamStart`/`WalFinalize`/`WalSessionRoll` effects are not emitted yet; extraction continues in a later seam. |

Still staged bodies (`RunStage`) in `CaptureController._runCaptureStage`:
device session start/stop/update, pendant suspend/resume tails, phone session
start/stop tails, restore-marker writes, frame flush, recording-state marks,
conversation processing, socket reconnect logic, mic interruption/stall
recovery, batch-mode/settings/onboarding tails.

## Dispatch semantics

`dispatch(event)` is serialized FIFO:

- Queued events run one at a time; effects are awaited fully before the next
  event is dequeued, and events arriving during awaited effects join the queue
  normally.
- One event's failure does not poison the queue: the failure completes that
  dispatch's outcome and the loop continues.
- **Publication order**: effects run against a staged internal state
  (`stagedReadModel`) while the committed `readModel` still shows the previous
  owner. The new owner is published only after every effect completes, so no
  listener can observe pendant ownership while the phone transport is still
  closing — and `finish` runs `ProcessConversationStage` while the published
  owner is still the phone.
- Effect failure **fails closed physically, not just logically**: before the
  safe-idle commit the coordinator best-effort denies both native writer
  gates, stops the native mic, stops the BLE stream, and closes the socket.
  Then `failedClosed` (idle, `lastFailure` recorded) is committed, the
  snapshot is persisted, and the outcome carries the original error.
  `throwIfFailed()` rethrows it for callers whose legacy contract threw.
- A stage may convert a failure into its legacy user-visible path by returning
  `CaptureStageFailure` — state still fails closed, the caller sees the
  historical non-throwing completion (`absorbed`).
- A `PolicyWrite` that comes back `superseded` (a newer out-of-band intent won
  the policy revision) abandons the rest of the transition. If no effect had
  run yet the dispatch normally keeps the pre-transition state and reports
  `false` (the legacy `stopStreamRecording` supersede contract). Over a
  committed `phoneBatchPaused` or `pendantBatchPaused` session the outcome
  depends on the newer intent's effective policy, re-read after the lost
  write: a still-muted policy is already safe — the paused writer stays
  closed in its file and the dispatch keeps the committed state, `.bin`,
  identity and debt untouched. An unmuted effective policy means shared
  admission opened under a live native batch writer, so the transition fails
  closed — writer gates denied, mic/BLE stopped, socket closed, mute `true`
  restored after the deny (a superseded or failed safety mute changes nothing
  physically; it never reopens hardware) — and the session-cleanup stage the
  early return skipped still runs best-effort before the safe commit:
  `StopPhoneBatchStage` for a phone-batch stop/finish, `StopDeviceSessionStage`
  and `DeviceStopTelemetryStage` for a pendant disconnect, `SuspendPendantStage`
  for a call start. A transition that had already latched `callActive` — a
  phone stop under a call, or a call starting over the paused pendant —
  keeps the call phase and its converted call-reason suspension instead of
  idle; without a call, a `phoneBatchPaused` failure keeps its phone-reason
  pendant debt with `awaitingPhoneResume` for a later explicit stop. If
  physical effects already ran the transition fails closed, since neither old
  nor target state matches the physical world anymore.
- Snapshot persistence is required durability: the snapshot of the target
  state is written before the in-memory publish, and a failed write fails the
  transition closed (physical deny + safe idle) exactly like an effect failure.
  A reducer/environment exception happens before any effect could have run,
  so it reports the error on the unchanged state instead of tearing hardware
  down. A state-neutral event does not write at all: the encoded target is
  compared against the last persisted encoding (seeded from the on-disk
  snapshot at launch, and from the sanitized state when restore resets
  ownership) and the write is skipped when they are identical — a redundant
  no-op write can never fail a transition closed.
- `CheckPhonePermission` is the admission preflight for every phone start
  (live and batch) and for a live-phone batch-mode roll — rolling a running
  phone session between live and batch re-opens the mic, so the permission
  check runs before `BatchModeStage`, `MintRecording`, and
  `StartPhoneSessionStage`; toggles that roll no phone session never prompt.
  It is always the first effect, before any teardown,
  suspension, policy write, mint, or hardware start. A `false` result abandons
  the transition with the committed state untouched and the outcome `false` —
  deliberately *not* fail-closed, because nothing physical has changed. An
  *effect* failure after the preflight follows the normal fail-closed path,
  and a pendant this dispatch itself suspended for the takeover is recovered
  **inside the
  same pump**: after the physical deny and safe-idle commit, the suspended
  policy is restored (`writePolicy(wasPaused)`, re-checked for supersede) and
  a nested
  `DeviceStartRequested` `_run` is awaited — not queued behind events already
  waiting. The dispatch outcome then reports the post-recovery state plus the
  original error; if recovery itself fails, the committed state stays idle.
  Recovery runs only when the failed `PhoneStartRequested` *newly* suspended
  the pendant — failing over a pre-existing `awaitingPhoneResume` debt keeps
  the original suspension and its flag for the next explicit retry instead of
  auto-restarting the pendant — and unrelated event failures never
  auto-recover.
- `failedClosed` clears `active` and the whole suspension stack (plus
  `callActive`/`micInterrupted`/`mutedBeforePhone`) so recovery events can
  start safely; only the monotonic `sessionSeq` and the known
  `connectedDevice` identity survive. The one scoped exception is the held
  phone-reason onboarding debt above: a failed phone start over
  `awaitingPhoneResume` (outside a call) reinstates that single original
  suspension entry and the flag rather than clearing them, and the
  pre-transition policy mute is re-written after the physical deny so a start
  that unmuted admission before failing never leaves it open.
- `dispose()` denies new dispatch (`admitted: false`) and completes what is
  still queued as denied.

## Snapshot

`CaptureCoordinatorState.encode()`/`tryParse()` are a versioned
(`snapshotVersion = 1`) JSON round-trip of the complete logical state —
strict parse, mirroring `CapturePolicy`: wrong types are a format error, never
a silent coercion. Malformed or unsupported snapshots parse to `null` and the
coordinator restores **idle**.

`CaptureCoordinator` restores through `sanitizedForLaunch()`, which always
yields idle: ownership and suspension debt are never resurrected, no hardware
opens during restore, and a persisted phone-pause mute cannot leak into a
fresh launch (the launch-marker path recovers it deliberately). Only
`sessionSeq` survives so minted keys stay unique. The sanitized form is
**not** written eagerly at construction — `_lastPersistedSnapshot` seeds from
the raw on-disk bytes, so the first transition whose target re-encodes
differently persists it inside the serialized pump; a launch that never
dispatches simply sanitizes again next launch.

## Invariants

- At most one source owns capture; suspension is explicit LIFO debt.
- Old stop/deny effects are ordered before new open effects in every
  handoff transition.
- Fresh recording ids for every new source session; phone pause/resume keeps
  its recording id and its socket — a deliberate narrow exception to
  "paused source has no active transport", enforced by also stopping the
  native mic and flushing frames so no audio crosses while paused. Batch
  pause is the wider exception: `phoneBatchLive → phoneBatchPaused` (including
  a user pause taken while `audioInterrupted`) emits only `PolicyWrite(true)`
  — the native `.bin` writer stays open in the same file and the muted shared
  policy drops packets at admission, so `phoneBatchPaused → phoneBatchLive`
  emits only `PolicyWrite(false)`; a `NativeMicStop`/`NativeMicStart` pair
  would finalize the file and mint a new recorder session under the same
  recording id.
- A call during active pendant capture suspends the pendant; a call ending
  while the phone owns capture does not resume it — the phone suspension
  survives until the phone itself stops.
- While a call is active, `PhoneStopRequested`/`FinishRequested` stop and
  process the phone but do not reopen the pendant or restore the shared
  policy: the target is `callActive` with no owner, and the pendant's
  suspension converts to call-reason debt. The call-end transition pops
  exactly one suspension and resumes it.
- A pendant suspended purely for a call keeps its conversation id across a
  reconnect; one whose conversation a phone takeover already ended resumes
  post-call under a fresh minted id. `finish` always processes the phone
  conversation before the pendant may reopen.
- A pendant disconnect while the pendant owns capture runs the full physical
  teardown — writer-gate deny, `StopDeviceSessionStage` (BLE streams, WAL
  finalize, recording state, device identity), socket close, then telemetry
  completion — before the idle commit; while the phone or a call owns capture
  only the pendant identity is cleared and the owner is untouched.
- Phone-stop/-finish policy: the stop's forced mute is always followed by a
  restore of the suspended pendant's prior policy (`wasPaused`), ordered after
  the phone teardown, so a previously-live pendant comes back unmuted and a
  previously-paused one stays muted — unless a call still holds the channel,
  in which case no restore runs and the call-end resume applies `wasPaused`.
- `PhoneStopRequested`/`FinishRequested` with no phone owner is a no-op: it
  never runs a stop stage or a policy write against a pendant or a call —
  with one exception. An unowned stop/finish still settles an
  `awaitingPhoneResume` phone-suspension debt held by the interim stop: a
  normal stop or finish consumes it (the connected pendant is resumed under a
  fresh minted id, or the debt ends when it is disconnected or the stop is
  not a user stop), while a repeat interim stop keeps it held.
  (`FinishRequested` still runs `ProcessConversationStage` — finishing a
  pendant conversation is a processing request, not an ownership claim.)
- `OfflineMuteToggled` routes through the phase-correct pause/resume
  reducers: it cannot flip the shared policy under a paused or batch phone
  owner, another owner, or a call; the bare `PolicyWrite(false)` remains only
  for the idle offline-unmute case.
- `PhoneStartRequested` with `resumePolicy: false` under a muted shared
  policy is rejected before minting, so no owner is published for a start
  whose mic body would refuse admission.
- Recording ids are minted only through the `MintRecording` effect /
  `mintRecordingId` port; staged session bodies no longer call
  `RecordingLifecycleTelemetry.prepare`, so the minted id folded into the
  session is never replaced mid-transition. `mode_changed` rolls mint their
  replacement id in the same transition.
- A failed `mode_changed` session roll inside `BatchModeStage` reports the
  failure (`CaptureStageFailure` or throw) so the transition fails closed
  instead of publishing a new owner under hardware that never started.
- Batch pendants never hand off until a native per-source writer gate exists:
  a phone start over `pendantBatchLive`/`pendantBatchPaused` is refused, and a
  batch-capable pendant connecting during phone capture does not activate a
  batch writer. Honest limitation: on `DeviceUpdated(null)` while a batch
  pendant records, the no-op gate cannot truly deny the native writer, so the
  deny degrades to a shared-policy `PolicyWrite(true)` (native drops packets
  while muted) instead of claiming per-source physical denial. The same
  shared-policy mute is the only deny available when an Omi call suspends a
  batch pendant — intentional privacy behavior with a real user-visible cost:
  the pendant's Transcribe Later session keeps its file across the call, but
  audio recorded during the call is dropped rather than captured, so the
  batch transcript has a gap for the call's duration instead of call audio.
- A repeated explicit `PhoneStartRequested` stops the previous phone session
  before minting a fresh recording id; only pause/resume and recovery preserve
  the existing id. Reconnection uses its own events
  (`SocketClosed`/`SocketConnected`/keepalive). A repeated direct
  `PhoneBatchStartRequested` remains a no-op, and a first direct batch start
  mints a source-unique recording id before the start stage. The C1 test-only
  `KeepAliveTick(testingProbe: true)` joins concurrent requests and permits
  the injected `RecordingState.systemAudioRecord` or `deviceRecord` lane to
  exercise the legacy reconnect stage without claiming a nonexistent mic.
- `DeviceStopRequested` while another source owns capture only updates pendant
  identity (`cleanDevice` clears `_recordingDevice`); it never touches the
  owner's socket, WAL, recording state, or the suspension stack.
- Legacy `DevicePauseRequested`/`DeviceResumeRequested` target the active
  phone when it owns capture (sharing the phone pause/resume transition),
  otherwise target the pendant. A call-suspended pendant only changes its
  `wasPaused` intent; no device control opens BLE beneath a phone or call.
  With no owner, the old device-pause API still writes the durable mute
  policy without opening hardware.
- Resume while idle is policy-only: `ResumeCaptureRequested`/
  `OfflineMuteToggled` with no owner emits `PolicyWrite(false)` and nothing
  else — no `ResumeDeviceTailStage`, no socket, no BLE open. An offline
  unmute changes admission, never ownership.
- A device start admitted under a muted policy is a legitimate paused
  capture: telemetry marks it started, not `failStart`. Any other failed
  start stage fails the transition closed rather than committing a session
  carrying a recording id the hardware never adopted.
- Inside the `writePolicy` port (`_setCaptureMuted`), the recording-state
  pause mark is written only after the durable policy write returns
  confirmed-unsuperseded; a superseded write cannot leave `recordingState`
  claiming a pause that never landed.
- Snapshot persist is the last I/O step of a safe transition (before publish).

## Read model

Two views over the same logical state:

- `readModel` — the committed, published view. Controller getters consumed by
  UI (`pendantPausedForPhone`, `pendantPausedForCall`, `liveCaptureDisplayState`
  inputs) read this; it never shows a new owner before its open effects finish.
- `stagedReadModel` — the in-dispatch view over the reducer's target state.
  Only effect bodies and staged internals read it, so a transition's own tail
  (e.g. `_ensureDeviceSocketConnection`, `_pendantSuspension` checks inside
  stage bodies) sees the state it is executing toward.

`CaptureReadModel` derives everything the controller getters and
`liveCaptureDisplayState` need: `phoneOwnsCapture`, `pendantOwns`,
`phonePaused`, `phoneBatchSession`, `pendantBatchSession`, `pendantSuspension`,
`pendantSuspendedForPhone`/`ForCall`, `pendantHoldsCapture`, `micInterrupted`,
`callActive`, `paused`, `deviceMuted`, `liveOwnerName`, `activeRecordingId`.

`pendantBatchSession` backs the public `CaptureController.isPendantBatchRecording`
getter consumed by the home record button: because a phone takeover of a batch
pendant is refused (invariants), the button shows
`context.l10n.phoneRecordingBlockedByPendantBatch` via `OmiFeedback.info`
instead of silently starting.

## Migrated entry paths

All of these now dispatch a `CaptureEvent` (public API signatures unchanged):
`streamRecording`, `stopStreamRecording`, `finishCapture`,
`streamDeviceRecording`, `stopStreamDeviceRecording`, `updateRecordingDevice`,
`pauseCapture`, `resumeCapture`, `pauseDeviceRecording`,
`resumeDeviceRecording`, `toggleOfflineMute`, `setBatchMode`,
`onTranscriptionSettingsChanged`, `onRecordProfileSettingChanged`,
`suspendBatchModeForOnboarding`, `restoreBatchModeAfterOnboarding`,
`startPhoneMicBatchForTesting`, `reconnectActiveCaptureForTesting`,
`onAppResumed`, launch restore-marker recovery, the Omi call listener, native
mic interruption/stall callbacks, socket `onClosed`/`onConnected`/`onError`,
and keepalive ticks.

Remaining legacy: the staged bodies listed above, plus UI-adjacent controller
concerns (location capture, metrics, optimistic processing) that never made
ownership decisions.
