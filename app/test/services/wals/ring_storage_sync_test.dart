import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/capture/live_audio_frame_pacer.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

LiveAudioFrameDelivery _delivered() => LiveAudioFrameDelivery.accepted(Future<bool>.value(true));

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
    bool deepBacklogEnabled = true,
    RingConnectionResolver? connectionResolver,
    RingConversationTimeoutSecondsProvider? conversationTimeoutSecondsProvider,
    RingBacklogSnapshotCompleted? onBacklogSnapshotCompleted,
  }) {
    final sync = RingStorageSyncImpl(
      listener,
      connectionResolver: connectionResolver ?? (_) async => connection,
      documentsDirectoryProvider: () async => directory,
      deepBacklogPolicy: () => deepBacklogEnabled,
      conversationTimeoutSecondsProvider: conversationTimeoutSecondsProvider ?? () => 120,
      onBacklogSnapshotCompleted: onBacklogSnapshotCompleted,
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
    expect(local.testWals.every((wal) => wal.seconds > 0), isTrue);
    expect(wal.status, WalStatus.synced);
  });

  test('ring registration persists the last record wall-clock end across VAD pauses', () async {
    const firstTimestamp = _FakeRingConnection.baseTimestamp + 100;
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 102,
      timestamps: {
        100: firstTimestamp,
        101: firstTimestamp + 2,
      },
      framesPerRecord: 100,
    );
    final local = localSync();

    await ringSync(connection, local).syncWal(wal: virtualWal(2));

    final recovered = local.testWals.single;
    expect(recovered.timerStart, firstTimestamp);
    expect(recovered.seconds, 2);
    expect(recovered.captureEndSeconds, firstTimestamp + 3);
    expect(recovered.wallClockEndSeconds, firstTimestamp + 3);
  });

  test('deep backlog runs only by opt-in or while charging', () {
    expect(
      ringShouldDrainDeepBacklog(
        autoSyncEnabled: false,
        isCharging: false,
      ),
      isFalse,
    );
    expect(
      ringShouldDrainDeepBacklog(
        autoSyncEnabled: true,
        isCharging: false,
      ),
      isTrue,
    );
    expect(
      ringShouldDrainDeepBacklog(
        autoSyncEnabled: false,
        isCharging: true,
      ),
      isTrue,
    );
  });

  test('conversation timeout mirrors backend minimum and four-hour sentinel', () {
    expect(effectiveConversationBoundarySeconds(30), 120);
    expect(effectiveConversationBoundarySeconds(300), 300);
    expect(effectiveConversationBoundarySeconds(-1), 4 * 60 * 60);
  });

  test('storage-authoritative scheduler persists the live head before draining backlog', () async {
    final timestamps = {
      for (var seq = 0; seq < 10000; seq++) seq: _FakeRingConnection.baseTimestamp + 10000,
    };
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 10000,
      timestamps: timestamps,
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: _FakeRingConnection.baseTimestamp + 10000,
    );
    final liveDelivered = Completer<void>();

    final session = await sync.startAudioTail(
      onLiveFrames: (frames) {
        if (!liveDelivered.isCompleted) liveDelivered.complete();
        return _delivered();
      },
    );

    expect(session, isNotNull);
    await liveDelivered.future.timeout(const Duration(seconds: 1));
    expect(connection.reads.first, (start: 9980, count: 20));
    expect(connection.advanceAttempts, isEmpty);

    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    expect(connection.reads[1], (start: 9884, count: 96));

    await connection.thirdRead.future.timeout(const Duration(seconds: 3));
    expect(connection.reads[2], (start: 9788, count: 96));
    expect(connection.advanceAttempts, isEmpty);

    await session!.cancel();
    expect(session.isActive, isFalse);
    final liveWal = local.testWals.singleWhere((wal) => wal.sourceId == 'ring_9980_10000');
    expect(liveWal.uploadIntent, WalUploadIntent.liveContinuity);
    expect(
      local.testWals.where((wal) => wal.sourceId != 'ring_9980_10000').every(
            (wal) => wal.uploadIntent == WalUploadIntent.liveContinuity,
          ),
      isTrue,
    );
  });

  test('disabled auto-sync recovers recent gap but does not start the deep prefix', () async {
    final timestamps = {
      for (var seq = 9980; seq < 10000; seq++) seq: _FakeRingConnection.baseTimestamp + 10000,
    };
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 10000,
      timestamps: timestamps,
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: _FakeRingConnection.baseTimestamp + 10000,
      deepBacklogEnabled: false,
    );
    final liveDelivered = Completer<void>();

    final session = await sync.startAudioTail(
      onLiveFrames: (_) {
        if (!liveDelivered.isCompleted) liveDelivered.complete();
        return _delivered();
      },
    );

    await liveDelivered.future.timeout(const Duration(seconds: 1));
    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    expect(connection.reads.first, (start: 9980, count: 20));
    expect(connection.reads[1], (start: 9884, count: 96));

    await session!.cancel();
  });

  test('manual Sync drains one tail-owned snapshot while preserving live priority', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final timestamps = {
      for (var seq = 0; seq < 192; seq++) seq: now - 1000,
      for (var seq = 192; seq < 212; seq++) seq: now,
    };
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 212,
      timestamps: timestamps,
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
    );
    final liveDelivered = Completer<void>();

    final session = await sync.startAudioTail(
      onLiveFrames: (_) {
        if (!liveDelivered.isCompleted) liveDelivered.complete();
        return _delivered();
      },
    );

    await liveDelivered.future.timeout(const Duration(seconds: 1));
    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    final firstRequest = sync.requestAudioTailBacklogDrain();
    final repeatedTap = sync.requestAudioTailBacklogDrain();

    expect(firstRequest, isNotNull);
    expect(repeatedTap, same(firstRequest));
    final receipt = await firstRequest!.timeout(const Duration(seconds: 5));

    expect(receipt?.targetWriteSeq, 212);
    expect(receipt?.deviceId, 'cv1-test');
    expect(connection.reads.take(3), [
      (start: 192, count: 20),
      (start: 96, count: 96),
      (start: 0, count: 96),
    ]);
    expect(connection.successfulAdvances, [96, 212]);
    expect(sync.isAudioTailActive, isTrue);

    await session!.cancel();
  });

  test('manual snapshot caps a deep READ at its captured write sequence', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final infoGate = Completer<RingInfo?>();
    final connection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 212,
      ringInfoGate: infoGate,
      growWriteSeqAfterFirstReadBy: 30,
      timestamps: {
        for (var seq = 212; seq < 242; seq++) seq: now,
      },
    );
    final local = localSync();
    File('${directory.path}/future-coverage.bin').writeAsBytesSync([1, 2, 3]);
    local.testWals = [
      // Live resume metadata deliberately has no durable file. It suppresses
      // replay but cannot authorize ADVANCE.
      Wal(
        timerStart: now - 1,
        codec: BleAudioCodec.opus,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'ring_201_212',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
      // A later durable island makes the unconstrained backlog end 300. The
      // old manual receipt may authorize only [200, 212), never [212, 300).
      Wal(
        timerStart: now + 100,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'archive2_ring_300_320_${now + 100}',
        uploadIntent: WalUploadIntent.historicalBackfill,
        filePath: 'future-coverage.bin',
        seconds: 2,
      ),
    ];
    final liveRangeStored = Completer<void>();
    listener.onWalUpdatedCallback = () {
      if (!liveRangeStored.isCompleted && local.testWals.any((wal) => wal.sourceId == 'ring_212_242')) {
        liveRangeStored.complete();
      }
    };
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
    );

    final start = sync.startAudioTail(
      onLiveFrames: (_) => _delivered(),
      resumeLiveContinuity: true,
    );
    await Future<void>.delayed(Duration.zero);
    final request = sync.requestAudioTailBacklogDrain();
    infoGate.complete(
      RingInfo(
        readSeq: 200,
        writeSeq: 212,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      ),
    );

    final session = await start;
    final receipt = await request!.timeout(const Duration(seconds: 1));
    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    await liveRangeStored.future.timeout(const Duration(seconds: 1));

    expect(receipt?.targetWriteSeq, 212);
    expect(connection.reads.take(2), [
      (start: 200, count: 12),
      (start: 212, count: 30),
    ]);
    expect(connection.successfulAdvances, [212]);
    expect(
      local.testWals.singleWhere((wal) => wal.sourceId == 'ring_200_212').uploadIntent,
      WalUploadIntent.historicalBackfill,
    );
    expect(
      local.testWals.singleWhere((wal) => wal.sourceId == 'ring_212_242').uploadIntent,
      WalUploadIntent.liveContinuity,
    );
    expect(
      local.testWals.where(
        (wal) =>
            wal.uploadIntent == WalUploadIntent.historicalBackfill &&
            (RingProtocol.parseSourceRange(wal.sourceId)?.start ?? 0) >= 212,
      ),
      isEmpty,
      reason: 'a later writeSeq may be streamed live but must not expand the completed manual snapshot',
    );
    await session!.cancel();
  });

  test('captured manual snapshot survives same-device tail replacement without expanding', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final firstInfo = Completer<RingInfo?>();
    final firstConnection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 212,
      ringInfoGate: firstInfo,
      rejectRead: true,
    );
    final replacementConnection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 242,
      timestamps: {
        for (var seq = 212; seq < 242; seq++) seq: now,
      },
    );
    var activeConnection = firstConnection;
    final local = localSync();
    local.testWals = [
      Wal(
        timerStart: now - 1,
        codec: BleAudioCodec.opus,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'ring_201_212',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
    ];
    final sync = ringSync(
      firstConnection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
      connectionResolver: (_) async => activeConnection,
    );

    final firstStart = sync.startAudioTail(
      onLiveFrames: (_) => _delivered(),
      resumeLiveContinuity: true,
    );
    await Future<void>.delayed(Duration.zero);
    final originalRequest = sync.requestAudioTailBacklogDrain();
    firstInfo.complete(
      RingInfo(
        readSeq: 200,
        writeSeq: 212,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      ),
    );
    final firstSession = await firstStart;
    await expectLater(firstSession!.done, throwsA(isA<Exception>()));
    expect(firstConnection.reads, [(start: 200, count: 12)]);

    // Android's disconnect callback clears the bound device before the
    // capture controller starts the replacement tail.
    sync.setDevice(null);
    activeConnection = replacementConnection;
    sync.setDevice(_device());
    final replacementSession = await sync.startAudioTail(
      onLiveFrames: (_) => _delivered(),
      resumeLiveContinuity: true,
    );
    final receipt = await originalRequest!.timeout(const Duration(seconds: 5));

    expect(receipt?.deviceId, 'cv1-test');
    expect(receipt?.targetWriteSeq, 212);
    expect(replacementConnection.reads.take(2), [
      (start: 212, count: 30),
      (start: 200, count: 12),
    ]);
    expect(replacementConnection.successfulAdvances, [212]);
    expect(
      local.testWals.where(
        (wal) =>
            wal.uploadIntent == WalUploadIntent.historicalBackfill &&
            (RingProtocol.parseSourceRange(wal.sourceId)?.start ?? 0) >= 212,
      ),
      isEmpty,
    );
    await replacementSession!.cancel();
  });

  test('pending manual snapshot is never adopted by a different device', () async {
    final firstInfo = Completer<RingInfo?>();
    final firstConnection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 212,
      ringInfoGate: firstInfo,
      rejectRead: true,
    );
    final otherConnection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
    );
    final local = localSync();
    local.testWals = [
      Wal(
        timerStart: _FakeRingConnection.baseTimestamp + 9999,
        codec: BleAudioCodec.opus,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-other',
        sourceId: 'ring_119_120',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
    ];
    final sync = ringSync(
      firstConnection,
      local,
      deepBacklogEnabled: false,
      connectionResolver: (deviceId) async => deviceId == 'cv1-test' ? firstConnection : otherConnection,
    );

    final firstStart = sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await Future<void>.delayed(Duration.zero);
    final request = sync.requestAudioTailBacklogDrain()!;
    firstInfo.complete(
      RingInfo(
        readSeq: 200,
        writeSeq: 212,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      ),
    );
    final firstSession = await firstStart;
    await expectLater(firstSession!.done, throwsA(isA<Exception>()));

    sync.setDevice(null);
    sync.setDevice(_device('cv1-other'));
    expect(await request, isNull);

    final otherSession = await sync.startAudioTail(
      onLiveFrames: (_) => _delivered(),
      resumeLiveContinuity: true,
    );
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(otherConnection.reads, isEmpty);
    await otherSession!.cancel();
  });

  test('explicit cancellation resolves a request while its device is detached', () async {
    final firstInfo = Completer<RingInfo?>();
    final connection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 212,
      ringInfoGate: firstInfo,
      rejectRead: true,
    );
    final sync = ringSync(
      connection,
      localSync(),
      deepBacklogEnabled: false,
    );

    final start = sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await Future<void>.delayed(Duration.zero);
    final request = sync.requestAudioTailBacklogDrain()!;
    firstInfo.complete(
      RingInfo(
        readSeq: 200,
        writeSeq: 212,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      ),
    );
    final session = await start;
    await expectLater(session!.done, throwsA(isA<Exception>()));

    sync.setDevice(null);
    // WalSyncs.cancelSync invokes this even when isAudioTailActive is false.
    sync.cancelRequestedAudioTailBacklogDrain();
    expect(await request, isNull);
  });

  test('cancelling manual Sync revokes deep drain without stopping live capture', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 10000,
      timestamps: {
        for (var seq = 0; seq < 9980; seq++) seq: now - 1000,
        for (var seq = 9980; seq < 10000; seq++) seq: now,
      },
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    final request = sync.requestAudioTailBacklogDrain();
    sync.cancelRequestedAudioTailBacklogDrain();

    expect(await request, isNull);
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(connection.reads, [
      (start: 9980, count: 20),
      (start: 9884, count: 96),
    ]);
    expect(sync.isAudioTailActive, isTrue);

    await session!.cancel();
  });

  test('restart advances archive-backed coverage without rereading it', () async {
    final connection = _FakeRingConnection(readSeq: 100, writeSeq: 120);
    final local = localSync();
    File('${directory.path}/archive.bin').writeAsBytesSync([1, 2, 3]);
    local.testWals = [
      Wal(
        timerStart: _FakeRingConnection.baseTimestamp,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'archive2_ring_100_120_${_FakeRingConnection.baseTimestamp}',
        uploadIntent: WalUploadIntent.historicalBackfill,
        filePath: 'archive.bin',
        seconds: 2,
      ),
    ];
    final sync = ringSync(
      connection,
      local,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await connection.firstAdvance.future.timeout(const Duration(seconds: 1));

    expect(connection.advanceAttempts, [120]);
    expect(connection.reads, isEmpty);

    await session!.cancel();
  });

  test('legacy archive identity is never trusted for device ADVANCE', () async {
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      rejectRead: true,
    );
    final local = localSync();
    File('${directory.path}/legacy-archive.bin').writeAsBytesSync([1, 2, 3]);
    local.testWals = [
      Wal(
        timerStart: _FakeRingConnection.baseTimestamp,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'archive_ring_100_120_${_FakeRingConnection.baseTimestamp}',
        uploadIntent: WalUploadIntent.historicalBackfill,
        filePath: 'legacy-archive.bin',
        seconds: 2,
      ),
    ];
    final sync = ringSync(
      connection,
      local,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await expectLater(session!.done, throwsA(isA<Exception>()));

    expect(connection.reads, [(start: 100, count: 20)]);
    expect(connection.advanceAttempts, isEmpty);
  });

  for (final invalidProof in [
    'corrupted',
    'non-disk',
    'null-path',
    'missing-file',
    'empty-file',
  ]) {
    test('$invalidProof recovery WAL cannot authorize device ADVANCE', () async {
      final connection = _FakeRingConnection(
        readSeq: 100,
        writeSeq: 120,
        rejectRead: true,
      );
      final local = localSync();
      final fileName = '$invalidProof.bin';
      if (invalidProof != 'missing-file' && invalidProof != 'null-path') {
        File('${directory.path}/$fileName').writeAsBytesSync(
          invalidProof == 'empty-file' ? [] : [1, 2, 3],
        );
      }
      local.testWals = [
        Wal(
          timerStart: _FakeRingConnection.baseTimestamp,
          codec: BleAudioCodec.opus,
          status: invalidProof == 'corrupted' ? WalStatus.corrupted : WalStatus.miss,
          storage: invalidProof == 'non-disk' ? WalStorage.mem : WalStorage.disk,
          originalStorage: WalStorage.sdcard,
          device: 'cv1-test',
          sourceId: 'archive2_ring_100_120_${_FakeRingConnection.baseTimestamp}',
          uploadIntent: WalUploadIntent.historicalBackfill,
          filePath: invalidProof == 'null-path' ? null : fileName,
          seconds: 2,
        ),
      ];
      final sync = ringSync(
        connection,
        local,
        deepBacklogEnabled: false,
      );

      final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
      await expectLater(session!.done, throwsA(isA<Exception>()));

      expect(connection.reads, [(start: 100, count: 20)]);
      expect(connection.advanceAttempts, isEmpty);
    });
  }

  test('tail ownership is visible while connection setup is pending and clears on null', () async {
    final connectionGate = Completer<DeviceConnection?>();
    final local = localSync();
    final sync = RingStorageSyncImpl(
      listener,
      connectionResolver: (_) => connectionGate.future,
      documentsDirectoryProvider: () async => directory,
      deepBacklogPolicy: () => false,
      conversationTimeoutSecondsProvider: () => 120,
      inactivityTimeout: const Duration(milliseconds: 100),
    )
      ..setDevice(_device())
      ..setLocalSync(local);

    final start = sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await Future<void>.delayed(Duration.zero);

    expect(sync.isAudioTailActive, isTrue);
    connectionGate.complete(null);
    expect(await start, isNull);
    expect(sync.isAudioTailActive, isFalse);
  });

  test('tail ownership clears when setup throws', () async {
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      codecError: StateError('codec failed'),
    );
    final sync = ringSync(
      connection,
      localSync(),
      deepBacklogEnabled: false,
    );

    await expectLater(
      sync.startAudioTail(onLiveFrames: (_) => _delivered()),
      throwsA(isA<StateError>()),
    );
    expect(sync.isAudioTailActive, isFalse);
  });

  test('manual request shares reserved owner while ring info is pending', () async {
    final infoGate = Completer<RingInfo?>();
    final connection = _FakeRingConnection(
      readSeq: 120,
      writeSeq: 120,
      ringInfoGate: infoGate,
    );
    final sync = ringSync(
      connection,
      localSync(),
      deepBacklogEnabled: false,
    );

    final start = sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await Future<void>.delayed(Duration.zero);
    final request = sync.requestAudioTailBacklogDrain();

    expect(sync.isAudioTailActive, isTrue);
    expect(request, isNotNull);
    expect(connection.ringInfoCalls, 1);
    expect(connection.reads, isEmpty);

    infoGate.complete(
      RingInfo(
        readSeq: 120,
        writeSeq: 120,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      ),
    );
    final session = await start;
    final receipt = await request;

    expect(receipt?.targetWriteSeq, 120);
    expect(connection.reads, isEmpty);
    await session!.cancel();
  });

  test('automatic deep snapshot reports one bounded cloud-work receipt', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 212,
      timestamps: {
        for (var seq = 0; seq < 212; seq++) seq: now - 1000,
      },
    );
    final completion = Completer<RingBacklogDrainReceipt>();
    final sync = ringSync(
      connection,
      localSync(),
      nowSeconds: now,
      onBacklogSnapshotCompleted: (receipt) {
        if (!completion.isCompleted) completion.complete(receipt);
      },
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
    final receipt = await completion.future.timeout(const Duration(seconds: 5));

    expect(receipt.deviceId, 'cv1-test');
    expect(receipt.targetWriteSeq, 212);
    await session!.cancel();
  });

  test('sparse old VAD records stop recent recovery after one timestamp probe', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final timestamps = {
      for (var seq = 0; seq < 9980; seq++) seq: now - 1000,
      for (var seq = 9980; seq < 10000; seq++) seq: now,
    };
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 10000,
      timestamps: timestamps,
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    await Future<void>.delayed(const Duration(milliseconds: 100));
    await session!.cancel();

    expect(connection.reads, [
      (start: 9980, count: 20),
      (start: 9884, count: 96),
    ]);
    final probeWal = local.testWals.singleWhere((wal) => wal.sourceId == 'ring_9884_9980');
    expect(probeWal.uploadIntent, WalUploadIntent.historicalBackfill);
    expect(probeWal.status, WalStatus.miss);
  });

  test('live cursor catches up sequentially instead of skipping records produced during a read', () async {
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      growWriteSeqAfterFirstReadBy: 30,
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());

    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    expect(connection.reads[0], (start: 100, count: 20));
    expect(connection.reads[1], (start: 120, count: 30));
    expect(connection.reads[1].start, connection.reads[0].start + connection.reads[0].count);

    await session!.cancel();
  });

  test('tail snapshots a five-minute conversation timeout before asynchronous setup', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final infoGate = Completer<RingInfo?>();
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      ringInfoGate: infoGate,
      timestamps: {
        for (var seq = 100; seq < 120; seq++) seq: now - 180,
      },
    );
    var configuredTimeout = 300;
    final local = localSync();
    final stored = Completer<void>();
    listener.onWalUpdatedCallback = () {
      if (!stored.isCompleted && local.testWals.any((wal) => wal.sourceId == 'ring_100_120')) {
        stored.complete();
      }
    };
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
      conversationTimeoutSecondsProvider: () => configuredTimeout,
    );

    final start = sync.startAudioTail(
      onLiveFrames: (_) => _delivered(),
      resumeLiveContinuity: true,
    );
    await Future<void>.delayed(Duration.zero);
    configuredTimeout = 120;
    infoGate.complete(
      RingInfo(
        readSeq: 100,
        writeSeq: 120,
        capacityPackets: 1000000,
        droppedPackets: 0,
        packetSize: RingProtocol.recordSize,
      ),
    );

    final session = await start;
    await stored.future.timeout(const Duration(seconds: 3));
    expect(
      local.testWals.singleWhere((wal) => wal.sourceId == 'ring_100_120').uploadIntent,
      WalUploadIntent.liveContinuity,
    );
    await session!.cancel();
  });

  test('reconnect without recent delivery history prioritizes the live head over old backlog', () async {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 250,
      timestamps: {
        for (var seq = 230; seq < 250; seq++) seq: now,
      },
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
    );

    final liveDelivered = Completer<void>();
    final session = await sync.startAudioTail(
      onLiveFrames: (_) {
        if (!liveDelivered.isCompleted) liveDelivered.complete();
        return _delivered();
      },
      resumeLiveContinuity: true,
    );

    await liveDelivered.future.timeout(const Duration(seconds: 1));
    expect(connection.reads[0], (start: 230, count: 20));
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(connection.reads, hasLength(1));

    await session!.cancel();
  });

  test('live reconnect resumes at earliest recent undelivered range', () {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final wals = [
      Wal(
        timerStart: now - 8,
        codec: BleAudioCodec.opus,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_9900_9920',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 2,
      ),
      Wal(
        timerStart: now - 6,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_9920_9940',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 2,
      ),
      Wal(
        timerStart: now - 4,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_9940_9960',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 2,
      ),
      Wal(
        timerStart: now - 1000,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_100_200',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 10,
      ),
    ];

    expect(
      ringLiveResumeSequence(
        wals: wals,
        deviceId: 'cv1-test',
        readSeq: 0,
        writeSeq: 10000,
        nowSeconds: now,
        recentSeconds: 120,
      ),
      9920,
    );
  });

  test('live reconnect recency uses persisted capture end instead of compressed duration', () {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final vadSpanningWal = Wal(
      timerStart: now - 1000,
      codec: BleAudioCodec.opus,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'cv1-test',
      sourceId: 'ring_9800_9900',
      uploadIntent: WalUploadIntent.liveContinuity,
      seconds: 2,
      captureEndSeconds: now - 10,
    );

    expect(
      ringLiveResumeSequence(
        wals: [vadSpanningWal],
        deviceId: 'cv1-test',
        readSeq: 9000,
        writeSeq: 10000,
        nowSeconds: now,
        recentSeconds: 120,
      ),
      9800,
    );
  });

  test('live reconnect honors a configured five-minute open conversation', () {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final openConversationWal = Wal(
      timerStart: now - 1000,
      codec: BleAudioCodec.opus,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'cv1-test',
      sourceId: 'ring_9800_9900',
      uploadIntent: WalUploadIntent.liveContinuity,
      seconds: 2,
      captureEndSeconds: now - 180,
    );

    expect(
      ringLiveResumeSequence(
        wals: [openConversationWal],
        deviceId: 'cv1-test',
        readSeq: 9000,
        writeSeq: 10000,
        nowSeconds: now,
        recentSeconds: 300,
      ),
      9800,
    );
    expect(
      ringLiveResumeSequence(
        wals: [openConversationWal],
        deviceId: 'cv1-test',
        readSeq: 9000,
        writeSeq: 10000,
        nowSeconds: now,
        recentSeconds: 120,
      ),
      isNull,
    );
  });

  test('delivered replay coverage suppresses an older overlapping pending range', () {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final wals = [
      Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_100_120',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 2,
      ),
      Wal(
        timerStart: now - 9,
        codec: BleAudioCodec.opus,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_100_110',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
      Wal(
        timerStart: now - 8,
        codec: BleAudioCodec.opus,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        device: 'cv1-test',
        sourceId: 'ring_110_120',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
    ];

    expect(
      ringLiveResumeSequence(
        wals: wals,
        deviceId: 'cv1-test',
        readSeq: 90,
        writeSeq: 130,
        nowSeconds: now,
        recentSeconds: 120,
      ),
      120,
    );
  });

  test('reconnect reads durable replay and uncovered tail as separate ranges', () async {
    const now = _FakeRingConnection.baseTimestamp + 130;
    final connection = _FakeRingConnection(
      readSeq: 90,
      writeSeq: 130,
    );
    final local = localSync();
    File('${directory.path}/range-100-110.bin').writeAsBytesSync([1, 2, 3]);
    File('${directory.path}/range-110-120.bin').writeAsBytesSync([4, 5, 6]);
    local.testWals = [
      Wal(
        timerStart: now - 2,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'ring_100_110',
        filePath: 'range-100-110.bin',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
      Wal(
        timerStart: now - 1,
        codec: BleAudioCodec.opus,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'ring_110_120',
        filePath: 'range-110-120.bin',
        uploadIntent: WalUploadIntent.liveContinuity,
        seconds: 1,
      ),
    ];
    final sync = ringSync(
      connection,
      local,
      nowSeconds: now,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(
      onLiveFrames: (_) => _delivered(),
      resumeLiveContinuity: true,
    );

    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    expect(connection.reads[0], (start: 100, count: 20));
    expect(connection.reads[1], (start: 120, count: 10));

    await session!.cancel();
  });

  test('recent delivery ending at the device cursor resumes that cursor instead of the head', () {
    const now = _FakeRingConnection.baseTimestamp + 10000;
    final delivered = Wal(
      timerStart: now - 10,
      codec: BleAudioCodec.opus,
      status: WalStatus.synced,
      storage: WalStorage.disk,
      device: 'cv1-test',
      sourceId: 'ring_980_1000',
      uploadIntent: WalUploadIntent.liveContinuity,
      seconds: 2,
    );

    expect(
      ringLiveResumeSequence(
        wals: [delivered],
        deviceId: 'cv1-test',
        readSeq: 1000,
        writeSeq: 1200,
        nowSeconds: now,
        recentSeconds: 120,
      ),
      1000,
    );
  });

  test('live WAL stays retryable until every accepted preview frame is sent', () async {
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      timestamps: {
        for (var seq = 100; seq < 120; seq++) seq: _FakeRingConnection.baseTimestamp + 10000,
      },
    );
    final local = localSync();
    final sync = ringSync(connection, local, deepBacklogEnabled: false);
    final previewCompleted = Completer<bool>();
    final previewAccepted = Completer<void>();

    final session = await sync.startAudioTail(
      onLiveFrames: (_) {
        if (!previewAccepted.isCompleted) previewAccepted.complete();
        return LiveAudioFrameDelivery.accepted(previewCompleted.future);
      },
    );

    await previewAccepted.future.timeout(const Duration(seconds: 1));
    final liveWal = local.testWals.singleWhere(
      (wal) => wal.sourceId == 'ring_100_120',
    );
    expect(liveWal.status, WalStatus.miss);

    previewCompleted.complete(true);
    await Future<void>.delayed(Duration.zero);
    expect(liveWal.status, WalStatus.synced);

    await session!.cancel();
  });

  test('interrupted live-head read leaves backlog cursor untouched', () async {
    final timestamps = {for (var seq = 0; seq < 1000; seq++) seq: _FakeRingConnection.baseTimestamp + 1000};
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 1000,
      truncateStartSeq: 980,
      timestamps: timestamps,
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: _FakeRingConnection.baseTimestamp + 1000,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());

    expect(session, isNotNull);
    await expectLater(session!.done, throwsA(isA<RingStorageException>()));
    expect(session.isActive, isFalse);
    await expectLater(session.cancel(), completes);
    expect(connection.reads, [(start: 980, count: 20)]);
    expect(connection.advanceAttempts, isEmpty);
    expect(local.testWals, isEmpty);
  });

  test('disconnect racing a durable live ADVANCE ends cleanly and leaves the device cursor retryable', () async {
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      failAdvance: true,
      connected: false,
    );
    final local = localSync();
    final sync = ringSync(connection, local);

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());

    expect(session, isNotNull);
    await expectLater(session!.done, completes);
    expect(connection.advanceAttempts, [120]);
    expect(connection.successfulAdvances, isEmpty);
    expect(local.testWals.map((wal) => wal.sourceId), ['ring_100_120']);
  });

  test('live ADVANCE rejection on a connected transport remains a protocol failure', () async {
    final connection = _FakeRingConnection(
      readSeq: 100,
      writeSeq: 120,
      failAdvance: true,
    );
    final local = localSync();
    final sync = ringSync(connection, local);

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());

    expect(session, isNotNull);
    await expectLater(
      session!.done,
      throwsA(
        isA<RingStorageException>().having(
          (error) => error.message,
          'message',
          contains('live covered-prefix'),
        ),
      ),
    );
    expect(connection.advanceAttempts, [120]);
    expect(connection.successfulAdvances, isEmpty);
    expect(local.testWals.map((wal) => wal.sourceId), ['ring_100_120']);
  });

  test('storage-authoritative scheduler preserves chronology when the pendant RTC is invalid', () async {
    final connection = _FakeRingConnection(
      readSeq: 0,
      writeSeq: 1000,
      framesPerRecord: 5,
      timestamps: {for (var seq = 0; seq < 1000; seq++) seq: 0},
    );
    final local = localSync();
    final sync = ringSync(
      connection,
      local,
      nowSeconds: _FakeRingConnection.baseTimestamp + 1000,
    );
    final liveDelivered = Completer<void>();

    final session = await sync.startAudioTail(
      onLiveFrames: (_) {
        if (!liveDelivered.isCompleted) liveDelivered.complete();
        return _delivered();
      },
    );

    await liveDelivered.future.timeout(const Duration(seconds: 1));
    await connection.secondRead.future.timeout(const Duration(seconds: 3));
    await Future<void>.delayed(const Duration(milliseconds: 100));
    await session!.cancel();

    final liveWal = local.testWals.singleWhere((wal) => wal.sourceId == 'ring_980_1000');
    final recentWal = local.testWals.singleWhere((wal) => wal.sourceId == 'ring_884_980');
    expect(recentWal.timerStart, _FakeRingConnection.baseTimestamp + 994);
    expect(liveWal.timerStart, _FakeRingConnection.baseTimestamp + 999);
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

    await expectLater(
      ringSync(firstConnection, local).syncWal(wal: wal),
      throwsA(isA<RingStorageException>()),
    );

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

    await expectLater(
      ringSync(connection, local).syncWal(wal: wal),
      throwsA(isA<RingStorageException>()),
    );

    expect(connection.advanceAttempts, isEmpty);
    expect(local.testWals, isEmpty);
    expect(wal.status, WalStatus.miss);
  });

  test('CRC mismatch prevents registration and ADVANCE', () async {
    final connection = _FakeRingConnection(readSeq: 400, writeSeq: 402, corruptCrc: true);
    final local = localSync();
    final wal = virtualWal(2);

    await expectLater(
      ringSync(connection, local).syncWal(wal: wal),
      throwsA(isA<RingStorageException>()),
    );

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

    await expectLater(
      ringSync(firstConnection, local).syncWal(wal: wal),
      throwsA(isA<RingStorageException>()),
    );

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

    await expectLater(
      ringSync(firstConnection, local, nowSeconds: 1800000000).syncWal(wal: wal),
      throwsA(isA<RingStorageException>()),
    );

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

  test('invalid RTC fallback continues from the predecessor wall-clock capture end', () async {
    final local = localSync();
    local.testWals = [
      Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 100,
        captureEndSeconds: 2000.75,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'ring_100_200',
      ),
    ];
    final connection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 201,
      timestamps: const {200: 0},
      framesPerRecord: 100,
    );

    await ringSync(connection, local, nowSeconds: 3000).syncWal(wal: virtualWal(1));

    final recovered = local.testWals.singleWhere((wal) => wal.sourceId == 'ring_200_201');
    expect(recovered.timerStart, 2000);
    expect(recovered.captureEndSeconds, 2001);
  });

  test('tail restart continues invalid RTC chronology from an archive2 predecessor', () async {
    final local = localSync();
    File('${directory.path}/archive2-predecessor.bin').writeAsBytesSync([1, 2, 3]);
    local.testWals = [
      Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 100,
        captureEndSeconds: 2000.75,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1-test',
        sourceId: 'archive2_ring_100_200_1000',
        filePath: 'archive2-predecessor.bin',
        uploadIntent: WalUploadIntent.historicalBackfill,
      ),
    ];
    final stored = Completer<void>();
    listener.onWalUpdatedCallback = () {
      if (!stored.isCompleted && local.testWals.any((wal) => wal.sourceId == 'ring_200_201')) {
        stored.complete();
      }
    };
    final connection = _FakeRingConnection(
      readSeq: 200,
      writeSeq: 201,
      timestamps: const {200: 0},
      framesPerRecord: 100,
    );
    final sync = ringSync(
      connection,
      local,
      nowSeconds: 3000,
      deepBacklogEnabled: false,
    );

    final session = await sync.startAudioTail(onLiveFrames: (_) => _delivered());
    await stored.future.timeout(const Duration(seconds: 3));

    final recovered = local.testWals.singleWhere((wal) => wal.sourceId == 'ring_200_201');
    expect(recovered.timerStart, 2000);
    expect(recovered.captureEndSeconds, 2001);
    await session!.cancel();
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

  test('byte-identical retry upgrades legacy capture-end metadata before acknowledgment', () async {
    final local = localSync();
    final legacyFile = File('${directory.path}/legacy-upgrade.bin')..writeAsBytesSync([1, 2, 3, 4]);
    final candidateFile = File('${directory.path}/range-upgrade.bin')..writeAsBytesSync([1, 2, 3, 4]);
    final legacy = Wal(
      timerStart: 1700000850,
      codec: BleAudioCodec.opus,
      seconds: 1,
      device: 'cv1-test',
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: legacyFile.path.split('/').last,
    );
    local.testWals = [legacy];
    final candidate = Wal(
      timerStart: 1700000850,
      codec: BleAudioCodec.opus,
      seconds: 1,
      captureEndSeconds: 1700000860.5,
      device: 'cv1-test',
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: candidateFile.path.split('/').last,
      sourceId: 'ring_850_852',
    );

    final result = await local.addExternalWal(candidate);

    expect(result, ExternalWalRegistration.alreadyRegistered);
    expect(legacy.captureEndSeconds, 1700000860.5);
    expect(local.testWals, [legacy]);
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

BtDevice _device([String id = 'cv1-test']) => BtDevice(name: 'Omi', id: id, type: DeviceType.omi, rssi: -40);

class _Listener implements IWalSyncListener {
  void Function()? onWalUpdatedCallback;

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}

  @override
  void onWalUpdated() => onWalUpdatedCallback?.call();
}

class _FakeRingConnection implements DeviceConnection {
  static const int baseTimestamp = 1710000000;

  int readSeq;
  int writeSeq;
  final int growWriteSeqAfterFirstReadBy;
  final int? truncateStartSeq;
  final bool corruptCrc;
  final bool failAdvance;
  final bool connected;
  final bool rejectRead;
  final Object? codecError;
  final Completer<RingInfo?>? ringInfoGate;
  final int framesPerRecord;
  final Map<int, int> timestamps;
  final reads = <({int start, int count})>[];
  final advanceAttempts = <int>[];
  final successfulAdvances = <int>[];
  final Completer<void> firstAdvance = Completer<void>();
  final Completer<void> secondRead = Completer<void>();
  final Completer<void> thirdRead = Completer<void>();
  final StreamController<List<int>> _notifications = StreamController<List<int>>.broadcast(sync: true);
  int ringInfoCalls = 0;

  _FakeRingConnection({
    required this.readSeq,
    required this.writeSeq,
    this.growWriteSeqAfterFirstReadBy = 0,
    this.truncateStartSeq,
    this.corruptCrc = false,
    this.failAdvance = false,
    this.connected = true,
    this.rejectRead = false,
    this.codecError,
    this.ringInfoGate,
    this.framesPerRecord = 1,
    this.timestamps = const {},
  });

  @override
  Future<RingInfo?> getRingInfo() async {
    ringInfoCalls++;
    final gate = ringInfoGate;
    if (gate != null && ringInfoCalls == 1) return gate.future;
    return RingInfo(
      readSeq: readSeq,
      writeSeq: writeSeq,
      capacityPackets: 1000000,
      droppedPackets: 0,
      packetSize: RingProtocol.recordSize,
    );
  }

  @override
  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async =>
      _notifications.stream.listen(onStorageBytesReceived);

  @override
  Future<bool> readRingFromSeq(int startSeq, {int? packetCount}) async {
    final count = packetCount!;
    reads.add((start: startSeq, count: count));
    if (rejectRead) return false;
    if (reads.length == 1 && growWriteSeqAfterFirstReadBy > 0) {
      writeSeq += growWriteSeqAfterFirstReadBy;
    }
    if (reads.length == 2 && !secondRead.isCompleted) secondRead.complete();
    if (reads.length == 3 && !thirdRead.isCompleted) thirdRead.complete();
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
    if (!firstAdvance.isCompleted) firstAdvance.complete();
    return true;
  }

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<BleAudioCodec> getAudioCodec() async {
    final error = codecError;
    if (error != null) throw error;
    return BleAudioCodec.opus;
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
