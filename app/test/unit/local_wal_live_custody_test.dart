import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _MockListener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _FakeCustodyConn implements DeviceConnection {
  int epoch = 1;
  RingInfo? info;
  int ackStatus = RingProtocol.ackOk;
  final advances = <({int seq, int? ringId})>[];

  @override
  int get ringCustodyEpoch => epoch;

  @override
  int get ringEffectiveCaps => 0x0F;

  @override
  RingInfo? get lastRingInfo => info;

  @override
  Future<RingInfo?> getRingInfo() async => info;

  @override
  Future<RingCommandAck?> advanceRingCustody(
    int newReadSeq, {
    required int expectedEpoch,
    required int? expectedRingId,
  }) async {
    advances.add((seq: newReadSeq, ringId: expectedRingId));
    return RingCommandAck(status: ackStatus);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late Directory custodyDir;
  // Every custody manager() hands out; tearDown flushes them before deleting storage (#20500).
  final custodies = <PendantRingCustody>[];

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('live_custody_');
    custodyDir = await Directory.systemTemp.createTemp('live_custody_cp_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
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
    if (custodyDir.existsSync()) custodyDir.deleteSync(recursive: true);
  });

  PendantRingCustody manager() {
    final custody = PendantRingCustody(
      store: PendantCustodyStore(directoryProvider: () async => custodyDir),
      walValidator: walFileManagerCustodyValidator,
    );
    custodies.add(custody);
    return custody;
  }

  RingInfo info(int ringId, {int readSeq = 0, int writeSeq = 100}) => RingInfo(
        readSeq: readSeq,
        writeSeq: writeSeq,
        capacityPackets: 1024,
        droppedPackets: 0,
        packetSize: 444,
        advertisedCaps: 0x0F,
        contractVersion: 1,
        ringId: ringId,
        infoBytes: 41,
      );

  WalFrame frame(int counter) =>
      WalFrame(payload: [0xAA, counter & 0xFF], syncKey: FrameSyncKey([counter & 0xFF, (counter >> 8) & 0xFF, 0]));

  LiveMarkNotification mark(int ringId, int ringSeq, int liveIndex) =>
      LiveMarkNotification(ringId: ringId, ringSeq: ringSeq, liveIndex: liveIndex);

  Future<void> pump() => Future<void>.delayed(const Duration(milliseconds: 60));

  test('#20376: live frames prove custody only after the WAL index save completes', () async {
    final custody = manager();
    final conn = _FakeCustodyConn()..info = info(42);
    final barrier = Completer<void>();
    final sync = LocalWalSyncImpl(
      _MockListener(),
      custody: custody,
      connectionResolver: (_) async => conn,
      freeDiskBytes: () async => 1 << 40,
      persistWals: (wals) async {
        await barrier.future;
        await WalFileManager.saveWals(wals);
      },
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    await sync.walReady;

    await custody.beginConnection(
      'dev',
      1,
      info(42),
      effectiveCaps: 0x0F,
      onAdvanceReady: (seq) async => (await conn.advanceRingCustody(seq, expectedEpoch: 1, expectedRingId: 42))?.status,
    );
    custody.setLivePersistEnabled('dev', 1, true);
    for (var i = 0; i < 20; i++) {
      sync.onFrameCaptured(frame(i));
    }
    custody.observeLiveMark('dev', 1, mark(42, 0, 0));
    custody.observeLiveMark('dev', 1, mark(42, 8, 19));
    await pump();
    expect(conn.advances, isEmpty, reason: 'marks alone cannot advance — nothing durable yet');

    final stopping = sync.stop();
    await pump();
    expect(conn.advances, isEmpty, reason: 'index save still gated — no ADVANCE may leak ahead of it');
    barrier.complete();
    await stopping;
    await pump();

    expect(conn.advances, hasLength(1));
    expect(conn.advances.single.seq, 8);
    expect(conn.advances.single.ringId, 42);
  });

  test('an app kill before the pendant drain produces no ADVANCE and no proof', () async {
    final custody = manager();
    final conn = _FakeCustodyConn()..info = info(42);
    final sync = LocalWalSyncImpl(
      _MockListener(),
      custody: custody,
      connectionResolver: (_) async => conn,
      freeDiskBytes: () async => 1 << 40,
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    await sync.walReady;
    await custody.beginConnection('dev', 1, info(42), effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('dev', 1, true);
    for (var i = 0; i < 20; i++) {
      sync.onFrameCaptured(frame(i));
    }
    custody.observeLiveMark('dev', 1, mark(42, 0, 0));
    custody.observeLiveMark('dev', 1, mark(42, 8, 19));
    await pump();

    expect(conn.advances, isEmpty);
    expect(custody.advanceTarget('dev', 1), isNull);
    expect(await WalFileManager.loadWals(), isEmpty);
    await sync.stop();
    await pump();
  });

  test('frames captured under ring A are never retagged to ring B on same-epoch INFO', () async {
    final custody = manager();
    final conn = _FakeCustodyConn()..info = info(42);
    final sync = LocalWalSyncImpl(
      _MockListener(),
      custody: custody,
      connectionResolver: (_) async => conn,
      freeDiskBytes: () async => 1 << 40,
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    await sync.walReady;
    await custody.beginConnection('dev', 1, info(42), effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('dev', 1, true);
    for (var i = 0; i < 10; i++) {
      sync.onFrameCaptured(frame(i));
    }

    custody.noteInfo('dev', 1, info(43));
    await sync.stop();
    await pump();
    expect(conn.advances, isEmpty, reason: 'ring-A buffered frames must not prove ring-B audio');

    for (var i = 0; i < 15; i++) {
      sync.onFrameCaptured(frame(i));
    }
    custody.observeLiveMark('dev', 1, mark(43, 0, 0));
    custody.observeLiveMark('dev', 1, mark(43, 5, 14));
    await sync.stop();
    await pump();

    expect(conn.advances, hasLength(1));
    expect(conn.advances.single.seq, 5);
    expect(conn.advances.single.ringId, 43);
  });

  test('frames from a stale connection epoch cannot prove the new session', () async {
    final custody = manager();
    final conn = _FakeCustodyConn()..info = info(42);
    final sync = LocalWalSyncImpl(
      _MockListener(),
      custody: custody,
      connectionResolver: (_) async => conn,
      freeDiskBytes: () async => 1 << 40,
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    await sync.walReady;
    await custody.beginConnection('dev', 1, info(42), effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('dev', 1, true);
    for (var i = 0; i < 10; i++) {
      sync.onFrameCaptured(frame(i));
    }

    custody.endConnection('dev', 1);
    await custody.beginConnection('dev', 2, info(42), effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('dev', 2, true);
    await sync.stop();
    await pump();

    expect(conn.advances, isEmpty, reason: 'epoch-1 frames must not produce epoch-2 proofs');
  });

  test('a failed index save keeps the live proof pending for the next save', () async {
    final custody = manager();
    final conn = _FakeCustodyConn()..info = info(42);
    var failNext = true;
    final sync = LocalWalSyncImpl(
      _MockListener(),
      custody: custody,
      connectionResolver: (_) async => conn,
      freeDiskBytes: () async => 1 << 40,
      persistWals: (wals) async {
        if (failNext) {
          failNext = false;
          throw const FileSystemException('index write failed');
        }
        await WalFileManager.saveWals(wals);
      },
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    await sync.walReady;
    await custody.beginConnection('dev', 1, info(42), effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('dev', 1, true);
    for (var i = 0; i < 15; i++) {
      sync.onFrameCaptured(frame(i));
    }
    custody.observeLiveMark('dev', 1, mark(42, 0, 0));
    custody.observeLiveMark('dev', 1, mark(42, 5, 14));

    try {
      await sync.stop();
    } catch (_) {}
    await pump();
    expect(conn.advances, isEmpty, reason: 'no durable index — no ADVANCE');

    await sync.stop();
    await pump();
    expect(conn.advances, hasLength(1));
    expect(conn.advances.single.seq, 5);
    expect(conn.advances.single.ringId, 42);
  });

  test('a lost live ACK keeps ranges for replay on the next connection; deleted files keep both', () async {
    final custody = manager();
    final conn = _FakeCustodyConn()..info = info(42);
    conn.ackStatus = -1;
    final sync = LocalWalSyncImpl(
      _MockListener(),
      custody: custody,
      connectionResolver: (_) async => conn,
      freeDiskBytes: () async => 1 << 40,
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    await sync.walReady;
    await custody.beginConnection('dev', 1, info(42), effectiveCaps: 0x0F);
    custody.setLivePersistEnabled('dev', 1, true);
    for (var i = 0; i < 15; i++) {
      sync.onFrameCaptured(frame(i));
    }
    custody.observeLiveMark('dev', 1, mark(42, 0, 0));
    custody.observeLiveMark('dev', 1, mark(42, 5, 14));
    await sync.stop();
    await pump();

    expect(await custody.isDurableLiveRecord('dev', 42, 3), isTrue);

    final custody2 = manager();
    int? replayedSeq;
    await custody2.beginConnection(
      'dev',
      2,
      info(42, readSeq: 0, writeSeq: 100),
      effectiveCaps: 0x0F,
      replayAdvance: (seq) async {
        replayedSeq = seq;
        return RingProtocol.ackOk;
      },
    );
    expect(replayedSeq, 5, reason: 'lost ACK must replay the durable frontier on reconnect');

    final wals = await WalFileManager.loadWals();
    final file = File('${tempDir.path}/${wals.first.filePath}');
    await file.delete();
    expect(
      await custody2.isDurableLiveRecord('dev', 42, 3),
      isFalse,
      reason: 'deleted audio must keep both copies — never dedupe a missing file',
    );
  });
}
