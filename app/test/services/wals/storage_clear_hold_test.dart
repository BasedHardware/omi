import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/ring_drain_policy.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_syncs.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _PhoneSync extends LocalWalSyncImpl {
  _PhoneSync() : super(_Listener());

  @override
  void start() {}

  @override
  Future<void> deleteAllPendingWals({WalDeleteProgress? onProgress, bool includeAccepted = true}) async {}

  /// When set, a single-recording upload runs until it completes.
  Completer<void>? upload;

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    await upload?.future;
    return null;
  }
}

/// A pendant reader that runs until cancelled (or forever, when [ignoresCancel]),
/// and that refuses a clear while it reads, as the real reader does.
class _Ring extends RingStorageSyncImpl {
  _Ring({this.ignoresCancel = false}) : super(_Listener());

  final bool ignoresCancel;
  final events = <String>[];
  Completer<void>? _read;
  int reads = 0;
  final pending = Wal(
    timerStart: 1704067200,
    codec: BleAudioCodec.opus,
    seconds: 11 * 3600,
    storage: WalStorage.sdcard,
    status: WalStatus.miss,
    fileNum: -1,
    device: 'pendant',
  );

  @override
  bool get isSyncing => _read != null;

  @override
  Future<void> refreshWalsFromDevice() async => events.add('discover');

  @override
  Future<List<Wal>> getMissingWals() async => pending.status == WalStatus.miss ? [pending] : [];

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    reads++;
    events.add('read');
    final read = _read = Completer<void>();
    await read.future;
    _read = null;
    events.add('read-stopped');
    return null;
  }

  void finishRead() {
    final read = _read;
    if (read != null && !read.isCompleted) read.complete();
  }

  @override
  void cancelSync() {
    if (ignoresCancel) return;
    finishRead();
  }

  @override
  Future<void> deleteAllPendingWals() async {
    if (isSyncing) {
      events.add('clear-refused');
      return;
    }
    events.add('clear');
    pending.status = WalStatus.synced;
  }
}

final _pendant = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);

Future<void> _settleMicrotasks() async {
  for (var i = 0; i < 5; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  group('Manage Storage transfer hold', () {
    late _Ring ring;
    late WalSyncs syncs;

    void attach({bool ignoresCancel = false}) {
      ring = _Ring(ignoresCancel: ignoresCancel);
      syncs = WalSyncs(_Listener(), phoneSync: _PhoneSync(), ringSync: ring);
      addTearDown(() {
        ring.finishRead();
        syncs.disableRingDrain();
      });
      syncs.setDevice(_pendant, firmwareVersion: '3.0.25');
      syncs.configureRingDrain(() => true);
    }

    test('a clear during an active pendant read stops it, then clears the pendant', () async {
      if (!ringDrainRecoveryEnabled) return;
      attach();
      await _settleMicrotasks();
      expect(ring.isSyncing, isTrue, reason: 'the independent drain is reading the 11 h backlog');

      // Today: the clear is refused while the read runs and only logs.
      await syncs.deleteAllPendingWals();
      expect(ring.events.last, 'clear-refused');

      final release = syncs.holdTransfersForClear();
      expect(await syncs.settleTransfersForClear(timeout: const Duration(seconds: 2)), isTrue);
      await syncs.deleteAllPendingWals();
      expect(ring.events.last, 'clear');
      release();
    });

    test('while held, the pendant drain cannot restart; discovery still lists the ring', () async {
      if (!ringDrainRecoveryEnabled) return;
      attach();
      await _settleMicrotasks();
      final release = syncs.holdTransfersForClear();
      expect(await syncs.settleTransfersForClear(timeout: const Duration(seconds: 2)), isTrue);
      final readsBefore = ring.reads;

      expect(await syncs.wakeRingDrain(), isFalse);
      expect(await syncs.wakeRingDrain(manual: true), isFalse);
      await syncs.wakeRingDrain(deviceId: _pendant.id, fromBle: true);
      await syncs.wakeRingDrain(discoveryOnly: true);
      await _settleMicrotasks();
      expect(ring.reads, readsBefore);
      expect(ring.events, contains('discover'));
      expect(syncs.transfersHeldForClear, isTrue);

      release();
      release(); // a second release is a no-op, never a negative count
      expect(syncs.transfersHeldForClear, isFalse);
      unawaited(syncs.wakeRingDrain());
      await _settleMicrotasks();
      expect(ring.reads, readsBefore + 1, reason: 'released, a normal wake resumes the drain');
    });

    test('an account switch drops the hold; the old session\'s release cannot underflow it', () async {
      if (!ringDrainRecoveryEnabled) return;
      attach();
      await _settleMicrotasks();
      final staleRelease = syncs.holdTransfersForClear();
      expect(syncs.transfersHeldForClear, isTrue);
      syncs.clearUserData();
      expect(syncs.transfersHeldForClear, isFalse);
      final current = syncs.holdTransfersForClear();
      staleRelease();
      expect(syncs.transfersHeldForClear, isTrue, reason: 'the stale release belongs to the old session');
      current();
      expect(syncs.transfersHeldForClear, isFalse);
    });

    test('while held, manual and coordinated transfers refuse to start', () async {
      if (!ringDrainRecoveryEnabled) return;
      attach();
      await _settleMicrotasks();
      final release = syncs.holdTransfersForClear();
      await syncs.settleTransfersForClear(timeout: const Duration(seconds: 2));
      expect(await syncs.syncAll(), isNull);
      await expectLater(syncs.syncWal(wal: ring.pending), throwsStateError);
      release();
    });

    test('a single-recording upload started from its row is joined before a clear', () async {
      final phone = _PhoneSync();
      final standalone = WalSyncs(_Listener(), phoneSync: phone, ringSync: _Ring());
      final upload = phone.upload = Completer<void>();
      final sync = standalone.syncWal(
        wal: Wal(timerStart: 1704067200, codec: BleAudioCodec.opus, seconds: 60, storage: WalStorage.disk),
      );
      final release = standalone.holdTransfersForClear();
      expect(
        await standalone.settleTransfersForClear(
          timeout: const Duration(milliseconds: 200),
          poll: const Duration(milliseconds: 20),
        ),
        isFalse,
        reason: 'the upload may still be writing the row a clear would delete',
      );
      upload.complete();
      await sync;
      expect(await standalone.settleTransfersForClear(timeout: const Duration(seconds: 2)), isTrue);
      release();
    });

    test('a read that will not stop is reported, never cleared over', () async {
      if (!ringDrainRecoveryEnabled) return;
      attach(ignoresCancel: true);
      await _settleMicrotasks();
      final release = syncs.holdTransfersForClear();
      final settled = await syncs.settleTransfersForClear(
        timeout: const Duration(milliseconds: 300),
        poll: const Duration(milliseconds: 20),
      );
      expect(settled, isFalse);
      await syncs.deleteAllPendingWals();
      expect(ring.events.last, 'clear-refused');
      expect(ring.pending.status, WalStatus.miss);
      release();
    });
  });

  group('storage clear selection and verification', () {
    var next = 1704067200;
    Wal wal(WalStatus status, {WalStorage storage = WalStorage.disk, int seconds = 60, int fileNum = 1}) => Wal(
          timerStart: next += 60,
          codec: BleAudioCodec.opus,
          seconds: seconds,
          status: status,
          storage: storage,
          fileNum: fileNum,
          device: 'pendant',
        );

    test('each scope targets only its rows; live buffers and accepted uploads are never targets', () {
      final synced = wal(WalStatus.synced);
      final miss = wal(WalStatus.miss);
      final ring = wal(WalStatus.miss, storage: WalStorage.sdcard, fileNum: -1);
      final refused = wal(WalStatus.uploadRejected);
      final accepted = wal(WalStatus.uploaded);
      final live = wal(WalStatus.miss, storage: WalStorage.mem);
      final rows = [synced, miss, ring, refused, accepted, live];

      expect(storageClearTargets(rows, StorageClearScope.uploaded), [synced]);
      expect(storageClearTargets(rows, StorageClearScope.notUploaded), [miss, ring]);
      expect(storageClearTargets(rows, StorageClearScope.all), [synced, miss, ring, refused]);
    });

    test('amounts are hours by place, with the fresh pendant backlog when the ring row is unlisted', () {
      final amounts = StorageAmounts.of([
        wal(WalStatus.synced, seconds: 3600),
        wal(WalStatus.miss, seconds: 600),
        wal(WalStatus.miss, storage: WalStorage.sdcard, fileNum: -1, seconds: 7200),
      ]);
      expect(amounts.uploadedSeconds, 3600);
      expect(amounts.phonePendingSeconds, 600);
      expect(amounts.devicePendingSeconds, 7200);
      expect(amounts.pendingCount, 2);

      expect(amounts.unuploadedSeconds, 7800);

      final refusedOnly = StorageAmounts.of([
        wal(WalStatus.synced, seconds: 3600),
        wal(WalStatus.uploadRejected, seconds: 1800),
        wal(WalStatus.outsideRecoveryWindow, seconds: 900),
      ]);
      expect(refusedOnly.pendingCount, 0);
      expect(refusedOnly.unuploadedCount, 2, reason: 'Delete everything must warn that these are lost');
      expect(refusedOnly.unuploadedSeconds, 2700);

      final reading = StorageAmounts.of([wal(WalStatus.miss, seconds: 600)], freshDeviceSeconds: 39600);
      expect(reading.devicePendingSeconds, 39600);
      expect(reading.pendingCount, 2);
    });

    test('a rebuilt ring row counts as left only beyond what the clear itself could record', () {
      final target = wal(WalStatus.miss, storage: WalStorage.sdcard, fileNum: -1, seconds: 39600);
      final refilled = wal(WalStatus.miss, storage: WalStorage.sdcard, fileNum: -1, seconds: 40);
      final kept = wal(WalStatus.miss, storage: WalStorage.sdcard, fileNum: -1, seconds: 39650);
      expect(refilled.id, isNot(target.id));

      final cleared = verifyStorageClear(
          targets: [target], current: [refilled], elapsed: const Duration(seconds: 20), failed: false);
      expect(cleared.complete, isTrue);
      expect(cleared.deletedSeconds, 39600);

      final unreachable =
          verifyStorageClear(targets: [target], current: [kept], elapsed: const Duration(seconds: 20), failed: false);
      expect(unreachable.complete, isFalse);
      expect(unreachable.remainingOnDeviceSeconds, 39600);
      expect(unreachable.deletedSeconds, 0);
    });

    test('phone rows left behind are reported with their audio', () {
      final a = wal(WalStatus.miss, seconds: 60);
      final b = wal(WalStatus.miss, seconds: 120);
      final outcome = verifyStorageClear(targets: [a, b], current: [b], elapsed: Duration.zero, failed: false);
      expect(outcome.remainingCount, 1);
      expect(outcome.remainingSeconds, 120);
      expect(outcome.deletedSeconds, 60);
      expect(outcome.remainingOnDeviceSeconds, 0);
    });
  });
}
