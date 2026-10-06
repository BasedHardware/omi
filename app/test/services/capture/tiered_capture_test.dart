import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  Future<void> connect() async {
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('tiered_capture_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    await connect();
  });
  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  test('default 120 second deadline pauses BLE and socket, finalizes once, and stays paused on reconnect', () async {
    final socket = world.socket!;
    await world.elapse(const Duration(seconds: 119));
    expect(world.controller.isPaused, false);
    await world.elapse(const Duration(seconds: 1));
    expect(world.controller.silencePaused, true);
    expect(world.controller.isPaused, true);
    expect(socket.closeCalls, 1);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
    expect(world.processCalls, 1);
    final sockets = world.sockets.length;
    world.controller.updateRecordingDevice(null);
    await world.settle();
    await connect();
    await world.controller.streamDeviceRecording(); // Home's check-only start
    await world.elapse(const Duration(seconds: 150));
    expect(world.controller.isPaused, true);
    expect(world.sockets.length, sockets);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
  });

  test('speech resets the configured deadline, audio packets do not', () async {
    SharedPreferencesUtil().conversationSilenceDuration = 30;
    await connect();
    await world.elapse(const Duration(seconds: 20));
    world.controller.onSegmentReceived([
      TranscriptSegment(
          id: 'speech',
          text: 'hello',
          speaker: 'SPEAKER_0',
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: []),
    ]);
    await world.settle();
    await world.elapse(const Duration(seconds: 20));
    expect(world.controller.isPaused, false);
    world.deviceConnection!.emitAudio();
    await world.elapse(const Duration(seconds: 10));
    expect(world.controller.silencePaused, true);
  });

  for (final charging in [false, true]) {
    test('${charging ? 'charging' : 'foreground'} resumes silence as a fresh session but respects manual mute',
        () async {
      await world.elapse(const Duration(seconds: 120));
      final recording = world.controller.activeRecordingId;
      final sockets = world.sockets.length;
      if (charging) {
        world.controller.onChargingStarted();
      } else {
        world.controller.onAppResumed();
      }
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.isPaused, false);
      expect(world.controller.silencePaused, false);
      expect(world.controller.activeRecordingId, isNot(recording));
      expect(world.sockets.length, sockets + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      await world.controller.pauseCapture();
      world.controller.onChargingStarted();
      world.controller.onAppResumed();
      await world.settle();
      expect(world.controller.isPaused, true);
      expect(world.sockets.length, sockets + 1);
    });
  }

  test('manual pause takes over silence reason and prevents auto resume', () async {
    await world.elapse(const Duration(seconds: 120));
    await world.controller.pauseCapture();
    expect(world.controller.silencePaused, false);
    await world.controller.resumeAfterSilence();
    expect(world.controller.isPaused, true);
  });

  test('late transcript delivery cannot reopen an expired capture', () async {
    await world.elapse(const Duration(seconds: 120));
    await world.controller.pendingSourceSwitch;
    world.controller.onSegmentReceived([
      TranscriptSegment(
          id: 'late',
          text: 'still speaking',
          speaker: null,
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: []),
    ]);
    await world.settle();
    expect(world.controller.isPaused, true);
  });
}
