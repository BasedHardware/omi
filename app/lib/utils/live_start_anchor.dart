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
    final authoritative = episode?.timerStartedAt;
    if (authoritative != null) {
      // A current server episode replaces any cached capture or Wrap Up
      // anchor, including one retained since yesterday. Re-read on every poll
      // because late recorded speech can correct this same episode's start.
      _episodeId = episode!.id;
      _restartedAt = null;
      _start = authoritative;
      _captureFloor = authoritative;
      return authoritative;
    }
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
        if (_captureFloor == null || episode.startedAt.isAfter(_captureFloor!)) {
          _captureFloor = episode.startedAt;
        }
      }
      return _start;
    }
    if (_episodeId != null) {
      // A cap rotation briefly has no live row. Keep the old anchor through that gap; the
      // successor's server-owned start replaces it only after that row is visible.
      _episodeId = null;
      if (streaming && _start != null) {
        _captureFloor = _start;
        return _start;
      }
    }
    final floor = _captureFloor;
    if (floor != null && captureStart != null && captureStart.isBefore(floor)) captureStart = floor;
    if (captureStart != null && !captureStart.isAfter(now)) {
      if (!_hasCaptureStart || _start == null || captureStart.isBefore(_start!)) _start = captureStart;
      _hasCaptureStart = true;
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
