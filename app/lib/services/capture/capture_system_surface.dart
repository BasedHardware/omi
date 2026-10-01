import 'dart:async';

import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_lifetime.dart';
import 'package:omi/services/capture/capture_voice_meter.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';

abstract interface class CaptureSystemSurfaceSink {
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action);
  Future<void> publish(Map<String, Object?> snapshot);
  Future<void> close();
}

/// Projects the existing capture owner into an OS presentation. Owns only the
/// presentation clock and delivery, never audio, recovery, or mute authority.
class CaptureSystemSurface {
  CaptureSystemSurface(this.capture, this.sink, {DateTime Function()? now, this.voiceMeter})
      : _now = now ?? DateTime.now;

  final CaptureController capture;
  final CaptureSystemSurfaceSink sink;
  final CaptureVoiceMeter? voiceMeter;
  final DateTime Function() _now;
  String? _recordingId;
  int? _conversationRevision;
  DateTime? _anchor;
  DateTime? _pausedAt;
  String? _lastFingerprint;
  bool _closed = false;
  bool _busy = false;
  bool _ready = false;
  CaptureOwned? _listener;
  Timer? _heartbeat;
  Timer? _waveTick;
  Future<void> _delivery = Future.value();

  Future<void> start() async {
    _listener = capture.lifetime.listenTo(capture, _changed);
    capture.lifetime.own(close);
    // A bounded health refresh advances the stale deadline, not the timer.
    _heartbeat = capture.lifetime.periodic(const Duration(seconds: 30), (_) => _changed(force: true));
    final meter = voiceMeter;
    if (meter != null) {
      capture.systemSurfaceAudioTap = meter.add;
    }
    // The HTML wave breathes every 1.6 seconds, regardless of speech. Advance
    // each quarter-cycle while capture runs, including silent and unmetered sources.
    // ActivityKit animates these bounded updates; it cannot run an infinite loop.
    _waveTick = capture.lifetime.periodic(const Duration(milliseconds: 400), (_) {
      if (_closed || !_ready) return;
      final value = snapshot;
      if (value['active'] == true && value['paused'] == false) _changed(force: true);
    });
    try {
      await sink.start(_act);
      if (_closed) return;
      _ready = true;
      _changed(force: true);
    } catch (error) {
      Logger.debug('Live Activity unavailable: $error');
      await close();
    }
  }

  Map<String, Object?> get snapshot {
    final id = capture.activeRecordingId;
    final revision = capture.systemSurfaceConversationRevision;
    final state = capture.recordingState;
    final active = id != null &&
        (state == RecordingState.record ||
            state == RecordingState.deviceRecord ||
            state == RecordingState.pause ||
            state == RecordingState.interrupted ||
            (state == RecordingState.initialising && _anchor != null && id == _recordingId));
    // Only a user pause offers Resume. Connecting and interruptions recover on
    // their own; they freeze the clock but still offer Pause for privacy.
    final userPaused = capture.isPaused || state == RecordingState.pause;
    final interrupted = state == RecordingState.interrupted;
    final connecting = state == RecordingState.initialising;
    final paused = userPaused || interrupted || connecting;
    final now = _now();
    if (id != _recordingId || revision != _conversationRevision) {
      _recordingId = id;
      _conversationRevision = revision;
      _anchor = null;
      _pausedAt = null;
      voiceMeter?.reset();
    }
    if (active) {
      _anchor ??= now;
      if (paused) {
        _pausedAt ??= now;
      } else if (_pausedAt != null) {
        _anchor = _anchor!.add(now.difference(_pausedAt!));
        _pausedAt = null;
      }
    }
    final batch = capture.systemSurfaceBatchCapture;
    final status = !active
        ? 'ended'
        : userPaused
            ? 'paused'
            : interrupted
                ? 'interrupted'
                : connecting
                    ? 'connecting'
                    : batch
                        ? 'recording'
                        : capture.transcriptServiceReady
                            ? 'listening'
                            : 'reconnecting';
    return {
      'recordingId': id ?? '',
      'conversationRevision': revision,
      'active': active,
      'status': status,
      'source': capture.systemSurfacePhoneCapture ? 'phone' : 'pendant',
      'batch': batch,
      'startedAt': _anchor == null ? 0.0 : _anchor!.millisecondsSinceEpoch / 1000,
      'elapsed': _anchor == null ? 0 : (_pausedAt ?? now).difference(_anchor!).inSeconds.clamp(0, 2147483647),
      // Fractional capture time holds the decorative wave's phase across Stop / Start.
      'waveTime':
          _anchor == null ? 0.0 : (_pausedAt ?? now).difference(_anchor!).inMilliseconds.clamp(0, 2147483647000) / 1000,
      'paused': paused,
      'canPause': active && !capture.isCallActive,
      'canFinish': active &&
          (capture.systemSurfacePhoneCapture || batch || capture.segments.isNotEmpty || capture.photos.isNotEmpty),
      'busy': _busy,
      'actionFailed': false,
      ..._voice(active && !paused),
    };
  }

  /// Audio metadata is independent of the decorative wave's presentation clock.
  Map<String, Object?> _voice(bool capturing) {
    final meter = voiceMeter;
    final voice = capturing && meter != null && meter.voiceActive;
    return {
      'metered': capturing && meter != null && meter.hasSignal,
      'voice': voice,
      'levels': voice ? meter.levels() : const <int>[],
      'levelsEnd': meter?.latestBin ?? 0,
    };
  }

  void _changed({bool force = false}) {
    if (_closed || !_ready) return;
    final value = snapshot;
    // Elapsed time is drawn by the OS. Only a frozen value is significant.
    // The wave tick paces animation; audio levels never start or stop the loop.
    final fingerprint = {...value}
      ..remove('elapsed')
      ..remove('waveTime')
      ..remove('metered')
      ..remove('voice')
      ..remove('levels')
      ..remove('levelsEnd');
    if (value['paused'] == true) fingerprint['elapsed'] = value['elapsed'];
    final key = fingerprint.toString();
    if (!force && key == _lastFingerprint) return;
    _lastFingerprint = key;
    _delivery = _delivery.then((_) async {
      if (!_closed) await sink.publish(value);
    }).catchError((Object error) {
      _lastFingerprint = null;
      Logger.debug('Live Activity update failed: $error');
    });
  }

  Future<Map<String, Object?>> _act(Map<String, Object?> request) async {
    final current = snapshot;
    // A tap on an old card targets an old recording or conversation revision.
    // Repeats are safe: pause/resume are idempotent and Finish bumps the revision.
    if (_closed ||
        current['active'] != true ||
        request['recordingId'] != current['recordingId'] ||
        request['conversationRevision'] != current['conversationRevision']) {
      throw StateError('Recording is no longer available');
    }
    if (_busy) throw StateError('A recording action is already running');
    final action = request['action'];
    final allowed = switch (action) {
      'pause' || 'resume' => current['canPause'],
      'finish' => current['canFinish'],
      _ => false,
    };
    if (allowed != true) throw StateError('Action is unavailable for this recording');
    _busy = true;
    _changed(force: true);
    try {
      await capture.performSystemSurfaceAction(action as String,
          recordingId: current['recordingId'] as String, conversationRevision: current['conversationRevision'] as int);
      return snapshot;
    } finally {
      _busy = false;
      _changed(force: true);
    }
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _heartbeat?.cancel();
    _waveTick?.cancel();
    final meter = voiceMeter;
    if (meter != null) {
      if (capture.systemSurfaceAudioTap == meter.add) capture.systemSurfaceAudioTap = null;
      meter.dispose();
    }
    await _listener?.release();
    await _delivery;
    try {
      await sink.close();
    } catch (error) {
      Logger.debug('Live Activity cleanup unavailable: $error');
    }
  }
}
