import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';

/// Whether Activity holds something worth a dot on Home's bell.
///
/// Only delight lights the bell: a new daily recap. Changes Omi made on its own
/// (memories, people, tasks) are listed in Activity but never light it, so the
/// bell does not turn into a chore. Activity is not a to-do list: opening or
/// leaving it marks everything seen, with no per-item read state.
class ActivitySeen {
  ActivitySeen({int Function()? read, void Function(int)? write})
      : _read = read ?? (() => SharedPreferencesUtil().getInt(_key)),
        _write = write ?? ((value) => SharedPreferencesUtil().saveInt(_key, value));

  static ActivitySeen instance = ActivitySeen();

  static const _key = 'activityDelightSeenAtMs';

  final int Function() _read;
  final void Function(int) _write;
  int _latestDelightMs = 0;

  /// True while a delight item is newer than the last visit to Activity.
  final ValueNotifier<bool> hasNew = ValueNotifier(false);

  /// When Activity was last opened or left, in epoch milliseconds; 0 if never.
  int get seenAtMs => _read();

  /// Reported by every surface after a successful load of delight items, even an empty one.
  void observe(Iterable<DateTime> delights, {DateTime? now}) {
    for (final at in delights) {
      final ms = at.millisecondsSinceEpoch;
      if (ms > _latestDelightMs) _latestDelightMs = ms;
    }
    final seen = seenAtMs;
    if (seen == 0) {
      // First successful load on this install is the baseline, not news: what exists now (or
      // nothing at all) is seen, and the next recap to arrive lights the bell.
      final nowMs = (now ?? DateTime.now()).millisecondsSinceEpoch;
      _write(nowMs > _latestDelightMs ? nowMs : _latestDelightMs);
      hasNew.value = false;
      return;
    }
    hasNew.value = _latestDelightMs > seen;
  }

  /// Activity was opened or left: everything it holds has been seen.
  void markSeen({DateTime? now}) {
    final ms = (now ?? DateTime.now()).millisecondsSinceEpoch;
    _write(ms > _latestDelightMs ? ms : _latestDelightMs);
    hasNew.value = false;
  }
}
