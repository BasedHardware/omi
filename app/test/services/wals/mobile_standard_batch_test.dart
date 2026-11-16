import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';
import 'package:omi/services/wals/mobile_standard_batch.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/capture/capture_end.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import '../../support/on_device_fakes.dart';
import '../../support/faulting_wal_writer.dart';
import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

class FakeVad implements MobileBatchVad {
  double value = 0;
  bool fail = false;
  int calls = 0;
  @override
  Future<double> probability(List<int> opus) async {
    calls++;
    if (fail) throw StateError('model failure');
    return value;
  }

  @override
  Future<void> close() async {}
}

// Pause a real directory snapshot so capture can append while its delivery is
// blocked; subsequent reads use the real current disk inventory.
class _PausedDirectory implements Directory {
  _PausedDirectory(this.source);
  final Directory source;
  final started = Completer<void>();
  final release = Completer<void>();
  bool _first = true;
  @override
  String get path => source.path;
  @override
  Stream<FileSystemEntity> list({bool recursive = false, bool followLinks = true}) async* {
    if (_first) {
      _first = false;
      final snapshot = await source.list(recursive: recursive, followLinks: followLinks).toList();
      started.complete();
      await release.future;
      yield* Stream.fromIterable(snapshot);
    } else {
      yield* source.list(recursive: recursive, followLinks: followLinks);
    }
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class RecordingWedgeMonitor extends CaptureWedgeMonitor {
  RecordingWedgeMonitor()
      : super(
            featureGate: () async => true,
            track: (_, __) {},
            bleRetry: (_) async {},
            appBuild: () => 'test',
            platform: () => 'test');
  int connected = 0;
  final List<bool> endedIntentionally = [];
  final List<bool> transcriptExpected = [];
  @override
  void setTranscriptExpected(int handle, bool expected) => transcriptExpected.add(expected);
  @override
  int onCaptureSessionConnected({required String deviceId, required String source}) => ++connected;
  @override
  void onCaptureSessionEnded(int handle, {required int binaryBytesSent, bool intentional = false}) {
    endedIntentionally.add(intentional);
  }
}

List<List<int>> readFrames(File file) {
  final bytes = file.readAsBytesSync();
  final result = <List<int>>[];
  var offset = 0;
  while (offset < bytes.length) {
    final length = ByteData.sublistView(bytes).getUint32(offset, Endian.little);
    result.add(bytes.sublist(offset + 4, offset + 4 + length));
    offset += 4 + length;
  }
  return result;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late MobileBatchBuffer buffer;
  late MobileStandardBatch lane;
  late FakeVad vad;
  late List<Wal> published;
  var clock = DateTime.utc(2026, 10, 14);
  var uid = 'owner';
  final state = ListenClientState.instance;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('mobile_standard_batch_');
    published = [];
    buffer = MobileBatchBuffer(directory: directory, publish: (wal) async => published.add(wal));
    vad = FakeVad();
    clock = DateTime.utc(2026, 10, 14);
    uid = 'owner';
    state.resetForTest();
    lane = MobileStandardBatch(
        buffer: buffer,
        loadVad: () async => vad,
        freeDiskBytes: () async => 1 << 40,
        visibility: state,
        ownerUid: () => uid,
        now: () => clock);
  });
  tearDown(() async {
    await lane.close();
    await directory.delete(recursive: true);
  });

  bool route(int value, {bool realtime = false}) =>
      lane.route([value], codec: BleAudioCodec.opus, realtimeConsumer: realtime);
  Future<void> enable() async {
    lane.authorize(true);
    await lane.pendingInitialization;
  }

  test('old servers and missing capability stay streaming', () async {
    final old = MessageServiceStatusEvent.fromJson({'type': 'service_status', 'status': 'ready'});
    lane.authorize(old.mobileStandardBatch);
    expect(route(1), false);
    expect(directory.listSync(), isEmpty);
  });

  test('hidden batch retains original speech AND silence; visible frames never replay', () async {
    await enable();
    final streamed = <int>[];
    for (final value in [0, 2, 0]) {
      if (!route(value)) streamed.add(value);
      await lane.pendingInference;
    }
    state.capturePageOpened();
    lane.visibilityChanged();
    if (!route(3)) streamed.add(3);
    state.capturePageClosed();
    if (!route(4)) streamed.add(4);
    await lane.close();
    final saved = published.expand((w) => readFrames(File('${directory.path}/${w.filePath}'))).toList();
    expect(saved, [
      [0],
      [2],
      [0],
      [4]
    ]);
    expect(streamed, [3]);
    expect(saved.expand((frame) => frame).where((v) => streamed.contains(v)), isEmpty);
  });

  test('voice command / realtime demand overrides hidden transcript', () async {
    await enable();
    expect(route(1), true);
    expect(route(2, realtime: true), false);
    await buffer.pending;
    expect(published.single.totalFrames, 1);
  });

  test('UID change, lease expiry and server rollback return to stream', () async {
    await enable();
    expect(route(1), true);
    uid = 'other';
    expect(route(2), false);
    uid = 'owner';
    clock = clock.add(const Duration(minutes: 2));
    expect(route(3), false);
    lane.authorize(false);
    expect(route(4), false);
  });

  test('model errors return to live without losing the already owned frame', () async {
    await enable();
    vad.fail = true;
    expect(route(7), true);
    await lane.pendingInference;
    expect(route(8), false);
    await buffer.pending;
    expect(readFrames(File('${directory.path}/${published.single.filePath}')), [
      [7]
    ]);
  });

  test('60 seconds of silence is still sealed and processed; no VAD discard', () async {
    await enable();
    for (var i = 0; i < 6000; i++) {
      expect(route(0), true);
      await lane.pendingInference;
    }
    await buffer.pending;
    expect(published.single.totalFrames, 6000);
    expect(published.single.seconds, 60);
    expect(File('${directory.path}/${published.single.filePath}').readAsBytesSync(),
        encodeWalFrames(List.generate(6000, (_) => [0])));
  });

  test('VAD hangover prioritizes speech at two seconds without discarding padding', () async {
    await enable();
    vad.value = 0.4;
    expect(route(1), true);
    await lane.pendingInference;
    clock = clock.add(const Duration(seconds: 2));
    vad.value = 0;
    expect(route(0), true);
    await lane.pendingInference;
    await buffer.pending;
    expect(readFrames(File('${directory.path}/${published.single.filePath}')), [
      [1],
      [0]
    ]);
  });

  test('speech is reported with its capture time, and the two-second seal does not un-report it', () async {
    final heard = <(String?, DateTime)>[];
    lane.onSpeech = (recording, at) => heard.add((recording, at));
    lane.authorize(true);
    await lane.pendingInitialization;
    vad.value = 0.9;
    final spoke = clock;
    expect(lane.route([1], codec: BleAudioCodec.opus, realtimeConsumer: false, recordingSessionId: 'rec'), true);
    await lane.pendingInference;
    vad.value = 0;
    clock = clock.add(const Duration(seconds: 3));
    expect(lane.route([2], codec: BleAudioCodec.opus, realtimeConsumer: false, recordingSessionId: 'rec'), true);
    await lane.pendingInference;
    expect(heard, [('rec', spoke)]);
  });

  test('an end report observes unregistered audio and never seals or moves a chunk boundary', () async {
    final sent = <int>[];
    final reporter = CaptureEndReporter(
      post: (signal, {required pendingWals, required sentAt}) async {
        sent.add(pendingWals);
        return true;
      },
      pendingWals: (signal) => buffer.pendingJournalCount(signal.recordingSessionId, through: signal.decidedAt),
      disabled: () async => false,
    );
    lane.authorize(true);
    await lane.pendingInitialization;
    vad.value = 0.9; // speech throughout, so the VAD's own 2 s silence seal never fires
    expect(lane.route([1], codec: BleAudioCodec.opus, realtimeConsumer: false, recordingSessionId: 'rec'), true);
    await lane.pendingInference;
    expect(await buffer.pendingJournalCount('rec'), 1);
    expect(await buffer.pendingJournalCount('other'), 0);

    // The end is reported while the final chunk is still open.
    final end = CaptureEndSignal(
        recordingSessionId: 'rec', type: CaptureEndType.userInitiated, lastSpeechAt: clock, decidedAt: clock);
    await reporter.report(end);
    expect(sent, [1], reason: 'the open chunk is pending; the marker cannot say zero');
    expect(published, isEmpty, reason: 'reporting an end sealed nothing');

    // Capture goes on untouched: the next frame lands in the same chunk.
    expect(lane.route([2], codec: BleAudioCodec.opus, realtimeConsumer: false, recordingSessionId: 'rec'), true);
    await lane.pendingInference;
    await reporter.uploadAccepted('rec');
    expect(sent, [1], reason: 'still open, still pending, nothing resent');
    expect(published, isEmpty);

    // The capture lifecycle seals; only then does the audio become a file.
    buffer.seal();
    await buffer.pending;
    expect(readFrames(File('${directory.path}/${published.single.filePath}')), [
      [1],
      [2]
    ]);
    expect(await buffer.pendingJournalCount('rec'), 0);
    await reporter.uploadAccepted('rec');
    expect(sent, [1, 0], reason: 'zero only after the final audio is registered and accepted');
  });

  test('a chunk whose publish fails stays counted as unregistered', () async {
    final failing =
        MobileBatchBuffer(directory: directory, publish: (wal) async => throw StateError('index unavailable'));
    await failing.initialize();
    expect(failing.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'), true);
    failing.seal();
    await failing.pending;
    expect(failing.failed, isTrue);
    expect(await failing.pendingJournalCount('rec'), 1, reason: 'its audio is in the journal, not the file index');
    expect(await failing.pendingJournalCount('rec', ownerUid: uid), 1);
    expect(await failing.pendingJournalCount('rec', ownerUid: 'next-account'), 0,
        reason: 'another account can never upload this journal, so it must not hold that account\'s recording open');
    await File('${directory.path}/unknown.batch-journal').writeAsString('{');
    expect(await failing.pendingJournalCount('rec', ownerUid: 'next-account'), 1,
        reason: 'a journal with unreadable ownership still counts for every account');
  });

  test('unknown-clock audio stays in the end watermark before and during a failed index publication', () async {
    final failing =
        MobileBatchBuffer(directory: directory, publish: (wal) async => throw StateError('index unavailable'));
    await failing.initialize();
    final future = DateTime.utc(2038);
    expect(failing.append([1], uid: uid, codec: BleAudioCodec.opus, now: future, recordingSessionId: 'rec'), true);
    expect(await failing.pendingJournalCount('rec', through: clock, now: clock), 1);
    expect(published, isEmpty, reason: 'the watermark must never seal or publish audio');
    failing.seal();
    await failing.pending;
    expect(await failing.pendingJournalCount('rec', through: clock, now: clock), 1);
    // If the clock is trusted, a chunk after the decided end is trailing silence.
    expect(await failing.pendingJournalCount('rec', through: clock, now: future), 0);
    expect(failing.failed, isTrue);
  });

  for (final operation in ['periodic flush', 'write']) {
    test('append $operation failure retains earlier accepted audio in the disk count', () async {
      late FaultingWalWriter writer;
      final broken = MobileBatchBuffer(
          directory: directory,
          publish: (_) async => fail('failed append must not publish'),
          openWriter: (file) => writer = FaultingWalWriter(file));
      await broken.initialize();
      expect(broken.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'), true);
      if (operation == 'periodic flush') {
        for (var i = 1; i < BleAudioCodec.opus.getFramesPerSecond() - 1; i++) {
          expect(broken.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'), true);
        }
        writer.failFlush = true;
      } else {
        writer.failWrite = true;
      }
      expect(broken.append([2], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'),
          operation == 'periodic flush');
      expect(broken.failed, isTrue);
      expect(broken.hasFrames, isFalse);
      expect(await broken.pendingJournalCount('rec'), 1);
      final fresh = MobileBatchBuffer(directory: directory, publish: (_) async {});
      expect(await fresh.pendingJournalCount('rec'), 1);
      expect(await MobileBatchBuffer.recover(directory, []), hasLength(1));
    });
  }

  test('process loss before seal and journal replay retain pending evidence without a memory set', () async {
    await buffer.initialize();
    expect(buffer.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'), true);
    final fresh = MobileBatchBuffer(directory: directory, publish: (_) async {});
    expect(await fresh.pendingJournalCount('rec'), 1);
    final recovered = await MobileBatchBuffer.recover(directory, []);
    expect(recovered.single.recordingSessionId, 'rec');
    expect(await fresh.pendingJournalCount('rec'), 1, reason: 'replay does not erase the retained journal');
    expect(
        await fresh.pendingJournalCount('rec',
            acceptedFileBytes: {recovered.single.filePath!: recovered.single.storageTotalBytes}),
        0);
    expect(buffer.append([2], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'), true);
    expect(
        await fresh.pendingJournalCount('rec',
            acceptedFileBytes: {recovered.single.filePath!: recovered.single.storageTotalBytes}),
        1,
        reason: 'acceptance of a prefix cannot hide a later append to the replayed journal');
    expect(await fresh.pendingJournalCount('other'), 0);
    expect(published, isEmpty, reason: 'the observer never seals or publishes');
  });

  test('unreadable journal metadata over-counts and unreadable directory omits the end marker', () async {
    await File('${directory.path}/unknown.batch-journal').writeAsString('{');
    expect(await buffer.pendingJournalCount('rec'), 1);
    final missing = MobileBatchBuffer(directory: Directory('${directory.path}/unavailable'), publish: (_) async {});
    final sent = <int>[];
    final reporter = CaptureEndReporter(
        post: (signal, {required pendingWals, required sentAt}) async {
          sent.add(pendingWals);
          return true;
        },
        pendingWals: (_) => missing.pendingJournalCount('rec'),
        disabled: () async => false);
    await reporter.report(CaptureEndSignal(
        recordingSessionId: 'rec', type: CaptureEndType.userInitiated, lastSpeechAt: clock, decidedAt: clock));
    expect(sent, isEmpty, reason: 'an unknown disk inventory cannot assert zero');
    await missing.initialize();
    await reporter.uploadAccepted('rec');
    expect(sent, [0], reason: 'a later successful observation can clear the end');
  });

  test('an append during an empty directory snapshot defers the marker instead of reporting zero', () async {
    final paused = _PausedDirectory(directory);
    final observer = MobileBatchBuffer(directory: paused, publish: (_) async {});
    final sent = <int>[];
    final reporter = CaptureEndReporter(
        post: (signal, {required pendingWals, required sentAt}) async {
          sent.add(pendingWals);
          return true;
        },
        pendingWals: (_) => observer.pendingJournalCount('rec'),
        observationVersion: () => MobileBatchBuffer.journalRevision,
        disabled: () async => false);
    final reporting = reporter.report(CaptureEndSignal(
        recordingSessionId: 'rec', type: CaptureEndType.userInitiated, lastSpeechAt: clock, decidedAt: clock));
    await paused.started.future;
    expect(buffer.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'rec'), true);
    paused.release.complete();
    await reporting;
    expect(sent, isEmpty);
    await reporter.uploadAccepted('rec');
    expect(sent, [1]);
    await buffer.close();
    await reporter.uploadAccepted('rec');
    expect(sent, [1, 0]);
  });

  test('bounded capacity preserves backlog and refuses new batch admission', () async {
    final tiny = MobileBatchBuffer(directory: directory, maxBytes: 5, publish: (wal) async => published.add(wal));
    await tiny.initialize();
    expect(tiny.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock), true);
    expect(tiny.append([2], uid: uid, codec: BleAudioCodec.opus, now: clock), false);
    await tiny.close();
    expect(readFrames(File('${directory.path}/${published.single.filePath}')), [
      [1]
    ]);
  });

  test('file limit is rechecked after a recording-origin handoff', () async {
    final tiny = MobileBatchBuffer(directory: directory, maxFiles: 1, publish: (wal) async => published.add(wal));
    await tiny.initialize();
    expect(tiny.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'first'), true);
    expect(tiny.append([2], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'second'), false);
    await tiny.close();
    expect(published.single.recordingSessionId, 'first');
    expect(readFrames(File('${directory.path}/${published.single.filePath}')), [
      [1]
    ]);
  });

  test('retained torn originals consume the batch admission budget', () async {
    final original = File('${directory.path}/audio_omimobilebatchretained.bin.torn');
    await original.writeAsBytes(List.filled(8, 7));
    final tiny = MobileBatchBuffer(directory: directory, maxBytes: 8, publish: (wal) async => published.add(wal));
    await tiny.initialize();
    expect(tiny.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock), false);
    await tiny.close();
    expect(await original.readAsBytes(), List.filled(8, 7));
    expect(published, isEmpty);
  });

  test('restart recovers writes missing from shared WAL index and never duplicates indexed files', () async {
    await enable();
    expect(route(1), true);
    await lane.pendingInference;
    final recovered = await MobileBatchBuffer.recover(directory, []); // fresh objects, no in-memory WAL
    expect(recovered.single.totalFrames, 1);
    expect(recovered.single.ownerUid, 'owner');
    final again = await MobileBatchBuffer.recover(directory, recovered);
    expect(again.length, 1);
    expect(again.single.status, WalStatus.miss);
  });

  test('batch files preserve recording origin and cannot disable stream repair evidence', () async {
    final batch = Wal(
        timerStart: 1001,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 50,
        recordingSessionId: 'origin',
        filePath: 'audio_omimobilebatch001_opus_16000_1_fs160_1001.75.bin');
    final live = Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        recordingSessionId: 'origin',
        filePath: 'audio_omi_opus_16000_1_fs160_1000.bin');
    expect(nextSyncUploadBatch([live, batch], 1002), [batch]);
    expect(nextSyncUploadBatch([live], 1002), [live]);
    final bounds = syncUploadAudioBounds([batch]);
    expect(bounds.start, 1001.75);
    expect(bounds.end, 1002.25);
    await buffer.initialize();
    expect(buffer.append([1], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'first'), true);
    expect(buffer.append([2], uid: uid, codec: BleAudioCodec.opus, now: clock, recordingSessionId: 'second'), true);
    await buffer.close();
    expect(published.map((w) => w.recordingSessionId), ['first', 'second']);
  });

  test('corrupt journal cannot strand another owner-stamped recovered recording', () async {
    await enable();
    expect(route(1), true);
    await lane.pendingInference;
    await File('${directory.path}/bad.batch-journal').writeAsString('{"owner_uid":false}');
    final recovered = await MobileBatchBuffer.recover(directory, []);
    expect(recovered.single.totalFrames, 1);
  });

  test('unknown free space refuses batching before model load', () async {
    var loads = 0;
    final unavailable = MobileStandardBatch(
        buffer: buffer,
        loadVad: () async {
          loads++;
          return vad;
        },
        freeDiskBytes: () async => null,
        visibility: state,
        ownerUid: () => uid,
        now: () => clock);
    unavailable.authorize(true);
    await unavailable.pendingInitialization;
    expect(unavailable.route([1], codec: BleAudioCodec.opus, realtimeConsumer: false), false);
    expect(loads, 0);
    await unavailable.close();
  });

  test('failed index publish retains the journal for restart/retry', () async {
    final broken = MobileBatchBuffer(directory: directory, publish: (_) async => throw StateError('index unavailable'));
    await broken.initialize();
    expect(broken.append([9], uid: uid, codec: BleAudioCodec.opus, now: clock), true);
    await broken.close();
    expect(broken.failed, true);
    final recovered = await MobileBatchBuffer.recover(directory, []);
    expect(readFrames(File('${directory.path}/${recovered.single.filePath}')), [
      [9]
    ]);
  });

  test('real pendant controller selects exactly one WAL / socket owner per packet', () async {
    final monitor = RecordingWedgeMonitor();
    final world = await CaptureReplayWorld.boot(
        tempDir: directory,
        pendantCodec: BleAudioCodec.opus,
        initialPrefs: {'uid': 'owner'},
        captureWedgeMonitor: monitor);
    world.deviceConnection = ScriptedDeviceConnection();
    world.controller.installMobileStandardBatch(lane);
    try {
      await world.controller
          .streamDeviceRecording(device: BtDevice(id: 'omi', name: 'Omi', type: DeviceType.omi, rssi: -40));
      await world.settle();
      world.socket!.emitServerMessage('{"type":"service_status","status":"ready","mobile_standard_batch":true}');
      await lane.pendingInitialization;
      final endedBeforeBatch = monitor.endedIntentionally.length;
      world.deviceConnection!.emitAudio(value: 7);
      await world.settle();
      await lane.pendingInference;
      expect(monitor.endedIntentionally.length, endedBeforeBatch);
      expect(monitor.transcriptExpected.last, false);
      final startsDuringBatch = monitor.connected;
      expect(world.socket!.sentBinary, isEmpty);
      expect(world.wal.syncs.phone.testFrames, isEmpty);
      state.capturePageOpened();
      world.deviceConnection!.emitAudio(value: 8);
      await world.settle();
      await buffer.pending;
      expect(monitor.connected, startsDuringBatch);
      expect(monitor.transcriptExpected.last, true);
      expect(world.socket!.sentBinary.single, List.filled(80, 8));
      expect(world.wal.syncs.phone.testFrames.single.payload, List.filled(80, 8));
      expect(readFrames(File('${directory.path}/${published.single.filePath}')), [List.filled(80, 7)]);
    } finally {
      await world.dispose();
      monitor.dispose();
    }
  });

  test('phone-only overflow wins over an unexpired Standard batch authorization', () async {
    final previous = OnDeviceTranscriptionController.instance;
    final onPhone = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), manageNativeCustody: false);
    onPhone.debugActivate();
    onPhone.updateEntitlement(atCap: true, paid: true);
    OnDeviceTranscriptionController.instance = onPhone;
    final world = await CaptureReplayWorld.boot(
        tempDir: directory, pendantCodec: BleAudioCodec.opus, initialPrefs: {'uid': 'owner'});
    world.deviceConnection = ScriptedDeviceConnection();
    world.controller.installMobileStandardBatch(lane);
    try {
      await world.controller
          .streamDeviceRecording(device: BtDevice(id: 'omi', name: 'Omi', type: DeviceType.omi, rssi: -40));
      await world.settle();
      world.socket!.emitServerMessage('{"type":"service_status","status":"ready","mobile_standard_batch":true}');
      await lane.pendingInitialization;
      world.deviceConnection!.emitAudio(value: 9);
      await world.settle();
      await buffer.pending;
      expect(world.socket!.sentBinary, isEmpty);
      expect(published, isEmpty);
      expect(world.wal.syncs.phone.testFrames.single.payload, List.filled(80, 9));
    } finally {
      await world.dispose();
      onPhone.dispose();
      OnDeviceTranscriptionController.instance = previous;
    }
  });

  test('local-preview grant ignores transcript visibility; ordinary grant keeps the visibility rule', () async {
    lane.authorize(true, localPreview: true);
    expect(lane.warmingUp, true);
    await lane.pendingInitialization;
    expect(lane.warmingUp, false);
    state.capturePageOpened();
    expect(state.value.transcriptVisible, true);
    expect(route(1), true, reason: 'visible audio still journals in local-preview mode');
    await lane.pendingInference;
    lane.visibilityChanged();
    expect(route(2), true);
    await lane.pendingInference;
    lane.authorize(true);
    expect(lane.localPreview, false);
    expect(route(3), false, reason: 'ordinary Standard batch hands visible audio back to live');
    lane.authorize(false, localPreview: true);
    expect(lane.localPreview, false, reason: 'a revoked grant is never a local-preview grant');
    clock = clock.add(const Duration(minutes: 3));
    lane.authorize(true, localPreview: true);
    clock = clock.add(const Duration(minutes: 2));
    expect(route(4), false, reason: 'same two-minute expiry as any authorization');
  });

  testWidgets('existing visibility signal drives foreground/background routing', (tester) async {
    await tester.runAsync(() async {
      await enable();
      state.capturePageOpened();
      expect(route(1), false);
      state.onLifecycle(AppLifecycleState.paused);
      expect(route(2), true);
      await lane.pendingInference;
      state.onLifecycle(AppLifecycleState.resumed);
      expect(route(3), false);
      await lane.close();
    });
  });
}
