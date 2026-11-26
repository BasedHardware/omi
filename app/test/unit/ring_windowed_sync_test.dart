import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_transfer_keep_alive.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal_syncs.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:omi/services/wals/device_capture_clock.dart';
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
  int sessionGeneration = 1;

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

List<int> _record(int seq, {int? timestamp}) {
  final audio = <int>[];
  for (var i = 0; i < _framesPerRecord; i++) {
    audio
      ..add(1)
      ..add(seq & 0xFF);
  }
  audio.addAll(List<int>.filled(440 - audio.length, 0));
  final ts = ByteData(4)..setUint32(0, timestamp ?? 1700000000 + seq, Endian.big);
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

  int? deferAdvanceAt;

  /// Drop the link after this many records of the next read (then clears).
  int? dropAfterRecords;
  void Function()? beforeRead;
  Future<void>? readGate;

  /// Whether the pendant's clock has been set. When it has not, records carry
  /// no usable time and the phone estimates one.
  bool rtcValid = true;
  int Function(int)? timestampFor;

  void Function(List<int>)? _onBytes;
  StreamController<List<int>> _controller = StreamController<List<int>>.broadcast();

  @override
  BtDevice get device =>
      BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40, firmwareRevision: '3.0.25');

  @override
  Future<BleAudioCodec> getAudioCodec() async => BleAudioCodec.opus;

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
      RingStatus(usedBytes: 0, unreadPackets: writeSeq - readSeq, freeBytes: 0, rtcValid: rtcValid ? 1 : 0);

  @override
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount, bool Function()? canStart}) async {
    beforeRead?.call();
    if (readGate case final gate?) await gate;
    if (canStart?.call() == false) return false;
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
        _onBytes?.call(_record(startSeq + i, timestamp: timestampFor?.call(startSeq + i)));
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
    if (deferAdvanceAt case final deferred? when newReadSeq >= deferred) {
      return null;
    }
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
        totalFrames: (ring.writeSeq - ring.readSeq) * _framesPerRecord,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'pendant-1',
        storageTotalBytes: (ring.writeSeq - ring.readSeq) * 444,
      );

  RingStorageSyncImpl syncFor(_RingModel ring, _FakeLocalSync local, Wal wal,
      {PendantRingCustody? custody,
      DateTime Function()? clock,
      Timer Function(Duration, void Function())? transferTimer}) {
    final sync = RingStorageSyncImpl(_Listener(), clock: clock, transferTimer: transferTimer)
      ..testConnection = ring
      ..testCustody = custody ?? newCustody()
      ..testWindowRecords = 120
      ..testLiveMarkSettle = Duration.zero;
    sync.setLocalSync(local);
    sync.setDevice(BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40));
    sync.testWals = [wal];
    return sync;
  }

  int framesStored(_FakeLocalSync local) => local.added.fold(0, (sum, w) => sum + w.totalFrames);

  test('ring reclaims during real 503 backoff and continues after upload pass timeout', () async {
    SharedPreferences.setMockInitialValues({'uid': 'ring-test-owner'});
    await SharedPreferencesUtil.init();
    await WalFileManager.init();
    final now = DateTime.now();
    final ring = _RingModel(readSeq: 1000, writeSeq: 1240);
    final listener = _Listener();
    final storage = RingStorageSyncImpl(listener)
      ..testConnection = ring
      ..testCustody = newCustody()
      ..testWindowRecords = 120;
    final sleeping = Completer<void>();
    final resumeUpload = Completer<void>();
    final deadlines = <void Function()>[];
    final uploads = <String>[];
    final gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => null,
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        uploads.addAll(files.map((file) => file.uri.pathSegments.last));
        throw const SyncUploadHttpException(503, 'Test backend unavailable');
      },
    );
    SyncRateLimiter.instance.clear();
    final phone = LocalWalSyncImpl(
      listener,
      now: () => now,
      freeDiskBytes: () async => 1024 * 1024 * 1024,
      persistWals: (_) async {},
      uploadGate: gate,
      sleep: (duration) async {
        if (!sleeping.isCompleted) sleeping.complete();
        await resumeUpload.future;
      },
    );
    final start = now.millisecondsSinceEpoch ~/ 1000;
    phone.testWals = [
      for (final (name, time) in [('live.bin', start - 120), ('history.bin', start - 60 * 60)])
        Wal(
          filePath: name,
          timerStart: time,
          codec: BleAudioCodec.opus,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          conversationId: name,
          seconds: 75,
          device: 'phone',
        ),
    ];
    for (final wal in phone.testWals) {
      await File('${tempDir.path}/${wal.filePath}').writeAsBytes([1, 0, 0, 0, 42]);
    }
    final syncs = WalSyncs(listener, phoneSync: phone, ringSync: storage);
    syncs.enableRingDrain(() => true);
    final timedOut = Completer<void>();
    final uploadExited = Completer<void>();
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        try {
          await syncs.syncAll();
          return const RecordingTransferDrainResult.skipped();
        } finally {
          uploadExited.complete();
        }
      },
      autoUploadEnabled: () => true,
      scheduleTimeout: (_, fire) => deadlines.add(fire),
      scheduleCooldown: (_, __) {},
      onPassTimedOut: (_, __) {
        syncs.cancelUploadPass();
        timedOut.complete();
      },
    )..onRingWake = syncs.wakeRingDrain;
    try {
      final upload = coordinator.wake(WakeTrigger.startup);
      await sleeping.future;
      expect(uploads, ['live.bin']);

      syncs.setDevice(ring.device);
      await syncs.wakeRingDrain();
      expect(ring.readSeq, 1240, reason: 'the uploader is still in its 503 backoff');
      expect(ring.reads, [(1000, 120), (1120, 120)]);

      deadlines.single();
      await timedOut.future;
      await upload;
      expect(uploadExited.isCompleted, isFalse);
      ring.writeSeq = 1480;
      coordinator.setForeground(false);
      unawaited(coordinator.wake(WakeTrigger.deviceConnected));
      await syncs.wakeRingDrain();
      expect(ring.readSeq, 1480, reason: 'the abandoned uploader still has not exited');
      expect(ring.reads, [(1000, 120), (1120, 120), (1240, 120), (1360, 120)]);

      resumeUpload.complete();
      await uploadExited.future;
      expect(uploads, ['live.bin'], reason: 'the stale upload cannot enter Phase 2');
    } finally {
      if (!resumeUpload.isCompleted) resumeUpload.complete();
      syncs.disableRingDrain();
      coordinator.dispose();
      SyncRateLimiter.instance.clear();
    }
  }, skip: !ringDrainRecoveryEnabled);

  test('one manual sync uploads ring audio that becomes durable after its first upload with Auto Sync off', () async {
    SharedPreferences.setMockInitialValues({'uid': 'ring-test-owner', 'autoSyncOfflineRecordings': false});
    await SharedPreferencesUtil.init();
    await WalFileManager.init();
    SyncRateLimiter.instance.clear();
    addTearDown(SyncRateLimiter.instance.clear);

    final releaseRead = Completer<void>();
    addTearDown(() {
      if (!releaseRead.isCompleted) releaseRead.complete();
    });
    final pendant = _RingModel(readSeq: 1000, writeSeq: 1240)..readGate = releaseRead.future;
    final listener = _Listener();
    final storage = RingStorageSyncImpl(listener)
      ..testConnection = pendant
      ..testCustody = newCustody()
      ..testWindowRecords = 120;
    final uploads = <String>[];
    final phone = LocalWalSyncImpl(
      listener,
      freeDiskBytes: () async => 1024 * 1024 * 1024,
      persistWals: (_) async {},
      uploadGate: SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => null,
        uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploads.addAll(files.map((file) => file.uri.pathSegments.last));
          return UploadFilesResult.queued('ring-job');
        },
      ),
    );
    final firstUpload = Completer<void>();
    final syncs = WalSyncs(listener, phoneSync: phone, ringSync: storage);
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        await syncs.syncAll();
        if (!firstUpload.isCompleted) firstUpload.complete();
        return const RecordingTransferDrainResult.skipped();
      },
      autoUploadEnabled: () => SharedPreferencesUtil().autoSyncOfflineRecordings,
    )
      ..onRingWake = syncs.wakeRingDrain
      ..onManualRingWake = syncs.wakeManualRingDrain;
    addTearDown(coordinator.dispose);
    addTearDown(syncs.disableRingDrain);
    expect(SharedPreferencesUtil().autoSyncOfflineRecordings, isFalse);
    syncs.enableRingDrain(() => false, onDurableChunk: coordinator.wakeForRingChunk);
    syncs.setDevice(pendant.device);
    await syncs.wakeRingDrain(); // Settle the connection's discovery-only pass.

    var manualCompleted = false;
    final manual = coordinator.wake(WakeTrigger.userRetry).then((_) => manualCompleted = true);
    await firstUpload.future;
    expect(uploads, isEmpty);
    expect(manualCompleted, isFalse);
    releaseRead.complete();
    await manual;

    expect(pendant.readSeq, 1240);
    final ringFiles = (await phone.getAllWals()).map((wal) => wal.filePath).toSet();
    expect(ringFiles, isNotEmpty);
    expect(uploads, unorderedEquals(ringFiles), reason: 'the same manual request submits each newly durable chunk');
  }, skip: !ringDrainRecoveryEnabled);

  test('cancelled upload releases leave the reconnected Android reader lease active', () async {
    SharedPreferences.setMockInitialValues({'uid': 'ring-test-owner'});
    await SharedPreferencesUtil.init();
    await WalFileManager.init();
    final nativeCalls = <String>[];
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SyncTransferKeepAlive.channel, (call) async {
      nativeCalls.add(call.method);
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(SyncTransferKeepAlive.channel, null));
    final keepAlive = SyncTransferKeepAlive(isAndroid: () => true);
    final uploadEntered = Completer<void>();
    final uploadMayExit = Completer<void>();
    final readerEntered = Completer<void>();
    final readerMayExit = Completer<void>();
    addTearDown(() {
      if (!uploadMayExit.isCompleted) uploadMayExit.complete();
      if (!readerMayExit.isCompleted) readerMayExit.complete();
    });

    final pendant = _RingModel(readSeq: 1000, writeSeq: 1000)
      ..readGate = readerMayExit.future
      ..beforeRead = () {
        if (!readerEntered.isCompleted) readerEntered.complete();
      };
    final listener = _Listener();
    final storage = RingStorageSyncImpl(listener)
      ..testConnection = pendant
      ..testCustody = newCustody()
      ..testWindowRecords = 120;
    final phone = LocalWalSyncImpl(listener, freeDiskBytes: () async => 1024 * 1024 * 1024, persistWals: (_) async {});
    final syncs = WalSyncs(listener, phoneSync: phone, ringSync: storage, keepAlive: keepAlive);
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        final release = await keepAlive.acquireScoped();
        try {
          uploadEntered.complete();
          await uploadMayExit.future;
          return const RecordingTransferDrainResult.skipped();
        } finally {
          await release();
        }
      },
      autoUploadEnabled: () => true,
      acquireTransferLease: keepAlive.acquireScoped,
    );
    addTearDown(coordinator.dispose);
    addTearDown(syncs.disableRingDrain);
    syncs.enableRingDrain(() => true);
    syncs.setDevice(pendant.device);
    await syncs.wakeRingDrain();

    final upload = coordinator.wake(WakeTrigger.startup);
    await uploadEntered.future;
    expect(keepAlive.refCount, 2);
    syncs.cancelSync();
    await keepAlive.releaseAll();
    expect(nativeCalls, ['start', 'stop']);

    syncs.setDevice(null);
    pendant.epoch++;
    pendant.writeSeq = 1240;
    syncs.setDevice(pendant.device);
    final reader = syncs.wakeRingDrain();
    await readerEntered.future;
    expect(nativeCalls, ['start', 'stop', 'start']);
    uploadMayExit.complete();
    await upload;
    expect(keepAlive.refCount, 1, reason: 'only the reconnected reader still owns the service');
    expect(nativeCalls, ['start', 'stop', 'start']);

    readerMayExit.complete();
    await reader;
    expect(pendant.readSeq, 1240);
    expect(nativeCalls, ['start', 'stop', 'start', 'stop']);
  }, skip: !ringDrainRecoveryEnabled);

  test('cancellation at radio admission sends no next read window', () async {
    final ring = _RingModel(readSeq: 1000, writeSeq: 1240);
    final local = _FakeLocalSync();
    final sync = syncFor(ring, local, ringWal(ring));
    ring.beforeRead = () {
      if (ring.reads.isNotEmpty) sync.cancelSync();
    };

    await sync.syncAll();

    expect(ring.reads, [(1000, 120)]);
    expect(ring.readSeq, 1120);
    expect(framesStored(local), 120 * _framesPerRecord);
  }, skip: !ringDrainRecoveryEnabled);

  for (final confirmation in ['live ACK', 'device INFO']) {
    test('delayed reclaim confirmed by $confirmation resumes without downloading twice', () async {
      final ring = _RingModel(readSeq: 1000, writeSeq: 1240)..deferAdvanceAt = 1120;
      final local = _FakeLocalSync();
      final custody = newCustody();
      final wal = ringWal(ring);
      final sync = syncFor(ring, local, wal, custody: custody, transferTimer: (delay, callback) {
        if (delay != const Duration(seconds: 1)) return Timer(delay, callback);
        return Timer(Duration.zero, () async {
          expect(ring.reads, [(1000, 120)]);
          expect(framesStored(local), 120 * _framesPerRecord);
          ring.readSeq = 1120;
          ring.deferAdvanceAt = null;
          if (confirmation == 'live ACK') await custody.markAdvanced('pendant-1', ring.epoch, 1120);
          callback();
        });
      });

      await sync.syncAll();

      expect(ring.reads, [(1000, 120), (1120, 120)]);
      expect(ring.delivered, List.generate(240, (index) => 1000 + index));
      expect(framesStored(local), 240 * _framesPerRecord);
      expect(wal.status, WalStatus.synced);
    });
  }

  for (final scenario in ['timeout', 'reconnect', 'account change']) {
    test('leaves reclaim pending after $scenario during confirmation', () async {
      final ring = _RingModel(readSeq: 1000, writeSeq: 1240)..deferAdvanceAt = 1120;
      final local = _FakeLocalSync();
      final wal = ringWal(ring);
      var waits = 0;
      final sync = syncFor(ring, local, wal, transferTimer: (delay, callback) {
        if (delay != const Duration(seconds: 1)) return Timer(delay, callback);
        return Timer(Duration.zero, () {
          waits++;
          if (scenario == 'reconnect') ring.epoch++;
          if (scenario == 'account change') local.sessionGeneration++;
          callback();
        });
      });

      await sync.syncAll();

      expect(waits, scenario == 'timeout' ? 8 : 1);
      expect(ring.reads, [(1000, 120)]);
      expect(ring.readSeq, lessThan(1120));
      expect(framesStored(local), 120 * _framesPerRecord);
      expect(wal.status, WalStatus.miss);
    });
  }

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

    final resumedFrom = ring.reads.first.$1;
    expect(resumedFrom, greaterThanOrEqualTo(creditedAtDrop),
        reason: 'completed indexed tail receipts may advance before the next READ');
    expect(ring.readSeq, 1500);
    expect(wal2.status, WalStatus.synced);
    final redelivered = ring.delivered.length - 500;
    expect(redelivered, lessThanOrEqualTo(120), reason: 'only the interrupted read may repeat');
    expect(ring.delivered.length - deliveredAtDrop, 1500 - resumedFrom);
    if (ringDrainRecoveryEnabled) {
      expect(redelivered, 0, reason: 'the indexed partial tail is replayed without a second transfer');
    }
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

  test('a recording that spans several reads stays one recording when the pendant has no clock', () async {
    // Without a usable device clock the phone estimates each chunk's time from
    // one starting point and the frames counted since. Restarting that estimate
    // for every read would split one recording into several and shift each
    // later part by however long the transfer took.
    final ring = _RingModel(readSeq: 1000, writeSeq: 1450)..rtcValid = false;
    final local = _FakeLocalSync();
    final wal = ringWal(ring);
    final sync = syncFor(ring, local, wal)..testWindowRecords = 150;

    await sync.syncAll();

    expect(ring.reads, [(1000, 150), (1150, 150), (1300, 150)]);
    expect(local.added, hasLength(9), reason: 'three chunks of 60, 60 and 30 records from each read');
    final runs = local.added.map((w) => w.clockRun).toSet();
    expect(runs, hasLength(1), reason: 'one recording, one estimated clock run');
    expect(runs.single, isNotNull);
    final fps = BleAudioCodec.opus.getFramesPerSecond();
    for (var i = 1; i < local.added.length; i++) {
      final previous = local.added[i - 1];
      expect(
        local.added[i].timerStart,
        previous.timerStart + previous.totalFrames ~/ fps,
        reason: 'chunk $i starts where chunk ${i - 1} ended, across the read boundary too',
      );
    }
  });

  for (final scenario in ['bad phone', 'absurd duration', 'zero duration', 'bad between good']) {
    test('windowed capture time cannot discard bytes: $scenario', () async {
      final ring = _RingModel(readSeq: 1000, writeSeq: 1003)..rtcValid = scenario == 'bad between good';
      final phone = scenario == 'bad phone' ? DateTime.utc(1970) : DateTime.utc(2026, 11, 15);
      if (scenario == 'bad between good') {
        final good = phone.millisecondsSinceEpoch ~/ 1000 - 100;
        ring.timestampFor = (seq) => seq == 1001 ? good + 400000 : good + (seq - 1000) * 2;
      }
      final local = _FakeLocalSync();
      final wal = ringWal(ring);
      if (scenario == 'absurd duration') wal.totalFrames = 1000000000000;
      if (scenario == 'zero duration') wal.totalFrames = 0;
      final sync = syncFor(ring, local, wal, clock: () => phone)..testWindowRecords = 1;
      await sync.syncAll();
      expect(ring.reads, [(1000, 1), (1001, 1), (1002, 1)]);
      expect(framesStored(local), 3 * _framesPerRecord);
      expect(ring.readSeq, 1003);
      expect(wal.status, WalStatus.synced);
      if (ringDrainRecoveryEnabled) {
        expect(
            local.added.map((w) => (w.downloadSeqStart, w.downloadSeqEnd)), [(1000, 1001), (1001, 1002), (1002, 1003)]);
      }
      if (!deviceCaptureClockRepairOff && scenario != 'bad between good') {
        expect(local.added.every((w) => w.timerStart == 0 && w.clockRun != null), isTrue);
      }
    });
  }

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
      final ring = _RingModel(readSeq: 1000, writeSeq: 1060);
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
      final ring = _RingModel(readSeq: 1000, writeSeq: 1096);
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

    test('a short unsent stretch after the last mark is read, not left for a mark that will never come', () async {
      // The phone is past the first mark and has released everything up to the
      // last one. Then one batch the phone was not sent is committed and the
      // wearer goes quiet: no mark follows, and nothing else will move the ring.
      final ring = _RingModel(readSeq: 1030, writeSeq: 1066);
      final custody = await liveCustody(ring, markSeqs: [1000, 1030]);
      final local = _FakeLocalSync();
      final wal = ringWal(ring);
      final sync = syncFor(ring, local, wal, custody: custody);

      expect(await sync.hasFilesToSync(), isTrue);
      await sync.syncAll();

      expect(ring.reads, [(1030, 36)]);
      expect(ring.readSeq, 1066);
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
