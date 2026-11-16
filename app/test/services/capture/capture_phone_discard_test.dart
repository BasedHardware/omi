// Undo on Home's recording bar (David, 2026-11-16): a phone recording discarded in its first
// seconds keeps nothing. Nothing is processed, no audio is left for offline sync, the server's copy
// is deleted, and a pendant the phone took over from resumes.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_phone_discard_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    CaptureController.discardDeleteRetryDelays = CaptureController.defaultDiscardDeleteRetryDelays;
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<int> startPhone() async {
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    return world.hostApi.lastStartSessionId!;
  }

  Future<List<String?>> walRecordings() async =>
      (await world.wal.syncs.phone.getAllWals()).map((w) => w.recordingSessionId).toList();

  test('a discarded phone recording is not processed, leaves no audio, and its server copy is deleted', () async {
    final session = await startPhone();
    world.injectAudioFrames(120, sessionId: session);
    await world.settle();
    final c = world.controller;
    final recording = c.activeRecordingId;
    expect(recording, isNotNull);

    expect(await c.discardPhoneRecording(), isTrue);
    await world.settle();
    await c.pendingDiscardDeletes;

    expect(world.processCalls, 0, reason: 'a discard is never processed');
    expect(c.recordingState, RecordingState.stop);
    expect(c.liveCaptureSource, isNull);
    expect(c.isPaused, isFalse, reason: 'the next recording must not start paused');
    expect(c.segments, isEmpty);
    expect(await walRecordings(), isNot(contains(recording)), reason: 'offline sync must not resurrect it');
    expect(world.discardDeletes, [recording]);
  });

  test('a pendant the phone took over from resumes after the discard', () async {
    final link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    await startPhone();
    await world.controller.pendingSourceSwitch;
    await world.settle();
    final processedForTakeover = world.processCalls;

    await world.controller.discardPhoneRecording();
    await world.settle();

    expect(world.controller.recordingState, RecordingState.deviceRecord);
    expect(link.openAudioSubscriptions, 1);
    expect(world.processCalls, processedForTakeover, reason: 'the discarded phone recording is not processed');
  });

  test('a failed server delete is retried until it lands', () async {
    CaptureController.discardDeleteRetryDelays = const [Duration.zero, Duration.zero, Duration.zero];
    var failures = 2;
    world.deleteDiscardedResult = (_) => failures-- <= 0;
    await startPhone();
    final recording = world.controller.activeRecordingId;

    await world.controller.discardPhoneRecording();
    await world.controller.pendingDiscardDeletes;

    expect(world.discardDeletes, [recording, recording, recording]);
  });

  test('Transcribe Later and an idle phone have nothing to discard', () async {
    expect(await world.controller.discardPhoneRecording(), isFalse);
    await world.startBatchCapture();
    expect(await world.controller.discardPhoneRecording(), isFalse);
    expect(world.controller.isPhoneMicBatchRecording, isTrue);
    expect(world.discardDeletes, isEmpty);
  });
}
