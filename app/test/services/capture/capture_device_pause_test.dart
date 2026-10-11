import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  bool rejectMuteWrite = false;
  final muteWrites = <bool>[];

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_pause_');
    rejectMuteWrite = false;
    muteWrites.clear();
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      deviceMuteWriter: (id, muted) async {
        expect(id, pendant.id);
        // The pendant must acknowledge before the app claims the new state.
        expect(SharedPreferencesUtil().capturePolicy.muted, !muted);
        if (rejectMuteWrite) throw StateError('pendant refused mute');
        muteWrites.add(muted);
      },
    );
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
      expect(muteWrites, [true]);
      await world.controller.resumeDeviceRecording();
      await world.settle();
      expect(world.sockets.length, count + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      expect(muteWrites, [true, false]);
    });
  }

  test('device pause failure reaches the UI caller without confirming pause', () async {
    rejectMuteWrite = true;
    await expectLater(world.controller.pauseCapture(), throwsStateError);
    expect(muteWrites, isEmpty);
    expect(world.controller.isPaused, false);
  });

  test('a refused device unmute keeps the durable local mute', () async {
    await world.controller.pauseCapture();
    rejectMuteWrite = true;
    await expectLater(world.controller.resumeCapture(), throwsStateError);
    expect(muteWrites, [true]);
    expect(world.controller.isPaused, true);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
  });
}
