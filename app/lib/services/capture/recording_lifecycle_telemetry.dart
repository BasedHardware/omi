import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:uuid/uuid.dart';

typedef RecordingTelemetryEmitter = void Function(String eventName, Map<String, dynamic> properties);
typedef RecordingIdFactory = String Function();
typedef RecordingClock = DateTime Function();

/// Owns the analytics identity and timing for one mobile capture session.
///
/// Preparing a session mints the ID early enough to send it to `/v4/listen`,
/// but does not claim that recording started until the capture source confirms
/// it is producing audio.
class RecordingLifecycleTelemetry {
  RecordingLifecycleTelemetry({
    RecordingTelemetryEmitter? emitter,
    RecordingIdFactory? idFactory,
    RecordingClock? clock,
  })  : _emitter = emitter ?? _emitProductionEvent,
        _idFactory = idFactory ?? _defaultId,
        _clock = clock ?? DateTime.now;

  static const String startedEvent = 'Recording Started';
  static const String completedEvent = 'Recording Completed';
  static const String startFailedEvent = 'Recording Start Failed';

  final RecordingTelemetryEmitter _emitter;
  final RecordingIdFactory _idFactory;
  final RecordingClock _clock;

  String? _recordingId;
  String? _source;
  DateTime? _startedAt;
  bool _startedEmitted = false;

  String? get recordingId => _recordingId;

  static String _defaultId() => const Uuid().v4();

  static void _emitProductionEvent(String eventName, Map<String, dynamic> properties) {
    AnalyticsManager().track(eventName, properties: properties);
  }

  String prepare({required String source}) {
    if (_recordingId != null) return _recordingId!;
    _recordingId = _idFactory();
    _source = source;
    return _recordingId!;
  }

  void markStarted() {
    if (_recordingId == null || _source == null || _startedEmitted) return;
    _startedAt = _clock();
    _startedEmitted = true;
    _emit(startedEvent, {
      'recording_id': _recordingId,
      'recording_source': _source,
    });
  }

  void complete({String reason = 'user_stopped'}) {
    if (_recordingId == null) return;
    if (!_startedEmitted) {
      failStart(failureClass: 'pipeline_closed');
      return;
    }
    if (_startedAt != null) {
      _emit(completedEvent, {
        'recording_id': _recordingId,
        'recording_source': _source,
        'duration_seconds': _durationSeconds(_startedAt!),
        'reason': _normalizeReason(reason),
      });
    }
    _clear();
  }

  void failStart({required String failureClass}) {
    if (_recordingId == null) return;
    if (_startedEmitted) {
      complete(reason: 'pipeline_closed');
      return;
    }
    _emit(startFailedEvent, {
      'recording_id': _recordingId,
      'recording_source': _source,
      'failure_class': _normalizeFailureClass(failureClass),
    });
    _clear();
  }

  double _durationSeconds(DateTime startedAt) {
    final milliseconds = _clock().difference(startedAt).inMilliseconds;
    return (milliseconds < 0 ? 0 : milliseconds) / 1000.0;
  }

  void _emit(String eventName, Map<String, dynamic> properties) {
    try {
      _emitter(eventName, properties);
    } catch (_) {
      // Analytics must never change capture behavior.
    }
  }

  void _clear() {
    _recordingId = null;
    _source = null;
    _startedAt = null;
    _startedEmitted = false;
  }

  static String _normalizeReason(String reason) => switch (reason) {
        'user_stopped' || 'device_disconnected' || 'mode_changed' || 'pipeline_closed' => reason,
        _ => 'unknown',
      };

  static String _normalizeFailureClass(String failureClass) => switch (failureClass) {
        'permission_denied' ||
        'capture_unavailable' ||
        'pipeline_unavailable' ||
        'pipeline_closed' ||
        'unknown' =>
          failureClass,
        _ => 'unknown',
      };
}
