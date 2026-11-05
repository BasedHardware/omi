import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/wal_syncs.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

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
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async => null;

  @override
  Future<SyncLocalFilesResponse?> syncLiveCaptureOnly({IWalSyncProgressListener? progress}) async => null;
}

class _SpySdcard extends SDCardWalSyncImpl {
  _SpySdcard() : super(_Listener());

  BtDevice? attached;
  int listings = 0;
  int reads = 0;
  int starts = 0;
  int syncAllCalls = 0;
  final phantom = Wal(
    timerStart: 1704067200,
    codec: BleAudioCodec.opus,
    seconds: 60,
    status: WalStatus.miss,
    storage: WalStorage.sdcard,
    device: 'pendant',
    fileNum: 1,
  );

  @override
  void setDevice(BtDevice? device) => attached = device;

  @override
  Future<List<Wal>> getMissingWals() async {
    listings++;
    return [phantom];
  }

  @override
  Future<void> start() async => starts++;

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    syncAllCalls++;
    return null;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    reads++;
    return null;
  }
}

// Regression: background/auto-sync discovery read firmware off the raw connect
// object, which is frequently 'Unknown'. isRingBufferFirmware('Unknown') is
// false, so ring-buffer devices (fw >= 3.0.20 — current firmware) were routed
// to the multi-file enumerator and their offline recordings were never
// enumerated, uploaded, or turned into conversations (#10033). The fix resolves
// the enriched firmware first; only the Auto Sync page used to pass it.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('legacy SD isolation', () {
    for (final firmware in [null, '', 'Unknown']) {
      test('unknown firmware ($firmware) never attaches, lists, starts or reads legacy SD', () async {
        final sdcard = _SpySdcard();
        final syncs = WalSyncs(_Listener(), sdcardSync: sdcard, phoneSync: _PhoneSync());
        final raw = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40, firmwareRevision: firmware);
        syncs.setDevice(raw, firmwareVersion: firmware);
        expect(sdcard.attached, isNull);
        expect(await syncs.getMissingWals(), isEmpty);
        expect(await syncs.getAllWals(), isEmpty);
        await expectLater(syncs.syncWal(wal: sdcard.phantom), throwsStateError);
        syncs.start();
        await syncs.syncAll();
        expect(sdcard.starts, 0);
        expect(sdcard.syncAllCalls, 0);
        expect(sdcard.listings, 0);
        expect(sdcard.reads, 0);
      });
    }

    for (final firmware in ['1.0.2', '3.0.16', '3.0.21']) {
      test('a later resolution to $firmware re-routes the attached unknown device', () async {
        final sdcard = _SpySdcard();
        final syncs = WalSyncs(_Listener(), sdcardSync: sdcard, phoneSync: _PhoneSync());
        final raw = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
        syncs.setDevice(raw, firmwareVersion: '');
        expect(sdcard.attached, isNull);
        syncs.updateFirmwareVersion('other-device', '3.0.10');
        expect(sdcard.attached, isNull, reason: 'ignore another device\'s late read');
        syncs.updateFirmwareVersion(raw.id, firmware);
        if (firmware == '3.0.21') {
          expect(sdcard.attached, isNull);
          expect(await syncs.getAllWals(), isEmpty);
        } else {
          expect(sdcard.attached?.id, raw.id);
          expect(sdcard.attached?.firmwareRevision, firmware);
          expect(await syncs.getAllWals(), [sdcard.phantom]);
          await syncs.syncWal(wal: sdcard.phantom);
          syncs.start();
          expect(sdcard.starts, 1);
          expect(sdcard.reads, 1);
        }
        syncs.setDevice(null);
        syncs.updateFirmwareVersion(raw.id, '3.0.10');
        expect(sdcard.attached, isNull, reason: 'a late retry cannot reattach after disconnect');
      });
    }

    for (final firmware in ['3.0.20', '3.0.21', '3.1.0']) {
      test('$firmware never attaches, lists or reads legacy SD WALs', () async {
        final sdcard = _SpySdcard();
        final syncs = WalSyncs(_Listener(), sdcardSync: sdcard, phoneSync: _PhoneSync());
        final raw = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
        syncs.setDevice(raw, firmwareVersion: firmware);
        // Ring-owned recordings remain visible; the spy still holds a phantom SD recording.
        final ringWal = Wal(
          timerStart: 1704067200,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.sdcard,
          device: 'pendant',
          fileNum: -1,
        );
        syncs.ring.testWals = [ringWal];
        expect(sdcard.attached, isNull);
        expect(await syncs.getMissingWals(), [ringWal]);
        expect(await syncs.getAllWals(), [ringWal]);
        await expectLater(syncs.syncWal(wal: sdcard.phantom), throwsStateError);
        syncs.start();
        await syncs.syncAll();
        expect(sdcard.starts, 0);
        expect(sdcard.syncAllCalls, 0);
        expect(sdcard.listings, 0);
        expect(sdcard.reads, 0);
      });
    }

    for (final firmware in ['1.0.2', '3.0.10', '3.0.16', '3.0.19']) {
      test('$firmware keeps legacy attachment, listing and read routing', () async {
        final sdcard = _SpySdcard();
        final syncs = WalSyncs(_Listener(), sdcardSync: sdcard, phoneSync: _PhoneSync());
        final device = BtDevice(
          id: 'pendant',
          name: 'Omi',
          type: DeviceType.omi,
          rssi: -40,
          firmwareRevision: firmware,
        );
        syncs.setDevice(device);
        expect(sdcard.attached, same(device));
        expect(await syncs.getMissingWals(), [sdcard.phantom]);
        expect(await syncs.getAllWals(), [sdcard.phantom]);
        await syncs.syncWal(wal: sdcard.phantom);
        syncs.start();
        await syncs.syncAll();
        expect(sdcard.starts, 1);
        expect(sdcard.syncAllCalls, 1);
        expect(sdcard.listings, 4);
        expect(sdcard.reads, 1);
      });
    }

    test('switching from legacy to ring drops cached phantom inventory', () async {
      final sdcard = _SpySdcard();
      final syncs = WalSyncs(_Listener(), sdcardSync: sdcard, phoneSync: _PhoneSync());
      final device = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
      syncs.setDevice(device, firmwareVersion: '3.0.19');
      expect(await syncs.getAllWals(), [sdcard.phantom]);
      syncs.setDevice(device, firmwareVersion: '3.0.21');
      expect(await syncs.getAllWals(), isEmpty);
      expect(sdcard.attached, isNull);
      expect(sdcard.listings, 1);
    });
  });

  group('resolveDiscoveryFirmware', () {
    test('enriched value wins over a raw Unknown connect object', () {
      expect(WalSyncs.resolveDiscoveryFirmware('3.0.20', 'Unknown'), '3.0.20');
    });

    test('falls back to raw when enriched is Unknown/empty/null', () {
      expect(WalSyncs.resolveDiscoveryFirmware('Unknown', '3.0.20'), '3.0.20');
      expect(WalSyncs.resolveDiscoveryFirmware('', '3.0.20'), '3.0.20');
      expect(WalSyncs.resolveDiscoveryFirmware(null, '3.0.17'), '3.0.17');
    });
  });

  group('end-to-end routing decision', () {
    test('a ring-buffer device with a raw Unknown object now routes to ring', () {
      // Before the fix this classified false (raw 'Unknown') -> multi-file
      // enumerator -> recordings never discovered.
      final resolved = WalSyncs.resolveDiscoveryFirmware('3.0.20', 'Unknown');
      expect(WalSyncs.isRingBufferFirmware(resolved), isTrue);
    });

    test('older multi-file firmware still routes to storage', () {
      final resolved = WalSyncs.resolveDiscoveryFirmware('3.0.18', 'Unknown');
      expect(WalSyncs.isRingBufferFirmware(resolved), isFalse);
    });
  });
}
