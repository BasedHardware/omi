import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

// Clear/delete semantics on multi-file device storage, pinned two ways:
// a row whose delete reached the device always leaves the list (its positional
// index is potentially burned — FC-deleted-device-file-stays-addressable), and
// a row whose delete never reached the device stays listed, because
// refreshWalsFromDevice rebuilds the list from the device listing and would
// resurrect a prematurely removed row as a brand-new pending recording
// (#14688 — "waiting to sync" recordings that cannot be cleared). Unit tests
// cannot reach a live device delete (it goes through ServiceManager), so these
// cover the never-attempted side and the stale previous-device row; the
// drop-after-attempt side is pinned by legacy_storage_limitless_seam_test.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Wal storageWal({
    required int timerStart,
    required int fileNum,
    required WalStatus status,
    String device = 'pendant-1',
  }) =>
      Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        status: status,
        storage: WalStorage.sdcard,
        seconds: 60,
        storageOffset: 0,
        storageTotalBytes: 480000,
        fileNum: fileNum,
        device: device,
        deviceModel: 'Omi',
        totalFrames: 6000,
        syncedFrameOffset: 0,
      );

  test('deleteAllPendingWals without the device keeps every row', () async {
    final sync = StorageSyncImpl(_Listener());
    sync.testWals = [
      storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.miss),
      storageWal(timerStart: 2000, fileNum: 1, status: WalStatus.miss),
    ];

    await sync.deleteAllPendingWals();

    expect((await sync.getMissingWals()).map((w) => w.timerStart), [1000, 2000]);
  });

  test('deleteAllSyncedWals without the device keeps every row', () async {
    final sync = StorageSyncImpl(_Listener());
    final rows = [
      storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.synced),
      storageWal(timerStart: 2000, fileNum: 1, status: WalStatus.synced),
    ];
    sync.testWals = rows;

    await sync.deleteAllSyncedWals();

    expect(rows.every(sync.owns), isTrue);
  });

  test('deleteWal keeps the row when no delete can reach the device', () async {
    final sync = StorageSyncImpl(_Listener());
    final row = storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.miss);
    sync.testWals = [row];

    await sync.deleteWal(row);

    expect((await sync.getMissingWals()).single.timerStart, 1000);
  });

  test('deleteWal still drops a recording left by a previous device', () async {
    final sync = StorageSyncImpl(_Listener());
    sync.testDevice = BtDevice(
      id: 'pendant-2',
      name: 'Omi Pendant',
      type: DeviceType.omi,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: 'pendant-2'),
    );
    final stale = storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.miss, device: 'pendant-1');
    sync.testWals = [stale];

    await sync.deleteWal(stale);

    expect(await sync.getMissingWals(), isEmpty);
  });

  // Bulk clears must filter rows by device ownership the same way: after a
  // pendant switch, a stale row's fileNum names a different recording on the
  // new pendant, so sending it would delete that pendant's audio (#14688).
  // A row that slipped past the filter would reach ServiceManager for the
  // device delete and throw in this unit test, so these tests also prove the
  // stale rows never enter the firmware-delete path; they drop locally like
  // the single-row path above.
  test('deleteAllPendingWals drops previous-device rows without a device delete', () async {
    final sync = StorageSyncImpl(_Listener());
    sync.testDevice = BtDevice(
      id: 'pendant-2',
      name: 'Omi Pendant',
      type: DeviceType.omi,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: 'pendant-2'),
    );
    sync.testWals = [
      storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.miss, device: 'pendant-1'),
      storageWal(timerStart: 2000, fileNum: 1, status: WalStatus.miss, device: 'pendant-1'),
    ];

    await sync.deleteAllPendingWals();

    expect(await sync.getMissingWals(), isEmpty);
  });

  test('deleteAllSyncedWals drops previous-device rows without a device delete', () async {
    final sync = StorageSyncImpl(_Listener());
    sync.testDevice = BtDevice(
      id: 'pendant-2',
      name: 'Omi Pendant',
      type: DeviceType.omi,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: 'pendant-2'),
    );
    final stale = [
      storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.synced, device: 'pendant-1'),
      storageWal(timerStart: 2000, fileNum: 1, status: WalStatus.synced, device: 'pendant-1'),
    ];
    sync.testWals = stale;

    await sync.deleteAllSyncedWals();

    expect(stale.any(sync.owns), isFalse);
  });

  test('deleteAllSyncedWals leaves the previous device pending rows listed', () async {
    final sync = StorageSyncImpl(_Listener());
    sync.testDevice = BtDevice(
      id: 'pendant-2',
      name: 'Omi Pendant',
      type: DeviceType.omi,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: 'pendant-2'),
    );
    final staleSynced = storageWal(timerStart: 1000, fileNum: 0, status: WalStatus.synced, device: 'pendant-1');
    final stalePending = storageWal(timerStart: 2000, fileNum: 1, status: WalStatus.miss, device: 'pendant-1');
    sync.testWals = [staleSynced, stalePending];

    await sync.deleteAllSyncedWals();

    // Only the status this clear covers drops: the other device's pending
    // recording keeps its local row for its own reconnect.
    expect(sync.owns(staleSynced), isFalse);
    expect(await sync.getMissingWals(), [stalePending]);
  });
}
