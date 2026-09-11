import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

final _device = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

Wal _sdWal() => Wal(
      timerStart: 2000,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: 'omi-1',
      fileNum: 1,
    );

Wal _phoneWal() =>
    Wal(timerStart: 1000, codec: BleAudioCodec.opus, seconds: 60, status: WalStatus.miss, storage: WalStorage.disk);

Wal _phoneCopyOf(Wal wal) => Wal(
      timerStart: wal.timerStart,
      codec: wal.codec,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: wal.device,
      originalStorage: WalStorage.sdcard,
    );

final _reachedDevice = throwsA(predicate((e) => '$e'.contains('Service manager is not initiated')));

void main() {
  group('SDCardWalSyncImpl.deleteWal', () {
    SDCardWalSyncImpl sync() => SDCardWalSyncImpl(_Listener())
      ..testDevice = _device
      ..testWals = [_sdWal()];

    test('leaves the device alone when a phone recording is deleted', () async {
      final s = sync();
      await s.deleteWal(_phoneWal());
      expect((await s.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('leaves the device alone when the phone copy of an SD recording is deleted', () async {
      final s = sync();
      expect(_phoneCopyOf(_sdWal()).id, _sdWal().id);
      await s.deleteWal(_phoneCopyOf(_sdWal()));
      expect((await s.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('still sends the delete to the device for its own recording', () async {
      await expectLater(sync().deleteWal(_sdWal()), _reachedDevice);
    });
  });

  group('StorageSyncImpl.deleteWal', () {
    StorageSyncImpl sync() => StorageSyncImpl(_Listener())
      ..setDevice(_device)
      ..testWals = [_sdWal()];

    test('leaves the device alone when a phone recording is deleted', () async {
      final s = sync();
      await s.deleteWal(_phoneWal());
      expect((await s.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('leaves the device alone when the phone copy of a device recording is deleted', () async {
      final s = sync();
      await s.deleteWal(_phoneCopyOf(_sdWal()));
      expect((await s.getMissingWals()).map((w) => w.id), [_sdWal().id]);
    });

    test('still sends the delete to the device for its own recording', () async {
      await expectLater(sync().deleteWal(_sdWal()), _reachedDevice);
    });
  });
}
