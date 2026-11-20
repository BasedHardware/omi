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
/// them with recorded time, which is on the same clock. [lastSpeechAt] is null
/// when the VAD never scored speech in this recording; that is reported as it
/// is, never replaced by an invented time.
class CaptureEndSignal {
  const CaptureEndSignal({
    required this.recordingSessionId,
    required this.type,
    required this.lastSpeechAt,
    required this.decidedAt,
  });

  final String recordingSessionId;
  final CaptureEndType type;
  final DateTime? lastSpeechAt;
  final DateTime decidedAt;
}

/// Decides when a pendant recording has ended. Owns one fact per recording:
/// the last moment the on-phone VAD heard speech. It is a second clock beside
/// the 2-second chunk seal, which must never clear it.
///
/// Pure and synchronous: no timer runs. The silence end is evaluated on each
/// incoming packet, so it costs one comparison while the pendant streams and
/// nothing when it does not. A recording with no speech has no silence end; an
/// explicit stop or a lost pendant is still reported, with no speech time.
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
    if (recordingSessionId == null || recordingSessionId.isEmpty) return null;
    // A journaled packet is what makes this a recording the lane owns, speech or not.
    _bind(recordingSessionId);
    final seconds = _silenceSeconds;
    final speech = _lastSpeechAt;
    if (seconds == null || speech == null || _silenceEndedAt != null) return null;
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

  /// The recording stopped for [type] at [now]. Null only when the lane never
  /// journaled a packet of it. With no speech scored, the end is still
  /// reported and carries no speech time.
  CaptureEndSignal? stopped(String? recordingSessionId, CaptureEndType type, DateTime now) {
    if (recordingSessionId == null || recordingSessionId != _recordingSessionId) return null;
    final speech = _lastSpeechAt;
    _lastSpeechAt = null;
    _silenceEndedAt = null;
    _recordingSessionId = null;
    return CaptureEndSignal(
      recordingSessionId: recordingSessionId,
      type: type,
      lastSpeechAt: speech,
      decidedAt: speech != null && now.isBefore(speech) ? speech : now,
    );
  }
}

typedef CaptureEndPoster = Future<bool> Function(CaptureEndSignal signal,
    {required int pendingWals, required DateTime sentAt});

/// Tells the server about an end, and tells it once more when all audio of
/// that recording up to the end has been accepted, so the final copy carries
/// zero pending files. Purely an observer of capture and upload: it seals
/// nothing, starts no upload and changes no chunk boundary. At most two accepted reports per end: the first, and the
/// one at zero. A report the server did not accept is retried on the next
/// accepted file. Latency information only: a marker that is never sent
/// changes nothing about custody or upload, and the server keeps its wait.
///
/// Held in memory by design. If the app dies before the resend, the recording
/// simply takes the server's ordinary wait.
class CaptureEndReporter {
  CaptureEndReporter({
    required CaptureEndPoster post,
    required FutureOr<int> Function(CaptureEndSignal signal) pendingWals,
    required Future<bool> Function() disabled,
    DateTime Function()? now,
    Object? Function()? scope,
    int Function()? observationVersion,
  })  : _post = post,
        _pendingWals = pendingWals,
        _disabled = disabled,
        _now = now ?? DateTime.now,
        _scope = scope ?? (() => null),
        _observationVersion = observationVersion ?? (() => 0);

  static const int maxTracked = 16;

  final CaptureEndPoster _post;

  /// Audio of the signal's recording, up to its end, that the server has not
  /// accepted: registered files, and anything still being written or
  /// published. The reporter only reads this; it never seals or uploads.
  final FutureOr<int> Function(CaptureEndSignal signal) _pendingWals;
  final Future<bool> Function() _disabled;

  final DateTime Function() _now;
  final Object? Function() _scope;
  final int Function() _observationVersion;
  final Map<String, Object?> _scopes = {};
  final Map<String, CaptureEndSignal> _open = {};
  final Set<String> _accepted = {};
  Future<void> _queue = Future.value();

  /// Sends complete before later ones start, so a resend never overtakes the
  /// first report of the same end.
  Future<void> report(CaptureEndSignal signal) {
    final scope = _scope(); // Bind before this report waits for any queued work.
    return _queue = _queue.then((_) => _send(signal, first: true, scope: scope));
  }

  /// A file of [recordingSessionId] was accepted by the server.
  Future<void> uploadAccepted(String? recordingSessionId) {
    final signal = recordingSessionId == null ? null : _open[recordingSessionId];
    if (signal == null) return Future.value();
    final scope = _scopes[recordingSessionId];
    return _queue = _queue.then((_) => _send(signal, first: false, scope: scope));
  }

  void _forget(String id) {
    _open.remove(id);
    _accepted.remove(id);
    _scopes.remove(id);
  }

  Future<void> _send(CaptureEndSignal signal, {required bool first, required Object? scope}) async {
    final id = signal.recordingSessionId;
    if (scope != _scope()) {
      if (identical(_open[id], signal)) _forget(id);
      return;
    }
    if (first) {
      // A later end of the same recording replaces the earlier one.
      _forget(id);
      while (_open.length >= maxTracked) {
        _forget(_open.keys.first);
      }
      _open[id] = signal;
      _scopes[id] = scope;
    } else if (!identical(_open[id], signal)) {
      return;
    }
    try {
      if (await _disabled()) {
        _forget(id);
        return;
      }
      final version = _observationVersion();
      final pending = await _pendingWals(signal);
      // Disk observation may yield through logout or a successor account.
      // Its emptied active index must never become an old recording's zero.
      if (scope != _scope()) {
        _forget(id);
        return;
      }
      // Keep the end for a later accepted-file wake if capture changed the
      // inventory during the read. A stale empty snapshot proves nothing.
      if (version != _observationVersion()) return;
      // Once the server holds this end, only "nothing left" is worth a call.
      if (_accepted.contains(id) && pending != 0) return;
      final accepted = await _post(signal, pendingWals: pending, sentAt: _now());
      if (!accepted) return; // Not bound yet or unreachable: the next accepted file retries.
      if (pending == 0) {
        _forget(id);
      } else {
        _accepted.add(id);
      }
    } catch (_) {
      // Never surfaces: the server's ordinary wait is the fallback.
    }
  }
}
