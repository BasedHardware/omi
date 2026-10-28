import 'package:omi/backend/schema/episode.dart';

/// The start a live running length counts from. While an episode is live, its own start owns the
/// timer. Without an episode, capture time is the fallback and survives short server gaps.
class LiveStartAnchor {
  DateTime? _start;
  String? _episodeId;
  String? _captureId;
  bool _hasCaptureStart = false;
  DateTime? _captureFloor;

  /// When the person last ended the live conversation. The next stretch counts from here, including
  /// once the next episode opens at its first words a little later.
  DateTime? _restartedAt;

  void clear() {
    _start = null;
    _hasCaptureStart = false;
    _episodeId = null;
    _captureId = null;
    _restartedAt = null;
    _captureFloor = null;
  }

  /// The person ended the live conversation: the running length starts again at 0 from [now].
  void restart(DateTime now) {
    _restartedAt = now;
    _captureFloor = now;
    _start = now;
    _episodeId = null;
  }

  DateTime? resolve({
    required Episode? episode,
    required DateTime? captureStart,
    String? captureId,
    required bool streaming,
    required DateTime now,
  }) {
    if (captureId != null && captureId != _captureId) {
      if (_captureId != null) {
        _start = null;
        _hasCaptureStart = false;
        _episodeId = null;
        _restartedAt = null;
        _captureFloor = null;
      }
      _captureId = captureId;
    }
    final restartedAt = _restartedAt;
    if (restartedAt != null) {
      // Keep counting from the restart: the next episode opens at its first words, and adopting its
      // later start would make the label jump backwards.
      if (episode != null) {
        _episodeId = episode.id;
        _restartedAt = null;
      }
      _start = restartedAt;
      return _start;
    }
    if (episode != null) {
      // Episodes can span several capture conversations. Their server-owned start is the live
      // row's elapsed-time authority, including after a hard-cap rotation. Keep an explicit
      // Wrap Up restart when it has already been adopted for this episode.
      if (_episodeId != episode.id) {
        _episodeId = episode.id;
        _start = episode.startedAt;
      }
      return _start;
    }
    final floor = _captureFloor;
    if (floor != null && captureStart != null && captureStart.isBefore(floor)) captureStart = floor;
    if (captureStart != null && !captureStart.isAfter(now)) {
      if (!_hasCaptureStart || _start == null || captureStart.isBefore(_start!)) _start = captureStart;
      _hasCaptureStart = true;
    }
    if (_episodeId != null) {
      // The server episode disappeared. This is now capture duration, not a new episode.
      // Count from the known capture start; with the lease lapsed during the quiet that
      // closed it, keep the old start
      // rather than reading 0s.
      _episodeId = null;
      if (captureStart != null && !captureStart.isAfter(now)) {
        if (_start == null || captureStart.isBefore(_start!)) _start = captureStart;
        return _start;
      }
    }
    if (!streaming) {
      _start = null;
      _hasCaptureStart = false;
      _captureFloor = null;
      return null;
    }
    if (captureStart != null && !captureStart.isAfter(now) && (_start == null || captureStart.isBefore(_start!))) {
      _start = captureStart;
    }
    return _start;
  }
}
