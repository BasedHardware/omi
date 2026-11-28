part of 'capture_controller.dart';

/// Mutable state for [_CaptureLiveRecovery]. Lives in one controller field so
/// the self-healing paths stay out of the controller body.
class _LiveRecoveryState {
  /// Last codec each pendant reported. A codec read that fails or times out
  /// falls back to it instead of wedging the serialized capture queue.
  final Map<String, BleAudioCodec> codecByDevice = {};

  /// Set by an explicit caller stop (e.g. the voice-profile flow taking the
  /// phone mic). Orphan audio is then neither persisted nor used to restart.
  bool deviceStoppedByCaller = false;

  Timer? kickTimer;
  bool kickDueWhileReconnectInFlight = false;
  CaptureSessionToken? kickDueToken;
  final List<DateTime> kicks = [];

  BleDeviceSource? orphanSource;
  int orphanDropped = 0;
  DateTime? lastOrphanAt;
  DateTime? lastOrphanLogAt;
  DateTime? lastOrphanRestartAt;
  int orphanPackets = 0;

  /// A pendant start arrived inside a capture-fencing sync pass.
  bool deferredStart = false;
  bool deferredStartRunning = false;
}

/// Capture-recovery analytics; one registered event, bounded fields.
void _emitCaptureRecovery(CaptureRecoveryObservedKind kind, CaptureRecoveryObservedTrigger trigger) {
  try {
    const TypedEvents().emit(CaptureRecoveryObserved(kind: kind, trigger: trigger));
  } catch (error) {
    Logger.debug('[Capture] recovery analytics failed: $error');
  }
}

/// Live-capture recovery: reconnect the transcription socket after a server
/// close, a network change or an app resume, and never drop pendant audio that
/// arrives while capture holds no BLE listener.
extension _CaptureLiveRecovery on CaptureController {
  /// Spacing of kicked reconnect attempts, indexed by attempts in the last
  /// five minutes. The periodic timer stays idle while a retry is pending.
  static const _kickBackoff = [
    Duration(seconds: 1),
    Duration(seconds: 20),
    Duration(seconds: 40),
    Duration(seconds: 80),
    Duration(seconds: 160),
  ];
  static const _kickWindow = Duration(minutes: 5);
  static const _minimumReconnectInterval = Duration(seconds: 20);
  static const _orphanRestartInterval = Duration(seconds: 30);
  static const _orphanEpisodeGap = Duration(seconds: 5);
  static const _codecReadTimeout = Duration(seconds: 35);

  /// Close codes the server sends for a session that cannot resume by itself.
  static const _terminalCloseCodes = {1008, 4001, 4002, 4004, 4005};

  void _installLiveRecovery() {
    lifetime.listen<void>(_connectivity.networkChanges, (_) => _kickLiveRecovery('network_change'));
    OrphanAudioRoute.sink = _onOrphanAudio;
    lifetime.own(() {
      if (identical(OrphanAudioRoute.sink, _onOrphanAudio)) OrphanAudioRoute.sink = null;
      _liveRecovery.kickTimer?.cancel();
    });
  }

  Future<BleAudioCodec> _rememberingCodec(String deviceId, Future<BleAudioCodec> Function() read) async {
    try {
      final codec = await read().timeout(_codecReadTimeout);
      _liveRecovery.codecByDevice[deviceId] = codec;
      return codec;
    } catch (error) {
      final known = _liveRecovery.codecByDevice[deviceId];
      if (known == null) rethrow;
      Logger.debug('[Capture] codec read failed ($error); using last known $known');
      return known;
    }
  }

  void _kickLiveRecoveryAfterClose(int? closeCode) {
    if (_terminalCloseCodes.contains(closeCode)) return;
    _kickLiveRecovery('socket_closed_${closeCode ?? 'none'}');
  }

  /// Bring capture back whenever it should be on: re-install a missing pendant
  /// audio stream, and reconnect a socket that is not delivering transcripts.
  void _kickLiveRecovery(String reason) {
    if (_captureControllerDisposed || _fenceUplinkForSync()) return;
    if (_committedUplinkAdmitted && _bleBytesStream == null) {
      _uplinkReconcileNeeded = true;
      if (!_uplinkReconcileRunning) {
        _uplinkReconcileRunning = true;
        unawaited(_reconcileFencedUplink());
      }
    }
    if (!_shouldReconnectTranscriptionSocket || _transcriptServiceReady) return;
    if (_liveRecovery.kickTimer?.isActive ?? false) {
      return;
    }
    if (recordingState == RecordingState.deviceRecord) _socketReconnectPending = true;
    if (!(_keepAliveTimer?.isActive ?? false)) _startKeepAliveServices();
    final now = _now();
    final kicks = _liveRecovery.kicks..removeWhere((at) => now.difference(at) > _kickWindow);
    final backoff = _kickBackoff[kicks.length.clamp(0, _kickBackoff.length - 1)];
    final lastAttempt = _keepAliveLastExecutedAt;
    final untilRateLimit =
        lastAttempt == null ? Duration.zero : lastAttempt.add(_minimumReconnectInterval).difference(now);
    final delay = backoff > untilRateLimit ? backoff : untilRateLimit;
    Logger.debug('[Capture] live recovery ($reason) in ${delay.inSeconds}s');
    final token = _sessionOwner?.token;
    _liveRecovery.kickTimer?.cancel();
    _liveRecovery.kickTimer = _scheduling.once(delay, () => unawaited(_runKickedReconnect(token)));
  }

  /// One immediate keep-alive tick, under the same guards and in-flight
  /// de-duplication as the periodic one.
  Future<void> _runKickedReconnect(CaptureSessionToken? token) async {
    _liveRecovery.kickTimer = null;
    if (_captureControllerDisposed || !_captureSessionIsCurrent(token)) return;
    if (!_shouldReconnectTranscriptionSocket || _transcriptServiceReady || !recordingDeviceServiceReady) return;
    if (!_auth.isSignedIn()) return;
    if (_keepAliveReconnectInFlight) {
      // The timer's backoff has elapsed. Preserve this retry until the active
      // connect settles instead of dropping it at the in-flight guard.
      _liveRecovery.kickDueWhileReconnectInFlight = true;
      _liveRecovery.kickDueToken = token;
      return;
    }
    if (_reconnectCooldownRemaining() > Duration.zero) {
      _kickLiveRecovery('reconnect_rate_limited');
      return;
    }
    _liveRecovery.kicks.add(_now());
    _keepAliveLastExecutedAt = _now();
    _keepAliveReconnectInFlight = true;
    try {
      await _capture.dispatch(const KeepAliveTick());
    } catch (error) {
      Logger.debug('[Capture] kicked reconnect failed: $error');
    } finally {
      _keepAliveReconnectInFlight = false;
    }
    final retryDue = _liveRecovery.kickDueWhileReconnectInFlight;
    final retryToken = _liveRecovery.kickDueToken;
    _liveRecovery.kickDueWhileReconnectInFlight = false;
    _liveRecovery.kickDueToken = null;
    if (retryDue &&
        !_captureControllerDisposed &&
        _captureSessionIsCurrent(retryToken) &&
        !_transcriptServiceReady &&
        _shouldReconnectTranscriptionSocket) {
      await _runKickedReconnect(retryToken);
      return;
    }
    if (!_transcriptServiceReady && _shouldReconnectTranscriptionSocket) {
      _kickLiveRecovery('reconnect_failed');
    }
  }

  Duration _reconnectCooldownRemaining() {
    final lastAttempt = _keepAliveLastExecutedAt;
    if (lastAttempt == null) return Duration.zero;
    final remaining = lastAttempt.add(_minimumReconnectInterval).difference(_now());
    return remaining > Duration.zero ? remaining : Duration.zero;
  }

  void _transcriptionSocketRecovered() {
    _liveRecovery.kickTimer?.cancel();
    _liveRecovery.kickTimer = null;
    _liveRecovery.kicks.clear();
  }

  bool _orphanAudioAdmitted(String deviceId, {bool ignoreMute = false}) {
    if (_captureControllerDisposed) return false;
    final device = _recordingDevice;
    final suspension = _pendantSuspension;
    final reconnect = suspension?.reason == SuspendReason.reconnect &&
        suspension?.deviceId == deviceId &&
        suspension?.accountId == _preferences.uid &&
        _auth.isSignedIn();
    // The physical link can return before the provider's debounced connect.
    // Retain received frames for the exact account/device even while its
    // recordingDevice mirror is null. Only a later start may restore identity.
    if (device?.id != deviceId && !(device == null && reconnect)) return false;
    final type = device?.type ?? (reconnect ? suspension?.deviceType : null);
    if (type != DeviceType.omi && type != DeviceType.openglass) return false;
    if ((!ignoreMute && (_preferences.capturePolicy.muted || (reconnect && suspension!.wasPaused))) ||
        _preferences.batchModeEnabled) {
      return false;
    }
    if (_liveRecovery.deviceStoppedByCaller || (suspension != null && !reconnect)) return false;
    final staged = _capture.stagedReadModel;
    return !staged.phoneOwnsCapture && !staged.callActive;
  }

  /// Pendant audio the transport received while capture held no listener.
  /// Persist it to the safety WAL (later uploaded like any recording), then
  /// try to bring live capture back.
  ///
  /// The write is synchronous and never moves a WAL session boundary: frames
  /// are stored only while the WAL already tracks this pendant's codec (the
  /// pendant was the last source). Otherwise they are counted and dropped, so
  /// orphan audio can never race a live start or retag a phone session.
  void _onOrphanAudio(String deviceId, List<int> packet) {
    if (!_orphanAudioAdmitted(deviceId) || packet.length <= BleDeviceSource.headerSize) return;
    final state = _liveRecovery;
    final now = _now();
    final last = state.lastOrphanAt;
    state.lastOrphanAt = now;
    if (last == null || now.difference(last) > _orphanEpisodeGap) state.orphanSource = null;
    state.orphanPackets++;
    final codec = state.codecByDevice[deviceId];
    final phone = _wal.getSyncs().phone;
    final persistable = codec != null && codec.isOpusSupported() && phone.currentCodec == codec;
    if (persistable) {
      final source = state.orphanSource ??=
          BleDeviceSource(codec: codec, deviceId: deviceId, deviceModel: _activeSource?.deviceModel ?? 'Omi');
      for (final frame in source.processBytes(List<int>.from(packet))) {
        phone.onFrameCaptured(frame, captureRoot: _captureEvidenceRoot);
      }
      CaptureContinuityMonitor.instance.onFrameInCustody();
    } else {
      state.orphanDropped++;
    }
    final lastLog = state.lastOrphanLogAt;
    if (lastLog == null || now.difference(lastLog) > const Duration(minutes: 10)) {
      state.lastOrphanLogAt = now;
      _emitCaptureRecovery(
          CaptureRecoveryObservedKind.pendantAudioOrphaned, CaptureRecoveryObservedTrigger.orphanAudio);
      unawaited(DebugLogManager.logWarning('capture_stopped_with_device_streaming', {
        'phase': _capture.stagedReadModel.phase.name,
        'recording_state': recordingState.name,
        'persisted': persistable,
        'packets': state.orphanPackets,
        'dropped': state.orphanDropped,
      }));
    }
    _restartFromOrphanAudio(now);
  }

  /// A pendant that streams to nobody: re-install the stream if capture still
  /// owns it, or start capture if a connect skipped it (e.g. during a sync).
  void _restartFromOrphanAudio(DateTime now) {
    final last = _liveRecovery.lastOrphanRestartAt;
    if (last != null && now.difference(last) < _orphanRestartInterval) return;
    if (SyncWakeScope.syncOnly || isPaused) return;
    _liveRecovery.lastOrphanRestartAt = now;
    if (_capture.stagedReadModel.phase == CapturePhase.pendantLive) {
      _kickLiveRecovery('orphan_audio');
      return;
    }
    _startIdlePendantCapture(CaptureRecoveryObservedTrigger.orphanAudio);
  }

  /// Foreground: reconnect what is down, and start a connected pendant that
  /// capture left idle (a skipped or failed start).
  void _recoverCaptureOnResume() {
    _kickLiveRecovery('app_resumed');
    if (SyncWakeScope.syncOnly) {
      if (_recordingDevice != null) _deferDeviceStartPastSyncPass(trigger: CaptureRecoveryObservedTrigger.appResumed);
      return;
    }
    // A muted pendant left idle (a failed or skipped start) is started too: a
    // muted device start lands paused with its button listener, so the Paused
    // card and the double-tap unmute come back without an app reinstall.
    _startIdlePendantCapture(CaptureRecoveryObservedTrigger.appResumed, admitMuted: true);
  }

  bool _idlePendantNeedsCapture({bool admitMuted = false}) {
    final device = _recordingDevice;
    if (_captureControllerDisposed || device == null || !_orphanAudioAdmitted(device.id, ignoreMute: admitMuted)) {
      return false;
    }
    return _capture.stagedReadModel.phase == CapturePhase.idle && (admitMuted || !isPaused);
  }

  void _startIdlePendantCapture(CaptureRecoveryObservedTrigger trigger, {bool admitMuted = false}) {
    if (!_idlePendantNeedsCapture(admitMuted: admitMuted)) return;
    Logger.debug('[Capture] pendant connected with capture idle; starting device capture (${trigger.wireName})');
    _emitCaptureRecovery(CaptureRecoveryObservedKind.captureStartRedriven, trigger);
    unawaited(streamDeviceRecording(device: _recordingDevice).catchError((Object error) {
      Logger.debug('[Capture] idle pendant capture start failed: $error');
    }));
  }

  /// A pendant start requested while an upload pass fences live capture. The
  /// pass used to swallow it, leaving a connected pendant uncaptured (and a
  /// legacy pendant discarding audio) until a cold start. Start it the moment
  /// the fence drops; the pass itself has a hard time limit.
  void _deferDeviceStartPastSyncPass({
    CaptureRecoveryObservedTrigger trigger = CaptureRecoveryObservedTrigger.syncPass,
  }) {
    final state = _liveRecovery;
    if (!state.deferredStart) {
      _emitCaptureRecovery(CaptureRecoveryObservedKind.captureStartSkipped, trigger);
      unawaited(
          DebugLogManager.logWarning('capture_start_skipped', {'reason': 'sync_pass', 'trigger': trigger.wireName}));
    }
    state.deferredStart = true;
    if (state.deferredStartRunning) return;
    state.deferredStartRunning = true;
    unawaited(_runDeferredDeviceStart());
  }

  Future<void> _runDeferredDeviceStart() async {
    final state = _liveRecovery;
    try {
      // A coalesced periodic wake can raise the next fence in the same turn
      // this one drops; a start swallowed again re-arms the flag and loops.
      while (state.deferredStart) {
        while (SyncWakeScope.syncOnly) {
          await SyncWakeScope.whenIdle;
          if (_captureControllerDisposed) return;
        }
        state.deferredStart = false;
        // Replays exactly the start the pass swallowed, for any pendant and mode.
        // A phone recording or call that owns capture now is not a reason to drop
        // it: the reducer records the pendant as suspended and resumes it after.
        final device = _recordingDevice;
        final staged = _capture.stagedReadModel;
        if (device == null || state.deviceStoppedByCaller || staged.pendantOwns || _pendantSuspension != null) {
          return;
        }
        _emitCaptureRecovery(
            CaptureRecoveryObservedKind.captureStartRedriven, CaptureRecoveryObservedTrigger.passEnded);
        await streamDeviceRecording(device: device);
      }
    } catch (error) {
      Logger.debug('[Capture] deferred device start failed: $error');
    } finally {
      state.deferredStartRunning = false;
      if (state.deferredStart && !_captureControllerDisposed) {
        state.deferredStartRunning = true;
        unawaited(_runDeferredDeviceStart());
      }
    }
  }

  /// A mute that outlived the app process: the audio start correctly refused
  /// to subscribe, so it never reached its own pause mark. Commit the session
  /// as paused instead of failing it closed to idle, which hid Resume, dropped
  /// the button subscription and left double-press nothing to resume.
  void _commitMutedStartAsPaused() {
    if (!isPaused || _recordingDevice == null) return;
    if (recordingState == RecordingState.deviceRecord || recordingState == RecordingState.pause) return;
    final phase = _capture.stagedReadModel.phase;
    if (phase != CapturePhase.pendantPaused && phase != CapturePhase.pendantBatchPaused) return;
    updateRecordingState(RecordingState.pause);
    unawaited(BatteryWidgetService().updateMuteState(true));
    _publishCaptureChange();
  }

  /// Resume (app, quick action or pendant double-press). Muted with no paused
  /// session, Resume only clears the mute, so also start the idle pendant.
  Future<void> _resumeStartingIdlePendant(CaptureEvent event) async {
    final idleMuted = isPaused && _recordingDevice != null && _capture.readModel.phase == CapturePhase.idle;
    final outcome = await _dispatchWithResumeFence(event);
    outcome.throwIfFailed();
    final device = _recordingDevice;
    if (!idleMuted || _captureControllerDisposed || device == null || isPaused) return;
    if (_liveRecovery.deviceStoppedByCaller || _pendantSuspension != null) return;
    final staged = _capture.stagedReadModel;
    if (staged.phase != CapturePhase.idle || staged.phoneOwnsCapture || staged.callActive) return;
    await streamDeviceRecording(device: device);
  }
}
