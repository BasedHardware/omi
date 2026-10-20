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
  final List<DateTime> kicks = [];

  BleDeviceSource? orphanSource;
  bool orphanWalPrimed = false;
  bool orphanPriming = false;
  final List<List<int>> orphanBacklog = [];
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
  /// five minutes. The 15 s keep-alive keeps running underneath.
  static const _kickBackoff = [
    Duration(seconds: 1),
    Duration(seconds: 2),
    Duration(seconds: 5),
    Duration(seconds: 10),
    Duration(seconds: 15),
  ];
  static const _kickWindow = Duration(minutes: 5);
  static const _orphanRestartInterval = Duration(seconds: 30);
  static const _orphanEpisodeGap = Duration(seconds: 5);
  static const _orphanBacklogLimit = 3000; // ~30 s of pendant packets
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
    if (recordingState == RecordingState.deviceRecord) _socketReconnectPending = true;
    if (!(_keepAliveTimer?.isActive ?? false)) _startKeepAliveServices();
    final now = _now();
    final kicks = _liveRecovery.kicks..removeWhere((at) => now.difference(at) > _kickWindow);
    final delay = _kickBackoff[kicks.length.clamp(0, _kickBackoff.length - 1)];
    kicks.add(now);
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
    if (!_auth.isSignedIn() || _keepAliveReconnectEpoch == _keepAliveEpoch) return;
    _keepAliveLastExecutedAt = _now();
    final reconnectEpoch = _keepAliveEpoch;
    _keepAliveReconnectEpoch = reconnectEpoch;
    try {
      await _capture.dispatch(const KeepAliveTick());
    } catch (error) {
      Logger.debug('[Capture] kicked reconnect failed: $error');
    } finally {
      if (_keepAliveReconnectEpoch == reconnectEpoch) _keepAliveReconnectEpoch = null;
    }
  }

  bool _orphanAudioAdmitted(String deviceId) {
    final device = _recordingDevice;
    if (_captureControllerDisposed || device == null || device.id != deviceId) return false;
    if (device.type != DeviceType.omi && device.type != DeviceType.openglass) return false;
    if (_preferences.capturePolicy.muted || _preferences.batchModeEnabled) return false;
    if (_liveRecovery.deviceStoppedByCaller || _pendantSuspension != null) return false;
    final staged = _capture.stagedReadModel;
    return !staged.phoneOwnsCapture && !staged.callActive;
  }

  /// Pendant audio the transport received while capture held no listener.
  /// Persist it to the safety WAL (later uploaded like any recording), then
  /// try to bring live capture back.
  void _onOrphanAudio(String deviceId, List<int> packet) {
    if (!_orphanAudioAdmitted(deviceId) || packet.length <= BleDeviceSource.headerSize) return;
    final state = _liveRecovery;
    final now = _now();
    final last = state.lastOrphanAt;
    state.lastOrphanAt = now;
    if (last == null || now.difference(last) > _orphanEpisodeGap) {
      state.orphanWalPrimed = false;
      state.orphanSource = null;
    }
    state.orphanPackets++;
    final codec = state.codecByDevice[deviceId];
    final persistable = codec != null && codec.isOpusSupported();
    if (persistable) {
      // While priming is stuck, keep the newest audio: drop the oldest packet.
      if (state.orphanBacklog.length >= _orphanBacklogLimit) state.orphanBacklog.removeAt(0);
      state.orphanBacklog.add(List<int>.from(packet));
      if (state.orphanWalPrimed) {
        _flushOrphanBacklog(deviceId, codec);
      } else if (!state.orphanPriming) {
        unawaited(_primeOrphanWal(deviceId, codec));
      }
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
      }));
    }
    _restartFromOrphanAudio(now);
  }

  /// The WAL tracks one codec; a session boundary first, exactly as a fresh
  /// pendant stream does, so orphan frames never inherit another source's codec.
  ///
  /// The boundary is only taken while the transport still has no listener and
  /// no phone/call owns capture, rechecked after the await; when the WAL already
  /// tracks this codec (the pendant was the last source) no boundary is needed.
  Future<void> _primeOrphanWal(String deviceId, BleAudioCodec codec) async {
    final state = _liveRecovery;
    state.orphanPriming = true;
    try {
      final phone = _wal.getSyncs().phone;
      bool orphaned() => _orphanAudioAdmitted(deviceId) && _bleBytesStream == null;
      if (!orphaned()) {
        state.orphanBacklog.clear();
        return;
      }
      if (phone.currentCodec != codec) {
        await phone.onAudioCodecChanged(codec);
        if (!orphaned()) {
          // A live start or phone session won the race; it owns the WAL now.
          _flushOrphanBacklog(deviceId, codec);
          return;
        }
      }
      final model = _activeSource?.deviceModel ?? 'Omi';
      phone.setDeviceInfo(deviceId, model);
      state.orphanSource = BleDeviceSource(codec: codec, deviceId: deviceId, deviceModel: model);
      state.orphanWalPrimed = true;
      _flushOrphanBacklog(deviceId, codec);
    } catch (error, stack) {
      Logger.error('[Capture] orphan audio WAL setup failed: $error\n$stack');
    } finally {
      state.orphanPriming = false;
    }
  }

  /// Writes the backlog only while the WAL still tracks this pendant's codec
  /// and no phone/call owns capture; otherwise the packets cannot be stored
  /// without corrupting another session and are dropped.
  void _flushOrphanBacklog(String deviceId, BleAudioCodec codec) {
    final state = _liveRecovery;
    final phone = _wal.getSyncs().phone;
    if (!_orphanAudioAdmitted(deviceId) || phone.currentCodec != codec) {
      state.orphanBacklog.clear();
      return;
    }
    final source = state.orphanSource ??= BleDeviceSource(codec: codec, deviceId: deviceId, deviceModel: 'Omi');
    for (final packet in state.orphanBacklog) {
      for (final frame in source.processBytes(packet)) {
        phone.onFrameCaptured(frame, captureRoot: _captureEvidenceRoot);
      }
    }
    state.orphanBacklog.clear();
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
    _startIdlePendantCapture(CaptureRecoveryObservedTrigger.appResumed);
  }

  bool get _idlePendantNeedsCapture {
    final device = _recordingDevice;
    if (_captureControllerDisposed || device == null || !_orphanAudioAdmitted(device.id)) return false;
    return _capture.stagedReadModel.phase == CapturePhase.idle && !isPaused;
  }

  void _startIdlePendantCapture(CaptureRecoveryObservedTrigger trigger) {
    if (!_idlePendantNeedsCapture) return;
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
      while (SyncWakeScope.syncOnly) {
        await SyncWakeScope.whenIdle;
        if (_captureControllerDisposed) return;
      }
      if (!state.deferredStart) return;
      state.deferredStart = false;
      // Replays exactly the start the pass swallowed, for any pendant and mode.
      // A phone recording or call that owns capture now is not a reason to drop
      // it: the reducer records the pendant as suspended and resumes it after.
      final device = _recordingDevice;
      final staged = _capture.stagedReadModel;
      if (device == null || state.deviceStoppedByCaller || staged.pendantOwns || _pendantSuspension != null) {
        return;
      }
      _emitCaptureRecovery(CaptureRecoveryObservedKind.captureStartRedriven, CaptureRecoveryObservedTrigger.passEnded);
      await streamDeviceRecording(device: device);
    } catch (error) {
      Logger.debug('[Capture] deferred device start failed: $error');
    } finally {
      state.deferredStartRunning = false;
    }
  }
}
