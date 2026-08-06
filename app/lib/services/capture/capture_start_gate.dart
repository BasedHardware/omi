import 'dart:async';

bool canReuseActiveDeviceCapture({
  required String? activeDeviceId,
  required String? requestedDeviceId,
  required bool recordingActive,
  required bool audioPathActive,
}) =>
    activeDeviceId != null && requestedDeviceId == activeDeviceId && recordingActive && audioPathActive;

/// Coalesces concurrent requests to rebuild the capture transport.
///
/// Device readiness can be reported by more than one observer during startup.
/// Opening two forced transcription sockets gives each backend runtime a
/// different recording-session owner even though the UI shows one pendant.
class CaptureStartGate {
  Future<void>? _inFlight;

  Future<void> run(Future<void> Function() start) {
    final existing = _inFlight;
    if (existing != null) return existing;

    final future = Future<void>.sync(start);
    _inFlight = future;
    return future.whenComplete(() {
      if (identical(_inFlight, future)) _inFlight = null;
    });
  }
}
