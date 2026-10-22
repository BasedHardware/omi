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
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_syncs.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _ManualTimer implements Timer {
  _ManualTimer(this.callback);
  final void Function() callback;
  @override
  bool isActive = true;
  @override
  int tick = 0;
  @override
  void cancel() => isActive = false;
  void fire() {
    if (!isActive) return;
    isActive = false;
    tick++;
    callback();
  }
}

class _BlockedCustody implements PendantRingCustody {
  final firstRecord = Completer<bool>();
  @override
  Future<bool> isDurableLiveRecord(String deviceId, int? ringId, int seq) =>
      seq == 5 ? firstRecord.future : Future.value(false);
  @override
  bool isIncarnationInvalid(String deviceId, int epoch) => false;
  @override
  Future<void> markAdvanced(String deviceId, int epoch, int seq, {int? markSeq}) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _until(bool Function() ready) async {
  final deadline = Stopwatch()..start();
  while (deadline.elapsed < const Duration(seconds: 5)) {
    if (ready()) return;
    await Future<void>.delayed(const Duration(milliseconds: 1));
  }
  fail('Ring transfer did not reach the expected test boundary');
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
  bool statusRequested = false;
  int custodyEpochValue = 1;
  int effectiveCapsValue = 0;
  bool readResult = true;
  Object? readFailure;

  void emit(List<int> bytes) => onBytes?.call(bytes);

  @override
  Future<RingInfo?> getRingInfo() async => ringInfo;

  @override
  Future<RingStatus?> getRingStatus() async {
    statusRequested = true;
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
    final failure = readFailure;
    if (failure != null) throw failure;
    return readResult;
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

  RingStorageSyncImpl syncWith(_FakeLocalSync local, _FakeRingDevice card, Wal wal,
      {Timer Function(Duration, void Function())? transferTimer}) {
    final sync = RingStorageSyncImpl(_Listener(), transferTimer: transferTimer)
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

  // Transfer to Phone reaches the ring through WalSyncs.syncWal, which sends
  // the ring's virtual recording (fileNum -1) to RingStorageSyncImpl.
  WalSyncs walSyncsWith(_FakeLocalSync local, _FakeRingDevice card, Wal wal) {
    final syncs = WalSyncs(_Listener());
    syncs.ring
      ..testConnection = card
      ..testWals = [wal]
      ..setLocalSync(local)
      ..setDevice(BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40));
    return syncs;
  }

  for (final partialAudio in [false, true]) {
    test('idle read after BEGIN stops safely (partial audio=$partialAudio)', () async {
      final card = _FakeRingDevice(
          ringInfo: RingInfo(readSeq: 5, writeSeq: 7, capacityPackets: 100, droppedPackets: 0, packetSize: 444));
      final local = _FakeLocalSync();
      final wal = ringWal()..storageTotalBytes = 2 * 444;
      final timers = <_ManualTimer>[];
      final sync = syncWith(local, card, wal, transferTimer: (delay, callback) {
        expect(delay, const Duration(seconds: 15));
        final timer = _ManualTimer(callback);
        timers.add(timer);
        return timer;
      });
      addTearDown(sync.stop);
      addTearDown(card.controller.close);
      final transfer = sync.syncWal(wal: wal);
      await _until(() => card.readCalls.isNotEmpty);
      card.emit(_readBegin(5, 2));
      await _until(() => timers.length == 1);
      if (partialAudio) {
        card.emit(_record());
        await _until(() => timers.length == 2);
        expect(timers.first.isActive, isFalse);
        timers.first.fire();
        expect(card.stopCalls, isEmpty, reason: 'an old idle deadline cannot stop fresh data');
      }
      // Control chatter is not transfer progress and must not reset the idle deadline.
      card.emit([RingProtocol.notifyAck]);
      card.emit([RingProtocol.notifyData]);
      card.emit(_readBegin(5, 2));
      await Future<void>.delayed(Duration.zero);
      timers.last.fire();
      await expectLater(transfer, throwsException);
      expect(card.stopCalls, hasLength(1));
      expect(card.advanceCalls, isEmpty);
      expect(wal.status, WalStatus.miss);
      expect(sync.isSyncing, isFalse);
      expect(wal.isSyncing, isFalse);
      expect(wal.syncStartedAt, isNull);
      expect(timers.every((timer) => !timer.isActive), isTrue);
      expect(local.added, hasLength(partialAudio ? 1 : 0));
      if (partialAudio) {
        final path = await Wal.getFilePath(local.added.single.filePath);
        expect(path, isNotNull);
        expect(await File(path!).length(), greaterThan(0), reason: 'received audio survives the timeout');
      }
    });
  }

  for (final throws in [false, true]) {
    test('read command failure cleans up the transfer (throws=$throws)', () async {
      final card = _FakeRingDevice(
          ringInfo: RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444))
        ..readResult = false
        ..readFailure = throws ? StateError('synthetic GATT failure') : null;
      final wal = ringWal();
      final timers = <_ManualTimer>[];
      final sync = syncWith(_FakeLocalSync(), card, wal, transferTimer: (_, callback) {
        final timer = _ManualTimer(callback);
        timers.add(timer);
        return timer;
      });
      await expectLater(sync.syncWal(wal: wal), throwsException);
      // A callback racing with cancellation must not re-arm the cleaned-up timer.
      card.emit(_readBegin(5, 1));
      expect(timers, isEmpty);
      expect(card.stopCalls, hasLength(1));
      expect(card.advanceCalls, isEmpty);
      expect(wal.status, WalStatus.miss);
      expect(sync.isSyncing, isFalse);
      await card.controller.close();
      await sync.stop();
    });
  }

  test('a healthy DONE cancels the idle watchdog without a spurious STOP', () async {
    final card = _FakeRingDevice(
        ringInfo: RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444));
    final local = _FakeLocalSync();
    final wal = ringWal();
    final timers = <_ManualTimer>[];
    final sync = syncWith(local, card, wal, transferTimer: (_, callback) {
      final timer = _ManualTimer(callback);
      timers.add(timer);
      return timer;
    });
    addTearDown(sync.stop);
    addTearDown(card.controller.close);
    final transfer = sync.syncWal(wal: wal);
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await transfer;
    expect(wal.status, WalStatus.synced);
    expect(card.advanceCalls, [6]);
    expect(timers, hasLength(2));
    for (final timer in timers) {
      expect(timer.isActive, isFalse);
      timer.fire();
    }
    expect(card.stopCalls, isEmpty);
  });

  test('a transfer marks the listed recording as syncing for the whole read', () async {
    final card = _FakeRingDevice(
        ringInfo: RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444));
    final local = _FakeLocalSync();
    final wal = ringWal();
    final timers = <_ManualTimer>[];
    final sync = syncWith(local, card, wal, transferTimer: (_, callback) {
      final timer = _ManualTimer(callback);
      timers.add(timer);
      return timer;
    });
    addTearDown(sync.stop);
    addTearDown(card.controller.close);
    // A recording page opened before setDevice() rebuilt the list holds its own
    // instance; the transfer UI reads the listed one.
    final stale = Wal(
      timerStart: wal.timerStart,
      codec: wal.codec,
      seconds: wal.seconds,
      status: wal.status,
      storage: wal.storage,
      device: wal.device,
      storageTotalBytes: wal.storageTotalBytes,
    );
    final transfer = sync.syncWal(wal: stale);
    await _until(() => card.readCalls.isNotEmpty);
    expect(wal.isSyncing, isTrue);
    expect(wal.syncStartedAt, isNotNull);
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await transfer;
    expect(wal.status, WalStatus.synced);
    expect(wal.isSyncing, isFalse);
    expect(wal.syncStartedAt, isNull);
    expect(wal.syncEtaSeconds, isNull);
    expect(wal.syncSpeedKBps, isNull);
  });

  for (final receivedDone in [false, true]) {
    test('slow custody work preserves accepted bytes (DONE received=$receivedDone)', () async {
      final recordCount = receivedDone ? 2 : 3;
      final card = _FakeRingDevice(
          ringInfo: RingInfo(
              readSeq: 5, writeSeq: 5 + recordCount, capacityPackets: 100, droppedPackets: 0, packetSize: 444));
      final local = _FakeLocalSync();
      final custody = _BlockedCustody();
      final wal = ringWal()..storageTotalBytes = recordCount * 444;
      final timers = <_ManualTimer>[];
      final sync = syncWith(local, card, wal, transferTimer: (_, callback) {
        final timer = _ManualTimer(callback);
        timers.add(timer);
        return timer;
      })
        ..testCustody = custody;
      addTearDown(sync.stop);
      addTearDown(card.controller.close);
      final transfer = sync.syncWal(wal: wal);
      await _until(() => card.readCalls.isNotEmpty);
      card.emit(_readBegin(5, recordCount));
      card.emit(_record());
      await _until(() => timers.length == 2);
      // These callbacks arrive while the first record's custody check is held.
      card.emit(_record(timestamp: 1700000001));
      expect(timers, hasLength(3), reason: 'radio activity resets the deadline before queued I/O can run');
      if (receivedDone) {
        card.emit(_done(0, 7));
        expect(timers.last.isActive, isFalse, reason: 'queued DONE ends the radio idle deadline, not custody work');
      }
      timers.last.fire();
      if (!receivedDone) await _until(() => card.stopCalls.isNotEmpty);
      custody.firstRecord.complete(false);
      await expectLater(transfer, receivedDone ? completes : throwsException);
      expect(local.added.single.totalFrames, 2, reason: 'both received records survive slow custody work');
      expect(card.stopCalls, hasLength(receivedDone ? 0 : 1));
      expect(card.advanceCalls, receivedDone ? [7] : isEmpty);
      expect(wal.status, receivedDone ? WalStatus.synced : WalStatus.miss);
      expect(timers.every((timer) => !timer.isActive), isTrue);
    });
  }

  test('READ_BEGIN with a mismatched start seq aborts the transfer — no advance', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(9, 1)); // wrong start: requested readStart was 5
    card.emit(_record());
    card.emit(_done(0, 6));
    await expectLater(future, throwsException);

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
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(5, 2));
    card.emit(_record());
    card.emit(_record());
    card.emit(_done(0, 6)); // consumed 2 records but DONE only covers 1
    await expectLater(future, throwsException);

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
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await expectLater(future, throwsException);

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
    await _until(() => card.statusRequested);
    card.custodyEpochValue = 11;
    card.statusGate!.complete(RingStatus(usedBytes: 0, unreadPackets: 1, freeBytes: 0, rtcValid: 1));
    await expectLater(future, throwsException);

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
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await expectLater(future, throwsException);

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
    await _until(() => card.readCalls.isNotEmpty);
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
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(3, 6)); // status error
    await expectLater(future, throwsException);

    expect(card.advanceCalls, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  test('WalSyncs.syncWal fails a ring transfer that the device ends with an error', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info);
    final local = _FakeLocalSync();
    final wal = ringWal()..fileNum = -1;
    final syncs = walSyncsWith(local, card, wal);

    // Transfer to Phone reports "Transfer complete" whenever this call returns.
    final transfer = syncs.syncWal(wal: wal);
    await _until(() => card.readCalls.isNotEmpty);
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(3, 6)); // status error
    await expectLater(transfer, throwsException);

    expect(card.advanceCalls, isEmpty);
    expect(wal.status, WalStatus.miss);
    expect(syncs.ring.isSyncing, isFalse);
    expect(local.added, hasLength(1), reason: 'the audio that arrived stays saved on the phone');
    await card.controller.close();
    await syncs.ring.stop();
  });

  test('WalSyncs.syncWal rethrows a ring transfer error instead of returning an empty success', () async {
    final info = RingInfo(readSeq: 5, writeSeq: 6, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    final card = _FakeRingDevice(ringInfo: info)..statusGate = Completer<RingStatus?>();
    final wal = ringWal()..fileNum = -1;
    final syncs = walSyncsWith(_FakeLocalSync(), card, wal);
    final error = StateError('synthetic GATT failure');

    final transfer = syncs.syncWal(wal: wal);
    await _until(() => card.statusRequested);
    card.statusGate!.completeError(error);
    await expectLater(transfer, throwsA(same(error)));

    expect(card.readCalls, isEmpty);
    expect(wal.status, WalStatus.miss);
    expect(syncs.ring.isSyncing, isFalse);
    await card.controller.close();
    await syncs.ring.stop();
  });
}
