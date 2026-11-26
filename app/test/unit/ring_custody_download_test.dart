import 'dart:async';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:fake_async/fake_async.dart';
import 'package:omi/services/wals/ring_drain_policy.dart' show waitForRingRead, decodeCustodyRingAudio;
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/services/wals/device_capture_clock.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _FakeLocalSync implements LocalWalSync {
  _FakeLocalSync();

  bool failIndexSave = false;
  bool persistRealIndex = false;
  Completer<void>? indexGate;
  int indexAttempts = 0;
  final added = <Wal>[];

  @override
  int get sessionGeneration => 1;

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    indexAttempts++;
    await indexGate?.future;
    if (failIndexSave) throw const FileSystemException('index write failed');
    added.add(wal);
    if (persistRealIndex) {
      wal.ownerUid = 'owner';
      await WalFileManager.saveWals([...await WalFileManager.loadIndexedWals(), wal]);
    }
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
  Object? ringInfoError;
  Object? readError;
  final int caps;
  void Function(List<int>)? onBytes;
  final controller = StreamController<List<int>>.broadcast();
  final advances = <_Advance>[];
  final reads = <int>[];
  int stopCalls = 0;
  final _firstAdvance = Completer<void>();
  final _readReady = Completer<void>();
  int ackStatus = RingProtocol.ackOk;
  RingInfo? postAckInfo;
  int custodyEpochValue = 7;

  void emit(List<int> bytes) => onBytes?.call(bytes);

  /// Completes when the first advance reaches the card.
  Future<void> get firstAdvance => _firstAdvance.future;

  /// Wait for the listener and transfer state to be ready before delivering bytes.
  Future<void> get readReady => _readReady.future;

  @override
  Future<RingInfo?> getRingInfo() async {
    if (ringInfoError != null) throw ringInfoError!;
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
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount, bool Function()? canStart}) async {
    reads.add(startSeq);
    if (!_readReady.isCompleted) _readReady.complete();
    if (readError != null) throw readError!;
    return true;
  }

  @override
  Future<bool> stopStorageSync() async {
    stopCalls++;
    return true;
  }

  @override
  Future<RingCommandAck?> advanceRingCustody(
    int newReadSeq, {
    required int expectedEpoch,
    required int? expectedRingId,
  }) async {
    advances.add(_Advance(newReadSeq, expectedEpoch, expectedRingId));
    if (ackStatus == RingProtocol.ackOk && newReadSeq > ringInfo.readSeq) {
      final previous = ringInfo;
      ringInfo = RingInfo(
          readSeq: newReadSeq,
          writeSeq: previous.writeSeq,
          capacityPackets: previous.capacityPackets,
          droppedPackets: previous.droppedPackets,
          packetSize: previous.packetSize,
          advertisedCaps: previous.advertisedCaps,
          contractVersion: previous.contractVersion,
          ringId: previous.ringId,
          infoBytes: previous.infoBytes);
    }
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
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
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

  RingStorageSyncImpl syncWith(_FakeLocalSync local, _FakeRingDevice card, Wal wal,
      {Timer Function(Duration, void Function())? timer,
      Timer Function(Duration, void Function())? persistenceTimer,
      DateTime Function()? clock,
      bool productionValidation = false,
      PendantRingCustody? custodyOverride}) {
    final custody = custodyOverride ??
        PendantRingCustody(
          walValidator: productionValidation
              ? null
              : (ref) async {
                  final path = await Wal.getFilePath(ref.fileName);
                  if (path == null) return false;
                  final f = File(path);
                  return f.existsSync() && await f.length() == ref.bytes;
                },
        );
    custodies.add(custody);
    final sync =
        RingStorageSyncImpl(_Listener(), transferTimer: timer, persistenceTimer: persistenceTimer, clock: clock)
          ..testConnection = card
          ..testCustody = custody;
    sync.setLocalSync(local);
    sync.setDevice(BtDevice(id: 'devkit-1', name: 'Omi DevKit', type: DeviceType.omi, rssi: -40));
    sync.testWals = [wal];
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

  for (final scenario in ['bad phone', 'absurd duration', 'zero duration', 'good bad good']) {
    test('R16b every decoded record is indexed and provable despite $scenario', () async {
      await WalFileManager.init();
      await WalFileManager.saveWals([]);
      final goodPhone = DateTime.utc(2026, 11, 15);
      final phone = scenario == 'bad phone' || scenario == 'good bad good' ? DateTime.utc(1970) : goodPhone;
      final count = scenario == 'good bad good' ? 3 : 1;
      final card = _FakeRingDevice(
          ringInfo: _info(writeSeq: 5 + count, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
      final local = _FakeLocalSync()..persistRealIndex = true;
      final wal = ringWal(records: count)..totalFrames = scenario == 'absurd duration' ? 1000000000000 : 0;
      final sync = syncWith(local, card, wal, clock: () => phone, productionValidation: true);
      addTearDown(sync.stop);
      addTearDown(card.controller.close);
      final transfer = sync.syncWal(wal: wal);
      // Attach an error listener before notification work starts on the baseline.
      final finished = expectLater(transfer, completes);
      await card.readReady;
      card.emit(_readBegin(5, count));
      final good = goodPhone.millisecondsSinceEpoch ~/ 1000;
      for (final ts in scenario == 'good bad good' ? [good, 0, good + 1] : [0]) {
        card.emit(_record(timestamp: ts));
      }
      card.emit(_done(0, 5 + count));
      await finished;
      final indexed = await WalFileManager.loadIndexedWals();
      expect(indexed.fold<int>(0, (sum, row) => sum + row.totalFrames), count);
      expect(card.advances.last.seq, 5 + count);
      final ranges = <int>[];
      for (final row in indexed) {
        final bytes = await File((await Wal.getFilePath(row.filePath))!).readAsBytes();
        expect(bytes, List.generate(row.totalFrames, (_) => [10, 0, 0, 0, ...List.filled(10, 0xAB)]).expand((v) => v));
        expect(row.fileSha256, sha256.convert(bytes).toString());
        expect(row.ownerUid, 'owner');
        expect(row.device, 'devkit-1');
        expect(row.downloadRingId, 42);
        ranges.addAll(List.generate(row.downloadSeqEnd! - row.downloadSeqStart!, (i) => row.downloadSeqStart! + i));
        expect(
            await walFileManagerCustodyValidator(CustodyWalRef(
                fileName: row.filePath!,
                bytes: bytes.length,
                frames: row.totalFrames,
                ownerUid: row.ownerUid,
                fileSha256: row.fileSha256,
                downloadDeviceId: row.device,
                downloadRingId: 42,
                downloadSeqStart: row.downloadSeqStart,
                downloadSeqEnd: row.downloadSeqEnd)),
            isTrue);
      }
      expect(ranges..sort(), List.generate(count, (i) => 5 + i));
      if (!deviceCaptureClockRepairOff) {
        final unknown = indexed.where((row) => row.timerStart == 0);
        expect(unknown, isNotEmpty);
        expect(
            unknown
                .every((row) => row.clockRun != null && walCaptureTimeClass(row, good) == WalCaptureTimeClass.unknown),
            isTrue);
      }
      if (deviceCaptureClockRepairOff && count == 1) {
        final oldStart = phone.millisecondsSinceEpoch ~/ 1000 - wal.totalFrames ~/ wal.codec.getFramesPerSecond();
        expect(indexed.single.timerStart, oldStart, reason: 'OFF retains the old estimate exactly');
      }
    }, skip: !ringDrainRecoveryEnabled);
  }

  test('R16b DATA uses one 10001-row index snapshot until its own durable write', () async {
    await WalFileManager.init();
    final bytes = [10, 0, 0, 0, ...List.filled(10, 0xAB), 10, 0, 0, 0, ...List.filled(10, 0xAB)];
    await File('${tempDir.path}/existing.bin').writeAsBytes(bytes, flush: true);
    final row = Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 2,
        filePath: 'existing.bin',
        storage: WalStorage.disk,
        status: WalStatus.miss,
        ownerUid: 'owner',
        device: 'devkit-1',
        downloadRingId: 42,
        downloadSeqStart: 6,
        downloadSeqEnd: 8,
        downloadFileBytes: bytes.length,
        fileSha256: sha256.convert(bytes).toString());
    await WalFileManager.saveWals([
      row,
      for (var i = 0; i < 10000; i++)
        Wal(
            timerStart: i + 1000,
            codec: BleAudioCodec.opus,
            seconds: 1,
            filePath: 'unrelated-$i.bin',
            storage: WalStorage.disk,
            status: WalStatus.miss)
    ]);
    var loads = 0, hashes = 0;
    final custody = PendantRingCustody(indexLoader: () async {
      loads++;
      return WalFileManager.loadIndexedWals();
    }, fileDigest: (file) async {
      hashes++;
      return (await sha256.bind(file.openRead()).first).toString();
    });
    final local = _FakeLocalSync()..persistRealIndex = true;
    final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 8, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final wal = ringWal(records: 3);
    final sync = syncWith(local, card, wal, custodyOverride: custody);
    addTearDown(sync.stop);
    addTearDown(card.controller.close);
    final transfer = sync.syncWal(wal: wal);
    await card.readReady;
    final initialLoads = loads, initialHashes = hashes;
    card.emit(_readBegin(5, 3));
    for (var i = 0; i < 3; i++) {
      card.emit(_record(timestamp: 0));
    }
    final wait = Stopwatch()..start();
    while (hashes - initialHashes < 2 && wait.elapsed < const Duration(seconds: 5)) {
      await Future<void>.delayed(const Duration(milliseconds: 1));
    }
    expect(hashes - initialHashes, 2, reason: 'only records 6 and 7 overlap; each skip hashes fresh');
    expect(loads, initialLoads, reason: 'DATA performs no whole-index loads');
    card.emit(_done(0, 8));
    await transfer;
    expect(local.added.single.totalFrames, 1, reason: 'existing records never become a second audio file');
    expect(loads - initialLoads, 1, reason: 'only an indexed gap write by this read refreshes the snapshot');
    expect(card.advances.last.seq, 8);
  }, skip: !ringDrainRecoveryEnabled);

  test('syncAll persists the failure cause, original stack and phase for list and transfer errors', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await DebugLogManager.setEnabled(true);
    addTearDown(() => DebugLogManager.setEnabled(false));
    // DebugLogManager caches its log file. Exercise both phases in the same
    // test directory, clearing through its ordered writer between failures.
    for (final phase in ['list-read', 'transfer']) {
      await DebugLogManager.clear();
      final error = StateError('ring $phase failed');
      final card = _FakeRingDevice(ringInfo: _info());
      if (phase == 'list-read') {
        card.ringInfoError = error;
      } else {
        card.readError = error;
      }
      addTearDown(card.controller.close);
      final wal = ringWal()..deviceDownloadFraction = 0.5;
      final sync = syncWith(_FakeLocalSync(), card, wal);

      final response = await sync.syncAll();

      // Logging is fire-and-forget in production; wait for the actual persisted record.
      Map<String, dynamic>? failure;
      for (var attempt = 0; attempt < 100 && failure == null; attempt++) {
        final logFiles = await DebugLogManager.listLogFiles();
        final lines = logFiles.isEmpty ? <String>[] : await logFiles.first.readAsLines();
        for (final line in lines) {
          final record = jsonDecode(line) as Map<String, dynamic>;
          if (record['message'] == 'RingStorageSync failed') failure = record;
        }
        if (failure == null) await Future<void>.delayed(const Duration(milliseconds: 20));
      }

      expect(failure, isNotNull, reason: '$phase failure must retain its diagnostic cause after cleanup');
      expect(failure!['level'], 'ERROR');
      expect(failure['extra'], {'device': 'devkit-1', 'error': error.toString(), 'phase': phase});
      expect(failure['stack'], contains('_FakeRingDevice.${phase == 'list-read' ? 'getRingInfo' : 'readRingFromSeq'}'));
      expect(response, isNotNull);
      expect(response!.newConversationIds, isEmpty);
      expect(response.updatedConversationIds, isEmpty);
      expect(sync.isSyncing, isFalse);
      expect(wal.status, WalStatus.miss);
      expect(wal.deviceDownloadFraction, isNull);
      expect(card.advances, isEmpty);
    }
  });

  test('caps-0 legacy flow: durable records then a single anonymous advance after validated DONE', () async {
    final card = _FakeRingDevice(ringInfo: _info());
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await card.readReady.timeout(const Duration(seconds: 5));
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

  test('records from different days never share a chunk; a stale restarted clock gets its own run', () async {
    final card = _FakeRingDevice(ringInfo: _info());
    final local = _FakeLocalSync();
    final wal = ringWal(records: 5);
    final sync = syncWith(local, card, wal);

    final future = sync.syncWal(wal: wal);
    await card.readReady.timeout(const Duration(seconds: 5));
    card.emit(_readBegin(5, 5));
    const day1 = 1790422841;
    card.emit(_record(timestamp: day1));
    card.emit(_record(timestamp: day1 + 1));
    // Pendant off overnight: the next recording is a day later.
    card.emit(_record(timestamp: day1 + 86400));
    // Power loss: the clock restarts from its last phone sync, behind day 2.
    card.emit(_record(timestamp: day1 + 600));
    card.emit(_record(timestamp: day1 + 601));
    card.emit(_done(0, 10));
    await future;

    expect(local.added.map((w) => w.timerStart), [day1, day1 + 86400, day1 + 600]);
    expect(local.added[0].clockRun, isNull);
    expect(local.added[1].clockRun, isNull);
    expect(local.added[2].clockRun, isNotNull);
    expect(local.added[2].filePath, contains('_clke${local.added[2].clockRun}_${day1 + 600}'));
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
      await card.readReady.timeout(const Duration(seconds: 5));
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
    await card.readReady.timeout(const Duration(seconds: 5));
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
    await card.readReady.timeout(const Duration(seconds: 5));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await expectLater(future, throwsException);

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
    await card.readReady.timeout(const Duration(seconds: 5));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.emit(_done(0, 6));
    await expectLater(future, throwsException);

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
    await card.readReady.timeout(const Duration(seconds: 5));
    card.emit(_readBegin(5, 1));
    card.emit(_record());
    card.custodyEpochValue = 8;
    card.emit(_done(0, 6));
    await expectLater(future, throwsException);

    expect(card.advances, isEmpty);
    expect(wal.status, isNot(WalStatus.synced));
    await card.controller.close();
    await sync.stop();
  });

  Future<void> until(bool Function() ready) async {
    final watch = Stopwatch()..start();
    while (!ready() && watch.elapsed < const Duration(seconds: 10)) {
      await Future<void>.delayed(const Duration(milliseconds: 1));
    }
    expect(ready(), isTrue, reason: 'synthetic pendant did not reach the expected boundary');
  }

  test('R16 DONE behind stalled index hits persistence deadline and keeps owner until settle', () async {
    final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 66, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync()..indexGate = Completer<void>();
    final wal = ringWal(records: 61);
    void Function()? deadline;
    final sync = syncWith(local, card, wal, persistenceTimer: (duration, callback) {
      if (duration == const Duration(seconds: 45)) deadline = callback;
      return Timer(duration, callback);
    });
    final pending = sync.syncWal(wal: wal);
    final checked = expectLater(pending, throwsException);
    await card.readReady;
    card.emit(_readBegin(5, 61));
    for (var i = 0; i < 60; i++) {
      card.emit(_record(frameSizes: List.filled(100, 1)));
    }
    await until(() => local.indexAttempts == 1);
    card.emit(_done(0, 65));
    await Future<void>.delayed(Duration.zero);
    expect(deadline, isNotNull);
    deadline!();
    await until(() => card.stopCalls > 0);
    expect(card.advances, isEmpty, reason: 'a pending index is never proof');
    await expectLater(sync.syncWal(wal: wal), throwsStateError);
    expect(card.reads, [5]);
    local.indexGate!.complete();
    await checked;
    expect(sync.isSyncing, isFalse);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('R16 empty records wait for a durable indexed marker before ADVANCE', () async {
    final card =
        _FakeRingDevice(ringInfo: _info(caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync()..indexGate = Completer<void>();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);
    final pending = sync.syncWal(wal: wal);
    await card.readReady;
    card.emit(_readBegin(5, 1));
    card.emit(_record(frameSizes: []));
    card.emit(_done(0, 6));
    await until(() => local.indexAttempts == 1);
    expect(card.advances, isEmpty);
    final markerFiles = tempDir.listSync().whereType<File>().where((f) => f.path.endsWith('.ring-empty'));
    expect(markerFiles, hasLength(1));
    local.indexGate!.complete();
    await pending;
    expect(local.added.single.totalFrames, 0);
    expect(local.added.single.status, WalStatus.synced);
    expect(local.added.single.fileSha256, hasLength(64));
    expect(card.advances.single.seq, 6);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('cancel during index save stops read, settles exact tail, and ACKs before releasing ownership', () async {
    final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 66, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync()..indexGate = Completer<void>();
    final wal = ringWal(records: 61);
    final sync = syncWith(local, card, wal);
    final pending = sync.syncWal(wal: wal);
    final checked = expectLater(pending, throwsException);
    await card.readReady;
    card.emit(_readBegin(5, 61));
    for (var i = 0; i < 60; i++) {
      card.emit(_record(frameSizes: List.filled(100, 1)));
    }
    await until(() => local.indexAttempts == 1);
    sync.cancelSync();
    await until(() => card.stopCalls > 0);
    expect(sync.isSyncing, isTrue);
    await expectLater(sync.syncWal(wal: wal), throwsStateError);
    expect(card.reads, [5]);
    local.indexGate!.complete();
    await checked;
    expect(card.advances.map((a) => a.seq), [65]);
    expect(local.added.single.totalFrames, 6000);
    expect(sync.isSyncing, isFalse);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('old-epoch disk completion is replayed before next READ, with no second audio file', () async {
    final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 66, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync()..indexGate = Completer<void>();
    final wal = ringWal(records: 61);
    final sync = syncWith(local, card, wal);
    final custody = custodies.last;
    final pending = sync.syncWal(wal: wal);
    final checked = expectLater(pending, throwsException);
    await card.readReady;
    card.emit(_readBegin(5, 61));
    for (var i = 0; i < 60; i++) {
      card.emit(_record(frameSizes: List.filled(100, 1)));
    }
    await until(() => local.indexAttempts == 1);
    custody.endConnection('devkit-1', 7);
    card.custodyEpochValue = 8;
    sync.cancelSync();
    local.indexGate!.complete();
    await checked;
    expect(card.advances, isEmpty, reason: 'old-epoch command is fenced');
    expect(local.added, hasLength(1));
    local.indexGate = null;
    final next = sync.syncWal(wal: wal);
    await until(() => card.reads.length == 2);
    expect(card.advances.map((a) => a.seq), [65]);
    expect(card.reads, [5, 65], reason: 'durable [5,65) is ACKed before choosing new READ start');
    card.emit(_readBegin(65, 1));
    card.emit(_record());
    card.emit(_done(0, 66));
    await next;
    expect(local.added, hasLength(2), reason: 'only the one new record creates a file');
    expect(local.added.last.totalFrames, 1);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('a proven downloaded island is skipped while the missing prefix alone creates a file', () async {
    final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 8, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync();
    final wal = ringWal(records: 3);
    final sync = syncWith(local, card, wal);
    final custody = custodies.last;
    await custody.beginConnection('devkit-1', 7, card.ringInfo);
    await File('${tempDir.path}/existing.bin').writeAsBytes([1, 17], flush: true);
    await custody.recordDurableRingRange(
        'devkit-1', 7, 42, 6, 8, [const CustodyWalRef(fileName: 'existing.bin', bytes: 2, frames: 1)]);
    final pending = sync.syncWal(wal: wal);
    await card.readReady;
    expect(card.advances, isEmpty, reason: 'no proof for [5,6)');
    card.emit(_readBegin(5, 3));
    for (var i = 0; i < 3; i++) {
      card.emit(_record());
    }
    card.emit(_done(0, 8));
    await pending;
    expect(local.added, hasLength(1));
    expect(local.added.single.totalFrames, 1, reason: 'already indexed [6,8) is not written again');
    expect(card.advances.last.seq, 8);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('R16 a same-length replacement after READ admission is written again rather than skipped', () async {
    final card = _FakeRingDevice(
        ringInfo: _info(writeSeq: 7, caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync();
    final wal = ringWal(records: 2);
    final sync = syncWith(local, card, wal);
    final custody = PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => Directory('${tempDir.path}/real_custody')));
    custodies.add(custody);
    sync.testCustody = custody;
    final file = File('${tempDir.path}/island.bin');
    await file.writeAsBytes([1, 17], flush: true);
    final indexed = Wal(
        codec: BleAudioCodec.opus,
        timerStart: 1000,
        seconds: 1,
        totalFrames: 1,
        filePath: 'island.bin',
        storage: WalStorage.disk,
        status: WalStatus.miss,
        ownerUid: 'owner',
        device: 'devkit-1',
        downloadRingId: 42,
        downloadSeqStart: 6,
        downloadSeqEnd: 7,
        downloadFileBytes: 2,
        fileSha256: sha256.convert([1, 17]).toString());
    await WalFileManager.init();
    await WalFileManager.saveWals([indexed]);
    final pending = sync.syncWal(wal: wal);
    // Fake index writer below does not update the real index, so no final ACK.
    final checked = expectLater(pending, throwsException);
    await card.readReady;
    await file.writeAsBytes([1, 18], flush: true);
    card.emit(_readBegin(5, 2));
    card.emit(_record());
    card.emit(_record());
    card.emit(_done(0, 7));
    await checked;
    expect(local.added.single.totalFrames, 2,
        reason: 'hash revalidation discarded stale duplicate-suppression authority');
    expect(card.advances, isEmpty);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('31 minutes of an owned read never abandons its completion future', () {
    fakeAsync((time) {
      final done = Completer<bool>();
      bool? result;
      waitForRingRead(done.future).then((value) => result = value);
      time.elapse(const Duration(minutes: 31));
      expect(result, isNull, reason: 'the reader DATA-silence watchdog owns cancellation, not elapsed total time');
      done.complete(false); // the same completion used by cancel / silence / EOF
      time.flushMicrotasks();
      expect(result, isFalse);
    });
  }, skip: !ringDrainRecoveryEnabled);

  test('custody decoder keeps a terminal exact-fit frame and refuses truncated nonzero tails', () {
    expect(decodeCustodyRingAudio([2, 17, 18]), [
      [17, 18]
    ]);
    expect(decodeCustodyRingAudio([1, 17, 0, 0]), [
      [17]
    ]);
    expect(decodeCustodyRingAudio(List.filled(440, 0)), isEmpty);
    expect(() => decodeCustodyRingAudio([1, 17, 2, 18]), throwsFormatException);
    expect(() => decodeCustodyRingAudio([1]), throwsFormatException);
  });

  test('malformed ring tail retains the record and never creates reclaim proof', () async {
    final card =
        _FakeRingDevice(ringInfo: _info(caps: RingProtocol.capMaskV1, ringId: 42), caps: RingProtocol.capMaskV1);
    final local = _FakeLocalSync();
    final wal = ringWal();
    final sync = syncWith(local, card, wal);
    final pending = sync.syncWal(wal: wal);
    final checked = expectLater(pending, throwsException);
    await card.readReady;
    card.emit(_readBegin(5, 1));
    final bad = _record();
    bad[bad.length - 1] = 2; // claims two bytes beyond the record boundary
    card.emit(bad);
    card.emit(_done(0, 6));
    await checked;
    expect(card.advances, isEmpty);
    expect(local.added, isEmpty);
    await card.controller.close();
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);

  test('kill switch OFF retains the original 30-minute read timeout', () {
    fakeAsync((time) {
      final done = Completer<bool>();
      Object? error;
      waitForRingRead(done.future).then((_) {}, onError: (Object value) {
        error = value;
      });
      time.elapse(const Duration(minutes: 30));
      expect(error, isA<TimeoutException>());
      done.complete(false);
      time.flushMicrotasks();
    });
  }, skip: ringDrainRecoveryEnabled);

  test('disconnected connection lookup defers without starting a read or completing the virtual row', () async {
    final wal = ringWal();
    final sync = RingStorageSyncImpl(_Listener(), connectionResolver: (_) async => null);
    sync.setLocalSync(_FakeLocalSync());
    sync.setDevice(BtDevice(id: 'devkit-1', name: 'Omi', type: DeviceType.omi, rssi: -40));
    sync.testWals = [wal];
    await sync.syncAll();
    expect(wal.status, WalStatus.miss);
    expect(sync.isSyncing, isFalse);
    await sync.stop();
  }, skip: !ringDrainRecoveryEnabled);
}
