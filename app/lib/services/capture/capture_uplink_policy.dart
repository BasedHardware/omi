part of 'capture_controller.dart';

/// Pendant uplink effects share the existing admission and session owners.
extension _CaptureUplinkPolicy on CaptureController {
  Future<void> _resumeSilenceLogged() async {
    await _dispatchLogged(const ResumeSilencePaused());
  }

  /// Resume must not clear paused intent until both live transports can start.
  /// Keep genuine sync passes fenced; resume through the normal startup path
  /// after the drain, which also re-arms the socket keepalive.
  Future<CaptureDispatchOutcome> _dispatchWithResumeFence(CaptureEvent event) async {
    final resume = event is ResumeCaptureRequested || event is DeviceResumeRequested || event is ResumeSilencePaused;
    if (resume) {
      while (SyncWakeScope.syncOnly) {
        await SyncWakeScope.whenIdle;
      }
    }
    final outcome = await _capture.dispatch(event);
    if (resume &&
        outcome.admitted &&
        !outcome.failed &&
        !_captureControllerDisposed &&
        _capture.readModel.pendantOwns &&
        !isPaused &&
        _socket?.state == SocketServiceState.connected) {
      _startKeepAliveServices();
    }
    return outcome;
  }

  void _armUplinkSilence() {
    if (_capture.stagedReadModel.phase == CapturePhase.pendantLive && !isPaused && !_preferences.batchModeEnabled) {
      _uplinkSilence.speechOrStart();
    }
  }

  Future<void> _pauseDeviceTailBody() async {
    var revision = _preferences.capturePolicy.revision;
    await BatteryWidgetService().updateMuteState(true);
    if (_preferences.capturePolicy.revision != revision) return;
    await _bleBytesStream?.cancel();
    if (_preferences.capturePolicy.revision != revision) return;
    await _preferences.saveBool('nativeBleForegroundReady', false);
    await _preferences.saveBool('nativeBleStreamingEnabled', false);
    _keepAliveTimer?.cancel();
    _keepAliveTimer = null;
    await _abandonTranscriptionSocket(reason: 'device capture paused');
    _publishCaptureChange();
  }

  Future<void> _resumeDeviceTailBody() async {
    if (_recordingDevice == null) return;
    final connection = await _ensureDeviceConnection(_recordingDevice!.id, force: true);
    if (connection == null) throw StateError('Capture connection unavailable');
    final revision = _preferences.capturePolicy.revision;
    if (!_admitsCapture(revision)) return;
    await BatteryWidgetService().updateMuteState(false);
    if (!_admitsCapture(revision)) return;
    await _ensureDeviceSocketConnection();
    if (!_admitsCapture(revision)) return;
    await _initiateDeviceAudioStreaming();
    if (!_admitsCapture(revision)) return;
    updateRecordingState(RecordingState.deviceRecord);
    _publishCaptureChange();
  }

  Future<void> _abandonTranscriptionSocket({required String reason}) async {
    final previousSocket = _socket;
    _socket = null;
    _transcriptServiceReady = false;
    if (previousSocket != null) _completeWedgeSession(previousSocket, intentional: true);
    try {
      await previousSocket?.stop(reason: reason);
    } catch (e, stack) {
      Logger.error('[SttMode] Failed to stop the previous socket after $reason: $e\n$stack');
    }
  }

  bool get _shouldReconnectTranscriptionSocket {
    final activeDeviceCapture = _recordingDevice != null && recordingState == RecordingState.deviceRecord && !isPaused;
    final activePhoneOrSystemCapture = recordingState == RecordingState.record ||
        recordingState == RecordingState.interrupted ||
        recordingState == RecordingState.systemAudioRecord;
    return activeDeviceCapture || activePhoneOrSystemCapture;
  }
}
