/// Calendar gaps are a telemetry input, never conversation-list placeholders.
/// The server filters declined/tentative/all-day events. Cache accepted active
/// events until their end: a short later capture must not erase monitoring.
class CalendarCaptureWindow {
  const CalendarCaptureWindow(this.id, this.start, this.end);
  final String id;
  final DateTime start;
  final DateTime end;
}

class CalendarCaptureGapMonitor {
  CalendarCaptureGapMonitor({required this.load, required this.ownerKey, required this.emit});
  final Future<List<CalendarCaptureWindow>?> Function(DateTime start, DateTime end) load;
  final String Function() ownerKey;
  final void Function(Map<String, Object?> properties) emit;
  final Map<String, CalendarCaptureWindow> _active = {};
  final Set<String> _reported = {};
  String? _owner;
  DateTime? _lastFetch;
  bool _loading = false;
  bool _disposed = false;

  void dispose() {
    _disposed = true;
    _active.clear();
    _reported.clear();
  }

  Future<void> check(DateTime now, {required String? Function() gapReason, required String Function() phase}) async {
    if (_disposed) return;
    final owner = ownerKey();
    if (owner != _owner) {
      _owner = owner;
      _active.clear();
      _reported.clear();
      _lastFetch = null;
    }
    if (owner.isEmpty) return;
    if (!_loading && (_lastFetch == null || now.difference(_lastFetch!) >= const Duration(minutes: 2))) {
      _loading = true;
      _lastFetch = now;
      try {
        final windows = await load(now.subtract(const Duration(hours: 8)), now.add(const Duration(minutes: 2)));
        if (_disposed || owner != ownerKey()) return;
        for (final window in windows ?? <CalendarCaptureWindow>[]) {
          if (!window.start.isAfter(now) && window.end.isAfter(now)) _active[window.id] = window;
        }
      } catch (_) {
        // A failed calendar read is unknown, never proof of a capture gap.
      } finally {
        _loading = false;
      }
    }
    if (_disposed || owner != ownerKey()) return;
    _active.removeWhere((_, window) => !window.end.isAfter(now));
    _reported.removeWhere((key) => !_active.keys.any((id) => key.startsWith('$id:')));
    final reason = gapReason(); // sample health after the await, not before it
    if (reason == null) return;
    for (final window in _active.values) {
      if (now.difference(window.start) < const Duration(minutes: 1)) continue;
      if (!_reported.add('${window.id}:$reason')) continue;
      try {
        emit({
          'reason': reason,
          'phase': phase(),
          'meeting_elapsed_seconds': now.difference(window.start).inSeconds,
          'calendar_evidence': 'accepted_capture_gap',
        });
      } catch (_) {}
    }
  }
}
