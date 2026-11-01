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
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import '../../support/on_device_fakes.dart';
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
