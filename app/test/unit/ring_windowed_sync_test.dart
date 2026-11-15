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

// Field report, firmware 3.0.24: one unbounded ring read ran for 30 minutes
// while the phone fell behind on storing it. Whatever was still in memory when
// the link dropped was fetched again on the next pass: 440,500 records
// downloaded in eight hours, 194,000 credited, and the backlog never cleared.
// These tests pin the bounded, credited reads that replace it.

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _FakeLocalSync implements LocalWalSync {
  final added = <Wal>[];

  @override
  int get sessionGeneration => 1;

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async => added.add(wal);

  @override
  Future<bool> ensureStorageAdmission({required int bytes, required int admittedGeneration}) async => true;

  @override
  Future<bool> hasDurableWal(Wal wal, {required int admittedGeneration}) async => added.contains(wal);

  @override
  void releaseStorageAdmission(int bytes) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const _framesPerRecord = 100;

List<int> _record(int seq) {
  final audio = <int>[];
  for (var i = 0; i < _framesPerRecord; i++) {
    audio
      ..add(1)
      ..add(seq & 0xFF);
  }
  audio.addAll(List<int>.filled(440 - audio.length, 0));
  final ts = ByteData(4)..setUint32(0, 1700000000 + seq, Endian.big);
  return [RingProtocol.notifyData, ...ts.buffer.asUint8List(), ...audio];
}

List<int> _readBegin(int startSeq, int packetCount) {
  final bd = ByteData(13);
  bd.setUint8(0, RingProtocol.notifyReadBegin);
  bd.setUint64(1, startSeq, Endian.big);
  bd.setUint32(9, packetCount, Endian.big);
  return bd.buffer.asUint8List();
}

List<int> _done(int nextSeq) {
  final bd = ByteData(10);
  bd.setUint8(0, RingProtocol.notifyDone);
  bd.setUint8(1, 0);
  bd.setUint64(2, nextSeq, Endian.big);
  return bd.buffer.asUint8List();
}

List<int> _liveMark(int ringId, int ringSeq, int liveIndex) {
  final bd = ByteData(19);
  bd.setUint8(0, RingProtocol.notifyLiveMark);
  bd.setUint64(1, ringId, Endian.big);
  bd.setUint64(9, ringSeq, Endian.big);
  bd.setUint16(17, liveIndex, Endian.big);
  return bd.buffer.asUint8List();
}

/// A pendant ring that behaves like the firmware: a read streams the requested
/// range, an advance moves the read pointer, INFO reports where both are.
class _RingModel implements DeviceConnection {
  _RingModel({required this.readSeq, required this.writeSeq, this.caps = 0x0F});

  int readSeq;
  int writeSeq;
  final int caps;
  final int ringId = 42;
  int epoch = 7;

  final reads = <(int, int?)>[];
  final advances = <(int, int?)>[];
  final delivered = <int>[];
  int infoRequests = 0;

  /// Acknowledgements to swallow: the advance is applied, the ack never arrives.
  int loseAcks = 0;

  /// Drop the link after this many records of the next read (then clears).
  int? dropAfterRecords;

  void Function(List<int>)? _onBytes;
  StreamController<List<int>> _controller = StreamController<List<int>>.broadcast();

  RingInfo get info => RingInfo(
        readSeq: readSeq,
        writeSeq: writeSeq,
        capacityPackets: 1 << 20,
        droppedPackets: 0,
        packetSize: 444,
        advertisedCaps: caps,
        contractVersion: caps == 0 ? 0 : 1,
        ringId: caps == 0 ? null : ringId,
        infoBytes: caps == 0 ? 31 : 41,
      );

  @override
  Future<RingInfo?> getRingInfo() async {
    infoRequests++;
    return info;
  }

  @override
  Future<RingStatus?> getRingStatus() async =>
      RingStatus(usedBytes: 0, unreadPackets: writeSeq - readSeq, freeBytes: 0, rtcValid: 1);

  @override
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount}) async {
    reads.add((startSeq, packetCount));
    final available = writeSeq - startSeq;
    final count = (packetCount == null || packetCount > available) ? available : packetCount;
    final dropAt = dropAfterRecords;
    dropAfterRecords = null;
    scheduleMicrotask(() async {
      _onBytes?.call(_readBegin(startSeq, count));
      for (var i = 0; i < count; i++) {
        if (dropAt != null && i == dropAt) {
          // Link lost: the stream ends and the next connection is a new epoch.
          epoch++;
          await _controller.close();
          _controller = StreamController<List<int>>.broadcast();
          return;
        }
        delivered.add(startSeq + i);
        _onBytes?.call(_record(startSeq + i));
        if (i % 50 == 49) await Future<void>.delayed(Duration.zero);
      }
      _onBytes?.call(_done(startSeq + count));
    });
    return true;
  }

  @override
  Future<bool> stopStorageSync() async => true;

  @override
  Future<RingCommandAck?> advanceRingCustody(
    int newReadSeq, {
    required int expectedEpoch,
    required int? expectedRingId,
  }) async {
    if (expectedEpoch != epoch) return const RingCommandAck(status: RingProtocol.ackRingIdMismatch);
    advances.add((newReadSeq, expectedRingId));
    if (newReadSeq > writeSeq) return const RingCommandAck(status: RingProtocol.ackSeqOutOfRange);
    if (newReadSeq > readSeq) readSeq = newReadSeq;
    if (loseAcks > 0) {
      loseAcks--;
      return null;
    }
    return const RingCommandAck(status: RingProtocol.ackOk);
  }

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    _onBytes = onStorageBytesReceived;
    return _controller.stream.listen((_) {});
  }

  @override
  int get ringCustodyEpoch => epoch;

  @override
  Future<void> get ringCustodyReady => Future.value();

  @override
  int get ringEffectiveCaps => caps;

  @override
  RingInfo? get lastRingInfo => info;

  @override
  bool get ringLivePersistEnabled => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  final custodies = <PendantRingCustody>[];

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('ring_windowed_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
  });

  tearDown(() async {
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

  PendantRingCustody newCustody({bool trustAll = false}) {
    final custody = PendantRingCustody(
      walValidator: trustAll
          ? (_) async => true
          : (ref) async {
              final path = await Wal.getFilePath(ref.fileName);
              if (path == null) return false;
              final f = File(path);
              return f.existsSync() && await f.length() == ref.bytes;
            },
    );
    custodies.add(custody);
    return custody;
  }

  Wal ringWal(_RingModel ring) => Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'pendant-1',
        storageTotalBytes: (ring.writeSeq - ring.readSeq) * 444,
      );

  RingStorageSyncImpl syncFor(_RingModel ring, _FakeLocalSync local, Wal wal, {PendantRingCustody? custody}) {
    final sync = RingStorageSyncImpl(_Listener())
      ..testConnection = ring
      ..testCustody = custody ?? newCustody()
      ..testWals = [wal]
      ..testWindowRecords = 120;
    sync.setLocalSync(local);
    sync.setDevice(BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40));
    return sync;
  }

  int framesStored(_FakeLocalSync local) => local.added.fold(0, (sum, w) => sum + w.totalFrames);

  test('a backlog larger than one window is read in bounded ranges, each released before the next', () async {
    final ring = _RingModel(readSeq: 1000, writeSeq: 1500);
    final local = _FakeLocalSync();
    final wal = ringWal(ring);
    final sync = syncFor(ring, local, wal);

    await sync.syncAll();

    expect(ring.reads, [(1000, 120), (1120, 120), (1240, 120), (1360, 120), (1480, 20)]);
    expect(ring.readSeq, 1500, reason: 'the pendant was advanced past everything it sent');
    expect(ring.delivered.length, 500, reason: 'no record is transferred twice');
    expect(framesStored(local), 500 * _framesPerRecord);
    expect(wal.status, WalStatus.synced);
    // Each read is released before the next one is requested.
    for (final (start, _) in ring.reads.skip(1)) {
      expect(ring.advances.any((a) => a.$1 == start), isTrue, reason: 'read at $start began before its advance');
    }
    expect(ring.advances.every((a) => a.$2 == 42), isTrue, reason: 'advances are bound to the ring incarnation');
  });

  test('a link drop costs at most the read in flight; the next pass resumes from the read pointer', () async {
    final ring = _RingModel(readSeq: 1000, writeSeq: 1500);
    final local = _FakeLocalSync();
    final custody = newCustody();
    final wal = ringWal(ring);
    final sync = syncFor(ring, local, wal, custody: custody);

    // Third read loses the link after 50 of its 120 records.
    var readCount = 0;
    final original = ring.reads;
    Future<void> armDrop() async {
      while (original.length < 2 || ring.readSeq < 1240) {
        await Future<void>.delayed(const Duration(milliseconds: 1));
        if (++readCount > 5000) fail('second window was never released');
      }
      ring.dropAfterRecords = 50;
    }

    final armed = armDrop();
    await sync.syncAll();
    await armed;

    expect(wal.status, WalStatus.miss, reason: 'an interrupted pass leaves the recording pending');
    expect(ring.readSeq, greaterThanOrEqualTo(1240), reason: 'completed reads stay credited');
    final creditedAtDrop = ring.readSeq;
    final deliveredAtDrop = ring.delivered.length;

    // Reconnected: a second pass picks up where the pendant's read pointer is.
    final wal2 = ringWal(ring);
    final sync2 = syncFor(ring, local, wal2, custody: custody);
    ring.reads.clear();
    await sync2.syncAll();

    expect(ring.reads.first.$1, creditedAtDrop, reason: 'nothing below the read pointer is fetched again');
    expect(ring.readSeq, 1500);
    expect(wal2.status, WalStatus.synced);
    final redelivered = ring.delivered.length - 500;
    expect(redelivered, lessThanOrEqualTo(120), reason: 'only the interrupted read may repeat');
    expect(ring.delivered.length - deliveredAtDrop, 1500 - creditedAtDrop);
  });

  test('firmware that frees ring space itself keeps the single unbounded read', () async {
    final ring = _RingModel(readSeq: 1000, writeSeq: 1500, caps: 0);
    final local = _FakeLocalSync();
    final wal = ringWal(ring);
    final sync = syncFor(ring, local, wal);

    await sync.syncAll();

    expect(ring.reads, [(1000, null)], reason: 'legacy firmware is read exactly as before');
    expect(ring.advances, [(1500, null)], reason: 'one anonymous advance after DONE');
    expect(framesStored(local), 500 * _framesPerRecord);
    expect(wal.status, WalStatus.synced);
  });

  test('a lost advance acknowledgement is settled from the read pointer, not by reading again', () async {
    final ring = _RingModel(readSeq: 1000, writeSeq: 1360)..loseAcks = 2;
    final local = _FakeLocalSync();
    final wal = ringWal(ring);
    final sync = syncFor(ring, local, wal);

    await sync.syncAll();

    expect(ring.readSeq, 1360);
    expect(ring.delivered.length, 360, reason: 'no range was downloaded twice');
    expect(ring.delivered.toSet().length, 360);
    expect(wal.status, WalStatus.synced);
    expect(ring.infoRequests, greaterThan(1), reason: 'the read pointer was consulted after the lost ack');
  });

  test('audio the phone already holds from the live stream is released without a transfer', () async {
    final ring = _RingModel(readSeq: 1000, writeSeq: 1500);
    final local = _FakeLocalSync();
    final custody = newCustody(trustAll: true);
    // Live proof for [1000, 1300): a mark every 30 records, as the pendant
    // emits one per committed batch, with every live packet between them durable.
    await custody.beginConnection('pendant-1', ring.epoch, ring.info, effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('pendant-1', ring.epoch, true);
    custody.observeLiveMark('pendant-1', ring.epoch, RingProtocol.parseLiveMarkNotification(_liveMark(42, 1000, 0))!);
    for (var batch = 1; batch <= 10; batch++) {
      for (var c = (batch - 1) * 60; c < batch * 60; c++) {
        custody.observeLiveFrame('pendant-1', ring.epoch, c, 0);
      }
      custody.observeLiveMark(
        'pendant-1',
        ring.epoch,
        RingProtocol.parseLiveMarkNotification(_liveMark(42, 1000 + batch * 30, batch * 60))!,
      );
    }
    await custody.recordDurableLiveFrames(
      'pendant-1',
      ring.epoch,
      0,
      600,
      const CustodyWalRef(fileName: 'live.bin', bytes: 10, frames: 600, liveRingId: 42),
    );
    final wal = ringWal(ring);
    final sync = syncFor(ring, local, wal, custody: custody);

    await sync.syncAll();

    expect(ring.reads.first.$1, 1300, reason: 'the proven live range is skipped, not downloaded');
    expect(ring.delivered.every((seq) => seq >= 1300), isTrue);
    expect(ring.delivered.length, 200);
    expect(ring.advances.first, (1300, 42));
    expect(ring.readSeq, 1500);
    expect(wal.status, WalStatus.synced);
  });

  group('the live tail is not a backlog', () {
    Future<PendantRingCustody> liveCustody(_RingModel ring, {required List<int> markSeqs}) async {
      final custody = newCustody(trustAll: true);
      await custody.beginConnection('pendant-1', ring.epoch, ring.info, effectiveCaps: 0x0F);
      custody.setLivePersistEnabled('pendant-1', ring.epoch, true);
      var liveIndex = 0;
      for (final seq in markSeqs) {
        custody.observeLiveMark(
          'pendant-1',
          ring.epoch,
          RingProtocol.parseLiveMarkNotification(_liveMark(42, seq, liveIndex))!,
        );
        for (var n = 0; n < 60; n++) {
          custody.observeLiveFrame('pendant-1', ring.epoch, liveIndex + n, 0);
        }
        liveIndex += 60;
      }
      return custody;
    }

    test('audio the phone is receiving and proving is left to the live proof', () async {
      final ring = _RingModel(readSeq: 1000, writeSeq: 1070);
      final custody = await liveCustody(ring, markSeqs: [1000, 1030, 1060]);
      final wal = ringWal(ring);
      final sync = syncFor(ring, _FakeLocalSync(), wal, custody: custody);

      expect(await sync.hasFilesToSync(), isFalse);
      await sync.syncAll();

      expect(ring.reads, isEmpty, reason: 'audio that arrived live seconds ago is not downloaded again');
      expect(ring.advances, isEmpty);
    });

    test('only the stretch before the first mark is read; the rest is the live run', () async {
      // The batch written before a connection's first mark cannot be proven
      // live. Reading just that lets the live proof release everything after it.
      final ring = _RingModel(readSeq: 1000, writeSeq: 1100);
      final custody = await liveCustody(ring, markSeqs: [1036, 1066, 1096]);
      final local = _FakeLocalSync();
      final wal = ringWal(ring);
      final sync = syncFor(ring, local, wal, custody: custody);

      expect(await sync.hasFilesToSync(), isTrue);
      await sync.syncAll();

      expect(ring.reads, [(1000, 36)]);
      expect(ring.delivered, List.generate(36, (i) => 1000 + i));
      expect(ring.readSeq, 1036, reason: 'the pendant is released up to where the live proof takes over');
      expect(framesStored(local), 36 * _framesPerRecord);
      expect(wal.status, WalStatus.synced);
    });

    test('when marks stop while the ring keeps growing, there is real unread audio to fetch', () async {
      final ring = _RingModel(readSeq: 1000, writeSeq: 1200);
      final custody = await liveCustody(ring, markSeqs: [1000, 1030]);
      final local = _FakeLocalSync();
      final wal = ringWal(ring);
      final sync = syncFor(ring, local, wal, custody: custody);

      expect(await sync.hasFilesToSync(), isTrue);
      await sync.syncAll();

      expect(ring.reads, isNotEmpty);
      expect(ring.readSeq, 1200);
      expect(framesStored(local), 200 * _framesPerRecord);
    });

    test('a connection with no live marks is judged by the unread count alone', () async {
      final ring = _RingModel(readSeq: 1000, writeSeq: 1010);
      final wal = ringWal(ring);
      final sync = syncFor(ring, _FakeLocalSync(), wal);

      expect(await sync.hasFilesToSync(), isTrue);
      await sync.syncAll();
      expect(ring.reads, [(1000, 10)]);
    });
  });
}
