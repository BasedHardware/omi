import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';
import 'package:omi/services/wals/mobile_standard_batch.dart';
import 'package:omi/services/wals/wal.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';
import '../../support/live_preview_fakes.dart';

class _Vad implements MobileBatchVad {
  @override
  Future<double> probability(List<int> opus) async => 0;

  @override
  Future<void> close() async {}
}

List<List<int>> _frames(File file) {
  final bytes = file.readAsBytesSync();
  final frames = <List<int>>[];
  var offset = 0;
  while (offset < bytes.length) {
    final length = ByteData.sublistView(bytes).getUint32(offset, Endian.little);
    frames.add(bytes.sublist(offset + 4, offset + 4 + length));
    offset += 4 + length;
  }
  return frames;
}

const _admitted = '{"type":"service_status","status":"ready","mobile_standard_batch":true,"local_preview":true}';
const _batchOnly = '{"type":"service_status","status":"ready","mobile_standard_batch":true}';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final state = ListenClientState.instance;
  late Directory directory;
  late MobileBatchBuffer buffer;
  late MobileStandardBatch lane;
  late List<Wal> published;
  late FakeLivePreviewEngine engine;
  late CaptureReplayWorld world;

  LivePreviewController preview({bool allowed = true}) => LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        decodeOpus: (opus) => Int16List(opus.length * 4),
        requestAllowed: () async => allowed,
        feedChunkBytes: 640,
      );

  Future<void> boot({LivePreviewController? livePreview}) async {
    world = await CaptureReplayWorld.boot(
        tempDir: directory, pendantCodec: BleAudioCodec.opus, initialPrefs: {'uid': 'owner'});
    world.deviceConnection = ScriptedDeviceConnection();
    world.controller.installMobileStandardBatch(lane);
    if (livePreview != null) world.controller.installLivePreview(livePreview);
    await world.controller
        .streamDeviceRecording(device: BtDevice(id: 'omi', name: 'Omi', type: DeviceType.omi, rssi: -40));
    await world.settle();
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('local_preview_routing_');
    published = [];
    state.resetForTest();
    buffer = MobileBatchBuffer(directory: directory, publish: (wal) async => published.add(wal));
    lane = MobileStandardBatch(
        buffer: buffer,
        loadVad: () async => _Vad(),
        freeDiskBytes: () async => 1 << 40,
        visibility: state,
        ownerUid: () => 'owner',
        now: DateTime.now);
    engine = FakeLivePreviewEngine();
  });

  tearDown(() async {
    await world.dispose();
    await lane.close();
    state.resetForTest();
    await directory.delete(recursive: true);
  });

  test('admitted: visible and voice-command frames journal; refused frames still reach WAL and socket', () async {
    final live = preview();
    await boot(livePreview: live);
    expect(world.localPreviewRequests.last, true, reason: 'iOS client declares local_preview=enabled');

    // Before the verdict a local-preview socket gets no audio (that would open
    // the deferred cloud stream); the ordinary safety WAL still keeps it.
    world.deviceConnection!.emitAudio(value: 6);
    await world.settle();
    expect(world.socket!.sentBinary, isEmpty);
    expect(world.wal.syncs.phone.testFrames.map((frame) => frame.payload.first), [6]);

    world.socket!.emitServerMessage(_admitted);
    await lane.pendingInitialization;
    await world.settle();
    expect(world.controller.localPreviewAdmitted, true);
    expect(live.phase, LivePreviewPhase.streaming);
    expect(lane.localPreview, true);

    // On screen: ordinary Standard batch would hand this back to live STT.
    state.capturePageOpened();
    world.deviceConnection!.emitAudio(value: 7);
    // Voice command audio is copied for the command and still journaled.
    world.controller.debugArmVoiceCommandTimeout('omi');
    world.deviceConnection!.emitAudio(value: 8);
    await world.settle();
    await lane.pendingInference;
    expect(world.socket!.sentBinary, isEmpty);
    expect(world.wal.syncs.phone.testFrames.length, 1, reason: 'journaled frames never enter the safety WAL');

    // A frame the journal refuses (here: auto-sync off is a realtime consumer)
    // falls through to WAL + socket exactly as today.
    SharedPreferencesUtil().autoSyncOfflineRecordings = false;
    world.deviceConnection!.emitAudio(value: 9);
    await world.settle();
    await buffer.pending;
    expect(world.socket!.sentBinary.single, List.filled(80, 9));
    expect(world.wal.syncs.phone.testFrames.last.payload, List.filled(80, 9));
    expect(_frames(File('${directory.path}/${published.single.filePath}')), [List.filled(80, 7), List.filled(80, 8)]);

    // The preview received a decoded copy of every pendant packet it saw.
    expect(engine.fed, isNotEmpty);
    expect(world.controller.segments, isEmpty, reason: 'preview text never enters capture segments');
  });

  test('socket close revokes admission until the server grants it again', () async {
    final live = preview();
    await boot(livePreview: live);
    world.socket!.emitServerMessage(_admitted);
    await lane.pendingInitialization;
    await world.settle();
    expect(world.controller.localPreviewAdmitted, true);
    world.controller.onClosed(1006);
    expect(world.controller.localPreviewAdmitted, false);
    expect(live.phase, LivePreviewPhase.inactive);
    expect(lane.localPreview, false);
  });

  test('a server without local_preview keeps today: visible frames stream, no preview', () async {
    final live = preview();
    await boot(livePreview: live);
    world.socket!.emitServerMessage(_batchOnly);
    await lane.pendingInitialization;
    await world.settle();
    expect(world.controller.localPreviewAdmitted, false);
    expect(live.phase, LivePreviewPhase.inactive);
    state.capturePageOpened();
    world.deviceConnection!.emitAudio(value: 4);
    await world.settle();
    expect(world.socket!.sentBinary.single, List.filled(80, 4));
    expect(engine.startedLanguages, isEmpty);
  });

  test('kill switch or no preview engine on this platform: local_preview is never declared', () async {
    await boot(livePreview: preview(allowed: false));
    expect(world.localPreviewRequests.last, false);
    await world.dispose();
    await boot();
    expect(world.localPreviewRequests.last, false);
    world.socket!.emitServerMessage(_admitted);
    await world.settle();
    expect(world.controller.localPreviewAdmitted, false, reason: 'a grant to a socket that did not ask is ignored');
  });

  test('audio taps are multicast: onboarding keeps its slot and listeners get the same packet', () async {
    await boot();
    final onboarding = <List<int>>[];
    final extra = <List<int>>[];
    void listener(List<int> packet) => extra.add(packet);
    world.controller.deviceAudioTap = onboarding.add;
    world.controller.addDeviceAudioListener(listener);
    world.deviceConnection!.emitAudio(value: 3, payloadLength: 4);
    await world.settle();
    expect(onboarding.single, [0, 0, 0, 3, 3, 3, 3]);
    expect(extra.single, [0, 0, 0, 3, 3, 3, 3]);
    world.controller.removeDeviceAudioListener(listener);
    world.controller.deviceAudioTap = null;
    world.deviceConnection!.emitAudio(value: 2, payloadLength: 4);
    await world.settle();
    expect(onboarding.length, 1);
    expect(extra.length, 1);
  });
}
