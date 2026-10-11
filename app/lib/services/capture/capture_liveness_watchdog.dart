import 'package:omi/services/capture/capture_coordinator.dart';

/// Independent of socket keepalive: readiness is not evidence of fresh audio.
/// Observations are scoped to a committed live session, and recoveries keep its
/// recording identity. This never controls a pendant subscription or uplink.
class CaptureLivenessWatchdog {
  static const stallThreshold = Duration(seconds: 45);
  static const recoveryCooldown = Duration(minutes: 1);
  String? _sessionKey;
  DateTime? _lastFrameAt;
  DateTime? _socketDownAt;
  DateTime? _lastRecoveryAt;

  bool framesStalledAt(DateTime now) => _lastFrameAt != null && now.difference(_lastFrameAt!) >= stallThreshold;

  void observeFrame(DateTime now) => _lastFrameAt = now;

  void reset() {
    _sessionKey = null;
    _lastFrameAt = null;
    _socketDownAt = null;
    _lastRecoveryAt = null;
  }

  CaptureLivenessFailure? check(CaptureCoordinatorState state, DateTime now,
      {required bool socketReady, int observationEpoch = 0}) {
    if (state.phase != CapturePhase.phoneLive || state.micInterrupted || state.active == null) {
      reset();
      return null;
    }
    if (_sessionKey != state.active!.sessionKey) {
      reset();
      _sessionKey = state.active!.sessionKey;
      _lastFrameAt = now;
    }
    _socketDownAt = socketReady ? null : (_socketDownAt ?? now);
    final stalled = now.difference(_lastFrameAt!) >= stallThreshold;
    final disconnected = _socketDownAt != null && now.difference(_socketDownAt!) >= stallThreshold;
    if (!stalled && !disconnected) return null;
    if (_lastRecoveryAt != null && now.difference(_lastRecoveryAt!) < recoveryCooldown) return null;
    _lastRecoveryAt = now;
    return CaptureLivenessFailure(
      sessionKey: _sessionKey!,
      gapStartedAt: stalled ? _lastFrameAt! : _socketDownAt!,
      observedAt: now,
      observationEpoch: observationEpoch,
      reason: socketReady ? CaptureLivenessReason.noFrames : CaptureLivenessReason.socketDown,
    );
  }
}
