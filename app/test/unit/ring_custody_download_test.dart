import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _FakeLocalSync implements LocalWalSync {
  _FakeLocalSync();

  bool failIndexSave = false;
  final added = <Wal>[];

  @override
  int get sessionGeneration => 1;

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    if (failIndexSave) throw const FileSystemException('index write failed');
    added.add(wal);
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

class _Advance {
  _Advance(this.seq, this.epoch, this.ringId);
  final int seq;
  final int epoch;
  final int? ringId;
}

class _FakeRingDevice implements DeviceConnection {
  _FakeRingDevice({required this.ringInfo, this.caps = 0});

  RingInfo ringInfo;
  final int caps;
  void Function(List<int>)? onBytes;
  final controller = StreamController<List<int>>.broadcast();
  final advances = <_Advance>[];
  final _firstAdvance = Completer<void>();
  int ackStatus = RingProtocol.ackOk;
  RingInfo? postAckInfo;
  int custodyEpochValue = 7;

  void emit(List<int> bytes) => onBytes?.call(bytes);

  /// Completes when the first advance reaches the card.
  Future<void> get firstAdvance => _firstAdvance.future;

  @override
  Future<RingInfo?> getRingInfo() async {
    final after = postAckInfo;
    if (after != null && advances.isNotEmpty) {
      final r = after;
      postAckInfo = null;
      return r;
    }
    return ringInfo;
  }

  @override
  Future<RingStatus?> getRingStatus() async =>
      RingStatus(usedBytes: 0, unreadPackets: ringInfo.unreadPackets, freeBytes: 0, rtcValid: 1);

  @override
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount}) async => true;

  @override
  Future<RingCommandAck?> advanceRingCustody(
    int newReadSeq, {
    required int expectedEpoch,
    required int? expectedRingId,
  }) async {
    advances.add(_Advance(newReadSeq, expectedEpoch, expectedRingId));
    if (!_firstAdvance.isCompleted) _firstAdvance.complete();
    return RingCommandAck(status: ackStatus);
  }

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    onBytes = onStorageBytesReceived;
    return controller.stream.listen((_) {});
  }

  @override
  int get ringCustodyEpoch => custodyEpochValue;

  @override
  Future<void> get ringCustodyReady => Future.value();

  @override
  int get ringEffectiveCaps => caps;

  @override
  RingInfo? get lastRingInfo => ringInfo;

  @override
  bool get ringLivePersistEnabled => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

List<int> _record({int timestamp = 1700000000, List<int> frameSizes = const [10]}) {
  final audio = <int>[];
  for (final s in frameSizes) {
    audio.add(s);
    audio.addAll(List<int>.filled(s, 0xAB));
  }
  audio.addAll(List<int>.filled(440 - audio.length, 0));
  final rec = ByteData(4)..setUint32(0, timestamp, Endian.big);
  return [RingProtocol.notifyData, ...rec.buffer.asUint8List(), ...audio];
}

List<int> _readBegin(int startSeq, int packetCount) {
  final bd = ByteData(13);
  bd.setUint8(0, RingProtocol.notifyReadBegin);
  bd.setUint64(1, startSeq, Endian.big);
  bd.setUint32(9, packetCount, Endian.big);
  return bd.buffer.asUint8List();
}

List<int> _done(int status, int nextSeq) {
  final bd = ByteData(10);
  bd.setUint8(0, RingProtocol.notifyDone);
  bd.setUint8(1, status);
  bd.setUint64(2, nextSeq, Endian.big);
  return bd.buffer.asUint8List();
}

RingInfo _info({int readSeq = 5, int writeSeq = 6, int caps = 0, int? ringId}) => RingInfo(
      readSeq: readSeq,
      writeSeq: writeSeq,
      capacityPackets: 100,
      droppedPackets: 0,
      packetSize: 444,
      advertisedCaps: caps,
      contractVersion: caps == 0 ? 0 : 1,
      ringId: ringId,
      infoBytes: caps == 0 ? 31 : 41,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  final custodies = <PendantRingCustody>[];

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('ring_custody_dl_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
  });

  tearDown(() async {
    // Checkpoint writes resolve their directory through path_provider, so they
    // must land before the mock is removed and the directory deleted (#20500).
    for (final custody in custodies) {
      await custody.flush();
    }
    custodies.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  RingStorageSyncImpl syncWith(_FakeLocalSync local, _FakeRingDevice card, Wal wal) {
    final custody = PendantRingCustody(
      walValidator: (ref) async {
        final path = await Wal.getFilePath(ref.fileName);
        if (path == null) return false;
        final f = File(path);
        return f.existsSync() && await f.length() == ref.bytes;
      },
    );
    custodies.add(custody);
    final sync = RingStorageSyncImpl(_Listener())
      ..testConnection = card
      ..testCustody = custody
      ..testWals = [wal];
    sync.setLocalSync(local);
    sync.setDevice(BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40));
    return sync;
  }

  Wal ringWal({int records = 1}) => Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'devkit-1',
        storageTotalBytes: records * 444,
      );

  test('caps-0 legacy flow: durable records then a single anonymous advance after validated DONE', () async {
    final card = _FakeRingDevice(ringInfo: _info());
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(local.added, hasLength(1));
    expect(card.advances, hasLength(1));
    expect(card.advances.single.seq, 6);
    expect(card.advances.single.ringId, isNull); // anonymous legacy advance
    expect(wal.status, WalStatus.synced);
    await card.controller.close();
    await sync.stop();
  });

  test(
    'CAP_APP_ACK_RECLAIM: incremental advance fires on each durable chunk, scoped to the read-proof ring id',
    () async {
      final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 68, caps: RingProtocol.capMaskV1, ringId: 42),
        caps: RingProtocol.capMaskV1,
      );
      final local = _FakeLocalSync();
      final wal = ringWal(records: 63);
      final sync = syncWith(local, card, wal);

      final future = sync.syncWal(wal: wal);
      await Future.delayed(const Duration(milliseconds: 50));
      card.emit(_readBegin(5, 63));
      for (var i = 0; i < 61; i++) {
        card.emit(_record(frameSizes: List.filled(100, 1)));
      }
      // The first 60 records fill a chunk. Wait for its advance instead of a fixed sleep: under CI
      // load the advance had not fired yet when a 300 ms sleep ended (#20500). The bound only keeps
      // a missing incremental advance from hanging; the expectation below still fails the test.
      await card.firstAdvance.timeout(const Duration(seconds: 10), onTimeout: () {});
      final incrementalCount = card.advances.length;
      for (var i = 0; i < 2; i++) {
        card.emit(_record(frameSizes: List.filled(100, 1)));
      }
      card.emit(_done(0, 68));
      await future;

      expect(
        incrementalCount,
        greaterThanOrEqualTo(1),
        reason: 'a mid-transfer incremental advance must fire under CAP_APP_ACK_RECLAIM',
      );
      expect(card.advances.last.seq, 68);
      expect(card.advances.every((a) => a.ringId == 42), isTrue);
      expect(wal.status, WalStatus.synced);
      await card.controller.close();
      await sync.stop();
    },
  );

  test('ACK 10 is benign only when a fresh INFO on the same ring confirms read_seq covers the target', () async {
    final card = _FakeRingDevice(ringInfo: _info());
    card.ackStatus = RingProtocol.ackSeqOutOfRange;
    card.postAckInfo = _info(readSeq: 6, writeSeq: 7);
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advances, hasLength(1));
    expect(wal.status, WalStatus.synced);
    await card.controller.close();
    await sync.stop();
  });

  test('ACK 10 with stale read_seq is NOT benign — no completion', () async {
    final card = _FakeRingDevice(ringInfo: _info());
    card.ackStatus = RingProtocol.ackSeqOutOfRange;
    card.postAckInfo = _info(readSeq: 5, writeSeq: 7); // still 5 < 6
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advances, hasLength(1));
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('ACK 11 ring-id mismatch fails closed — no completion, no fallback', () async {
    final card = _FakeRingDevice(
      ringInfo: _info(caps: RingProtocol.capMaskV1, ringId: 42),
      caps: RingProtocol.capMaskV1,
    );
    card.ackStatus = RingProtocol.ackRingIdMismatch;
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advances, hasLength(1));
    expect(card.advances.single.ringId, 42);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('reconnect (custody epoch bump) fences the advance — nothing sent', () async {
    final card = _FakeRingDevice(ringInfo: _info());
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.custodyEpochValue = 8;
    card.emit(_done(0, 6));
    await future;

    expect(card.advances, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });
}
