import 'package:flutter/foundation.dart';

/// Calendar evidence is telemetry, never conversation-list placeholders.
class CalendarCaptureWindow {
  const CalendarCaptureWindow(this.id, this.start, this.end);
  final String id;
  final DateTime start;
  final DateTime end;
}

/// Locally known windows, scoped to the account that requested them. This
/// monitor never fetches a calendar to discover whether polling is needed.
class CalendarMeetingSnapshot {
  const CalendarMeetingSnapshot({required this.owner, required this.windows});
  final String owner;
  final List<CalendarCaptureWindow> windows;
}

class CalendarCaptureGapMonitor {
  CalendarCaptureGapMonitor(
      {required this.load, required this.ownerKey, required this.localMeetings, required this.emit});
  final Future<List<CalendarCaptureWindow>?> Function(DateTime start, DateTime end) load;
  final String Function() ownerKey;
  final ValueListenable<CalendarMeetingSnapshot> localMeetings;
  final void Function(Map<String, Object?> properties) emit;
  final Map<String, CalendarCaptureWindow> _confirmed = {};
  final Set<String> _reported = {};
  String? _owner;
  String? _windowKey;
  DateTime? _nextFetch;
  Duration _backoff = const Duration(seconds: 60);
  bool _loading = false;
  bool _disposed = false;

  void dispose() {
    _disposed = true;
    _confirmed.clear();
    _reported.clear();
  }

  List<CalendarCaptureWindow> _windows(DateTime now) {
    final owner = ownerKey();
    if (owner != _owner) {
      _owner = owner;
      _confirmed.clear();
      _reported.clear();
      _resetBackoff();
    }
    if (owner.isEmpty || localMeetings.value.owner != owner) return [];
    return localMeetings.value.windows.where((w) => w.end.isAfter(now)).toList();
  }

  void _resetBackoff() {
    _windowKey = null;
    _nextFetch = null;
    _backoff = const Duration(seconds: 60);
  }

  /// Null means no timer or fetch: owning capture, no known meeting, or a
  /// retired account. A future meeting schedules its first check at start.
  DateTime? nextCheckAt(DateTime now, {required bool captureOwns}) {
    if (_disposed || _loading) return null;
    final windows = _windows(now);
    if (windows.isEmpty) {
      _resetBackoff();
      _confirmed.clear();
      _reported.clear();
      return null;
    }
    if (captureOwns) return null;
    final active = windows.where((w) => !w.start.isAfter(now)).toList();
    if (active.isEmpty) {
      _resetBackoff();
      return windows.map((w) => w.start).reduce((a, b) => a.isBefore(b) ? a : b);
    }
    final keys = active.map((w) => '${w.id}:${w.start.microsecondsSinceEpoch}:${w.end.microsecondsSinceEpoch}').toList()
      ..sort();
    final key = keys.join('|');
    if (key != _windowKey) {
      _resetBackoff();
      _windowKey = key;
    }
    return _nextFetch != null && _nextFetch!.isAfter(now) ? _nextFetch : now;
  }

  Future<void> check(DateTime now,
      {required bool Function() captureOwns,
      required String? Function() gapReason,
      required String Function() phase}) async {
    final due = nextCheckAt(now, captureOwns: captureOwns());
    if (due == null || due.isAfter(now) || _loading) return;
    final owner = _owner;
    final active = _windows(now).where((w) => !w.start.isAfter(now)).toList();
    if (active.isEmpty) return;
    _nextFetch = now.add(_backoff);
    _backoff = Duration(seconds: (_backoff.inSeconds * 2).clamp(60, 600));
    _loading = true;
    try {
      final windows = await load(
        active.map((w) => w.start).reduce((a, b) => a.isBefore(b) ? a : b),
        active.map((w) => w.end).reduce((a, b) => a.isAfter(b) ? a : b),
      );
      if (_disposed || owner != ownerKey() || captureOwns()) return;
      final knownIds = _windows(now).where((w) => !w.start.isAfter(now)).map((w) => w.id).toSet();
      for (final window in windows ?? <CalendarCaptureWindow>[]) {
        if (knownIds.contains(window.id) && !window.start.isAfter(now) && window.end.isAfter(now)) {
          _confirmed[window.id] = window;
        }
      }
      _confirmed.removeWhere((id, _) => !knownIds.contains(id));
      _reported.removeWhere((key) => !_confirmed.keys.any((id) => key.startsWith('$id:')));
      final reason = gapReason();
      if (reason == null) return;
      for (final window in _confirmed.values) {
        if (now.difference(window.start) < const Duration(minutes: 1)) continue;
        if (!_reported.add('${window.id}:$reason')) continue;
        try {
          emit({
            'reason': reason,
            'phase': phase(),
            'meeting_elapsed_seconds': now.difference(window.start).inSeconds,
            'calendar_evidence': 'accepted_capture_gap'
          });
        } catch (_) {}
      }
    } catch (_) {
      // Unavailable evidence is unknown, and retries still obey the backoff.
    } finally {
      _loading = false;
    }
  }
}
