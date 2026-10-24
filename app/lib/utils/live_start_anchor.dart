import 'package:omi/backend/schema/episode.dart';

/// The start a live running length counts from. Never moves later while the same live stretch
/// lasts, and never falls back to a transcript offset (which resets with every conversation).
class LiveStartAnchor {
  DateTime? _start;
  String? _episodeId;
  String? _captureId;

  /// When the person last ended the live conversation. The next stretch counts from here, including
  /// once the next episode opens at its first words a little later.
  DateTime? _restartedAt;

  void clear() {
    _start = null;
    _episodeId = null;
    _captureId = null;
    _restartedAt = null;
  }

  /// The person ended the live conversation: the running length starts again at 0 from [now].
  void restart(DateTime now) {
    _restartedAt = now;
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
      if (_captureId != null && episode == null) {
        _start = null;
        _episodeId = null;
        _restartedAt = null;
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
      if (_episodeId != episode.id) {
        // Adopted once per episode: the server's start is when the occasion's first words arrived.
        // A server clock ahead of the phone keeps the capture start instead, so a later read of the
        // same episode can never move the start forward (and the label back down).
        _episodeId = episode.id;
        if (!episode.startedAt.isAfter(now)) {
          _start = episode.startedAt;
        } else if (captureStart != null && !captureStart.isAfter(now)) {
          _start = _start == null || captureStart.isBefore(_start!) ? captureStart : _start;
        }
      }
      return _start;
    }
    if (_episodeId != null) {
      // The server episode disappeared. This is now capture duration, not a new episode.
      // Count from the known capture start; with the lease lapsed during the quiet that
      // closed it, keep the old start
      // rather than reading 0s.
      _episodeId = null;
      if (captureStart != null && !captureStart.isAfter(now)) {
        _start = captureStart;
        return _start;
      }
    }
    if (!streaming) {
      _start = null;
      return null;
    }
    if (captureStart != null && !captureStart.isAfter(now) && (_start == null || captureStart.isBefore(_start!))) {
      _start = captureStart;
    }
    return _start;
  }
}
