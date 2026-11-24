import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_views.dart';

class _CountedWal extends Wal {
  _CountedWal(int start, WalStatus status, {super.storage = WalStorage.disk})
      : super(timerStart: start, codec: BleAudioCodec.opus, seconds: 30, status: status);
  int reads = 0;
  @override
  WalStatus get status {
    reads++;
    return super.status;
  }
}

const _storages = [WalStorage.disk, WalStorage.disk, WalStorage.disk, WalStorage.sdcard, WalStorage.flashPage];

Wal _random(Random r, int n) => _CountedWal(
      1700000000 + r.nextInt(400) * 10,
      WalStatus.values[r.nextInt(WalStatus.values.length)],
      storage: _storages[r.nextInt(_storages.length)],
    )
      ..retryCount = r.nextInt(walMaxAutoRetries + 1)
      ..isSyncing = r.nextInt(5) == 0
      ..originalStorage = r.nextInt(4) == 0 ? WalStorage.sdcard : null
      ..seconds = r.nextInt(120) - 1
      ..device = r.nextInt(6) == 0 ? 'dev-$n' : 'phone';

/// Every selector, in the order each one reports.
Object _snapshot(WalDerivedViews v, int now) => {
      'status': {for (final e in v.statusCounts.entries.where((e) => e.value != 0)) e.key: e.value},
      'display': {for (final e in v.displayCounts.entries.where((e) => e.value != 0)) e.key: e.value},
      'legacyPending': v.legacyPending,
      'synced': v.synced,
      'corrupted': v.corrupted,
      'uploaded': v.uploaded,
      'missing': v.missing,
      'deletable': v.deletable,
      'attention': v.attention,
      'retryable': v.retryable,
      'refused': v.refused,
      'syncing': v.syncing,
      'pendingWork': v.pendingWork,
      'forward': v.hasForwardMoving,
      'counts': [v.legacyPendingCount, v.corruptedCount, v.deletableCount],
      'byDay': v.pendingSecondsByDayAt(nowSeconds: now),
      'refusals': [v.refusalSummary(nowSeconds: now).count, v.refusalSummary(nowSeconds: now).seconds],
    };

void _expectSame(WalDerivedViews incremental, List<Wal> rows, String step) {
  final fresh = WalDerivedViews(rows);
  try {
    const now = 1800000000;
    expect(_snapshot(incremental, now), _snapshot(fresh, now), reason: step);
    final ids = {for (final w in rows.take(5)) w.id};
    expect(incremental.rowsForIds(ids).toList(), fresh.rowsForIds(ids).toList(), reason: '$step rowsForIds');
  } finally {
    fresh.dispose();
  }
}

void _randomWalk(Random r) {
  var n = 0;
  var rows = [for (var i = 0; i < 60; i++) _random(r, n++)];
  final views = WalDerivedViews(rows);
  addTearDown(views.dispose);
  for (var step = 0; step < 300; step++) {
    final next = List<Wal>.of(rows);
    switch (r.nextInt(8)) {
      case 0: // capture flush: append rows
        next.addAll([for (var i = 0; i <= r.nextInt(3); i++) _random(r, n++)]);
      case 1: // delete / sweep
        if (next.isNotEmpty) next.removeAt(r.nextInt(next.length));
      case 2: // device rows arrive ahead of phone rows
        next.insert(0, _random(r, n++));
      case 3: // reorder
        next.shuffle(r);
      case 4: // replace a row with a new object of the same identity
        if (next.isNotEmpty) {
          final i = r.nextInt(next.length);
          final old = next[i];
          next[i] = _random(r, n++)
            ..device = old.device
            ..timerStart = old.timerStart;
        }
      case 5: // status/progress changes on retained rows
        for (final w in next.take(5)) {
          w.status = WalStatus.values[r.nextInt(WalStatus.values.length)];
          w.isSyncing = !w.isSyncing;
        }
      case 6: // identity and sort key change in place
        if (next.isNotEmpty) {
          next[r.nextInt(next.length)]
            ..timerStart += 7
            ..device = 'moved-$step';
        }
      case 7: // a row listed twice
        if (next.isNotEmpty) next.add(next[r.nextInt(next.length)]);
    }
    views.sync(next);
    rows = next;
    _expectSame(views, rows, 'step $step');
  }
}

void main() {
  for (var seed = 1; seed <= 20; seed++) {
    test('sync over random snapshots and row mutations equals a fresh derivation (seed $seed)', () {
      _randomWalk(Random(seed));
    });
  }

  test('a list edited in place is reconciled, not trusted as an unchanged prefix', () {
    final rows = [for (var i = 0; i < 10; i++) _CountedWal(1700000000 + i, WalStatus.miss)];
    final views = WalDerivedViews(rows);
    addTearDown(views.dispose);
    rows
      ..removeAt(3)
      ..add(_CountedWal(1700000100, WalStatus.synced));
    views.sync(rows);
    _expectSame(views, rows, 'in-place edit');
  });

  test('removed rows stop notifying the views', () {
    final kept = _CountedWal(1700000000, WalStatus.miss);
    final gone = _CountedWal(1700000010, WalStatus.miss);
    final views = WalDerivedViews([kept, gone]);
    addTearDown(views.dispose);
    views.sync([kept]);
    gone.status = WalStatus.synced;
    views.refresh();
    expect(views.statusCounts[WalStatus.synced] ?? 0, 0);
    expect(views.missing, [kept]);
  });

  test('appending to a large synced history reads only the appended rows', () {
    final history = [for (var i = 0; i < 20000; i++) _CountedWal(1600000000 + i, WalStatus.synced)];
    final views = WalDerivedViews(history);
    addTearDown(views.dispose);
    final synced = views.synced;
    for (final w in history) {
      w.reads = 0;
    }
    final added = _CountedWal(1700000000, WalStatus.miss);
    final next = List<Wal>.unmodifiable([...history, added]);
    final reconciles = views.fullReconciles;
    views.sync(next);
    expect(views.fullReconciles, reconciles, reason: 'an append takes the pointer-comparison fast path');
    expect(history.fold<int>(0, (sum, w) => sum + w.reads), 0,
        reason: 'a capture flush must not re-derive the retained history');
    expect(views.missing, [added]);
    expect(identical(views.synced, synced), isTrue, reason: 'unchanged buckets keep their sorted lists');
    _expectSame(views, next, 'append');
  });

  test('a previously passed list edited in place cannot fake an unchanged prefix', () {
    final a = _CountedWal(1700000000, WalStatus.miss);
    final b = _CountedWal(1700000010, WalStatus.miss);
    final c = _CountedWal(1700000020, WalStatus.synced);
    final first = <Wal>[a, b];
    final views = WalDerivedViews(first);
    addTearDown(views.dispose);
    // The caller reuses its list; the next snapshot is a new object whose
    // prefix matches the edited list but not what the views adopted.
    first[1] = c;
    final next = <Wal>[a, c, _CountedWal(1700000030, WalStatus.miss)];
    views.sync(next);
    _expectSame(views, next, 'edited previous list');
    expect(views.missing, isNot(contains(b)));
  });

  test('Wal.id follows device and timerStart changes after it was cached', () {
    final w = _CountedWal(1700000000, WalStatus.miss);
    expect(w.id, 'phone_1700000000');
    w.timerStart = 1700000100;
    expect(w.id, 'phone_1700000100');
    w.device = 'pendant';
    expect(w.id, 'pendant_1700000100');
    final views = WalDerivedViews([w]);
    addTearDown(views.dispose);
    w.device = 'moved';
    views.refresh();
    expect(views.rowsForIds({'moved_1700000100'}).toList(), [w]);
    expect(views.rowsForIds({'pendant_1700000100'}).toList(), isEmpty);
  });
}
