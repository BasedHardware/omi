/// Pure native-custody gate shared by the live Listen host and conformance.
/// A page cannot mint this decision; the host supplies the checked values.
///
/// Consumer evidence injects deterministic PCM over the authenticated socket.
/// Real microphone TCC is not the capture path, so it must not block the
/// journey that already opted into synthetic audio. Headless L3 has no TCC
/// prompt surface — matching macOS `ListenPreflightPolicy`.
const Map<String, Object?> listenEvidencePreflightPayload = <String, Object?>{
  'permission': 'granted',
  'deviceState': 'available',
  'deviceLabel': 'Evidence audio',
  'recovery': null,
};

/// Consumer evidence and the control probe are mutually exclusive hosts, but
/// both run on a simulator that never grants microphone TCC. The same
/// synthetic-PCM grant has to be wired through this second caller, or Start
/// stays disabled and the probe times out in `listen-act`.
bool listenEvidenceAudioEnabled({
  required bool consumerEvidence,
  required bool controlProbe,
}) =>
    consumerEvidence || controlProbe;

bool listenPreflightCanOpen(
  Map<Object?, Object?> payload, {
  bool evidenceAudioEnabled = false,
}) =>
    evidenceAudioEnabled ||
    (payload['permission'] == 'granted' &&
        payload['deviceState'] == 'available');
