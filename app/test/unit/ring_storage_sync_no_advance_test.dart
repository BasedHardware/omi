import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
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
  bool admit = true;
  final added = <Wal>[];

  @override
  int get sessionGeneration => 1;

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    if (failIndexSave) throw const FileSystemException('index write failed');
    added.add(wal);
  }

  @override
  Future<bool> ensureStorageAdmission({required int bytes, required int admittedGeneration}) async => admit;

  @override
  Future<bool> hasDurableWal(Wal wal, {required int admittedGeneration}) async => added.contains(wal);

  @override
  void releaseStorageAdmission(int bytes) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeRingDevice implements DeviceConnection {
  _FakeRingDevice({required this.ringInfo});

  final RingInfo ringInfo;
  void Function(List<int>)? onBytes;
  final controller = StreamController<List<int>>.broadcast();
  final advanceCalls = <int>[];
  final readCalls = <int>[];
  final stopCalls = <int>[];
  Completer<RingStatus?>? statusGate;
  int custodyEpochValue = 1;
  int effectiveCapsValue = 0;

  void emit(List<int> bytes) => onBytes?.call(bytes);

  @override
  Future<RingInfo?> getRingInfo() async => ringInfo;

  @override
  Future<RingStatus?> getRingStatus() async {
    final gate = statusGate;
    if (gate != null) return gate.future;
    return RingStatus(usedBytes: 0, unreadPackets: ringInfo.unreadPackets, freeBytes: 0, rtcValid: 1);
  }

  @override
  Future<bool> stopStorageSync() async {
    stopCalls.add(1);
    return true;
  }

  @override
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount}) async {
    readCalls.add(startSeq);
    return true;
  }

  @override
  Future<bool> advanceRing(int newReadSeq) async {
    advanceCalls.add(newReadSeq);
    return true;
  }

  @override
  Future<RingCommandAck?> advanceRingCustody(
    int newReadSeq, {
    required int expectedEpoch,
    required int? expectedRingId,
  }) async {
    advanceCalls.add(newReadSeq);
    return const RingCommandAck(status: RingProtocol.ackOk);
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
  int get ringEffectiveCaps => effectiveCapsValue;

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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('ring_no_advance_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
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

  RingStorageSyncImpl syncWith(_FakeLocalSync local, _FakeRingDevice card, Wal wal) {
    final sync = RingStorageSyncImpl(_Listener())
      ..testConnection = card
      ..testWals = [wal];
    sync.setLocalSync(local);
    sync.setDevice(BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40));
    return sync;
  }

  Wal ringWal() => Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'devkit-1',
        storageTotalBytes: 444,
      );

  test('READ_BEGIN with a mismatched start seq aborts the transfer — no advance', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(9, 1)); // wrong start: requested readStart was 5
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advanceCalls, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('DONE whose next_seq does not cover the consumed records does not advance', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 7, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync();
    final wal = ringWal()..storageTotalBytes = 2 * 444;
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 2));
    card.emit(_record());
    card.emit(_record());
    card.emit(_done(0, 6)); // consumed 2 records but DONE only covers 1
    await future;

    expect(card.advanceCalls, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('an index save failure leaves the ring untouched — no advance even on clean DONE', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync()..failIndexSave = true;
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advanceCalls, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('a same-object reconnect during the status await fences the stale INFO — no READ, no advance', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    card.statusGate = Completer<RingStatus?>();
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.custodyEpochValue = 11;
    card.statusGate!.complete(RingStatus(usedBytes: 0, unreadPackets: 1, freeBytes: 0, rtcValid: 1));
    await future;

    expect(card.readCalls, isEmpty);
    expect(card.advanceCalls, isEmpty);
    await card.controller.close();
    await sync.stop();
  });

  test('a mid-transfer index failure sends STOP on the source connection before unsubscribing', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync()..failIndexSave = true;
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advanceCalls, isEmpty);
    expect(card.stopCalls, isNotEmpty);
    await card.controller.close();
    await sync.stop();
  });

  test('control: a clean legacy transfer advances exactly once and sends no STOP', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await future;

    expect(card.advanceCalls, [6]);
    expect(card.stopCalls, isEmpty);
    expect(wal.status, WalStatus.synced);
    await card.controller.close();
    await sync.stop();
  });

  test('an errored DONE status does not advance or clear the ring', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await Future.delayed(const Duration(milliseconds: 50));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(3, 6)); // status error
    await future;

    expect(card.advanceCalls, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });
}
