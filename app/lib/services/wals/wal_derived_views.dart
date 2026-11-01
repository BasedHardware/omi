import 'dart:math';
import 'dart:collection';

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
  WalDerivedViews(Iterable<Wal> wals) {
    var order = 0;
    for (final w in wals) {
      _order[w] = order++;
      w.addViewChangeListener(_changed);
      _apply(w);
    }
  }

  int sortRevision = 0;
  final _entries = HashMap<Wal, _ViewEntry>.identity();
  final _order = HashMap<Wal, int>.identity();
  final _dirty = LinkedHashSet<Wal>.identity();
  final _hidden = <String, int>{};
  final _byId = <String, Set<Wal>>{};

  Iterable<Wal> rowsForIds(Set<String> ids) sync* {
    for (final id in ids) {
      final members = _byId[id];
      if (members == null) continue;
      final ordered = members.toList()..sort((a, b) => _order[a]!.compareTo(_order[b]!));
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
        final previous = _byId[old.id]!;
        previous.remove(w);
        if (previous.isEmpty) _byId.remove(old.id);
      }
      _byId.putIfAbsent(next.id, () => HashSet<Wal>.identity()).add(w);
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
    for (var i = 0; i < _buckets.length; i++) {
      _buckets[i].update(w, next.membership[i], sortChanged: old != null && old.start != next.start);
    }
    _entries[w] = next;
    _syncing = null;
    _pendingWork = null;
    _pendingSecondsByDay = null;
    _refusalSummary = null;
  }

  List<Wal> _list(int bucket, {bool newest = false}) => _buckets[bucket]
      .list(newest ? (a, b) => b.timerStart.compareTo(a.timerStart) : (a, b) => _order[a]!.compareTo(_order[b]!));
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
  List<Wal> get syncing =>
      _syncing ??= List.unmodifiable(_visibleSyncRows(_buckets[9].members.toList(), _hidden.containsKey)
        ..sort((a, b) => b.timerStart.compareTo(a.timerStart)));
  List<Wal>? _pendingWork;
  List<Wal> get pendingWork => _pendingWork ??= List.unmodifiable([...uploaded, ...syncing]);
  Map<DateTime, int>? _pendingSecondsByDay;
  Map<DateTime, int> get pendingSecondsByDay => _pendingSecondsByDay ??= _dayTotals();
  Map<DateTime, int> _dayTotals() {
    final totals = <DateTime, int>{};
    for (final w in pendingWork) {
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
    final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
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
}

class _ViewEntry {
  _ViewEntry(Wal w)
      : id = w.id,
        status = w.status,
        display = w.syncDisplayState,
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
          isAttentionSyncState(w.syncDisplayState),
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
