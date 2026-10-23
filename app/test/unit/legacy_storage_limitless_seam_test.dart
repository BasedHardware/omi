import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_syncs.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _FakeLocalSync implements LocalWalSync {
  _FakeLocalSync({this.failOnChunk});

  final int? failOnChunk;
  Future<void>? addGate;
  final added = <Wal>[];
  final events = <String>[];

  @override
  int get sessionGeneration => 1;

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    final gate = addGate;
    if (gate != null) await gate;
    if (failOnChunk == added.length + 1) {
      events.add('addExternalWal:FAIL');
      throw const FileSystemException('index write failed');
    }
    added.add(wal);
    events.add('addExternalWal:${wal.filePath}');
  }

  @override
  Future<bool> ensureStorageAdmission({required int bytes, required int admittedGeneration}) async => true;

  @override
  Future<bool> hasDurableWal(Wal wal, {required int admittedGeneration}) async => added.contains(wal);

  @override
  void releaseStorageAdmission(int bytes) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeStorageDevice implements DeviceConnection {
  _FakeStorageDevice({required this.script});

  final List<List<int>> script;
  final writes = <List<int>>[];
  final deletes = <int>[];
  void Function(List<int>)? onBytes;
  final controller = StreamController<List<int>>.broadcast();

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    onBytes = onStorageBytesReceived;
    return controller.stream.listen((_) {});
  }

  @override
  Future<bool> writeToStorage(int numFile, int command, int offset) async {
    writes.add([numFile, command, offset]);
    if (command == 0x11) {
      scheduleMicrotask(() {
        for (final p in script) {
          onBytes!(p);
        }
      });
    }
    return true;
  }

  @override
  Future<bool> deleteStorageFile(int fileIndex) async {
    deletes.add(fileIndex);
    return true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Delivers [script] through the subscription it returns, as the BLE transports
/// do: once that subscription is cancelled, no later packet reaches the sync.
class _SubscribedStorageDevice extends _FakeStorageDevice {
  _SubscribedStorageDevice({required super.script});

  final firstPacketHandled = Completer<void>();
  int stops = 0;

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    return controller.stream.listen((value) {
      onStorageBytesReceived(value);
      if (!firstPacketHandled.isCompleted) firstPacketHandled.complete();
    });
  }

  @override
  Future<bool> writeToStorage(int numFile, int command, int offset) async {
    writes.add([numFile, command, offset]);
    if (command == 0x11) {
      for (final p in script) {
        controller.add(p);
      }
    }
    return true;
  }

  @override
  Future<bool> stopStorageSync() async {
    stops++;
    return true;
  }
}

class _FakeLimitless implements LimitlessDeviceConnection {
  _FakeLimitless({required this.pages});

  final List<Map<String, Object?>?> pages;
  int _extractIdx = 0;
  final acks = <int>[];
  bool batchMode = false;
  bool realTimeMode = false;

  @override
  void clearBuffer() {}

  @override
  Future<void> enableBatchMode() async {
    batchMode = true;
  }

  @override
  Future<void> enableRealTimeMode() async {
    realTimeMode = true;
  }

  @override
  int? get clockDriftOffsetMs => null;

  @override
  Map<String, Object?>? extractFramesWithSessionInfo() {
    if (_extractIdx >= pages.length) return null;
    return pages[_extractIdx++];
  }

  @override
  Future<void> acknowledgeProcessedData(int index) async {
    acks.add(index);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

List<int> _dataPacket(List<int> frameSizes) {
  final audio = <int>[];
  for (final s in frameSizes) {
    audio.add(s);
    audio.addAll(List<int>.filled(s, 0xAB));
  }
  audio.addAll(List<int>.filled(440 - audio.length, 0));
  final ts = ByteData(4)..setUint32(0, 1700000000, Endian.big);
  return [...ts.buffer.asUint8List(), ...audio];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('legacy_seam_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  Wal storageWal({int totalBytes = 440, int fileNum = 1, int timerStart = 1700000000}) => Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 5,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'devkit-1',
        fileNum: fileNum,
        storageOffset: 0,
        storageTotalBytes: totalBytes,
      );

  StorageSyncImpl storageSyncWith(_FakeLocalSync local, _FakeStorageDevice card, Wal wal) {
    final sync = StorageSyncImpl(_Listener())
      ..testDevice = BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40)
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(local);
    return sync;
  }

  WalSyncs walSyncsWith(_FakeLocalSync local, _FakeStorageDevice card, List<Wal> wals) {
    final syncs = WalSyncs(_Listener());
    syncs.storage
      ..testDevice = BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40)
      ..testConnection = card
      ..testWals = wals
      ..setLocalSync(local);
    return syncs;
  }

  test('StorageSync: durable write failure means the file is never deleted and never marked synced', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final local = _FakeLocalSync(failOnChunk: 1);
    final wal = storageWal();
    final sync = storageSyncWith(local, card, wal);

    await sync.syncAll();

    expect(card.deletes, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('StorageSync: delete only happens after the chunk is durably registered', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final local = _FakeLocalSync();
    final wal = storageWal();
    final sync = storageSyncWith(local, card, wal);

    await sync.syncAll();

    expect(local.added, hasLength(1));
    expect(card.deletes, [1]);
    await card.controller.close();
    await sync.stop();
  });

  test('StorageSync: clearing synced recordings never deletes by the index of a file the sync deleted', () async {
    // Every read gets the same packets: device file 0 arrives whole, while file 1
    // is twice as large, so its transfer is cut short and it stays pending.
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final local = _FakeLocalSync();
    final transferred = storageWal()..fileNum = 0;
    final pending = storageWal(totalBytes: 2 * 440)
      ..fileNum = 1
      ..timerStart = 1700000600;
    final sync = storageSyncWith(local, card, transferred)..testWals = [transferred, pending];

    await sync.syncAll();

    expect(transferred.status, WalStatus.synced);
    expect(card.deletes, [0]);
    // The firmware re-indexed after that delete: the pending recording is file 0 now.
    expect(card.writes, [
      [0, 0x11, 0],
      [0, 0x11, 0],
    ]);
    expect(pending.status, WalStatus.miss);
    expect(pending.fileNum, 0);

    // File 0 is the pending recording, so clearing synced recordings must not send a
    // delete. A device delete goes through ServiceManager, which unit tests never
    // start, so reaching the device would throw here.
    await expectLater(sync.deleteAllSyncedWals(), completes);
    expect(await sync.getMissingWals(), [pending]);

    // Control: deleting the pending recording itself still reaches the device.
    final reachedDevice = throwsA(predicate((e) => '$e'.contains('Service manager is not initiated')));
    await expectLater(sync.deleteWal(pending), reachedDevice);
    await card.controller.close();
    await sync.stop();
  });

  test('StorageSync: a device switch during persistence never issues DELETE on either connection', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final gate = Completer<void>();
    final local = _FakeLocalSync()..addGate = gate.future;
    final wal = storageWal();
    final sync = storageSyncWith(local, card, wal);

    final future = sync.syncAll();
    await Future.delayed(const Duration(milliseconds: 200));
    sync.setDevice(BtDevice(id: 'devkit-2', name: 'Other', type: DeviceType.omi, rssi: -40));
    gate.complete();
    await future;

    expect(local.added, hasLength(1), reason: 'A-side audio persists independently of the device switch');
    expect(card.deletes, isEmpty, reason: 'the source connection must not delete after a device switch');
    await card.controller.close();
    await sync.stop();
  });

  test('StorageSync: cancelling mid-file ends the sync without waiting for the transfer timeout', () async {
    // Only the first of four packets arrives before the user cancels.
    final card = _SubscribedStorageDevice(
      script: [
        _dataPacket([40]),
      ],
    );
    final local = _FakeLocalSync();
    final wal = storageWal(totalBytes: 4 * 440);
    final sync = storageSyncWith(local, card, wal);

    final syncing = sync.syncAll();
    await card.firstPacketHandled.future;
    sync.cancelSync();
    // The transfer timeout is 10 minutes; a cancel must not wait for it.
    await syncing.timeout(const Duration(seconds: 5));

    expect(sync.isSyncing, isFalse);
    expect(card.stops, greaterThan(0), reason: 'the device is told to stop sending');
    expect(local.added, hasLength(1), reason: 'audio already downloaded is kept on the phone');
    expect(card.deletes, isEmpty, reason: 'a cancelled file stays on the device');
    expect(wal.status, WalStatus.miss);
    await card.controller.close();
    await sync.stop();
  });

  test('StorageSync: a packet ending in an orphan trailing size byte still completes', () async {
    final audio = <int>[];
    for (var i = 0; i < 10; i++) {
      audio.add(40);
      audio.addAll(List<int>.filled(40, 0xAB));
    }
    audio.add(80); // orphan size byte at the boundary
    audio.addAll(List<int>.filled(440 - audio.length, 0));
    final ts = ByteData(4)..setUint32(0, 1700000000, Endian.big);
    final packet = [...ts.buffer.asUint8List(), ...audio];

    final card = _FakeStorageDevice(
      script: [
        packet,
        [100],
      ],
    );
    final local = _FakeLocalSync();
    final wal = storageWal();
    final sync = storageSyncWith(local, card, wal);

    await sync.syncAll();

    expect(local.added, hasLength(1));
    expect(local.added.first.totalFrames, 10);
    expect(card.deletes, [1]);
    await card.controller.close();
    await sync.stop();
  });

  test('StorageSync: a short transfer (end marker before all bytes) is not deleted or synced', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final local = _FakeLocalSync();
    final wal = storageWal(totalBytes: 2 * 440); // only half the bytes arrive
    final sync = storageSyncWith(local, card, wal);

    await sync.syncAll();

    expect(card.deletes, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('WalSyncs.syncWal transfers a listed multi-file recording and then deletes it on the device', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final local = _FakeLocalSync();
    final wal = storageWal();
    final later = storageWal(fileNum: 2, timerStart: 1700000600);
    final syncs = walSyncsWith(local, card, [wal, later]);

    await syncs.syncWal(wal: wal);

    expect(card.writes, [
      [1, 0x11, 0],
    ]);
    expect(local.added, hasLength(1));
    expect(wal.status, WalStatus.synced);
    expect(wal.isSyncing, isFalse);
    expect(card.deletes, [1]);
    expect(later.fileNum, 1, reason: 'the firmware re-indexes the files above a deleted one');

    // File 1 now holds the later recording, so clearing synced files must not delete it.
    expect(syncs.storage.owns(wal), isFalse);
    await syncs.storage.deleteAllSyncedWals();
    expect(card.deletes, [1]);
    expect(await syncs.storage.getMissingWals(), [later]);
    await card.controller.close();
    await syncs.storage.stop();
  });

  test('WalSyncs.syncWal fails an incomplete multi-file transfer and keeps the file on the device', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final local = _FakeLocalSync();
    final wal = storageWal(totalBytes: 2 * 440); // only half the bytes arrive
    final syncs = walSyncsWith(local, card, [wal]);

    await expectLater(syncs.syncWal(wal: wal), throwsException);

    expect(card.writes, hasLength(1));
    expect(card.deletes, isEmpty);
    expect(wal.status, WalStatus.miss);
    expect(wal.isSyncing, isFalse);
    await card.controller.close();
    await syncs.storage.stop();
  });

  test('WalSyncs.syncWal refuses a multi-file recording while a device drain is running', () async {
    final card = _FakeStorageDevice(
      script: [
        _dataPacket([40]),
        [100],
      ],
    );
    final gate = Completer<void>();
    final local = _FakeLocalSync()..addGate = gate.future;
    final wal = storageWal();
    final syncs = walSyncsWith(local, card, [wal]);

    final drain = syncs.storage.syncAll();
    await Future.delayed(const Duration(milliseconds: 200));
    final refused = expectLater(syncs.syncWal(wal: wal), throwsException);
    gate.complete();
    await drain;
    await refused;

    expect(card.writes, hasLength(1), reason: 'the running drain keeps the only read');
    expect(wal.status, WalStatus.synced);
    expect(card.deletes, [1]);
    await card.controller.close();
    await syncs.storage.stop();
  });

  test('Limitless: a session gap ACKs only the saved batch max, never the pending page', () async {
    const ts1 = 1700000000000;
    const ts2 = ts1 + 200000; // >120s gap
    final card = _FakeLimitless(
      pages: [
        {
          'opus_frames': [
            [1, 2, 3],
          ],
          'timestamp_ms': ts1,
          'max_index': 0,
        },
        {
          'opus_frames': [
            [4, 5],
          ],
          'timestamp_ms': ts1,
          'max_index': 1,
        },
        {
          'opus_frames': [
            [6, 7],
          ],
          'timestamp_ms': ts2,
          'max_index': 2,
        },
        {
          'opus_frames': [
            [8],
          ],
          'timestamp_ms': ts2,
          'max_index': 2,
        },
      ],
    );
    final local = _FakeLocalSync();
    final wal = Wal(
      timerStart: ts1 ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: 5,
      status: WalStatus.miss,
      storage: WalStorage.flashPage,
      device: 'limitless-1',
      fileNum: 0,
      storageOffset: 0,
      storageTotalBytes: 2, // endPage = 2
    );
    final sync = FlashPageWalSyncImpl(_Listener())
      ..testDevice = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40)
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(local);

    await sync.syncWal(wal: wal);

    expect(wal.status, WalStatus.synced);
    expect(card.acks.first, 1);
    expect(card.acks.last, 2);
    await sync.stop();
  });

  test('Limitless: a failed durable save fails the transfer — no ACK, wal stays miss', () async {
    const ts1 = 1700000000000;
    final card = _FakeLimitless(
      pages: [
        {
          'opus_frames': [
            [1, 2, 3],
          ],
          'timestamp_ms': ts1,
          'max_index': 0,
        },
      ],
    );
    final local = _FakeLocalSync(failOnChunk: 1);
    final wal = Wal(
      timerStart: ts1 ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: 5,
      status: WalStatus.miss,
      storage: WalStorage.flashPage,
      device: 'limitless-1',
      fileNum: 0,
      storageOffset: 0,
      storageTotalBytes: 0,
    );
    final sync = FlashPageWalSyncImpl(_Listener())
      ..testDevice = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40)
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(local);

    // Transfer to Phone shows "Transfer complete" whenever syncWal returns normally.
    await expectLater(sync.syncWal(wal: wal), throwsException);

    expect(card.acks, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    expect(wal.isSyncing, isFalse);
    await sync.stop();
  });

  test('Limitless: a cancelled transfer returns quietly and keeps the wal pending', () async {
    final card = _FakeLimitless(pages: const []);
    final wal = Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 5,
      status: WalStatus.miss,
      storage: WalStorage.flashPage,
      device: 'limitless-1',
      fileNum: 0,
      storageOffset: 0,
      storageTotalBytes: 2,
    );
    final sync = FlashPageWalSyncImpl(_Listener())
      ..testDevice = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40)
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(_FakeLocalSync());

    final transfer = sync.syncWal(wal: wal);
    sync.cancelSync();

    expect(await transfer, isNull, reason: 'the page already reported the cancel');
    expect(wal.status, WalStatus.miss);
    expect(wal.isSyncing, isFalse);
    expect(card.realTimeMode, isTrue);
    await sync.stop();
  });

  test('Limitless: Transfer to Phone moves a recording opened before the pendant was listed again', () async {
    const ts1 = 1700000000000;
    Wal pendantWal() => Wal(
          timerStart: ts1 ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: 5,
          status: WalStatus.miss,
          storage: WalStorage.flashPage,
          device: 'limitless-1',
          fileNum: 0,
          storageOffset: 0,
          storageTotalBytes: 0,
        );
    final card = _FakeLimitless(
      pages: [
        {
          'opus_frames': [
            [1, 2, 3],
          ],
          'timestamp_ms': ts1,
          'max_index': 0,
        },
      ],
    );
    // The recording page keeps the Wal it was opened with. Every discovery wake
    // and sync pass relists the pendant as a new Wal with the same id.
    final opened = pendantWal();
    final listed = pendantWal();
    final sync = FlashPageWalSyncImpl(_Listener())
      ..testDevice = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40)
      ..testConnection = card
      ..testWals = [listed];
    sync.setLocalSync(_FakeLocalSync());

    await sync.syncWal(wal: opened);

    expect(listed.status, WalStatus.synced, reason: 'the sync pages read the listed entry');
    expect(listed.isSyncing, isFalse);
    expect(card.acks.last, 0, reason: 'the pendant frees the transferred pages');
    await sync.stop();
  });

  test('Limitless: Transfer to Phone fails for a recording that is no longer listed', () async {
    final card = _FakeLimitless(pages: const []);
    Wal pendantWal(int timerStart) => Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          seconds: 5,
          status: WalStatus.miss,
          storage: WalStorage.flashPage,
          device: 'limitless-1',
          fileNum: 0,
          storageOffset: 0,
          storageTotalBytes: 2,
        );
    final listed = pendantWal(1700000100);
    final sync = FlashPageWalSyncImpl(_Listener())
      ..testDevice = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40)
      ..testConnection = card
      ..testWals = [listed];
    sync.setLocalSync(_FakeLocalSync());

    await expectLater(sync.syncWal(wal: pendantWal(1700000000)), throwsException);

    expect(card.batchMode, isFalse, reason: 'the pendant is never asked for audio');
    expect(listed.isSyncing, isFalse);
    await sync.stop();
  });
}
