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
    int Function()? identityEpoch,
  })  : _emitter = emitter ?? _emitProductionEvent,
        _idFactory = idFactory ?? _defaultId,
        _clock = clock ?? DateTime.now,
        _identityEpoch = identityEpoch ?? (() => AnalyticsManager.identityEpoch);

  static const String startedEvent = 'Recording Started';
  static const String completedEvent = 'Recording Completed';
  static const String startFailedEvent = 'Recording Start Failed';

  final RecordingTelemetryEmitter _emitter;
  final RecordingIdFactory _idFactory;
  final RecordingClock _clock;

  final int Function() _identityEpoch;
  int? _ownerEpoch;
  DateTime? _preparedAt;
  bool _audioObserved = false;
  bool _transcriptObserved = false;
  int _audioBytes = 0;
  int _socketBytes = 0;
  int _socketErrors = 0;
  int _connections = 0;

  /// Counts capture observations, never inferred loss or server persistence.
  void observeAudio(int bytes) {
    if (_recordingId == null || bytes <= 0) return;
    _audioBytes += bytes;
    if (_audioObserved) return;
    _audioObserved = true;
    _milestone('audio');
  }

  void observeSent(int bytes) {
    if (_recordingId != null && bytes > 0) _socketBytes += bytes;
  }

  void observeTranscript() {
    if (_recordingId == null || _transcriptObserved) return;
    _transcriptObserved = true;
    _milestone('transcript');
  }

  void observeSocketError() {
    if (_recordingId != null) _socketErrors++;
  }

  void observeConnected() {
    if (_recordingId != null) _connections++;
  }

  void _milestone(String stage) => _emit('Recording Observation', {
        'recording_id': _recordingId,
        'recording_source': _source,
        'stage': stage,
        'since_prepare_ms':
            _preparedAt == null ? 0 : (_clock().difference(_preparedAt!).inMilliseconds).clamp(0, 2147483647),
      });

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
    _ownerEpoch = _identityEpoch();
    _preparedAt = _clock();
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
        'audio_observed': _audioObserved,
        'audio_observation_coverage':
            _source?.startsWith('phone_mic_batch') == true ? 'native_batch_unavailable' : 'dart_ingress',
        'transcript_observed': _transcriptObserved,
        'audio_bytes_observed': _audioBytes,
        'socket_bytes_submitted': _socketBytes,
        'socket_error_count': _socketErrors,
        'socket_connection_count': _connections,
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
    if (_ownerEpoch != _identityEpoch()) return;
    try {
      _emitter(eventName, properties);
    } catch (_) {
      // Analytics must never change capture behavior.
    }
  }

  void _clear() {
    _recordingId = null;
    _ownerEpoch = null;
    _preparedAt = null;
    _audioObserved = false;
    _transcriptObserved = false;
    _audioBytes = 0;
    _socketBytes = 0;
    _socketErrors = 0;
    _connections = 0;
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
