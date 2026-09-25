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
identity and resumes without a roll. Repeated call-start or reconnect events
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
| `mintRecordingId(sessionKey, source)` | `_recordingTelemetry.prepare`. |
| `currentRecordingId()` | folds ids minted inside staged bodies back into the committed session. |
| `readSnapshot` / `persistSnapshot` | shared-preferences snapshot store; persist is always the last step of a safe transition. |
| `runStage(stage)` | the staged-migration seam, below. |

## Staged migration seam

Composite transition bodies that are not yet decomposed into port calls run as
`CaptureStage`s through `runStage`, in reducer order, inside the same dispatch.
They are the legacy side-effect bodies extracted to private controller methods
— never a queued public API (which would deadlock).

Moved to pure reducer + ports: phase/ownership decisions, suspension stack,
policy writes, socket open/close ordering, BLE stream ordering, native mic
start/stop ordering, WAL finalize/roll, recording-id minting, snapshot
persistence. C1 compatibility exceptions remain: `updateRecordingDevice`
publishes its legacy synchronous device identity and retires a stale
`CaptureSessionOwner` generation before its queued `DeviceUpdated` executes,
so an already-awaited codec/open cannot publish an obsolete socket; `onClosed`
marks readiness and arms the reconnect timer at callback time so a pending
event cannot miss a virtual/OS timer deadline; `onConnected` mirrors the
interrupted status synchronously for existing read-model consumers. None of
these paths opens a capture source; their remaining bookkeeping belongs in
the coordinator admission fence during the next seam extraction.

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
  run yet the dispatch keeps the pre-transition state and reports `false`
  (the legacy `stopStreamRecording` supersede contract); if physical effects
  already ran the transition fails closed, since neither old nor target state
  matches the physical world anymore.
- Snapshot persistence is required durability: the snapshot of the target
  state is written before the in-memory publish, and a failed write fails the
  transition closed (physical deny + safe idle) exactly like an effect failure.
  A reducer/environment exception happens before any effect could have run,
  so it reports the error on the unchanged state instead of tearing hardware
  down.
- `failedClosed` clears `active` and the whole suspension stack (plus
  `callActive`/`micInterrupted`/`mutedBeforePhone`) so recovery events can
  start safely; only the monotonic `sessionSeq` and the known
  `connectedDevice` identity survive.
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
`sessionSeq` survives so minted keys stay unique.

## Invariants

- At most one source owns capture; suspension is explicit LIFO debt.
- Old stop/deny effects are ordered before new open effects in every
  handoff transition.
- Fresh recording ids for every new source session; phone pause/resume keeps
  its recording id and its socket — a deliberate narrow exception to
  "paused source has no active transport", enforced by also stopping the
  native mic and flushing frames so no audio crosses while paused.
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
  never runs a stop stage or a policy write against a pendant or a call.
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
  while muted) instead of claiming per-source physical denial.
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
`phonePaused`, `phoneBatchSession`, `pendantSuspension`,
`pendantSuspendedForPhone`/`ForCall`, `pendantHoldsCapture`, `micInterrupted`,
`callActive`, `paused`, `deviceMuted`, `liveOwnerName`, `activeRecordingId`.

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
