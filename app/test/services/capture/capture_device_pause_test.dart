import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_pause_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  });
  tearDown(() async {
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  for (final deviceControl in [false, true]) {
    test('pendant pause closes socket and resume opens it (device control: $deviceControl)', () async {
      final socket = world.socket!;
      if (deviceControl) {
        await world.controller.pauseDeviceRecording();
      } else {
        await world.controller.pauseCapture();
      }
      await world.settle();
      expect(socket.closeCalls, 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 0);
      expect(world.controller.keepAliveScheduledForTesting, false);
      final count = world.sockets.length;
      await world.controller.onTranscriptionSettingsChanged();
      await world.controller.changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16);
      await world.controller.streamDeviceRecording(device: pendant);
      await world.elapse(const Duration(seconds: 30));
      expect(world.sockets.length, count);
      expect(world.controller.isPaused, true);
      await world.controller.resumeDeviceRecording();
      await world.settle();
      expect(world.sockets.length, count + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
    });
  }
}
