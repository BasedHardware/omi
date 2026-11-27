import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/pendant_ring_drain_gate.dart';
import 'package:omi/services/wals/ring_drain_policy.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/wal_syncs.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _PhoneSync extends LocalWalSyncImpl {
  _PhoneSync({this.events}) : super(_Listener());

  final List<String>? events;

  @override
  void start() {}

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    events?.add('phone-history');
    return null;
  }

  @override
  Future<SyncLocalFilesResponse?> syncLiveCaptureOnly({IWalSyncProgressListener? progress}) async {
    events?.add('phone-live');
    return null;
  }
}

class _RingSync extends RingStorageSyncImpl {
  _RingSync(this.events) : super(_Listener());

  final List<String> events;
  final pending = Wal(
    timerStart: 1704067200,
    codec: BleAudioCodec.opus,
    seconds: 60,
    storage: WalStorage.sdcard,
    status: WalStatus.miss,
    fileNum: -1,
  );

  @override
  Future<void> refreshWalsFromDevice() async {}

  @override
  Future<List<Wal>> getMissingWals() async => pending.status == WalStatus.miss ? [pending] : [];

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    events.add(independentDiscovery ? 'independent-ring' : 'legacy-ring');
    pending.status = WalStatus.synced;
    return null;
  }
}

class _SettlingStorage extends StorageSyncImpl {
  _SettlingStorage(this.events, this.settled) : super(_Listener());

  final List<String> events;
  final Future<void> settled;
  final started = Completer<void>();
  bool fail = true;
  final pending = Wal(timerStart: 1704067200, codec: BleAudioCodec.opus, seconds: 60, status: WalStatus.miss);

  @override
  Future<void> refreshWalsFromDevice() async {}

  @override
  Future<List<Wal>> getMissingWals() async => [pending];

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    events.add('device-start');
    started.complete();
    await settled;
    events.add('device-settled');
    if (fail) throw TimeoutException('No data from device');
    return null;
  }
}

class _FailingSdcard extends _SpySdcard {
  _FailingSdcard(this.events);
  final List<String> events;

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    events.add('sd-failed');
    throw StateError('device read incomplete');
  }
}

class _DeleteSpyPhone extends _PhoneSync {
  _DeleteSpyPhone(this.events) : super(events: events);
  final List<String> events;

  @override
  Future<void> deleteAllSyncedWals() async => events.add('phone-delete');

  @override
  Future<void> deleteAllPendingWals() async => events.add('phone-pending-delete');
}

class _DeleteSpySdcard extends SDCardWalSyncImpl {
  _DeleteSpySdcard(this.events) : super(_Listener());
  final List<String> events;

  @override
  Future<void> deleteAllSyncedWals() async => events.add('sdcard-delete');

  @override
  Future<void> deleteAllPendingWals() async => events.add('sdcard-pending-delete');
}

class _DeleteSpyFlashPage extends FlashPageWalSyncImpl {
  _DeleteSpyFlashPage(this.events, {this.fail = false}) : super(_Listener());
  final List<String> events;
  final bool fail;

  @override
  Future<void> deleteAllSyncedWals() async {
    events.add('flash-delete');
    if (fail) throw StateError('device ACK was capped');
  }

  @override
  Future<void> deleteAllPendingWals() async {
    events.add('flash-pending-delete');
    if (fail) throw StateError('device ACK was capped');
  }
}

class _DeleteSpyStorage extends StorageSyncImpl {
  _DeleteSpyStorage(this.events) : super(_Listener());
  final List<String> events;

  @override
  Future<void> deleteAllSyncedWals() async => events.add('storage-delete');

  @override
  Future<void> deleteAllPendingWals() async => events.add('storage-pending-delete');
}

class _DeleteSpyRing extends RingStorageSyncImpl {
  _DeleteSpyRing(this.events) : super(_Listener());
  final List<String> events;

  @override
  Future<void> deleteAllSyncedWals() async => events.add('ring-delete');

  @override
  Future<void> deleteAllPendingWals() async => events.add('ring-pending-delete');
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

  group('remote pendant drain route', () {
    final cases = <(String, Future<bool?> Function(String), bool)>[
      ('missing flag', (_) async => null, true),
      ('resolved on', (_) async => true, true),
      ('resolved off', (_) async => false, false),
      ('failed read', (_) async => throw StateError('flags unavailable'), true),
    ];
    for (final (name, read, independent) in cases) {
      test('$name selects the effective cohort and reader', () async {
        final events = <String>[];
        final syncs = WalSyncs(
          _Listener(),
          phoneSync: _PhoneSync(events: events),
          ringSync: _RingSync(events),
          sdcardSync: _SpySdcard(),
        );
        addTearDown(syncs.disableRingDrain);
        final allowed = await PendantRingDrainGate.independentDrainAllowed(readFlag: (key) {
          expect(key, 'mobile-pendant-independent-ring-drain');
          return read(key);
        });
        final expectedIndependent = independent && ringDrainRecoveryEnabled;
        expect(allowed, independent);

        final pendant = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
        syncs.setDevice(pendant, firmwareVersion: '3.0.19');
        syncs.configureRingDrain(() => true, independentDrainAllowed: allowed);
        expect(syncs.drainCohort, isNull);
        syncs.updateFirmwareVersion(pendant.id, '3.0.25');
        await syncs.wakeRingDrain();
        expect(syncs.drainCohort, expectedIndependent ? 'on' : 'holdout');
        expect(events, expectedIndependent ? ['independent-ring'] : isEmpty);

        await syncs.syncAll();
        expect(
          events,
          expectedIndependent
              ? ['independent-ring', 'phone-live', 'phone-history']
              : ['phone-live', 'legacy-ring', 'phone-history'],
        );

        syncs.setDevice(null);
        expect(syncs.drainCohort, isNull);
      });
    }

    testWidgets('unresolved read defaults on after its deadline', (tester) async {
      final never = Completer<bool?>();
      final decision = PendantRingDrainGate.independentDrainAllowed(readFlag: (_) => never.future);
      await tester.pump(const Duration(seconds: 2));
      expect(await decision, isTrue);
    });
  });

  group('phone history after device failures', () {
    test('bounded stalled read settles before history uploads and the failure remains visible', () async {
      final events = <String>[];
      final settled = Completer<void>();
      final device = _SettlingStorage(events, settled.future);
      final syncs = WalSyncs(_Listener(), phoneSync: _PhoneSync(events: events), storageSync: device);
      final pass = syncs.syncAll();
      final failure = expectLater(pass, throwsA(isA<TimeoutException>()));
      await device.started.future;
      expect(events, ['phone-live', 'device-start']);
      settled.complete(); // The protocol's first-data/idle deadline has finished cleanup.
      await failure;
      expect(events, ['phone-live', 'device-start', 'device-settled', 'phone-history']);
      expect(device.pending.status, WalStatus.miss);
    });

    test('legacy SD exception cannot skip the independent phone backlog', () async {
      final events = <String>[];
      final syncs = WalSyncs(
        _Listener(),
        phoneSync: _PhoneSync(events: events),
        sdcardSync: _FailingSdcard(events),
      );
      syncs.setDevice(BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40), firmwareVersion: '3.0.16');
      await expectLater(syncs.syncAll(), throwsStateError);
      expect(events, ['phone-live', 'sd-failed', 'phone-history']);
    });

    test('user cancellation while device settles does not start a phone upload', () async {
      final events = <String>[];
      final settled = Completer<void>();
      final device = _SettlingStorage(events, settled.future)..fail = false;
      final syncs = WalSyncs(_Listener(), phoneSync: _PhoneSync(events: events), storageSync: device);
      final pass = syncs.syncAll();
      await device.started.future;
      syncs.cancelSync();
      settled.complete();
      await pass;
      expect(events, ['phone-live', 'device-start', 'device-settled']);
    });
  });

  test('bulk synced deletion reaches later stores after a flash ACK failure', () async {
    final events = <String>[];
    final syncs = WalSyncs(
      _Listener(),
      phoneSync: _DeleteSpyPhone(events),
      sdcardSync: _DeleteSpySdcard(events),
      flashPageSync: _DeleteSpyFlashPage(events, fail: true),
      storageSync: _DeleteSpyStorage(events),
      ringSync: _DeleteSpyRing(events),
    );

    await expectLater(syncs.deleteAllSyncedWals(), throwsStateError);
    expect(events, ['phone-delete', 'sdcard-delete', 'flash-delete', 'storage-delete', 'ring-delete']);
  });

  test('bulk pending deletion reaches later stores after a flash failure', () async {
    final events = <String>[];
    final syncs = WalSyncs(
      _Listener(),
      phoneSync: _DeleteSpyPhone(events),
      sdcardSync: _DeleteSpySdcard(events),
      flashPageSync: _DeleteSpyFlashPage(events, fail: true),
      storageSync: _DeleteSpyStorage(events),
      ringSync: _DeleteSpyRing(events),
    );

    await expectLater(syncs.deleteAllPendingWals(), throwsStateError);
    expect(events, [
      'phone-pending-delete',
      'sdcard-pending-delete',
      'flash-pending-delete',
      'storage-pending-delete',
      'ring-pending-delete',
    ]);
  });

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
