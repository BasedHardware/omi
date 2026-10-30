part of 'capture_controller.dart';

/// Feeds [CaptureContinuityMonitor]: every check reports whether a connected
/// pendant that should be captured has capture's audio subscription. The
/// timer runs only while a pendant is connected, so an idle app holds none.
extension _CaptureContinuityWatch on CaptureController {
  void _syncContinuityWatch() {
    if (_captureControllerDisposed) return;
    if (_recordingDevice == null) {
      _continuityTimer?.cancel();
      _continuityTimer = null;
      // Resolves an open episode: no pendant, nothing to capture.
      _observeContinuity();
      return;
    }
    _continuityTimer ??= lifetime.periodic(CaptureContinuityMonitor.checkInterval, (_) => _observeContinuity());
  }

  void _observeContinuity() {
    if (_captureControllerDisposed) return;
    final device = _recordingDevice;
    try {
      CaptureContinuityMonitor.instance.observe(CaptureContinuityProbe(
        deviceId: device?.id,
        source: (device == null ? null : conversationSourceForDeviceType(device.type)) ?? 'none',
        captureExpected: device != null && _orphanAudioAdmitted(device.id) && !isPaused,
        capturing: _bleBytesStream != null,
        phase: _capture.stagedReadModel.phase.name,
        syncFenced: SyncWakeScope.syncOnly,
      ));
    } catch (error) {
      Logger.debug('[Capture] continuity check failed: $error');
    }
  }
}
