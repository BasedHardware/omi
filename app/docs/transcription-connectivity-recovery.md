# Transcription connectivity and settings recovery

Tracking: [#20482](https://github.com/BasedHardware/omi/issues/20482).

## Ownership and data flow

`ConnectivityService` subscribes before reading the initial interface snapshot.
Interface changes advance a network revision; each reachability attempt also
has a probe revision. Only the latest probe on the current interface generation
may publish connectivity. The service owns a ten-second
probe cadence instead of consuming unowned checker status events. This also
recovers when the checker would not emit another status change.
VPN, tethering and other interfaces still require successful reachability.
The independent production probes and private development profile routing are
unchanged. Probes do not test whether a particular STT WebSocket is reachable.

The settings page keeps the active transcription source separate from saved
provider configuration. Omi and Omi Parakeet persist an Omi config; inactive
BYOK credentials and unavailable Whisper assets cannot gate that choice.
Editing a provider key updates only headers matching the previous generated
credential. Explicit different header values, custom URLs and parameters are
preserved, including when Advanced is collapsed. Parser and audio-field edits
participate in socket configuration identity. Configurations without these
overrides retain their legacy identity, including persisted paywall selections.

Saving dispatches the existing `TranscriptionSettingsChanged` capture event.
CaptureCoordinator retains capture/session ownership while replacing the
transcription socket. This change does not clear preferences, sign out, delete
recordings, modify WAL retention or alter subscription entitlements.

## Implementation and verification checklist

- [x] Fence startup snapshots, interface handovers and out-of-order probes.
- [x] Own periodic reachability checks; cover VPN and probe errors without real network I/O.
- [x] Rotate/clear generated Deepgram headers while preserving explicit overrides.
- [x] Preserve custom settings when Advanced is collapsed; reconnect on parser edits.
- [x] Permit saving Omi/Parakeet with an inactive missing Whisper model.
- [x] Preserve legacy configuration IDs and release an existing paywall pin on paid upgrade.
- [x] Exercise real settings widgets and the capture/WAL pipeline with retained bytes.
- [ ] Merge and ship a mobile build containing these changes. No backend deployment is required.
- [ ] On a physical CV1/iPhone, compare short recordings on Wi-Fi and cellular,
      including a handover while recording; confirm transcripts and Offline Sync.
- [ ] Privately correlate any continuing failure with app/iOS/firmware versions,
      a failed Wi-Fi timestamp and a successful cellular timestamp. This customer's
      network/provider/account cause and historical recording status remain unverified.

The earlier internet-detection change in #21299 is on main and listed in the
iOS 1.0.563 store notes; it does not establish that this report is resolved.
Do not reinstall, clear app data or reset the device as a troubleshooting step
before unsynced audio has been accounted for.
