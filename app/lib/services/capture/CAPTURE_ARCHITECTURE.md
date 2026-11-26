# Capture Coordinator Architecture

`capture_coordinator.dart` owns conversation capture in the mobile app. The
wearable can stream live or use Transcribe Later when its device type supports
batch capture. An Omi call can suspend wearable capture. Home and onboarding
send people without a wearable to pairing. Siri Start Listening uses that
same device capture path.

Related documents:

- [Ownership and injectable boundaries](OWNERSHIP.md)
- [Durable capture policy](CAPTURE_POLICY.md)
- [Transcription connectivity recovery](../../../docs/transcription-connectivity-recovery.md)
- [WAL custody](../wals/CUSTODY.md)

## State and admission

| Phase | Meaning |
|---|---|
| `idle` | No active owner. A wearable can still be connected. |
| `pendantLive` / `pendantPaused` | Wearable live capture, with intake blocked while muted. |
| `pendantBatchLive` / `pendantBatchPaused` | The device batch writer holds the recording. The shared policy blocks new packets while muted. |
| `callActive` | An Omi call holds the channel. A suspended wearable can resume after the call. |

`ActiveCaptureSession` carries the account, source, transport, device identity,
session key and recording ID. `SuspendedCapture` keeps the device and user pause
intent for calls and reconnect grace. A resumed connection can preserve a
recording identity without claiming coverage for the gap. An explicit stop
clears the pending resume for that recording. A same-device start while the
wearable already owns capture is a no-op.

The durable capture policy governs Dart ingress and native writers. A device
start resolves the effective mute before opening transport. An intentionally
muted start can commit a paused session without an audio subscription. An
unmuted start has to reach its device transport or fail closed with
`capture_unavailable`. If an upload pass fences transport during a start,
the registered reconciliation opens transport after the pass. Native ingress
health can defer started telemetry until verification. Without a connected device, idle mute and unmute change policy
without opening a socket or BLE subscription.

Historical phone phases, events, and ports remain in the coordinator for
compatibility with protected capture contracts and old snapshots. Launch
sanitization restores idle ownership and preserves the session sequence.
The legacy phone pause marker and pending discard recovery still handle
previous builds. Historical audio still uses the WAL recovery and upload paths.
Chat dictation and voice enrollment use their own microphone paths.

## Dispatch and I/O

`CaptureCoordinator.dispatch` queues events FIFO. The reducer produces a target
state and ordered effects. While effects run, `stagedReadModel` supplies the
pending owner to controller stages and `readModel` exposes the committed
state. The snapshot write is the last I/O step before publication. A failed
turn completes its own outcome and the queue continues.

`CaptureController` implements controller stages for device start/stop, BLE
subscriptions, WAL finalize/roll, location snapshots, calls, Transcribe Later,
and socket reconnect. Stages call private bodies to keep their I/O inside the
dispatch. Before publishing a failed transition, the coordinator best-effort
denies capture and tears down the affected transport. A stage can return a
`CaptureStageFailure` with an absorbed outcome for callers that historically
handle an unavailable start through the committed state.

A superseded policy write is checked against the effective policy. In
particular, an unmute that loses to a newer mute cannot reopen transport, and
a later mute cannot strand a previously admitted teardown. A call can hold
transport without changing the user's durable mute intent.

## Generation fences

`CaptureSessionOwner` fences stale callbacks across account, session, and
lifecycle changes. `updateRecordingDevice` can publish display identity
synchronously, with the ownership update queued. The device identity revision
fences awaited socket and BLE opens even if a device disconnects and
reconnects under the same ID while an open is pending. An obsolete open
retires its own resources. Installed audio subscriptions check the effective
policy and device ID so same-device metadata refreshes do not starve audio.

Reconnect and foreground recovery also check account/session ownership,
policy, call suspension, and the device-stopped flag. The WAL custody contract governs retention and retirement of local audio.

## UI and verification

Home and lock-screen presentations consume the committed capture read model
and connection health. Device controls, pairing, Siri controls and call
callbacks enter through `CaptureController`. The legacy system-audio reconnect
stage retains its existing server source.

Capture replay tests drive the real coordinator/controller with injected I/O.
`CaptureDependencies` and [the ownership contract](OWNERSHIP.md) describe
those boundaries. The flow-walker definitions under `app/e2e/flows`
and the physical wearable qualification harness cover device-facing paths at
different layers.

## Conversation windows on a continuing live socket (#20365)

A source recording/socket can carry several server conversations. Its recording ID stays stable,
while each completed conversation rotates a separate window revision with a factual phone-clock
start. Reset and rearm publish together; stopping/error does not open another window.

`capture_conversation_custody.dart` admits an immutable close before yielding: the WAL owner seals
an exclusive audio cut, and the close retains its segment arrivals, socket mode, interruption state
and account generation. Only stamping runs in the ordered tail. Each conversation has its own
confirmation/fallback; coverage and recovery never run inside that tail. Duplicate processing IDs
do not rotate the next window. Account clearing retires pending authority and timers, while
already-admitted writes remain fenced by their original WAL generation.

Process Now reserves the same cut before its disk/HTTP waits. A server close during its drain adopts
that exact window. After the local window has rotated, an intervening server ID is ambiguous until
the HTTP result supplies the exact ID: a matching ID confirms the original cut, a different ID owns
its own cut, and an absent result leaves ambiguous audio unlinked for recovery. Intervening audio
is never guessed into the earlier conversation. No upload preference or transcript-coverage rule
changes; the WAL [custody contract](../wals/CUSTODY.md) remains authoritative.

Implementation/verification checklist:

- [x] Rearm sequential windows without reconnecting or inventing future clock timestamps.
- [x] Seal/reserve exact WAL object identities at close admission, before queued I/O.
- [x] Keep per-close evidence and handle reversed/duplicate events and Process Now overlap.
- [x] Preserve partial, interrupted, uncertain and foreign-account audio and upload choices.
- [x] Exercise real controller/ledger/disk/recovery with synthetic ingress and restart discovery
  (`capture_next_conversation_window_test.dart`, `conversation_wal_snapshot_test.dart`); these replay
  tests substitute socket/device boundaries and do not certify native BLE or a physical pendant.
