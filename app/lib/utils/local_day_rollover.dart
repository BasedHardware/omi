import 'dart:async';

import 'package:clock/clock.dart';

/// Rechecks the civil clock at midnight and at most once a minute while open.
/// The short check also catches timezone/clock changes without a lifecycle event.
class LocalDayRollover {
  LocalDayRollover(this.onChanged) {
    _last = clock.now();
    _schedule();
  }

  final void Function() onChanged;
  late DateTime _last;
  Timer? _timer;

  void _schedule() {
    final now = clock.now();
    final midnight = DateTime(now.year, now.month, now.day + 1);
    final until = midnight.difference(now) + const Duration(seconds: 1);
    _timer = Timer(until < const Duration(minutes: 1) ? until : const Duration(minutes: 1), () {
      final current = clock.now();
      if (current.year != _last.year ||
          current.month != _last.month ||
          current.day != _last.day ||
          current.timeZoneOffset != _last.timeZoneOffset) {
        _last = current;
        onChanged();
      }
      _schedule();
    });
  }

  void cancel() => _timer?.cancel();
}
