import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

/// Scripted [DeviceConnection]: clearRing / writeToStorage / getStorageList
/// results are set per test; everything else is unimplemented.
class _FakeConnection implements DeviceConnection {
  _FakeConnection({this.clearRingResult = true, this.writeResult, this.storageList = const [0]});

  final bool clearRingResult;
  final bool Function(int numFile, int command)? writeResult;
  final List<int> storageList;

  int clearRingCalls = 0;
  int deleteCommands = 0;
  int storageListCalls = 0;

  @override
  Future<bool> clearRing() async {
    clearRingCalls++;
    return clearRingResult;
  }

  @override
  Future<bool> writeToStorage(int numFile, int command, int offset) async {
    if (command == 1) deleteCommands++;
    final result = writeResult;
    return result == null ? true : result(numFile, command);
  }

  @override
  Future<List<int>> getStorageList() async {
    storageListCalls++;
    return storageList;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final _device = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

Wal _ringWal() => Wal(
      timerStart: 2000,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: 'omi-1',
      fileNum: -1,
    );

Wal _sdWal({int timerStart = 3000, int fileNum = 1, String device = 'omi-1'}) => Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: device,
      fileNum: fileNum,
      storageTotalBytes: 800000,
    );

void main() {
  group('RingStorageSyncImpl durable delete', () {
    test('removes the wal after the device confirms the ring clear', () async {
      final connection = _FakeConnection();
      final sync = RingStorageSyncImpl(_Listener())
        ..setDevice(_device)
        ..testConnection = connection
        ..testWals = [_ringWal()];

      await sync.deleteWal(_ringWal());

      expect(connection.clearRingCalls, 1);
      expect(await sync.getMissingWals(), isEmpty);
    });

    test('keeps the wal when the device rejects the ring clear', () async {
      final connection = _FakeConnection(clearRingResult: false);
      final sync = RingStorageSyncImpl(_Listener())
        ..setDevice(_device)
        ..testConnection = connection
        ..testWals = [_ringWal()];

      await sync.deleteWal(_ringWal());

      expect(connection.clearRingCalls, 1);
      expect((await sync.getMissingWals()).map((w) => w.id), [_ringWal().id]);
    });

    test('keeps the wal when no device is set', () async {
      final sync = RingStorageSyncImpl(_Listener())..testWals = [_ringWal()];

      await sync.deleteWal(_ringWal());

      expect((await sync.getMissingWals()).map((w) => w.id), [_ringWal().id]);
    });

    test('keeps the wal when the connection cannot be established', () async {
      // No test connection and no ServiceManager: the failed lookup must keep
      // the wal (fail-closed) instead of dropping it, and must not throw.
      final sync = RingStorageSyncImpl(_Listener())
        ..setDevice(_device)
        ..testWals = [_ringWal()];

      await sync.deleteWal(_ringWal());

      expect((await sync.getMissingWals()).map((w) => w.id), [_ringWal().id]);
    });

    test('deleteAllPendingWals drops pending wals after a confirmed ring clear', () async {
      final connection = _FakeConnection();
      final sync = RingStorageSyncImpl(_Listener())
        ..setDevice(_device)
        ..testConnection = connection
        ..testWals = [_ringWal()];

      await sync.deleteAllPendingWals();

      expect(connection.clearRingCalls, 1);
      expect(await sync.getMissingWals(), isEmpty);
    });

    test('deleteAllPendingWals keeps pending wals when the ring clear fails', () async {
      final connection = _FakeConnection(clearRingResult: false);
      final sync = RingStorageSyncImpl(_Listener())
        ..setDevice(_device)
        ..testConnection = connection
        ..testWals = [_ringWal()];

      await sync.deleteAllPendingWals();

      expect((await sync.getMissingWals()).map((w) => w.id), [_ringWal().id]);
    });
  });

  group('SDCardWalSyncImpl durable delete', () {
    test('removes the wal after the delete command and a readback showing the bytes gone', () async {
      final connection = _FakeConnection(storageList: [0]);
      final sync = SDCardWalSyncImpl(_Listener())
        ..testDevice = _device
        ..testConnection = connection
        ..testWals = [_sdWal()];

      await sync.deleteWal(_sdWal());

      expect(connection.deleteCommands, 1);
      expect(connection.storageListCalls, 1);
      expect(await sync.getMissingWals(), isEmpty);
    });

    test('keeps the wal when no device is set', () async {
      final connection = _FakeConnection();
      final sync = SDCardWalSyncImpl(_Listener())
        ..testConnection = connection
        ..testWals = [_sdWal()];

      await sync.deleteWal(_sdWal());

      expect(connection.deleteCommands, 0);
      expect((await sync.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('keeps the wal when its owning device is not the active one', () async {
      final connection = _FakeConnection();
      final stale = _sdWal(device: 'omi-0');
      final sync = SDCardWalSyncImpl(_Listener())
        ..testDevice = _device
        ..testConnection = connection
        ..testWals = [stale];

      await sync.deleteWal(stale);

      expect(connection.deleteCommands, 0);
      expect((await sync.getMissingWals()).map((w) => w.id), [stale.id]);
    });

    test('keeps the wal when the delete command is not accepted', () async {
      final connection = _FakeConnection(writeResult: (_, __) => false, storageList: [0]);
      final sync = SDCardWalSyncImpl(_Listener())
        ..testDevice = _device
        ..testConnection = connection
        ..testWals = [_sdWal()];

      await sync.deleteWal(_sdWal());

      expect(connection.deleteCommands, 1);
      expect(connection.storageListCalls, 0);
      expect((await sync.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('keeps the wal when the readback still shows the recording on the card', () async {
      final connection = _FakeConnection(storageList: [800000]);
      final sync = SDCardWalSyncImpl(_Listener())
        ..testDevice = _device
        ..testConnection = connection
        ..testWals = [_sdWal()];

      await sync.deleteWal(_sdWal());

      expect(connection.deleteCommands, 1);
      expect(connection.storageListCalls, 1);
      expect((await sync.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('keeps the wal when the readback is empty (cannot confirm)', () async {
      final connection = _FakeConnection(storageList: []);
      final sync = SDCardWalSyncImpl(_Listener())
        ..testDevice = _device
        ..testConnection = connection
        ..testWals = [_sdWal()];

      await sync.deleteWal(_sdWal());

      expect((await sync.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('deleteAllPendingWals keeps the unconfirmed item and removes the confirmed one', () async {
      final confirmed = _sdWal(timerStart: 3000, fileNum: 1);
      final rejected = _sdWal(timerStart: 4000, fileNum: 2);
      final connection = _FakeConnection(writeResult: (numFile, _) => numFile != 2, storageList: [0]);
      final sync = SDCardWalSyncImpl(_Listener())
        ..testDevice = _device
        ..testConnection = connection
        ..testWals = [confirmed, rejected];

      await sync.deleteAllPendingWals();

      expect((await sync.getMissingWals()).map((w) => w.id), [rejected.id]);
    });
  });
}
