import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

void main() {
  late Directory directory;
  late _Listener listener;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi-ring-sync-test-');
    listener = _Listener();
  });

  tearDown(() async {
    if (await directory.exists()) await directory.delete(recursive: true);
  });

  LocalWalSyncImpl localSync({WalPersister? persister}) {
    return LocalWalSyncImpl(
      listener,
      walPersister: persister ?? (_) async => true,
      walPathResolver: (path) async => path == null ? null : '${directory.path}/${path.split('/').last}',
    );
  }

  RingStorageSyncImpl ringSync(
    _FakeRingConnection connection,
    LocalWalSync local, {
    int packetsPerRead = 2,
    int? nowSeconds,
  }) {
    final sync = RingStorageSyncImpl(
      listener,
      connectionResolver: (_) async => connection,
      documentsDirectoryProvider: () async => directory,
      packetsPerRead: packetsPerRead,
      inactivityTimeout: const Duration(milliseconds: 100),
      nowSeconds: () => nowSeconds ?? _FakeRingConnection.baseTimestamp + 10000,
    );
    sync.setDevice(_device());
    sync.setLocalSync(local);
    return sync;
  }

  Wal virtualWal(int records) => Wal(
        timerStart: _FakeRingConnection.baseTimestamp,
        codec: BleAudioCodec.opus,
        seconds: records,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'cv1-test',
        deviceModel: 'Omi',
        storageTotalBytes: records * RingProtocol.recordSize,
        totalFrames: records,
      );

  test('large backlog drains as independently durable bounded ranges', () async {
    final connection = _FakeRingConnection(readSeq: 100, writeSeq: 107);
    final local = localSync();
    final wal = virtualWal(7);

    await ringSync(connection, local).syncWal(wal: wal);

    expect(connection.reads,
        [(start: 100, count: 2), (start: 102, count: 2), (start: 104, count: 2), (start: 106, count: 1)]);
    expect(connection.successfulAdvances, [102, 104, 106, 107]);
    expect(local.testWals.map((wal) => wal.sourceId), [
      'ring_100_102',
      'ring_102_104',
      'ring_104_106',
      'ring_106_107',
    ]);
    expect(wal.status, WalStatus.synced);
  });

  test('durable ring WAL uses exact little-endian length-prefixed frame bytes', () async {
    const startSeq = 0x1234;
    final connection = _FakeRingConnection(readSeq: startSeq, writeSeq: startSeq + 2, framesPerRecord: 2);
    final local = localSync();

    await ringSync(connection, local).syncWal(wal: virtualWal(2));

    expect(connection.successfulAdvances, [startSeq + 2]);
    expect(local.testWals, hasLength(1));
    final bytes = await File('${directory.path}/${local.testWals.single.filePath}').readAsBytes();
    expect(bytes, [
      3,
      0,
      0,
      0,
      0x34,
      0x12,
      0,
      3,
      0,
      0,
      0,
      0x34,
      0x12,
      1,
      3,
      0,
      0,
      0,
      0x35,
      0x12,
      0,
      3,
      0,
      0,
      0,
      0x35,
      0x12,
      1,
    ]);
  });

  test('interrupted range keeps its cursor and retry resumes after the last durable advance', () async {
    final local = localSync();
    final firstConnection = _FakeRingConnection(readSeq: 200, writeSeq: 205, truncateStartSeq: 202);
    final wal = virtualWal(5);

    await ringSync(firstConnection, local).syncWal(wal: wal);

    expect(firstConnection.successfulAdvances, [202]);
    expect(local.testWals.map((wal) => wal.sourceId), ['ring_200_202']);
    expect(wal.status, WalStatus.miss);

    final resumedConnection = _FakeRingConnection(readSeq: 202, writeSeq: 205);
    await ringSync(resumedConnection, local).syncWal(wal: wal);

    expect(resumedConnection.reads, [(start: 202, count: 2), (start: 204, count: 1)]);
    expect(resumedConnection.successfulAdvances, [204, 205]);
    expect(local.testWals.map((wal) => wal.sourceId), [
      'ring_200_202',
      'ring_202_204',
      'ring_204_205',
    ]);
    expect(wal.status, WalStatus.synced);
  });

  test('failed manifest persistence rolls back registration and prevents ADVANCE', () async {
    final connection = _FakeRingConnection(readSeq: 300, writeSeq: 301);
    final local = localSync(persister: (_) async => false);
    final wal = virtualWal(1);

    await ringSync(connection, local).syncWal(wal: wal);

    expect(connection.advanceAttempts, isEmpty);
    expect(local.testWals, isEmpty);
    expect(wal.status, WalStatus.miss);
  });

  test('CRC mismatch prevents registration and ADVANCE', () async {
    final connection = _FakeRingConnection(readSeq: 400, writeSeq: 402, corruptCrc: true);
    final local = localSync();
    final wal = virtualWal(2);

    await ringSync(connection, local).syncWal(wal: wal);

    expect(connection.advanceAttempts, isEmpty);
    expect(local.testWals, isEmpty);
    expect(wal.status, WalStatus.miss);

    final retry = _FakeRingConnection(readSeq: 400, writeSeq: 402);
    await ringSync(retry, local).syncWal(wal: wal);

    expect(retry.successfulAdvances, [402]);
    expect(local.testWals.map((wal) => wal.sourceId), ['ring_400_402']);
  });

  test('capture timestamp discontinuity becomes a separate immutable WAL segment', () async {
    final connection = _FakeRingConnection(
      readSeq: 500,
      writeSeq: 502,
      timestamps: {
        500: _FakeRingConnection.baseTimestamp + 500,
        501: _FakeRingConnection.baseTimestamp + 620,
      },
    );
    final local = localSync();

    await ringSync(connection, local).syncWal(wal: virtualWal(2));

    expect(local.testWals.map((wal) => wal.timerStart), [
      _FakeRingConnection.baseTimestamp + 500,
      _FakeRingConnection.baseTimestamp + 620,
    ]);
    expect(connection.successfulAdvances, [502]);
  });

  test('failed ADVANCE retries the immutable range without duplicating its WAL', () async {
    final local = localSync();
    final firstConnection = _FakeRingConnection(readSeq: 600, writeSeq: 602, failAdvance: true);
    final wal = virtualWal(2);

    await ringSync(firstConnection, local).syncWal(wal: wal);

    expect(firstConnection.advanceAttempts, [602]);
    expect(firstConnection.successfulAdvances, isEmpty);
    expect(local.testWals, hasLength(1));
    final originalBytes = await File('${directory.path}/${local.testWals.single.filePath}').readAsBytes();

    final retryConnection = _FakeRingConnection(readSeq: 600, writeSeq: 602);
    await ringSync(retryConnection, local).syncWal(wal: wal);

    expect(retryConnection.successfulAdvances, [602]);
    expect(local.testWals, hasLength(1));
    expect(await File('${directory.path}/${local.testWals.single.filePath}').readAsBytes(), originalBytes);
  });

  test('invalid RTC fallback is monotonic across ranges and sequence identity survives retry time changes', () async {
    final local = localSync();
    final invalidTimestamps = {for (var seq = 700; seq < 704; seq++) seq: 0};
    final firstConnection = _FakeRingConnection(
      readSeq: 700,
      writeSeq: 704,
      timestamps: invalidTimestamps,
      framesPerRecord: 100,
      failAdvance: true,
    );
    final wal = virtualWal(4)
      ..totalFrames = 400
      ..timerStart = 1799999996;

    await ringSync(firstConnection, local, nowSeconds: 1800000000).syncWal(wal: wal);

    expect(local.testWals.single.sourceId, 'ring_700_702');
    expect(local.testWals.single.timerStart, 1799999996);

    final retry = _FakeRingConnection(
      readSeq: 700,
      writeSeq: 704,
      timestamps: invalidTimestamps,
      framesPerRecord: 100,
    );
    await ringSync(retry, local, nowSeconds: 1800000100).syncWal(wal: wal);

    expect(retry.successfulAdvances, [702, 704]);
    expect(local.testWals.map((wal) => wal.sourceId), ['ring_700_702', 'ring_702_704']);
    expect(local.testWals.map((wal) => wal.timerStart), [1799999996, 1799999998]);
  });

  test('byte-identical legacy timestamp WAL is reused instead of uploaded twice', () async {
    final local = localSync();
    final legacyFile = File('${directory.path}/legacy.bin')..writeAsBytesSync([1, 2, 3, 4]);
    final candidateFile = File('${directory.path}/range.bin')..writeAsBytesSync([1, 2, 3, 4]);
    local.testWals = [
      Wal(
        timerStart: 1700000800,
        codec: BleAudioCodec.opus,
        seconds: 1,
        device: 'cv1-test',
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: legacyFile.path.split('/').last,
      ),
    ];
    final candidate = Wal(
      timerStart: 1700000800,
      codec: BleAudioCodec.opus,
      seconds: 1,
      device: 'cv1-test',
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: candidateFile.path.split('/').last,
      sourceId: 'ring_800_802',
    );

    final result = await local.addExternalWal(candidate);

    expect(result, ExternalWalRegistration.alreadyRegistered);
    expect(local.testWals, hasLength(1));
    expect(await candidateFile.exists(), isFalse);
  });

  test('synced legacy WAL without immutable upload proof is conservatively registered again', () async {
    final local = localSync();
    File('${directory.path}/legacy.bin').writeAsBytesSync([1, 2, 3, 4]);
    File('${directory.path}/range.bin').writeAsBytesSync([1, 2, 3, 4]);
    local.testWals = [
      Wal(
        timerStart: 1700000900,
        codec: BleAudioCodec.opus,
        seconds: 1,
        device: 'cv1-test',
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: 'legacy.bin',
      ),
    ];
    final candidate = Wal(
      timerStart: 1700000900,
      codec: BleAudioCodec.opus,
      seconds: 1,
      device: 'cv1-test',
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: 'range.bin',
      sourceId: 'ring_900_902',
    );

    final result = await local.addExternalWal(candidate);

    expect(result, ExternalWalRegistration.added);
    expect(local.testWals, hasLength(2));
    expect(await File('${directory.path}/range.bin').exists(), isTrue);
  });
}

BtDevice _device() => BtDevice(name: 'Omi', id: 'cv1-test', type: DeviceType.omi, rssi: -40);

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}

  @override
  void onWalUpdated() {}
}

class _FakeRingConnection implements DeviceConnection {
  static const int baseTimestamp = 1710000000;

  int readSeq;
  final int writeSeq;
  final int? truncateStartSeq;
  final bool corruptCrc;
  final bool failAdvance;
  final int framesPerRecord;
  final Map<int, int> timestamps;
  final reads = <({int start, int count})>[];
  final advanceAttempts = <int>[];
  final successfulAdvances = <int>[];
  final StreamController<List<int>> _notifications = StreamController<List<int>>.broadcast(sync: true);

  _FakeRingConnection({
    required this.readSeq,
    required this.writeSeq,
    this.truncateStartSeq,
    this.corruptCrc = false,
    this.failAdvance = false,
    this.framesPerRecord = 1,
    this.timestamps = const {},
  });

  @override
  Future<RingInfo?> getRingInfo() async => RingInfo(
        readSeq: readSeq,
        writeSeq: writeSeq,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      );

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async =>
      _notifications.stream.listen(onStorageBytesReceived);

  @override
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount}) async {
    final count = packetCount!;
    reads.add((start: startSeq, count: count));
    scheduleMicrotask(() {
      _notifications.add(_readBegin(startSeq, count));
      final requested = <int>[];
      for (var seq = startSeq; seq < startSeq + count; seq++) {
        requested.addAll(_record(seq, timestamps[seq] ?? baseTimestamp + seq));
      }
      final sent =
          truncateStartSeq == startSeq ? requested.sublist(0, requested.length - RingProtocol.recordSize) : requested;
      final crc = RingTransferCrc32()..add(sent);
      for (var offset = 0; offset < sent.length; offset += 137) {
        final end = (offset + 137).clamp(0, sent.length);
        _notifications.add([RingProtocol.notifyData, ...sent.sublist(offset, end)]);
      }
      _notifications.add(_done(startSeq + count, corruptCrc ? crc.value ^ 0xFFFFFFFF : crc.value));
    });
    return true;
  }

  @override
  Future<bool> advanceRing(int newReadSeq) async {
    advanceAttempts.add(newReadSeq);
    if (failAdvance) return false;
    readSeq = newReadSeq;
    successfulAdvances.add(newReadSeq);
    return true;
  }

  @override
  Future<bool> stopStorageSync() async => true;

  static List<int> _readBegin(int startSeq, int count) {
    final bytes = ByteData(13)
      ..setUint8(0, RingProtocol.notifyReadBegin)
      ..setUint64(1, startSeq, Endian.big)
      ..setUint32(9, count, Endian.big);
    return bytes.buffer.asUint8List();
  }

  static List<int> _done(int nextSeq, int crc) {
    final bytes = ByteData(14)
      ..setUint8(0, RingProtocol.notifyDone)
      ..setUint8(1, 0)
      ..setUint64(2, nextSeq, Endian.big)
      ..setUint32(10, crc, Endian.big);
    return bytes.buffer.asUint8List();
  }

  List<int> _record(int sequence, int timestamp) {
    final bytes = Uint8List(RingProtocol.recordSize);
    ByteData.sublistView(bytes).setUint32(0, timestamp, Endian.big);
    var offset = RingProtocol.timestampBytes;
    for (var frame = 0; frame < framesPerRecord; frame++) {
      bytes[offset++] = 3;
      bytes[offset++] = sequence & 0xFF;
      bytes[offset++] = (sequence >> 8) & 0xFF;
      bytes[offset++] = frame & 0xFF;
    }
    return bytes;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
