import 'dart:async';
import 'dart:math' as math;

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

  /// The last published snapshot had a moving strip (levels to draw).
  bool _waveMoving = false;
  String? _recordingId;
  int? _conversationRevision;
  DateTime? _anchor;
  DateTime? _pausedAt;
  String? _lastFingerprint;
  bool _closed = false;
  bool _busy = false;

  /// Finish on the Lock Screen or in the island stops capture for good, so the presentation closes
  /// and stays closed until capture runs again (a resume or a new recording in Omi).
  bool _closedByFinish = false;
  bool _ready = false;
  CaptureOwned? _listener;
  Timer? _heartbeat;
  Timer? _voiceTick;
  Future<void> _delivery = Future.value();

  Future<void> start() async {
    _listener = capture.lifetime.listenTo(capture, _changed);
    capture.lifetime.own(close);
    // A bounded health refresh advances the stale deadline, not the timer.
    _heartbeat = capture.lifetime.periodic(const Duration(seconds: 30), (_) => _changed(force: true));
    final meter = voiceMeter;
    if (meter != null) {
      capture.systemSurfaceAudioTap = meter.add;
      // The OS cannot loop animations here; each update animates the strip
      // forward, so while audio is flowing the strip gets one update a second
      // (the presentation glides it across that second), plus one to settle it
      // when audio stops or capture pauses.
      _voiceTick = capture.lifetime.periodic(const Duration(seconds: 1), (_) {
        final value = snapshot;
        final moving = (value['levels'] as List).isNotEmpty;
        if (moving || _waveMoving) _changed(force: true, value: value);
      });
    }
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
    var active = id != null &&
        (state == RecordingState.record ||
            state == RecordingState.deviceRecord ||
            state == RecordingState.pause ||
            state == RecordingState.interrupted ||
            (state == RecordingState.initialising && _anchor != null && id == _recordingId));
    // Only a user pause offers Resume. Connecting and interruptions recover on
    // their own; they freeze the clock but still offer Pause for privacy.
    final userPaused = capture.isPaused || state == RecordingState.pause;
    if (_closedByFinish) {
      if (active && !userPaused && state != RecordingState.initialising) {
        _closedByFinish = false; // capturing again: show it again
      } else {
        active = false;
      }
    }
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
      'paused': paused,
      'canPause': active && !capture.isCallActive,
      // Finish always stops: with nothing heard yet there is simply nothing to process.
      'canFinish': active,
      'starred': capture.isConversationMarkedForStarring,
      'canStar': active,
      'busy': _busy,
      'actionFailed': false,
      ..._voice(active && !paused),
    };
  }

  /// Levels for the waveform; empty levels draw it still.
  ///
  /// While audio flows the strip always moves: heard voice at its real loudness,
  /// quiet moments as a soft undulation well below speech ([idleLevel]), so the
  /// card never looks frozen while Omi listens and never fakes someone talking.
  Map<String, Object?> _voice(bool capturing) {
    final meter = voiceMeter;
    final metered = capturing && meter != null && meter.hasSignal;
    return {
      'metered': metered,
      'voice': metered && meter.voiceActive,
      'levels': metered ? blendIdle(meter.levels(), meter.latestBin) : const <int>[],
      'levelsEnd': meter?.latestBin ?? 0,
    };
  }

  /// [real] loudness bins ending at bin [end], each raised to at least the idle undulation.
  static List<int> blendIdle(List<int> real, int end) {
    final start = end - real.length + 1;
    return [for (var i = 0; i < real.length; i++) math.max(real[i], idleLevel(start + i))];
  }

  /// The quiet-room strip: 8–26 % of full height, a smooth function of the absolute bin so a bar
  /// keeps its height as the strip slides (three slow waves, like breath rather than noise).
  static int idleLevel(int bin) {
    final t = bin.toDouble();
    final wave = (math.sin(t * 0.21) * 0.5 + 0.5) * 0.6 +
        (math.sin(t * 0.537 + 1.3) * 0.5 + 0.5) * 0.3 +
        (math.sin(t * 1.91 + 0.4) * 0.5 + 0.5) * 0.1;
    return (8 + 18 * wave).round();
  }

  void _changed({bool force = false, Map<String, Object?>? value}) {
    if (_closed || !_ready) return;
    value ??= snapshot;
    _waveMoving = (value['levels'] as List).isNotEmpty;
    // Elapsed time is drawn by the OS. Only a frozen value is significant.
    // Levels change constantly; the voice tick alone paces their delivery.
    final fingerprint = {...value}
      ..remove('elapsed')
      ..remove('levels')
      ..remove('levelsEnd');
    if (value['paused'] == true) fingerprint['elapsed'] = value['elapsed'];
    final key = fingerprint.toString();
    if (!force && key == _lastFingerprint) return;
    _lastFingerprint = key;
    final published = value;
    _delivery = _delivery.then((_) async {
      if (!_closed) await sink.publish(published);
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
      'star' => current['canStar'],
      _ => false,
    };
    if (allowed != true) throw StateError('Action is unavailable for this recording');
    _busy = true;
    _changed(force: true);
    try {
      await capture.performSystemSurfaceAction(action as String,
          recordingId: current['recordingId'] as String, conversationRevision: current['conversationRevision'] as int);
      if (action == 'finish') _closedByFinish = true;
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
    _voiceTick?.cancel();
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
