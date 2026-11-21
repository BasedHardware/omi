# Ring firmware and legacy SD sync

Investigation: 2026-11-05, against `origin/main` at
`b6f32242a0b269fca4214ab19321f2144bf9c328`. The reported device ran firmware
3.0.21 with app 1.0.585; this investigation used source and hermetic tests,
without a physical pendant, production API calls, or production data.

## Sync failure

`DeviceProvider` attached legacy SD sync after resolving device information,
even for ring-buffer firmware (>= 3.0.20). `WalSyncs` also combined legacy SD
inventory into both listing methods and ran the legacy download phase after
ring sync. The characteristic is shared, but ring status is
`[used, unread, free, rtc_valid]`, while legacy discovery interprets it as
`[total, offset, start_ts]`. That can create a phantom recording and send the
legacy read command to ring firmware.

Both legacy SD readers previously ignored the two-byte rejection ACK
`01 06` as unrecognized data and waited for their stall timeout. A rejection
with no downloaded chunks could also return normally and mark the WAL synced.

`WalSyncs.setDevice` now owns legacy SD attachment using the resolved firmware.
Ring firmware skips SD listing, startup and the SD download phase; stale
single-WAL requests are rejected. The SD implementation also guards direct
ring-firmware entry. Legacy firmware retains its attachment and routing.

Both SD readers now recognize command ACKs, log nonzero status in hex, fail the
attempt immediately, retain the WAL and device contents, and suppress further
reads on that connection. Device attachment/detachment resets the rejection
latch. Existing one-byte successful end statuses (4 and 100) remain successful.

## Capture start diagnostics

`RecordingLifecycleTelemetry.failStart` previously emitted analytics without a
Logger entry, including the `capture_unavailable` exit in
`CaptureController._startDeviceSessionBody`. It now logs the failure class,
source, preparation/start state, observed audio and connection count, even if
no analytics session was prepared.

`CaptureCoordinator._failClosed` is the shared terminal path for effect,
stage, snapshot and transition failures. It now logs the failure class/reason,
phase, source, call/device state and whether the failure was absorbed before
cleanup. Capture decisions and cleanup behavior are unchanged. Tests assert
both the telemetry log and the real controller's audio-setup failure log.

## Hidden Home card: findings only

No firmware-version or SD-sync visibility condition was found in the inspected
Home/conversation capture-card path:

- `lib/pages/conversations/widgets/processing_capture.dart` hides the capture
  card when `liveCaptureSource` is null and neither phone nor batch capture is
  active. A connected pendant by itself does not make a card visible.
- `CaptureController.liveCaptureSource` derives from committed coordinator
  ownership. A fail-closed capture transition removes that ownership, so a
  capture-start failure can indirectly hide the card. SD starvation causing
  that failure remains a plausible connection, not a reproduced causal result.
- `ConversationsPage` sets `deferStreamingToEpisode` when live episodes are
  enabled. `EpisodePresentation.streamingSource` then moves streaming capture
  into Today instead of showing a duplicate standalone capture card.
- The Home header's `BatteryInfoWidget` is mounted independently of these
  capture-card conditions.
- The separate daily-recaps row is opt-in via `HomeDailyRecapsSetting`; when
  disabled it is not mounted or fetched, independently of ring/SD state.

The reported card was not identified precisely enough to establish a separate
UI defect. No UI visibility behavior was changed. A device-level reproduction
should check audio/button delivery and identify the missing card after applying
the sync fix; local unit tests do not establish physical-device recovery.

## Local verification

The focused firmware-routing, SD custody/packet/delete, capture coordinator,
recording lifecycle and device late-ready suites passed (174 tests). Analysis
passed for all nine touched Dart files, and formatting passed at 120 columns.
The coordinator suite includes 2,000 seeded ownership sequences. Full command
lines and local output are in the uncommitted `app/.agent-artifacts/ringsync/`
handoff. These checks verify app logic, not physical audio/button delivery.
