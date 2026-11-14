import 'dart:async';

/// Why a recording ended, as the phone can honestly claim it. A lost pendant
/// is `disconnect`, never user intent; the server stores it as unknown.
enum CaptureEndType { userInitiated, silenceBackstop, disconnect }

extension CaptureEndTypeWire on CaptureEndType {
  String get wire => switch (this) {
        CaptureEndType.userInitiated => 'user_initiated',
        CaptureEndType.silenceBackstop => 'silence_backstop',
        CaptureEndType.disconnect => 'disconnect',
      };
}

/// One end of one recording. Times are this phone's clock: the server compares
/// them with recorded time, which is on the same clock.
class CaptureEndSignal {
  const CaptureEndSignal({
    required this.recordingSessionId,
    required this.type,
    required this.lastSpeechAt,
    required this.decidedAt,
  });

  final String recordingSessionId;
  final CaptureEndType type;
  final DateTime lastSpeechAt;
  final DateTime decidedAt;
}

/// Decides when a pendant recording has ended. Owns one fact per recording:
/// the last moment the on-phone VAD heard speech. It is a second clock beside
/// the 2-second chunk seal, which must never clear it.
///
/// Pure and synchronous: no timer runs. The silence end is evaluated on each
/// incoming packet, so it costs one comparison while the pendant streams and
/// nothing when it does not. A recording with no speech has no end to report.
class CaptureEndDetector {
  String? _recordingSessionId;
  DateTime? _lastSpeechAt;
  DateTime? _silenceEndedAt;
  int? _silenceSeconds;

  /// Server-provided silence timer. Null means: send no silence end.
  set silenceSeconds(int? seconds) => _silenceSeconds = (seconds != null && seconds > 0) ? seconds : null;
  int? get silenceSeconds => _silenceSeconds;

  DateTime? get lastSpeechAt => _lastSpeechAt;

  void _bind(String recordingSessionId) {
    if (_recordingSessionId == recordingSessionId) return;
    _recordingSessionId = recordingSessionId;
    _lastSpeechAt = null;
    _silenceEndedAt = null;
  }

  /// The VAD scored a frame of [recordingSessionId] as speech at [at].
  /// Speech after a silence end re-opens the recording: the next end carries a
  /// later decision time and supersedes the earlier one on the server.
  void speech(String? recordingSessionId, DateTime at) {
    if (recordingSessionId == null || recordingSessionId.isEmpty) return;
    _bind(recordingSessionId);
    if (_lastSpeechAt == null || at.isAfter(_lastSpeechAt!)) _lastSpeechAt = at;
    _silenceEndedAt = null;
  }

  /// A packet of [recordingSessionId] arrived at [now]. Returns the silence end
  /// the first time the timer has run out since the last speech.
  CaptureEndSignal? packet(String? recordingSessionId, DateTime now) {
    final seconds = _silenceSeconds;
    final speech = _lastSpeechAt;
    if (seconds == null || speech == null || _silenceEndedAt != null) return null;
    if (recordingSessionId == null || recordingSessionId != _recordingSessionId) return null;
    final decided = speech.add(Duration(seconds: seconds));
    if (now.isBefore(decided)) return null;
    _silenceEndedAt = decided;
    return CaptureEndSignal(
      recordingSessionId: recordingSessionId,
      type: CaptureEndType.silenceBackstop,
      lastSpeechAt: speech,
      decidedAt: decided,
    );
  }

  /// The recording stopped for [type] at [now]. Null when it never had speech.
  CaptureEndSignal? stopped(String? recordingSessionId, CaptureEndType type, DateTime now) {
    final speech = _lastSpeechAt;
    if (recordingSessionId == null || recordingSessionId != _recordingSessionId || speech == null) return null;
    _lastSpeechAt = null;
    _silenceEndedAt = null;
    _recordingSessionId = null;
    return CaptureEndSignal(
      recordingSessionId: recordingSessionId,
      type: type,
      lastSpeechAt: speech,
      decidedAt: now.isBefore(speech) ? speech : now,
    );
  }
}

typedef CaptureEndPoster = Future<bool> Function(CaptureEndSignal signal,
    {required int pendingWals, required DateTime sentAt});

/// Tells the server about an end, and tells it again once every sealed file of
/// that recording has been accepted, so the final copy carries zero pending
/// files. Measurement and latency only: a marker that is never sent changes
/// nothing about custody or upload, and the server falls back to its wait.
///
/// Held in memory by design. If the app dies before the resend, the recording
/// simply takes the server's ordinary wait.
class CaptureEndReporter {
  CaptureEndReporter({
    required CaptureEndPoster post,
    required int Function(String recordingSessionId) pendingWals,
    required Future<bool> Function() disabled,
    DateTime Function()? now,
  })  : _post = post,
        _pendingWals = pendingWals,
        _disabled = disabled,
        _now = now ?? DateTime.now;

  static const int maxTracked = 16;

  final CaptureEndPoster _post;
  final int Function(String recordingSessionId) _pendingWals;
  final Future<bool> Function() _disabled;
  final DateTime Function() _now;
  final Map<String, CaptureEndSignal> _open = {};
  final Map<String, int> _lastSentPending = {};
  Future<void> _queue = Future.value();

  /// Sends complete before later ones start, so a resend never overtakes the
  /// first report of the same end.
  Future<void> report(CaptureEndSignal signal) => _queue = _queue.then((_) => _send(signal, first: true));

  /// A file of [recordingSessionId] was accepted by the server.
  Future<void> uploadAccepted(String? recordingSessionId) {
    final signal = recordingSessionId == null ? null : _open[recordingSessionId];
    if (signal == null) return Future.value();
    return _queue = _queue.then((_) => _send(signal, first: false));
  }

  Future<void> _send(CaptureEndSignal signal, {required bool first}) async {
    final id = signal.recordingSessionId;
    if (first) {
      // A later end of the same recording replaces the earlier one.
      _open.remove(id);
      _lastSentPending.remove(id);
      while (_open.length >= maxTracked) {
        final oldest = _open.keys.first;
        _open.remove(oldest);
        _lastSentPending.remove(oldest);
      }
      _open[id] = signal;
    } else if (!identical(_open[id], signal)) {
      return;
    }
    try {
      if (await _disabled()) {
        _open.remove(id);
        _lastSentPending.remove(id);
        return;
      }
      final pending = _pendingWals(id);
      if (!first && _lastSentPending[id] == pending) return;
      final accepted = await _post(signal, pendingWals: pending, sentAt: _now());
      if (!accepted) return; // Not bound yet or unreachable: the next accepted file retries.
      _lastSentPending[id] = pending;
      if (pending == 0) {
        _open.remove(id);
        _lastSentPending.remove(id);
      }
    } catch (_) {
      // Never surfaces: the server's ordinary wait is the fallback.
    }
  }
}
