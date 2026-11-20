import 'dart:async';
import 'dart:math';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import 'wal.dart';

bool _onDevice(Wal w) => w.storage == WalStorage.sdcard || w.storage == WalStorage.flashPage;
bool _moving(Wal w) =>
    w.status == WalStatus.miss &&
    !w.onDeviceOnly &&
    (w.syncDisplayState == WalSyncDisplayState.waiting ||
        w.syncDisplayState == WalSyncDisplayState.retrying ||
        w.syncDisplayState == WalSyncDisplayState.syncing);

/// Shared pure selection used by provider views and standalone fixtures. Synced
/// phone twins suppress device rows even though they are absent from pending.
List<Wal> pendingSyncRows(Iterable<Wal> wals) {
  final hidden = <String>{};
  final pending = <Wal>[];
  for (final w in wals) {
    if (!_onDevice(w) && (w.status == WalStatus.uploaded || w.status == WalStatus.synced)) hidden.add(w.id);
    if (_moving(w)) pending.add(w);
  }
  return _visibleSyncRows(pending, hidden.contains);
}

/// One display inventory for every pending-work amount. A completed phone
/// twin suppresses its device row even when its server handle has expired.
List<Wal> pendingWorkRows(Iterable<Wal> wals, {int? nowSeconds}) {
  final rows = wals.toList(growable: false);
  final hidden = {
    for (final w in rows)
      if (!_onDevice(w) && (w.status == WalStatus.uploaded || w.status == WalStatus.synced)) w.id,
  };
  return _pendingWorkRows(rows, hidden.contains, nowSeconds);
}

List<Wal> _pendingWorkRows(Iterable<Wal> rows, bool Function(String) hidden, int? nowSeconds) =>
    _visibleSyncRows(rows.where((w) => w.countsAsPendingWork(nowSeconds: nowSeconds)).toList(), hidden);

List<Wal> _visibleSyncRows(List<Wal> pending, bool Function(String) hidden) {
  final visible = pending.where((w) => !(_onDevice(w) && hidden(w.id))).toList();
  final sources = visible.where(_onDevice).toList();
  return visible.where((w) {
    if (_onDevice(w) || w.originalStorage == null || w.originalStorage == WalStorage.disk) return true;
    return !sources.any((src) =>
        src.device == w.device &&
        w.timerStart >= src.timerStart &&
        w.timerStart <= src.timerStart + max(0, src.seconds));
  }).toList(growable: false);
}

/// Mutable rows report dirty identities, so a status/progress refresh updates
/// contributions in O(changed), without reading the synced history. Membership
/// changes install a new inventory revision. Lists materialize lazily and are
/// shared by all selectors; pending selection visits only forward-moving work.
class WalDerivedViews {
  WalDerivedViews(Iterable<Wal> wals, {this.onPendingWorkExpired, DateTime Function()? clock})
      : _clock = clock ?? DateTime.now {
    var order = 0;
    for (final w in wals) {
      _order[w] = order++;
      w.addViewChangeListener(_changed);
      _apply(w);
    }
    _source = List<Wal>.of(wals);
  }

  /// A private copy of the last adopted snapshot (pointers only): lets [sync]
  /// recognise the common append-only change by comparison, even if the
  /// caller later edits the list it passed.
  List<Wal>? _source;

  /// Full identity reconciles run by [sync]; the append fast path skips them.
  @visibleForTesting
  int fullReconciles = 0;

  /// Adopts a new inventory snapshot without rebuilding unchanged rows.
  ///
  /// A capture flush adds one row to an index that can hold ~100k synced
  /// recordings; constructing fresh views for it cost seconds of UI-isolate
  /// time per flush. This pass does only identity lookups for retained rows
  /// and the full per-row work for added or removed ones. Every selector
  /// afterwards equals a fresh `WalDerivedViews(wals)` over the same list.
  void sync(Iterable<Wal> wals) {
    final previous = _source;
    final rows = List<Wal>.of(wals);
    _source = rows;
    if (previous != null && rows.length >= previous.length) {
      var same = true;
      for (var i = 0; i < previous.length; i++) {
        if (!identical(previous[i], rows[i])) {
          same = false;
          break;
        }
      }
      if (same) {
        // Append-only: retained rows keep their positions and order.
        for (var i = previous.length; i < rows.length; i++) {
          final w = rows[i];
          if (_entries.containsKey(w)) {
            _syncAll(rows);
            return;
          }
          _order[w] = i;
          w.addViewChangeListener(_changed);
          _apply(w);
        }
        refresh();
        return;
      }
    }
    _syncAll(rows);
  }

  void _syncAll(List<Wal> wals) {
    fullReconciles++;
    final epoch = ++_syncEpoch;
    var position = 0;
    var lastRetained = -1;
    var reordered = false;
    var distinct = 0;
    for (final w in wals) {
      final previous = _order[w];
      _order[w] = position++;
      if (_seen[w] == epoch) {
        // Listed twice: the last position wins, as in the constructor.
        reordered = true;
        continue;
      }
      _seen[w] = epoch;
      distinct++;
      if (!_entries.containsKey(w)) {
        w.addViewChangeListener(_changed);
        _apply(w);
      } else if (previous != null) {
        // Retained rows keep their relative order unless a previous position
        // goes backwards; uniform shifts from inserted rows change nothing.
        if (previous < lastRetained) reordered = true;
        lastRetained = previous;
      }
    }
    // Every row seen this pass is in [_entries], so a shortfall means removals.
    if (distinct < _entries.length) {
      final gone = [
        for (final w in _entries.keys)
          if (_seen[w] != epoch) w
      ];
      gone.forEach(_remove);
    }
    refresh();
    if (reordered) {
      sortRevision++;
      for (final bucket in _buckets) {
        bucket.invalidate();
      }
      _syncing = null;
      _invalidatePendingWork();
      _refusalSummary = null;
    }
  }

  int _syncEpoch = 0;
  final _seen = HashMap<Wal, int>.identity();

  void _remove(Wal w) {
    w.removeViewChangeListener(_changed);
    _dirty.remove(w);
    _order.remove(w);
    _seen.remove(w);
    final old = _entries.remove(w);
    if (old == null) return;
    _unindexId(old.id, w);
    displayCounts[old.display] = displayCounts[old.display]! - 1;
    statusCounts[old.status] = statusCounts[old.status]! - 1;
    if (old.hiddenId != null) {
      final count = _hidden[old.hiddenId]! - 1;
      if (count == 0) {
        _hidden.remove(old.hiddenId);
      } else {
        _hidden[old.hiddenId!] = count;
      }
    }
    for (var i = 0; i < _buckets.length; i++) {
      if (old.membership[i]) _buckets[i].update(w, false, sortChanged: false);
    }
    _syncing = null;
    _invalidatePendingWork();
    _refusalSummary = null;
  }

  final void Function()? onPendingWorkExpired;
  final DateTime Function() _clock;
  Timer? _pendingWorkTimer;

  int sortRevision = 0;
  final _entries = HashMap<Wal, _ViewEntry>.identity();
  final _order = HashMap<Wal, int>.identity();
  final _dirty = LinkedHashSet<Wal>.identity();
  final _hidden = <String, int>{};
  // id -> the row, or a Set<Wal> on the rare id collision. One row per id is
  // the norm; a set per row cost ~100k allocations on a long-lived phone.
  final _byId = <String, Object>{};

  void _indexId(String id, Wal w) {
    final current = _byId[id];
    if (current == null) {
      _byId[id] = w;
    } else if (current is Wal) {
      if (!identical(current, w)) _byId[id] = HashSet<Wal>.identity()..addAll([current, w]);
    } else {
      (current as Set<Wal>).add(w);
    }
  }

  void _unindexId(String id, Wal w) {
    final current = _byId[id];
    if (current is Wal) {
      if (identical(current, w)) _byId.remove(id);
    } else if (current is Set<Wal>) {
      current.remove(w);
      if (current.length == 1) {
        _byId[id] = current.single;
      } else if (current.isEmpty) {
        _byId.remove(id);
      }
    }
  }

  Iterable<Wal> rowsForIds(Set<String> ids) sync* {
    for (final id in ids) {
      final members = _byId[id];
      if (members == null) continue;
      final ordered = (members is Wal ? [members] : (members as Set<Wal>).toList())
        ..sort((a, b) => _order[a]!.compareTo(_order[b]!));
      yield* ordered;
    }
  }

  final displayCounts = <WalSyncDisplayState, int>{};
  final statusCounts = <WalStatus, int>{};
  final _buckets = List.generate(10, (_) => _ViewBucket());
  void _changed(Wal wal) => _dirty.add(wal);

  void refresh() {
    if (_dirty.isEmpty) return;
    for (final w in _dirty) {
      _apply(w);
    }
    _dirty.clear();
  }

  void dispose() {
    _pendingWorkTimer?.cancel();
    for (final w in _entries.keys) {
      w.removeViewChangeListener(_changed);
    }
  }

  void _apply(Wal w) {
    final old = _entries[w];
    final next = _ViewEntry(w);
    if (old != null && old.start != next.start) sortRevision++;
    if (old?.id != next.id) {
      if (old != null) {
        _unindexId(old.id, w);
      }
      _indexId(next.id, w);
    }
    if (old != null) {
      displayCounts[old.display] = displayCounts[old.display]! - 1;
      statusCounts[old.status] = statusCounts[old.status]! - 1;
      if (old.hiddenId != null) {
        final count = _hidden[old.hiddenId]! - 1;
        if (count == 0) {
          _hidden.remove(old.hiddenId);
        } else {
          _hidden[old.hiddenId!] = count;
        }
      }
    }
    displayCounts[next.display] = (displayCounts[next.display] ?? 0) + 1;
    statusCounts[next.status] = (statusCounts[next.status] ?? 0) + 1;
    if (next.hiddenId != null) {
      _hidden.update(next.hiddenId!, (n) => n + 1, ifAbsent: () => 1);
    }
    final startChanged = old != null && old.start != next.start;
    for (var i = 0; i < _buckets.length; i++) {
      // Most rows (synced history) belong to one bucket; skip the hash work
      // for buckets whose membership and sort key did not change.
      final now = next.membership[i];
      if (now != (old?.membership[i] ?? false) || (now && startChanged)) {
        _buckets[i].update(w, now, sortChanged: startChanged);
      }
    }
    _entries[w] = next;
    _syncing = null;
    _invalidatePendingWork();
    _refusalSummary = null;
  }

  void _invalidatePendingWork() {
    _pendingWork = null;
    _stalledUploads = null;
    _pendingWorkTimer?.cancel();
    _pendingWorkTimer = null;
    _pendingSecondsByDay = null;
  }

  int _byOrder(Wal a, Wal b) => _order[a]!.compareTo(_order[b]!);
  // Ties keep source order, so the result never depends on update history.
  int _newestFirst(Wal a, Wal b) {
    final byStart = b.timerStart.compareTo(a.timerStart);
    return byStart != 0 ? byStart : _byOrder(a, b);
  }

  List<Wal> _list(int bucket, {bool newest = false}) => _buckets[bucket].list(newest ? _newestFirst : _byOrder);
  int get legacyPendingCount => _buckets[0].members.length;
  int get corruptedCount => _buckets[2].members.length;
  int get deletableCount => _buckets[5].members.length;
  List<Wal> get legacyPending => _list(0);
  List<Wal> get synced => _list(1);
  List<Wal> get corrupted => _list(2);
  List<Wal> get uploaded => _list(3, newest: true);
  List<Wal> get missing => _list(4);
  List<Wal> get deletable => _list(5);
  List<Wal> get attention => _list(6, newest: true);
  List<Wal> get retryable => _list(7);
  List<Wal> get refused => _list(8, newest: true);
  bool get hasForwardMoving => _buckets[9].members.isNotEmpty;

  List<Wal>? _syncing;
  List<Wal> get syncing => _syncing ??=
      List.unmodifiable(_visibleSyncRows(_buckets[9].members.toList(), _hidden.containsKey)..sort(_newestFirst));
  List<Wal>? _pendingWork;
  List<Wal> get pendingWork => pendingWorkAt();
  int? _pendingWorkComputedAt;
  int? _pendingWorkDeadline;
  List<Wal> pendingWorkAt({int? nowSeconds}) {
    final now = nowSeconds ?? _clock().millisecondsSinceEpoch ~/ 1000;
    if (_pendingWork == null ||
        (_pendingWorkDeadline != null && now >= _pendingWorkDeadline!) ||
        (_pendingWorkComputedAt != null && now < _pendingWorkComputedAt!)) {
      _pendingWorkComputedAt = now;
      _stalledUploads = null;
      final candidates = [...uploaded, ...syncing];
      _pendingWork = List.unmodifiable(_pendingWorkRows(candidates, _hidden.containsKey, now));
      final deadlines = candidates.map((w) => w.pendingWorkExpiresAt).whereType<int>().where((t) => t > now);
      _pendingWorkDeadline = deadlines.isEmpty ? null : deadlines.reduce(min);
      _pendingWorkTimer?.cancel();
      if (onPendingWorkExpired != null && _pendingWorkDeadline != null) {
        // Same timebase as the deadline (the caller's `now`), so an injected clock can never
        // produce a past deadline and a zero-delay re-arm loop; at least 1 s between expiries.
        final delay = max(1000, (_pendingWorkDeadline! - now) * 1000);
        _pendingWorkTimer = Timer(Duration(milliseconds: delay), () {
          _pendingWorkTimer = null;
          _pendingWork = null;
          _stalledUploads = null;
          _pendingSecondsByDay = null;
          onPendingWorkExpired!();
        });
      }
    }
    return _pendingWork!;
  }

  /// Retained uploads with no recent server confirmation. Display only: these
  /// rows never enter deletion/retry eligibility or mutate the custody ledger.
  List<Wal>? _stalledUploads;
  List<Wal> stalledUploadsAt({int? nowSeconds}) {
    pendingWorkAt(nowSeconds: nowSeconds);
    return _stalledUploads ??= List.unmodifiable(_visibleSyncRows(
        uploaded.where((w) => !w.countsAsPendingWork(nowSeconds: nowSeconds)).toList(), _hidden.containsKey));
  }

  Map<DateTime, int>? _pendingSecondsByDay;
  int? _pendingSecondsComputedAt;
  int? _pendingSecondsDeadline;
  Map<DateTime, int> get pendingSecondsByDay => pendingSecondsByDayAt();
  Map<DateTime, int> pendingSecondsByDayAt({int? nowSeconds}) {
    final now = nowSeconds ?? _clock().millisecondsSinceEpoch ~/ 1000;
    if (_pendingSecondsByDay == null ||
        (_pendingSecondsDeadline != null && now >= _pendingSecondsDeadline!) ||
        (_pendingSecondsComputedAt != null && now < _pendingSecondsComputedAt!)) {
      _pendingSecondsComputedAt = now;
      _pendingSecondsByDay = _dayTotals(now);
    }
    return _pendingSecondsByDay!;
  }

  Map<DateTime, int> _dayTotals(int nowSeconds) {
    final totals = <DateTime, int>{};
    _pendingSecondsDeadline = null;
    for (final w in pendingWorkAt(nowSeconds: nowSeconds)) {
      if (!w.countsAsPendingWork(nowSeconds: nowSeconds)) continue;
      final expires = w.pendingWorkExpiresAt;
      if (expires != null) {
        _pendingSecondsDeadline = _pendingSecondsDeadline == null ? expires : min(_pendingSecondsDeadline!, expires);
      }
      final date = DateTime.fromMillisecondsSinceEpoch(w.timerStart * 1000);
      final day = DateTime(date.year, date.month, date.day);
      totals[day] = (totals[day] ?? 0) + max(0, w.seconds);
    }
    return Map.unmodifiable(totals);
  }

  int get pendingSeconds => pendingSecondsByDay.values.fold(0, (a, b) => a + b);

  WalRefusalSummary? _refusalSummary;
  int? _refusalDeadline;
  int? _refusalComputedAt;
  WalRefusalSummary refusalSummary({int? nowSeconds}) {
    final now = nowSeconds ?? _clock().millisecondsSinceEpoch ~/ 1000;
    if (_refusalSummary == null ||
        (_refusalDeadline != null && now >= _refusalDeadline!) ||
        (_refusalComputedAt != null && now < _refusalComputedAt!)) {
      _refusalComputedAt = now;
      _refusalSummary = WalRefusalSummary.from(refused, nowSeconds: now);
      final deadlines = refused
          .where((w) => w.uploadRejectedAt > 0)
          .map((w) => w.uploadRejectedAt + 7 * 86400)
          .where((deadline) => deadline > now);
      _refusalDeadline = deadlines.isEmpty ? null : deadlines.reduce(min);
    }
    return _refusalSummary!;
  }
}

class _ViewBucket {
  final members = LinkedHashSet<Wal>.identity();
  List<Wal>? _cache;
  void update(Wal wal, bool included, {required bool sortChanged}) {
    final changed = included ? members.add(wal) : members.remove(wal);
    if (changed || (included && sortChanged)) _cache = null;
  }

  List<Wal> list(int Function(Wal, Wal) compare) => _cache ??= List.unmodifiable(members.toList()..sort(compare));
  void invalidate() => _cache = null;
}

class _ViewEntry {
  factory _ViewEntry(Wal w) => _ViewEntry._(w, w.syncDisplayState);
  _ViewEntry._(Wal w, this.display)
      : id = w.id,
        status = w.status,
        start = w.timerStart,
        hiddenId = !_onDevice(w) && (w.status == WalStatus.uploaded || w.status == WalStatus.synced) ? w.id : null,
        membership = [
          w.status != WalStatus.synced &&
              w.status != WalStatus.uploadRejected &&
              w.status != WalStatus.corrupted &&
              w.status != WalStatus.outsideRecoveryWindow &&
              w.status != WalStatus.unsupportedAudio &&
              (w.status == WalStatus.miss || w.status == WalStatus.uploaded || w.isSyncing),
          w.status == WalStatus.synced,
          w.status == WalStatus.corrupted ||
              w.status == WalStatus.outsideRecoveryWindow ||
              w.status == WalStatus.unsupportedAudio,
          w.status == WalStatus.uploaded,
          w.status == WalStatus.miss,
          w.status == WalStatus.miss && !w.isSyncing,
          isAttentionSyncState(display),
          walRetryCanHelp(w),
          w.status == WalStatus.uploadRejected,
          _moving(w),
        ];
  final String id;
  final WalStatus status;
  final WalSyncDisplayState display;
  final int start;
  final String? hiddenId;
  final List<bool> membership;
}
