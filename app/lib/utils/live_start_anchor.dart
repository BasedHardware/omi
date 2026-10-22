import 'package:omi/backend/schema/episode.dart';

/// The start a live running length counts from. Never moves later while the same live stretch
/// lasts, and never falls back to a transcript offset (which resets with every conversation).
class LiveStartAnchor {
  DateTime? _start;
  String? _episodeId;

  DateTime? resolve({
    required Episode? episode,
    required DateTime? captureStart,
    required bool streaming,
    required DateTime now,
  }) {
    if (episode != null && !episode.startedAt.isAfter(now)) {
      // The server's start is authoritative: it is when the occasion's first words arrived.
      _episodeId = episode.id;
      _start = episode.startedAt;
      return _start;
    }
    if (_episodeId != null && episode == null) {
      // The episode closed (idle, wrap-up): the next stretch counts from its own start.
      _episodeId = null;
      _start = null;
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
