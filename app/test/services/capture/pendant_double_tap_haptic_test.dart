import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

/// Double-tap actions are confirmed on the pendant itself, because the pendant has no screen and
/// the wearer usually is not looking at the phone.
void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  late ScriptedDeviceConnection link;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<void> doubleTap() async {
    world.controller.handleButtonEventForTesting(pendant.id, 2);
    await world.controller.pendingSourceSwitch;
    await world.settle();
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('pendant_pause_haptic_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
    link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    SharedPreferencesUtil().doubleTapAction = 1;
  });
  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  test('a double-tap pause and resume are felt on the pendant as a short then a longer pulse', () async {
    await doubleTap();
    expect(world.controller.isPaused, true);
    expect(link.hapticLevels, [1]);

    await doubleTap();
    expect(world.controller.isPaused, false);
    expect(link.hapticLevels, [1, 2]);
  });

  test('a double tap during an Omi call records the pause but does not vibrate', () async {
    world.omiCall.value = PhoneCallState.active;
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(world.controller.pendantPausedForCall, true);

    await doubleTap();
    expect(world.controller.isPaused, false, reason: 'a call suspension only records the intent');
    expect(link.hapticLevels, isEmpty);
  });

  test('starring and unstarring are felt as a longer then a short pulse', () async {
    SharedPreferencesUtil().doubleTapAction = 2;
    await doubleTap();
    expect(link.hapticLevels, [2]);

    await doubleTap();
    expect(link.hapticLevels, [2, 1]);
  });

  test('end and process is felt as a short pulse', () async {
    SharedPreferencesUtil().doubleTapAction = 0;
    await doubleTap();
    expect(world.processCalls, 1);
    expect(link.hapticLevels, [1]);
  });
}
