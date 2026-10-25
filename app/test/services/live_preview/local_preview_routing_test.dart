import 'dart:async';
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
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';
import '../../support/live_preview_fakes.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

class _Vad implements MobileBatchVad {
  static bool fail = false;
  @override
  Future<double> probability(List<int> opus) async {
    if (fail) throw StateError('model failure');
    return 0;
  }

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
  Completer<void>? vadGate;

  late List<RegisteredEvent> telemetry;
  LivePreviewController preview({bool allowed = true}) => LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: telemetry.add),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        decodeOpus: (opus) => Int16List(opus.length * 4),
        requestAllowed: () async => allowed,
        feedChunkBytes: 640,
      );

  Future<void> boot({
    LivePreviewController? livePreview,
    BleAudioCodec codec = BleAudioCodec.opus,
    DeviceType type = DeviceType.omi,
    Map<String, Object> prefs = const {},
  }) async {
    world = await CaptureReplayWorld.boot(
        tempDir: directory, pendantCodec: codec, initialPrefs: {'uid': 'owner', ...prefs});
    world.deviceConnection = ScriptedDeviceConnection();
    world.controller.installMobileStandardBatch(lane);
    if (livePreview != null) world.controller.installLivePreview(livePreview);
    await world.controller.streamDeviceRecording(device: BtDevice(id: 'omi', name: 'Omi', type: type, rssi: -40));
    await world.settle();
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('local_preview_routing_');
    published = [];
    state.resetForTest();
    buffer = MobileBatchBuffer(directory: directory, publish: (wal) async => published.add(wal));
    lane = MobileStandardBatch(
        buffer: buffer,
        loadVad: () async {
          await vadGate?.future;
          return _Vad();
        },
        freeDiskBytes: () async => 1 << 40,
        visibility: state,
        ownerUid: () => 'owner',
        now: DateTime.now);
    engine = FakeLivePreviewEngine();
    vadGate = null;
    telemetry = [];
    _Vad.fail = false;
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

    // A transient refusal (the journal's model fails) falls through to WAL +
    // socket exactly as today, and the grant stands.
    _Vad.fail = true;
    world.deviceConnection!.emitAudio(value: 10);
    await world.settle();
    await lane.pendingInference;
    world.deviceConnection!.emitAudio(value: 9);
    await world.settle();
    await buffer.pending;
    expect(world.controller.localPreviewAdmitted, true);
    expect(world.socket!.sentBinary.single, List.filled(80, 9));
    expect(world.wal.syncs.phone.testFrames.last.payload, List.filled(80, 9));
    expect(_frames(File('${directory.path}/${published.single.filePath}')),
        [List.filled(80, 7), List.filled(80, 8), List.filled(80, 10)]);

    // The preview received a decoded copy of every pendant packet it saw.
    expect(engine.fed, isNotEmpty);
    expect(world.controller.segments, isEmpty, reason: 'preview text never enters capture segments');
  });

  test('a per-session gate flipping mid-session drops the grant for the rest of the socket', () async {
    final live = preview();
    await boot(livePreview: live);
    world.socket!.emitServerMessage(_admitted);
    await lane.pendingInitialization;
    await world.settle();
    expect(world.controller.localPreviewAdmitted, true);
    state.capturePageOpened();
    SharedPreferencesUtil().autoSyncOfflineRecordings = false;
    world.deviceConnection!.emitAudio(value: 5);
    await world.settle();
    expect(world.controller.localPreviewAdmitted, false, reason: 'the preview hides; today\'s cloud view returns');
    expect(live.phase, LivePreviewPhase.inactive);
    expect(lane.localPreview, false);
    expect(world.socket!.sentBinary.single, List.filled(80, 5));
    final refused = telemetry.whereType<LivePreviewNotRequested>().single.properties;
    expect(refused, {'reason': 'auto_sync_off', 'mid_session': true});
    // A renewed grant on the same socket never re-admits it.
    SharedPreferencesUtil().autoSyncOfflineRecordings = true;
    world.socket!.emitServerMessage(_admitted.replaceFirst('"ready"', '"mobile_batch_admission"'));
    await world.settle();
    expect(world.controller.localPreviewAdmitted, false);
  });

  for (final (name, codec, type, prefs, reason) in [
    ('not an Omi pendant', BleAudioCodec.opus, DeviceType.friendPendant, <String, Object>{}, 'device_unsupported'),
    ('not an Opus codec', BleAudioCodec.pcm16, DeviceType.omi, <String, Object>{}, 'codec_unsupported'),
    (
      'auto-sync off',
      BleAudioCodec.opus,
      DeviceType.omi,
      <String, Object>{'autoSyncOfflineRecordings': false},
      'auto_sync_off'
    ),
  ]) {
    test('$name: local_preview is not requested and the reason is reported', () async {
      await boot(livePreview: preview(), codec: codec, type: type, prefs: prefs);
      expect(world.localPreviewRequests.last, false);
      expect(
          telemetry.whereType<LivePreviewNotRequested>().single.properties, {'reason': reason, 'mid_session': false});
      world.deviceConnection!.emitAudio(value: 2);
      await world.settle();
      expect(world.socket!.sentBinary, isNotEmpty, reason: 'today\'s streaming, no hold');
    });
  }

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

  test('a refusal streams the frames held before it, in order, then live frames', () async {
    final live = preview();
    await boot(livePreview: live);
    world.deviceConnection!.emitAudio(value: 1);
    world.deviceConnection!.emitAudio(value: 2);
    await world.settle();
    expect(world.socket!.sentBinary, isEmpty);
    world.socket!.emitServerMessage(_batchOnly);
    await world.settle();
    expect(world.socket!.sentBinary, [List.filled(80, 1), List.filled(80, 2)]);
    state.capturePageOpened();
    world.deviceConnection!.emitAudio(value: 3);
    await world.settle();
    expect(world.socket!.sentBinary, [List.filled(80, 1), List.filled(80, 2), List.filled(80, 3)]);
    expect(world.wal.syncs.phone.testFrames.map((frame) => frame.payload.first), [1, 2, 3]);
    expect(live.phase, LivePreviewPhase.inactive);
    final verdict = telemetry.whereType<LivePreviewVerdict>().single.properties;
    expect([verdict['verdict'], verdict['platform'], verdict['held_frames'], verdict['hold_timeout_replayed']],
        ['refused', 'ios', 2, false]);
  });

  test('socket close before the verdict: held frames are replayed to the replacement socket on refusal', () async {
    await boot(livePreview: preview());
    final first = world.socket!;
    world.deviceConnection!.emitAudio(value: 1);
    world.deviceConnection!.emitAudio(value: 2);
    await world.settle();
    first.emitClose(1006);
    await world.settle();
    await world.elapse(const Duration(seconds: 16));
    final second = world.socket!;
    expect(second, isNot(same(first)));
    expect(world.localPreviewRequests.last, true);
    world.deviceConnection!.emitAudio(value: 3);
    await world.settle();
    expect(first.sentBinary, isEmpty);
    expect(second.sentBinary, isEmpty);
    second.emitServerMessage(_batchOnly);
    await world.settle();
    expect(second.sentBinary, [List.filled(80, 1), List.filled(80, 2), List.filled(80, 3)],
        reason: 'live-transcript continuity across the reconnect, oldest first');
  });

  test('never-sent frames (warm-up, pre-verdict) stay in the safety WAL and upload through sync', () async {
    // No ConversationEvent ever confirms an admitted session, so its safety
    // WAL is unconfirmed: the ordinary recovery drain uploads it
    // (/v2/sync-local-files -> batch record), like any frame the socket never got.
    vadGate = Completer<void>();
    await boot(livePreview: preview());
    world.deviceConnection!.emitAudio(value: 1); // pre-verdict
    await world.settle();
    world.socket!.emitServerMessage(_admitted);
    await world.settle();
    expect(lane.warmingUp, true);
    world.deviceConnection!.emitAudio(value: 2); // journal still warming up
    await world.settle();
    vadGate!.complete();
    await lane.pendingInitialization;
    world.deviceConnection!.emitAudio(value: 3); // journaled
    await world.settle();
    await buffer.pending;
    expect(world.socket!.sentBinary, isEmpty, reason: 'nothing opens the deferred cloud stream');
    expect(world.wal.syncs.phone.testFrames.map((frame) => frame.payload.first), [1, 2]);

    await world.wal.syncs.phone.finalizeCurrentSession();
    await world.settle();
    final missing = await world.wal.syncs.phone.getMissingWals();
    expect(missing.fold<int>(0, (sum, wal) => sum + wal.totalFrames), 2, reason: 'unconfirmed, so pending upload');
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));
    expect((await world.walCounts())[WalStatus.synced], 1);
  });

  test('WAL refused (storage blocked) during the pre-verdict hold: frames reach the socket, in order', () async {
    await boot(livePreview: preview());
    world.deviceConnection!.emitAudio(value: 1); // WAL-accepted: held
    await world.settle();
    expect(world.socket!.sentBinary, isEmpty);
    world.wal.syncs.phone.debugRefusePendantFrames = true;
    world.deviceConnection!.emitAudio(value: 2); // WAL refused: no custody, so never held
    await world.settle();
    expect(world.socket!.sentBinary, [List.filled(80, 1), List.filled(80, 2)]);
    expect(world.wal.syncs.phone.testFrames.map((frame) => frame.payload.first), [1]);
  });

  test('WAL refused during journal warm-up: the frame reaches the socket instead of vanishing', () async {
    vadGate = Completer<void>();
    await boot(livePreview: preview());
    world.socket!.emitServerMessage(_admitted);
    await world.settle();
    expect(lane.warmingUp, true);
    world.deviceConnection!.emitAudio(value: 3); // warm-up, WAL kept it: off the socket
    await world.settle();
    world.wal.syncs.phone.debugRefusePendantFrames = true;
    world.deviceConnection!.emitAudio(value: 4); // warm-up, WAL refused: to the socket
    await world.settle();
    expect(world.socket!.sentBinary, [List.filled(80, 4)]);
    expect(world.wal.syncs.phone.testFrames.map((frame) => frame.payload.first), [3]);
    vadGate!.complete();
    await lane.pendingInitialization;
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
