part of 'capture_controller.dart';

/// Pendant uplink effects share the existing admission and session owners.
extension _CaptureUplinkPolicy on CaptureController {
  Future<void> _recoverCaptureRestoreMarkers() async {
    // Upgrade from #20837: an automatic power pause is not user mute intent.
    // The serialized reducer rechecks the marker so a newer manual mute wins.
    if (silencePaused) {
      final outcome = await _dispatchWithResumeFence(const ResumeSilencePaused());
      outcome.throwIfFailed();
    }
    final pending = _preferences.getBool(CaptureController._phoneRestorePendingKey);
    if (!pending) return;
    final mutedBefore = _preferences.getBool(CaptureController._phoneRestoreMutedKey);
    final outcome = await _capture.dispatch(LaunchRecovery(markerPending: pending, mutedBefore: mutedBefore));
    outcome.throwIfFailed();
  }

  Future<void> _resumeSilenceLogged() async {
    await _dispatchLogged(const ResumeSilencePaused());
  }

  /// Avoid committing mid-drain when possible. Transport reconciliation below
  /// owns correctness: another scope can rise after this check, even between
  /// coalesced passes of one wake.
  Future<CaptureDispatchOutcome> _dispatchWithResumeFence(CaptureEvent event) async {
    final resume = event is ResumeCaptureRequested || event is DeviceResumeRequested || event is ResumeSilencePaused;
    if (resume) {
      while (SyncWakeScope.syncOnly) {
        await SyncWakeScope.whenIdle;
      }
    }
    if (_captureControllerDisposed) {
      return CaptureDispatchOutcome.denied(_captureInstance?.state ?? CaptureCoordinatorState.idle());
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

  /// Every skipped transport attempt leaves demand, including attempts in a
  /// staged resume. Reconciliation waits for that transition to commit before
  /// inspecting CURRENT ownership; it never replays a policy write or mint.
  bool _fenceUplinkForSync() {
    if (_captureControllerDisposed) return true;
    if (!SyncWakeScope.syncOnly) return false;
    if (_capture.stagedReadModel.phase == CapturePhase.pendantLive && !isPaused) {
      _uplinkReconcileNeeded = true;
      if (!_uplinkReconcileRunning) {
        _uplinkReconcileRunning = true;
        unawaited(_reconcileFencedUplink());
      }
    }
    return true;
  }

  bool get _committedUplinkAdmitted =>
      !_captureControllerDisposed &&
      _capture.readModel.phase == CapturePhase.pendantLive &&
      _capture.stagedReadModel.phase == CapturePhase.pendantLive &&
      !isPaused &&
      _recordingDevice != null;

  Future<void> _reconcileFencedUplink() async {
    try {
      while (_uplinkReconcileNeeded && !_captureControllerDisposed) {
        while (SyncWakeScope.syncOnly) {
          await SyncWakeScope.whenIdle;
          if (_captureControllerDisposed) return;
        }
        await _captureInstance?.pendingDrain;
        if (_captureControllerDisposed) return;
        // Awaiting the capture commit can cross another scope rise. Record a
        // fresh demand and await its drop, rather than relying on a safe gap.
        if (_fenceUplinkForSync()) continue;
        // Consume all blocked attempts accumulated during this scope/commit,
        // not just the first one. Only a NEW fenced attempt may re-drive again.
        _uplinkReconcileNeeded = false;
        if (!_committedUplinkAdmitted) continue;
        await _ensureDeviceSocketConnection();
        if (!_committedUplinkAdmitted) continue;
        if (_bleBytesStream == null) await _initiateDeviceAudioStreaming();
        _fenceUplinkForSync();
      }
    } catch (error, stack) {
      Logger.error('[CaptureProvider] scope-drop uplink reconciliation failed: $error\n$stack');
    } finally {
      _uplinkReconcileRunning = false;
      // A new scope re-registers even after an I/O failure. Outside a scope,
      // preserve normal failure recovery using the existing keepalive timer.
      if (_committedUplinkAdmitted && !_fenceUplinkForSync()) _startKeepAliveServices();
    }
  }

  Future<void> _cancelUplinkAudio() async {
    final previous = _bleBytesStream;
    _bleBytesStream = null;
    await previous?.cancel();
  }

  void _armUplinkSilence() {
    // Disabled until firmware advertises a verified retain-and-drain protocol.
    // Keep manual pause/resume and legacy marker recovery available.
    _uplinkSilence.cancel();
  }

  Future<void> _pauseDeviceTailBody() async {
    var revision = _preferences.capturePolicy.revision;
    await BatteryWidgetService().updateMuteState(true);
    if (_preferences.capturePolicy.revision != revision) return;
    await _cancelUplinkAudio();
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
