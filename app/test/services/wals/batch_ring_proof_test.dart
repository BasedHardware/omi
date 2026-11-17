import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/services/wals/batch_ring_proof.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';
import 'package:omi/services/wals/mobile_standard_batch.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';

import '../../support/faulting_wal_writer.dart';
import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

class _Vad implements MobileBatchVad {
  @override
  Future<double> probability(List<int> opus) async => 0;
  @override
  Future<void> close() async {}
}

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _Pendant implements DeviceConnection {
  int epoch = 1;
  int ringId = 42;
  int ack = RingProtocol.ackOk;
  final advances = <({int epoch, int? ring, int seq})>[];
  @override
  int get ringCustodyEpoch => epoch;
  @override
  int get ringEffectiveCaps => 0x0F;
  @override
  Future<RingCommandAck?> advanceRingCustody(int seq,
      {required int expectedEpoch, required int? expectedRingId}) async {
    expect(expectedEpoch, epoch);
    expect(expectedRingId, ringId);
    advances.add((epoch: expectedEpoch, ring: expectedRingId, seq: seq));
    return RingCommandAck(status: ack);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory, checkpoints;
  late PendantRingCustody custody;
  late LocalWalSyncImpl phone;
  late MobileBatchBuffer buffer;
  late MobileStandardBatch lane;
  late _Pendant pendant;
  late FaultingWalWriter writer;
  final managers = <PendantRingCustody>[];
  final phones = <LocalWalSyncImpl>[];
  final buffers = <MobileBatchBuffer>[];
  final clock = DateTime.utc(2026, 11, 15);

  RingInfo info({int ring = 42, int read = 0, int write = 100}) => RingInfo(
      readSeq: read,
      writeSeq: write,
      capacityPackets: 1024,
      droppedPackets: 0,
      packetSize: 444,
      advertisedCaps: 0x0F,
      contractVersion: 1,
      ringId: ring,
      infoBytes: 41);

  PendantRingCustody manager({CustodyWalValidator? validator}) {
    final m = PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => checkpoints), walValidator: validator);
    managers.add(m);
    return m;
  }

  Future<LocalWalSyncImpl> ledger({Future<void> Function(List<Wal>)? persist}) async {
    final p = LocalWalSyncImpl(_Listener(),
        custody: custody,
        freeDiskBytes: () async => 1 << 40,
        persistWals: persist,
        connectionResolver: (_) async => pendant);
    phones.add(p);
    p.setDeviceInfo('pendant', 'Omi');
    p.start();
    await p.walReady;
    return p;
  }

  Future<void> connect({int epoch = 1, int ring = 42, int read = 0, bool live = true}) async {
    pendant.epoch = epoch;
    pendant.ringId = ring;
    await custody.beginConnection('pendant', epoch, info(ring: ring, read: read),
        replayAdvance: (seq) async =>
            (await pendant.advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: ring))?.status,
        onAdvanceReady: (seq) async =>
            (await pendant.advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: ring))?.status);
    custody.setLivePersistEnabled('pendant', epoch, live);
  }

  Future<void> install({Future<void> Function(Wal)? publish, int maxBytes = 1 << 30}) async {
    buffer = MobileBatchBuffer(
        directory: directory,
        maxBytes: maxBytes,
        openWriter: (file) => writer = FaultingWalWriter(file),
        publish: publish ??
            (wal) async {
              await phone.addExternalWal(wal, admittedGeneration: phone.sessionGeneration);
              expect(await phone.hasDurableWal(wal, admittedGeneration: phone.sessionGeneration), isTrue);
            });
    buffers.add(buffer);
    lane = MobileStandardBatch(
        buffer: buffer,
        loadVad: () async => _Vad(),
        freeDiskBytes: () async => 1 << 40,
        visibility: ListenClientState.instance,
        ownerUid: () => SharedPreferencesUtil().uid,
        now: () => clock,
        custody: custody);
    lane.authorize(true);
    await lane.pendingInitialization;
  }

  Future<bool> packet(int counter, {int fragment = 0, bool realtime = false}) async {
    final result = lane.route([counter & 0xFF, 7],
        codec: BleAudioCodec.opusFS320,
        realtimeConsumer: realtime,
        deviceId: 'pendant',
        packetCounter: counter,
        fragmentIndex: fragment,
        recordingSessionId: 'recording');
    await lane.pendingInference;
    return result;
  }

  void mark(int seq, int counter, {int epoch = 1, int ring = 42}) =>
      custody.observeLiveMark('pendant', epoch, LiveMarkNotification(ringId: ring, ringSeq: seq, liveIndex: counter));

  Future<void> frames(int from, int to) async {
    for (var i = from; i < to; i++) {
      expect(await packet(i), isTrue);
    }
    await buffer.pending; // Observe the actual metadata checkpoint boundary.
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    ListenClientState.instance.resetForTest();
    directory = await Directory.systemTemp.createTemp('batch_ring_proof_');
    checkpoints = await Directory.systemTemp.createTemp('batch_ring_checkpoints_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (call) async => call.method == 'getApplicationDocumentsDirectory' ? directory.path : null);
    await WalFileManager.init();
    pendant = _Pendant();
    custody = manager();
    phone = await ledger();
    await connect();
    await install();
  });

  tearDown(() async {
    await lane.close();
    for (final b in buffers) {
      await b.close();
    }
    for (final p in phones) {
      await p.stop();
    }
    for (final m in managers) {
      await m.flush();
    }
    buffers.clear();
    phones.clear();
    managers.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await directory.delete(recursive: true);
    await checkpoints.delete(recursive: true);
  });

  if (!batchRingProofEnabled) {
    test('compile-time OFF keeps today\'s batch bytes and emits no live observation or proof', () async {
      mark(0, 0);
      await frames(0, 50);
      mark(10, 50);
      await lane.close();
      await custody.flush();
      final indexed = await WalFileManager.loadIndexedWals();
      expect(indexed.single.totalFrames, 50);
      expect(indexed.single.liveRingId, isNull);
      expect(indexed.single.batchLiveSession, isNull);
      expect(custody.observeLiveFrameLatest('pendant', 50, 0), 0,
          reason: 'batch never touched the ordinary ordinal tracker');
      expect(pendant.advances, isEmpty);
    });
    return;
  }

  test('append -> fsync -> index -> proof -> persisted checkpoint -> ADVANCE', () async {
    final entered = Completer<void>(), release = Completer<void>();
    await lane.close();
    await install(publish: (wal) async {
      entered.complete();
      await release.future;
      await phone.addExternalWal(wal, admittedGeneration: phone.sessionGeneration);
    });
    addTearDown(() {
      if (!release.isCompleted) release.complete();
    });
    mark(0, 0);
    await frames(0, 49); // accepted, not yet a periodic fsync
    await custody.flush();
    expect(await WalFileManager.loadIndexedWals(), isEmpty);
    expect(pendant.advances, isEmpty);
    await packet(49); // periodic audio fsync + conservative journal checkpoint
    mark(10, 50);
    await custody.flush();
    expect(pendant.advances, isEmpty);
    buffer.seal();
    await entered.future;
    expect(await WalFileManager.loadIndexedWals(), isEmpty);
    expect(await custody.validatedAdvanceTarget('pendant', 1, 42), isNull);
    expect(pendant.advances, isEmpty, reason: 'sealed/fsynced file is not a persisted WAL index');
    release.complete();
    await buffer.pending;
    await custody.flush();
    expect(pendant.advances.map((a) => a.seq), [10]);
    expect(await custody.isDurableLiveRecord('pendant', 42, 5), isTrue,
        reason: 'spent live refs remain fresh-validation candidates for an in-flight read');
    expect(custody.advanceTarget('pendant', 1), isNull, reason: 'spent proofs do not reopen ADVANCE work');
    final wal = (await WalFileManager.loadIndexedWals()).single;
    expect(wal.liveOrdinalStart, 0);
    expect(wal.liveOrdinalEnd, 50);
    expect(wal.liveDeviceId, 'pendant');
    expect(wal.batchLiveSession, isNotEmpty);
  });

  test('a replayed batch WAL without a durable index never validates or reclaims', () async {
    mark(0, 0);
    await frames(0, 50);
    mark(10, 50);
    await custody.flush();
    writer.closeSync(); // process death: deliberately no seal/publish
    final recovered = await MobileBatchBuffer.recover(directory, []);
    expect(recovered.single.recoveredBatchJournal, isTrue);
    final wal = recovered.single;
    final ref = CustodyWalRef(
        fileName: wal.filePath!,
        bytes: wal.storageTotalBytes,
        frames: wal.totalFrames,
        liveRingId: wal.liveRingId,
        liveOrdinalStart: wal.liveOrdinalStart,
        liveOrdinalEnd: wal.liveOrdinalEnd,
        batchLiveSession: wal.batchLiveSession,
        liveDeviceId: wal.liveDeviceId,
        ownerUid: wal.ownerUid);
    expect(await WalFileManager.loadWals(), hasLength(1), reason: 'discovery is not an index commit');
    expect(await WalFileManager.loadIndexedWals(), isEmpty);
    expect(await walFileManagerCustodyValidator(ref), isFalse);
    await custody.recordDurableBatchWal(wal);
    await custody.flush();
    expect(pendant.advances, isEmpty);
  });

  for (final stage in ['append', 'audio_checkpoint', 'sealed_index_failed', 'indexed_ack_lost']) {
    test('restart at $stage retains samples and never expands old session ordinals', () async {
      final lostAck = stage == 'indexed_ack_lost';
      if (lostAck) pendant.ack = -1;
      if (stage == 'sealed_index_failed') {
        await lane.close();
        await install(publish: (_) async => throw const FileSystemException('index full'));
      }
      mark(0, 0);
      await frames(0, stage == 'append' ? 12 : 50);
      mark(10, stage == 'append' ? 12 : 50);
      await custody.flush();
      if (stage == 'sealed_index_failed' || lostAck) {
        await lane.close();
      } else {
        writer.closeSync();
      }
      await custody.flush();
      final before = await WalFileManager.loadWals();
      expect(before.single.totalFrames, stage == 'append' ? 12 : 50);
      final session = before.single.batchLiveSession;
      custody.endConnection('pendant', 1);
      await phone.stop();
      custody = manager();
      phone = await ledger(); // replay must save the recovered file before proof
      final indexed = await WalFileManager.loadIndexedWals();
      if (stage != 'append') expect(indexed, hasLength(1));
      final beforeReplay = pendant.advances.length;
      pendant.ack = RingProtocol.ackOk;
      // Integer epoch intentionally repeats: a new process can reuse 1.
      await connect();
      await custody.flush();
      if (stage == 'append') {
        expect(session, isNull, reason: 'no durable journal snapshot can prove the uncapped tail');
        expect(pendant.advances.length, beforeReplay);
      } else {
        expect(pendant.advances.length, greaterThan(beforeReplay));
        expect(pendant.advances.last.seq, 10);
        expect(custody.batchLiveContext('pendant')!.sessionId, isNot(session));
      }
    });
  }

  test('replay recovers extra complete frames without widening checkpoint proof', () async {
    mark(0, 0);
    await frames(0, 50);
    mark(10, 50);
    await frames(50, 57); // OS-visible tail beyond the last fsynced journal snapshot
    await custody.flush();
    writer.closeSync();
    final recovered = (await MobileBatchBuffer.recover(directory, [])).single;
    expect(recovered.totalFrames, 57);
    expect(recovered.liveOrdinalEnd, 50);
    expect(recovered.liveOrdinalEnd! - recovered.liveOrdinalStart!, 50);
    await phone.addExternalWal(recovered, admittedGeneration: phone.sessionGeneration);
    await custody.flush();
    expect(pendant.advances.last.seq, 10);
  });

  test('torn file below its journal prefix loses proof but retains original bytes', () async {
    mark(0, 0);
    await frames(0, 50);
    mark(10, 50);
    await custody.flush();
    writer.closeSync();
    final audio = directory.listSync().whereType<File>().singleWhere((f) => f.path.endsWith('.bin'));
    final truncate = await audio.open(mode: FileMode.append);
    await truncate.truncate(6 * 30 + 3);
    await truncate.close();
    final recovered = (await MobileBatchBuffer.recover(directory, [])).single;
    expect(recovered.totalFrames, 30);
    expect(recovered.batchLiveSession, isNull);
    expect(File('${audio.path}.torn').existsSync(), isTrue);
    await phone.addExternalWal(recovered, admittedGeneration: phone.sessionGeneration);
    await custody.flush();
    expect(pendant.advances, isEmpty);
  });

  for (final counters in [
    [0, 2, 3],
    [0, 1, 0],
    [65535, 0, 1]
  ]) {
    test('counter sequence $counters fails closed except an exact 16-bit wrap', () async {
      for (final i in counters) {
        await packet(i);
      }
      mark(0, counters.first);
      mark(1, counters.last + 1);
      await lane.close();
      await custody.flush();
      final wal = (await WalFileManager.loadIndexedWals()).single;
      if (counters.first == 65535) {
        expect(wal.liveOrdinalEnd, 3);
      } else {
        expect(wal.batchLiveSession, isNull);
        expect(pendant.advances, isEmpty);
      }
    });
  }

  test('fragmented live packets never create batch reclaim proof', () async {
    await packet(0);
    await packet(1, fragment: 1);
    mark(0, 0);
    mark(1, 2);
    await lane.close();
    await custody.flush();
    expect((await WalFileManager.loadIndexedWals()).single.batchLiveSession, isNull);
    expect(pendant.advances, isEmpty);
  });

  test('reconnect mid-batch seals separate coordinates even on the same ring', () async {
    await frames(0, 10);
    final old = custody.batchLiveContext('pendant')!;
    custody.endConnection('pendant', 1);
    await connect(epoch: 2);
    await frames(0, 12);
    await lane.close();
    await custody.flush();
    final indexed = await WalFileManager.loadIndexedWals();
    expect(indexed.map((w) => w.totalFrames), [10, 12]);
    expect(indexed.first.batchLiveSession, old.sessionId);
    expect(indexed.last.batchLiveSession, isNot(old.sessionId));
    expect(indexed.map((w) => w.liveOrdinalStart), [0, 0]);
    expect(pendant.advances, isEmpty, reason: 'unmapped old frames cannot prove a new session');
  });

  test('same-epoch ring change cannot retag old batch audio', () async {
    await frames(0, 10);
    custody.noteInfo('pendant', 1, info(ring: 43));
    pendant.ringId = 43;
    mark(0, 0, ring: 43);
    await frames(0, 50);
    mark(10, 50, ring: 43);
    await lane.close();
    await custody.flush();
    final indexed = await WalFileManager.loadIndexedWals();
    expect(indexed.map((w) => w.liveRingId), [42, 43]);
    expect(pendant.advances, everyElement((epoch: 1, ring: 43, seq: 10)));
    expect(pendant.advances, hasLength(1));
  });

  test('declined batch frame falls back once and joins adjacent ordinary proof', () async {
    mark(0, 0);
    await frames(0, 10);
    // Realtime/Custom STT eligibility refuses before any observation.
    expect(await packet(10, realtime: true), isFalse);
    final ordinary = phone.onFrameCaptured(WalFrame(payload: [10, 7], syncKey: FrameSyncKey([10, 0, 0])));
    expect(ordinary.liveOrdinal, 10, reason: 'declined batch must not consume this ordinal');
    await frames(11, 20);
    mark(8, 20);
    await lane.close();
    await phone.stop();
    await custody.flush();
    expect(pendant.advances.last.seq, 8, reason: 'batch + ordinary + batch is a contiguous union');
    final index = await WalFileManager.loadIndexedWals();
    expect(index.fold<int>(0, (n, w) => n + w.totalFrames), 20);
  });

  test('disk budget refusal leaves the ordinary counter untouched', () async {
    await lane.close();
    await install(maxBytes: 5);
    expect(await packet(0), isFalse);
    final ordinary = phone.onFrameCaptured(WalFrame(payload: [0, 7], syncKey: FrameSyncKey([0, 0, 0])));
    expect(ordinary.liveOrdinal, 0);
    expect(pendant.advances, isEmpty);
  });

  for (final failure in ['write', 'flush', 'index']) {
    test('$failure failure never authorizes batch reclaim', () async {
      if (failure == 'index') {
        await lane.close();
        await install(publish: (_) async => throw const FileSystemException('index full'));
      }
      mark(0, 0);
      await packet(0);
      if (failure == 'write') writer.failWrite = true;
      if (failure == 'flush') writer.failFlush = true;
      await packet(1);
      mark(1, 2);
      await lane.close();
      await custody.flush();
      expect(pendant.advances, isEmpty);
      expect(directory.listSync().where((f) => f.path.endsWith('.batch-journal')), isNotEmpty);
    });
  }

  test('legacy/no live-persist grant keeps batching without new custody metadata', () async {
    custody.setLivePersistEnabled('pendant', 1, false);
    await frames(0, 50);
    mark(10, 50);
    await lane.close();
    await custody.flush();
    expect((await WalFileManager.loadIndexedWals()).single.liveRingId, isNull);
    expect(pendant.advances, isEmpty);
  });

  test('foreign-account replay cannot authorize reclaim', () async {
    mark(0, 0);
    await frames(0, 50);
    mark(10, 50);
    await custody.flush();
    writer.closeSync();
    final recovered = (await MobileBatchBuffer.recover(directory, [])).single;
    SharedPreferencesUtil().uid = 'other';
    await phone.addExternalWal(recovered, admittedGeneration: phone.sessionGeneration);
    await custody.flush();
    expect(pendant.advances, isEmpty);
  });

  test('an index writer returning without persisting cannot create reclaim authority', () async {
    await phone.stop();
    phone = await ledger(persist: (_) async {});
    mark(0, 0);
    await frames(0, 50);
    mark(10, 50);
    await lane.close();
    await custody.flush();
    expect(await WalFileManager.loadIndexedWals(), isEmpty);
    expect(pendant.advances, isEmpty);
  });

  for (final transition in ['ring', 'owner', 'disconnect']) {
    test('$transition change while validating the index cannot publish stale batch proof', () async {
      await lane.close();
      await phone.stop();
      final entered = Completer<void>(), release = Completer<void>();
      var first = true;
      custody = manager(validator: (ref) async {
        if (first && ref.batchLiveSession != null) {
          first = false;
          entered.complete();
          await release.future;
        }
        return walFileManagerCustodyValidator(ref);
      });
      phone = await ledger();
      await connect();
      await install();
      mark(0, 0);
      await frames(0, 50);
      mark(10, 50);
      buffer.seal();
      await entered.future;
      try {
        switch (transition) {
          case 'ring':
            custody.noteInfo('pendant', 1, info(ring: 43));
            pendant.ringId = 43;
          case 'owner':
            SharedPreferencesUtil().uid = 'other';
          case 'disconnect':
            custody.endConnection('pendant', 1);
        }
      } finally {
        release.complete();
      }
      await buffer.pending;
      await custody.flush();
      expect(pendant.advances, isEmpty);
      if (transition == 'ring') expect(await custody.isDurableLiveRecord('pendant', 43, 5), isFalse);
      expect((await WalFileManager.loadIndexedWals()).single.totalFrames, 50);
    });
  }

  test('a persisted old-ring batch checkpoint never replays against a new ring', () async {
    pendant.ack = -1;
    mark(0, 0);
    await frames(0, 50);
    mark(10, 50);
    await lane.close();
    await custody.flush();
    final oldAttempts = pendant.advances.length;
    custody.endConnection('pendant', 1);
    custody = manager();
    await connect(ring: 43);
    await custody.flush();
    expect(pendant.advances.length, oldAttempts);
    expect(await custody.isDurableLiveRecord('pendant', 43, 5), isFalse);
  });

  for (final mode in ['mute', 'custom_stt']) {
    test('real CaptureController $mode keeps the existing batch admission boundary', () async {
      await lane.close();
      final prefs = <String, Object>{'uid': 'owner'};
      if (mode == 'custom_stt') {
        // The socket is hermetic: only its captured Custom STT mode is used.
        const config = CustomSttConfig(provider: SttProvider.deepgram, apiKey: 'synthetic');
        SharedPreferencesUtil().uid = 'owner';
        await SharedPreferencesUtil().saveCustomSttConfig(config);
        prefs['customSttConfig'] = SharedPreferencesUtil().getString('customSttConfig');
      }
      final world =
          await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opusFS320, initialPrefs: prefs);
      world.deviceConnection = ScriptedDeviceConnection();
      final shared = PendantRingCustody.shared;
      await shared.beginConnection('omi', 1, info());
      shared.setLivePersistEnabled('omi', 1, true);
      final routed = MobileStandardBatch(
          buffer: buffer,
          loadVad: () async => _Vad(),
          freeDiskBytes: () async => 1 << 40,
          visibility: ListenClientState.instance,
          ownerUid: () => SharedPreferencesUtil().uid,
          now: () => clock,
          custody: shared);
      world.controller.installMobileStandardBatch(routed);
      try {
        await world.controller
            .streamDeviceRecording(device: BtDevice(id: 'omi', name: 'Omi', type: DeviceType.omi, rssi: -40));
        await world.settle();
        world.socket!.emitServerMessage('{"type":"service_status","status":"ready","mobile_standard_batch":true}');
        await routed.pendingInitialization;
        if (mode == 'mute') await SharedPreferencesUtil().setCaptureMuted(true);
        world.deviceConnection!.emitRawAudio([0, 0, 0, 7, 8]);
        await world.settle();
        await routed.pendingInference;
        expect(buffer.hasFrames, isFalse);
        if (mode == 'mute') {
          expect(world.wal.syncs.phone.testFrames, isEmpty);
          expect(shared.observeLiveFrameLatest('omi', 0, 0), 0, reason: 'muted packet was not observed');
        } else {
          expect(world.wal.syncs.phone.testFrames.single.liveOrdinal, 0);
          expect(world.socket!.sentBinary, hasLength(1));
        }
      } finally {
        await routed.close();
        await world.dispose();
        await shared.flush();
        shared.endConnection('omi', 1);
      }
    });
  }

  test('an old unproven prefix holds newer batch proof behind it', () async {
    mark(5, 0);
    await frames(0, 50);
    mark(15, 50);
    await lane.close();
    await custody.flush();
    expect(await custody.isDurableLiveRecord('pendant', 42, 10), isTrue);
    expect(pendant.advances, isEmpty, reason: 'records [0,5) have no custody proof');
  });
}
