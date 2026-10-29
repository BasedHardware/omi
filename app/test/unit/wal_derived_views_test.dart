import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_views.dart';

Wal _row(int start, WalStatus status, {WalStorage storage = WalStorage.disk}) =>
    Wal(timerStart: start, codec: BleAudioCodec.opus, seconds: 30, status: status, storage: storage);

void main() {
  test('derived partitions/counts match full scans over mixed states and hide device twins', () {
    final rows = [
      for (final status in WalStatus.values) _row(1700000000 + status.index, status),
      _row(1700000100, WalStatus.miss)..retryCount = 1,
      _row(1700000200, WalStatus.miss)..retryCount = walMaxAutoRetries,
      _row(1700000300, WalStatus.miss)..isSyncing = true,
      _row(1700000400, WalStatus.miss)..onDeviceOnly = true,
      _row(1700000500, WalStatus.miss, storage: WalStorage.sdcard),
      _row(1700000500, WalStatus.synced),
      _row(1700000600, WalStatus.miss, storage: WalStorage.flashPage)..seconds = 100,
      _row(1700000610, WalStatus.miss)..originalStorage = WalStorage.flashPage,
      _row(1700000700, WalStatus.uploaded)..seconds = -1,
    ];
    final views = WalDerivedViews(rows);
    for (final status in WalStatus.values) {
      expect(views.statusCounts[status] ?? 0, rows.where((w) => w.status == status).length);
    }
    for (final state in WalSyncDisplayState.values) {
      expect(views.displayCounts[state] ?? 0, rows.where((w) => w.syncDisplayState == state).length);
    }
    expect(views.uploaded.toSet(), rows.where((w) => w.status == WalStatus.uploaded).toSet());
    expect(views.missing.toSet(), rows.where((w) => w.status == WalStatus.miss).toSet());
    expect(views.attention.toSet(), rows.where((w) => isAttentionSyncState(w.syncDisplayState)).toSet());
    expect(views.retryable.toSet(), rows.where(walRetryCanHelp).toSet());
    expect(views.deletable.toSet(), rows.where((w) => !w.isSyncing && w.status == WalStatus.miss).toSet());
    expect(views.syncing.map((w) => w.timerStart), [1700000600, 1700000300, 1700000100, 1700000001]);
    final oldRefusals = WalRefusalSummary.from(rows);
    expect(views.refusalSummary().count, oldRefusals.count);
    expect(views.refusalSummary().seconds, oldRefusals.seconds);
    expect(identical(views.refusalSummary(), views.refusalSummary()), isTrue);
    expect(views.pendingSecondsByDay.values.fold<int>(0, (a, b) => a + b), views.pendingSeconds);
    expect(views.pendingSeconds, 220);
  });

  test('incremental status, identity, duration and runtime changes match fresh full-scan views', () {
    final rows = [
      _row(1700000000, WalStatus.miss, storage: WalStorage.sdcard)..seconds = 100,
      _row(1700000000, WalStatus.synced)..originalStorage = WalStorage.sdcard,
      _row(1700000010, WalStatus.miss)..originalStorage = WalStorage.sdcard,
      _row(1700000200, WalStatus.miss)..retryCount = walMaxAutoRetries,
      _row(1700000300, WalStatus.uploadRejected)..uploadRejectedAt = 100,
    ];
    final incremental = WalDerivedViews(rows);
    addTearDown(incremental.dispose);
    final mutations = <void Function()>[
      () => rows[1].status = WalStatus.miss,
      () => rows[1].status = WalStatus.uploaded,
      () => rows[0].seconds = 150,
      () => rows[2].timerStart = 1900000000,
      () => rows[3].isSyncing = true,
      () => rows[1].device = 'changed-owner-source',
      () => rows[2].onDeviceOnly = true,
      () => rows[3].markCorrupted(),
      () => rows[4].seconds = 90,
      () => rows[1].status = WalStatus.synced,
    ];
    for (final mutate in mutations) {
      mutate();
      incremental.refresh();
      final full = WalDerivedViews(rows);
      for (final state in WalSyncDisplayState.values) {
        expect(incremental.displayCounts[state] ?? 0, full.displayCounts[state] ?? 0);
      }
      expect(incremental.legacyPending, full.legacyPending);
      expect(incremental.uploaded, full.uploaded);
      expect(incremental.syncing, full.syncing);
      expect(incremental.attention, full.attention);
      expect(incremental.pendingSecondsByDay, full.pendingSecondsByDay);
      expect(incremental.refusalSummary().seconds, full.refusalSummary().seconds);
      final ids = rows.map((w) => w.id).toSet();
      expect(incremental.rowsForIds(ids).toSet(), rows.toSet());
      full.dispose();
    }
  });

  test('refusal reported count advances at the exact seven-day deadline without an inventory refresh', () {
    final w = _row(1700000000, WalStatus.uploadRejected)..uploadRejectedAt = 100;
    final views = WalDerivedViews([w]);
    expect(views.refusalSummary(nowSeconds: 100).reportedCount, 0);
    expect(views.refusalSummary(nowSeconds: 100 + 7 * 86400).reportedCount, 1);
    expect(views.refusalSummary(nowSeconds: 100).reportedCount, 0);
  });
}
