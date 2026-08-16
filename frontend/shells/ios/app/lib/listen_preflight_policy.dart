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

bool listenPreflightCanOpen(
  Map<Object?, Object?> payload, {
  bool evidenceAudioEnabled = false,
}) =>
    evidenceAudioEnabled ||
    (payload['permission'] == 'granted' &&
        payload['deviceState'] == 'available');
