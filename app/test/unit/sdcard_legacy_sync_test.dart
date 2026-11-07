import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

const _packets = sdcardChunkSizeSecs * 100 * 2 + 1;

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _FakeLocalSync implements LocalWalSync {
  _FakeLocalSync({this.failOnChunk, this.afterChunk});

  final int? failOnChunk;
  final void Function(int count)? afterChunk;
  final added = <Wal>[];

  @override
  int get sessionGeneration => 1;

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    if (failOnChunk == added.length + 1) throw const FileSystemException('No space left on device');
    added.add(wal);
    afterChunk?.call(added.length);
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

class _FakeSdCard implements DeviceConnection {
  final writes = <List<int>>[];
  void Function(List<int>)? _onBytes;
  List<int> storageListResponse = const [];
  int getStorageListCalls = 0;
  List<int>? customReadResponse;
  RingInfo? fakeLastRingInfo;

  bool get cleared => writes.any((write) => write[1] == 1);

  @override
  RingInfo? get lastRingInfo => fakeLastRingInfo;

  @override
  Future<List<int>> getStorageList() async {
    getStorageListCalls++;
    return storageListResponse;
  }

  @override
  Future<BleAudioCodec> getAudioCodec() async => BleAudioCodec.opus;

  @override
  Future<String> getModelNumber() async => 'Omi';

  @override
  Future<String> getFirmwareRevision() async => '3.0.21';

  @override
  Future<String> getHardwareRevision() async => '2.0';

  @override
  Future<String> getManufacturerName() async => 'BasedHardware';

  @override
  Future<String?> getSerialNumber() async => null;

  @override
  Future<bool> hasPhotoStreamingCharacteristic() async => false;

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    _onBytes = onStorageBytesReceived;
    return null;
  }

  @override
  Future<bool> writeToStorage(int numFile, int command, int offset) async {
    writes.add([numFile, command, offset]);
    if (command == 0) {
      scheduleMicrotask(() {
        if (customReadResponse != null) {
          _onBytes!(customReadResponse!);
          return;
        }
        for (var i = 0; i < _packets; i++) {
          _onBytes!(List<int>.filled(83, 0)..[3] = 10);
        }
        _onBytes!([100]);
      });
    }
    return true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late Wal wal;
  late _FakeSdCard card;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('sdcard_legacy_sync_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 360,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: 'devkit-1',
      fileNum: 1,
      storageOffset: 0,
      storageTotalBytes: _packets * 80,
    );
    card = _FakeSdCard();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  SDCardWalSyncImpl syncWith(LocalWalSync local) {
    final sync = SDCardWalSyncImpl(_Listener())
      ..testDevice = BtDevice(
        id: 'devkit-1',
        name: 'Omi DevKit',
        type: DeviceType.omi,
        rssi: -40,
        firmwareRevision: '3.0.10',
      )
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(local);
    return sync;
  }

  test('a cancel after the first chunk keeps the SD card and does not mark the recording synced', () async {
    late SDCardWalSyncImpl sync;
    final local = _FakeLocalSync(
      afterChunk: (count) {
        if (count == 1) sync.cancelSync();
      },
    );
    sync = syncWith(local);

    await expectLater(sync.syncWal(wal: wal), throwsA(anything));

    expect(local.added, hasLength(1));
    expect(card.cleared, isFalse);
    expect(wal.status, isNot(WalStatus.synced));
  });

  test('a chunk that fails to save keeps the SD card and does not mark the recording synced', () async {
    final local = _FakeLocalSync(failOnChunk: 2);
    final sync = syncWith(local);

    await expectLater(sync.syncWal(wal: wal), throwsA(isA<FileSystemException>()));

    expect(local.added, hasLength(1));
    expect(card.cleared, isFalse);
    expect(wal.status, isNot(WalStatus.synced));
  });

  test('a clean download still clears the SD card and marks the recording synced', () async {
    final local = _FakeLocalSync();
    final sync = syncWith(local);

    await sync.syncWal(wal: wal);

    expect(local.added, hasLength(3));
    expect(card.cleared, isTrue);
    expect(wal.status, WalStatus.synced);
  });

  test('skips listing and sync on ring-buffer firmware even when ring status has used_bytes', () async {
    final local = _FakeLocalSync();
    card.storageListResponse = const [250412, 564, 3816292, 1];
    final sync = SDCardWalSyncImpl(_Listener())
      ..testDevice = BtDevice(
        id: 'devkit-1',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -40,
        firmwareRevision: 'Unknown',
      )
      ..testConnection = card;
    sync.setLocalSync(local);
    sync.setFirmwareVersion('3.0.21');

    await sync.start();

    expect(card.getStorageListCalls, 0);
    expect(await sync.getMissingWals(), isEmpty);
    expect(await sync.syncAll(), isNull);
    await expectLater(sync.syncWal(wal: wal), throwsA(isA<StateError>()));
    await sync.deleteWal(wal);
    expect(card.writes, isEmpty);

    // Even if setFirmwareVersion was not called upfront on a raw 'Unknown' connect
    // object, _getMissingWals() drops the phantom used_bytes listing once
    // lastRingInfo / getDeviceInfo reveals ring-buffer firmware.
    final fallbackSync = SDCardWalSyncImpl(_Listener())
      ..testDevice = BtDevice(
        id: 'devkit-1',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -40,
        firmwareRevision: 'Unknown',
      )
      ..testConnection = (card
        ..fakeLastRingInfo = RingInfo(
          readSeq: 0,
          writeSeq: 564,
          capacityPackets: 4096,
          droppedPackets: 0,
          packetSize: 444,
        ));
    fallbackSync.setLocalSync(local);

    await fallbackSync.start();
    expect(card.getStorageListCalls, 1);
    expect(await fallbackSync.getMissingWals(), isEmpty);
  });

  test('OmiDeviceConnection.performWriteToStorage refuses legacy SD card commands 0 and 1 on ring firmware', () async {
    final transportWrites = <List<int>>[];
    final transport = _RecordingStorageTransport(transportWrites, firmwareRevision: '3.0.21');
    final conn = OmiDeviceConnection(
      BtDevice(id: 'omi-ring', name: 'Omi', type: DeviceType.omi, rssi: -40, firmwareRevision: 'Unknown'),
      transport,
    );

    expect(await conn.performWriteToStorage(1, 0, 564), isFalse);
    expect(await conn.performWriteToStorage(1, 1, 0), isFalse);
    expect(transportWrites, isEmpty);
  });
}

class _RecordingStorageTransport extends DeviceTransport {
  _RecordingStorageTransport(this.writes, {this.firmwareRevision});
  final List<List<int>> writes;
  final String? firmwareRevision;

  @override
  String get deviceId => 'omi-ring';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (serviceUuid == deviceInformationServiceUuid &&
        characteristicUuid == firmwareRevisionCharacteristicUuid &&
        firmwareRevision != null) {
      return firmwareRevision!.codeUnits;
    }
    return const [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add(data);
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}
