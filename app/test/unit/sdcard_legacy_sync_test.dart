import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
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
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeSdCard implements DeviceConnection {
  final writes = <List<int>>[];
  void Function(List<int>)? _onBytes;

  bool get cleared => writes.any((write) => write[1] == 1);

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
      ..testDevice = BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40)
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(local);
    return sync;
  }

  test('a cancel after the first chunk keeps the SD card and does not mark the recording synced', () async {
    late SDCardWalSyncImpl sync;
    final local = _FakeLocalSync(afterChunk: (count) {
      if (count == 1) sync.cancelSync();
    });
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
}
