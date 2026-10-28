import 'dart:developer' show Timeline;

/// Code-owned labels only; never put recording IDs, paths or user content here.
enum LagWork { sync, syncDownload, syncUpload, reconcilePoll, upload, walLoad, indexSave, indexFlush }

final lagWork = LagWorkRegistry();

/// Bounded integer tokens and preallocated slots. Begin/end do no list/map
/// construction. Only a stall snapshot allocates. Completed spans are retained
/// because the watchdog may run just after the blocking work has returned.
class LagWorkRegistry {
  LagWorkRegistry({int Function()? nowUs, this.capacity = 64})
      : assert(capacity > 0),
        _nowUs = nowUs ?? (() => Timeline.now),
        _tags = List<LagWork?>.filled(capacity, null),
        _tokens = List<int>.filled(capacity, 0),
        _starts = List<int>.filled(capacity, 0),
        _ends = List<int>.filled(capacity, 0);

  final int capacity;
  final int Function() _nowUs;
  final List<LagWork?> _tags;
  final List<int> _tokens;
  final List<int> _starts;
  final List<int> _ends;
  int _next = 0;
  int _serial = 0;
  int dropped = 0;

  int begin(LagWork tag) {
    for (var offset = 0; offset < capacity; offset++) {
      final slot = (_next + offset) % capacity;
      if (_ends[slot] == -1) continue; // never evict active work
      _next = (slot + 1) % capacity;
      final token = ++_serial;
      _tags[slot] = tag;
      _tokens[slot] = token;
      _starts[slot] = _nowUs();
      _ends[slot] = -1;
      return token;
    }
    dropped++;
    return 0;
  }

  void end(int token) {
    if (token == 0) return;
    for (var slot = 0; slot < capacity; slot++) {
      if (_tokens[slot] == token && _ends[slot] == -1) {
        _ends[slot] = _nowUs();
        return;
      }
    }
  }

  List<String> overlapping(int startUs, int endUs) {
    final tags = <String>{};
    for (var slot = 0; slot < capacity; slot++) {
      final tag = _tags[slot];
      if (tag != null && _starts[slot] <= endUs && (_ends[slot] == -1 || _ends[slot] >= startUs)) {
        tags.add(tag.name);
      }
    }
    return tags.toList()..sort();
  }
}
