# Capture admission policy

The mobile capture controller and native audio sinks share one durable policy:
`capturePolicy` in Flutter preferences (`flutter.capturePolicy` natively).

```json
{"version":1,"revision":7,"muted":true}
```

`SharedPreferencesUtil.setCaptureMuted` is the only in-app mutation entry point.
It serializes durable writes and advances the revision for each user intent.
Mute denies Dart admission immediately and applies a process-scoped native deny
latch before persistence. Unmute persists first, then releases that latch; only
then does Dart admit capture. Native latches never authorize beyond the durable
policy. Failed writes leave the latch closed and errors propagate to the caller.
The returned future confirms preference persistence and native admission state,
not microphone shutdown or a native queue-drained acknowledgement.

The `com.omi/capture_policy` bridge accepts revisioned `setMuted` commands and
exposes `getRevision` so Flutter engine reconstruction retains the native revision
high-water mark. A process latch is not durable across OS process death; if
storage fails, that error must remain visible to the caller.

The ordinary device mute, Transcribe Later mute, phone pause and stop, and
explicit resume use this authority. Reconnect, mode changes, file rotation, and
session cleanup must not create an unmute intent. A manual file cut preserves
mute. Automatic phone session restarts preserve policy; an explicit phone start
can unmute. A user stop of a live phone recording mutes first (retiring its
callbacks) and then restores the policy the recording started from, so stopping
the phone never leaves the next source paused; Transcribe Later keeps its mute
across stop.

Dart callbacks carry the admitted revision. Native BLE/phone batch writers check
the same policy before admission and recheck the revision at a deferred write.
The Android native background live path applies the same gate. A callback from
an older authorization cannot resume sending or writing after mute/unmute.

The transition is conservative: absent canonical policy reads the OR of the two
old mute preferences. Dart initialization persists that value before deleting
legacy keys. A malformed or unsupported canonical policy denies capture. The
legacy fallback is an installation migration, never an alternative writable
policy; new application code cannot write the old keys.

## Live sources

One source captures at a time: the pendant, the phone microphone, or an Omi
phone call. `CaptureController` owns the switch, so no caller can mix two
sources into one transcription socket.

- An explicit phone start while a realtime pendant is streaming (or user-paused)
  hands the pendant off: its Dart and native BLE streams close, its conversation
  is processed if it has content, and it resumes by itself when the phone
  recording stops, in the state it was in (live or paused). `finishCapture`
  processes the phone conversation before that resume, so the processing request
  cannot reach the pendant's next conversation.
- A pendant that connects during a phone recording waits for it the same way,
  and a pendant (dis)connecting never rolls the phone's capture session.
- An Omi call (connecting, ringing, active) pauses a streaming pendant without
  touching the policy or its conversation; the pendant resumes when the call
  ends. A pendant the user paused stays paused.
- A phone pause mutes, releases the microphone and keeps the socket and the
  recording id; resume unmutes and restarts only the microphone, so the
  conversation continues.
- Transcribe Later pendants write natively under this single policy and are not
  handed off; phone and pendant capture in that mode is a known gap that needs a
  per-source native gate.

## Boundaries

This policy controls fresh audio entering mobile live transcription and local
recording. It does not erase or suppress recovery of previously captured audio.
Limitless flash drain transfers already-recorded pendant pages and must not
consume/ACK them while dropping bytes under a mobile mute gate. Mobile mute is
not a physical power-off command for independently recording hardware.

The existing CaptureSessionOwner remains responsible for session identity,
connection generations, foreground holds and capture's recovery requests.
Capture policy revision is durable user intent; it is not a second connection
or session generation. Recovery remains account-owned and may outlive capture.

## Verification

`app/test/fixtures/capture_policy.json` is parsed by Dart, Swift and Kotlin
production-policy tests. Real native batch writer tests exercise byte/file
admission, and the Dart capture replay exercises the actual controller, recorder
service, socket and WAL path with synthetic audio. These complement—not replace—
physical iOS/Android checks for suspension, process death and Bluetooth recovery.

Future OS-level stop acknowledgements should extend this policy boundary and
report requested versus applied revision. Preference persistence must never be
relabeled as proof that an OS microphone has stopped. Full recovery ownership
convergence remains described in `OWNERSHIP.md`.

## Tiered pendant uplink

Automatic silence pause is disabled under INV-CAP-1. Current firmware discards
sampled frames while connected with no audio subscriber, so a transcript deadline
cannot authorize cancelling the BLE subscription or closing the listen socket.
The timer is not armed and queued expiry events have no effects. Conversation
silence settings still reach the server for segmentation.

`uplinkSilencePaused` is retained only to recover historical #20837 state.
Startup clears that automatic mute through the serialized capture owner; a newer
explicit user pause clears the marker and remains authoritative. Foreground and
charge-start recovery of a historical marker still respect the sync fence.
Manual pendant pause and phone microphone pause keep their existing behavior.
A future pause needs an advertised, verified retention and drain capability; there
is no opt-in that bypasses that requirement on current firmware.

A committed, unmuted live pendant session must have connected transports or
active transport reconciliation whenever no sync scope is active. Resume
controls defer dispatch during a scope to avoid unnecessary work, but that gap
is not an admission guarantee: coalesced passes can raise another scope before
startup finishes. Every fenced socket/audio attempt records one coalesced
reconciliation demand. After scope drop and capture commit, it rechecks current
ownership and pause state, ensures the missing transports, and re-arms the
existing keepalive. A new scope re-fences the attempt and records demand again.
Reconciliation never writes policy, mints a session, or adds a retry timer.
Disposal or a newer paused/non-pendant state cancels admission.

The first successful charging observation inherits its connection's initial
resume gate. A connection admitted only for sync observes without resuming;
an authorized connection retains its charge edge even if another scope has
since started, and capture defers/reconciles the transport work above.

Periodic sync is a bounded backlog pass through RecordingTransferCoordinator.
It permits device discovery but fences live socket/audio starts, and expiration
cancels transfer work. iOS BGAppRefresh eligibility is opportunistic, with no hourly
promise. The current iOS bridge supports a suspended existing engine; cold-process
grants cannot safely bootstrap the UI-owned WAL/account graph and exit without
starting capture. Android reuses the existing foreground-task repeat callback and
main isolate. Neither platform starts a second capture engine for sync.
