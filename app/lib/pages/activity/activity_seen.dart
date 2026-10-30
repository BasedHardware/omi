import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/daily_summary.dart';

/// Whether Activity holds something worth a dot on Home's bell.
///
/// Only delight lights the bell: a new daily recap. Changes Omi made on its own
/// (memories, people, tasks) are listed in Activity but never light it, so the
/// bell does not turn into a chore. Activity is not a to-do list: opening or
/// leaving it marks everything seen, with no per-item read state.
///
/// The watermark belongs to the signed-in account: switching accounts neither carries one user's
/// seen time nor their lit dot into the next.
class ActivitySeen {
  ActivitySeen({int Function()? read, void Function(int)? write, String Function()? owner})
      : _owner = owner ?? (() => SharedPreferencesUtil().uid),
        _readOverride = read,
        _writeOverride = write;

  static ActivitySeen instance = ActivitySeen();

  static const _key = 'activityDelightSeenAtMs';

  /// When each recap arrived, for [observe]. A recap without a server creation time is left out:
  /// its stand-in time is the parse time, which would relight the bell on every refresh.
  static Iterable<DateTime> recapArrivals(Iterable<DailySummary> recaps) =>
      recaps.where((r) => r.createdAtKnown).map((r) => r.createdAt);

  final String Function() _owner;
  final int Function()? _readOverride;
  final void Function(int)? _writeOverride;
  String? _ownerSeen;
  int _latestDelightMs = 0;

  String get _scopedKey => '$_key:${_owner()}';
  int _read() => _readOverride?.call() ?? SharedPreferencesUtil().getInt(_scopedKey);
  void _write(int value) {
    final write = _writeOverride;
    if (write != null) {
      write(value);
    } else {
      SharedPreferencesUtil().saveInt(_scopedKey, value);
    }
  }

  /// A different account signed in: forget the previous one's in-memory state.
  /// Whether [hasNew] describes the signed-in account. A bell built after an account switch shows no
  /// dot until the new account's first load, even when that load fails. Read-only, safe in build.
  bool get describesCurrentOwner => _ownerSeen != null && _ownerSeen == _owner();

  void _syncOwner() {
    final owner = _owner();
    if (owner == _ownerSeen) return;
    _ownerSeen = owner;
    _latestDelightMs = 0;
    hasNew.value = false;
  }

  /// True while a delight item is newer than the last visit to Activity.
  final ValueNotifier<bool> hasNew = ValueNotifier(false);

  /// When Activity was last opened or left, in epoch milliseconds; 0 if never.
  int get seenAtMs => _read();

  /// Reported by every surface after a successful load of delight items, even an empty one.
  ///
  /// [delights] is the full current set, not a delta: a deleted recap drops out of it, so the bell
  /// goes dark when the only unseen recap is gone.
  void observe(Iterable<DateTime> delights, {DateTime? now}) {
    _syncOwner();
    _latestDelightMs = 0;
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

  /// Activity showed everything up to [through] (default now). A recap seen elsewhere after that,
  /// say by Home refreshing behind an open Activity, keeps the bell lit.
  void markSeen({DateTime? through}) {
    _syncOwner();
    final ms = (through ?? DateTime.now()).millisecondsSinceEpoch;
    _write(ms);
    hasNew.value = _latestDelightMs > ms;
  }
}
