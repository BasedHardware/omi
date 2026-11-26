import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

import '../support/capture/capture_replay_world.dart';
import '../support/capture/scripted_device_connection.dart';

void main() {
  final pendant = BtDevice(id: 'mute-test-pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
  late Directory directory;
  late CaptureReplayWorld world;
  late ScriptedDeviceConnection link;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_mute_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
    link = ScriptedDeviceConnection(orphanDeviceId: pendant.id);
    world.deviceConnection = link;
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  test('pendant mute blocks delivery until an explicit resume', () async {
    final capture = world.controller;
    await capture.streamDeviceRecording(device: pendant);
    link.emitFixtureFrames(20, firstFrameIndex: 0);
    await world.settle();
    final socket = world.socket!;
    final beforeMute = socket.sentBinary.length;
    expect(beforeMute, greaterThan(0));

    await capture.pauseDeviceRecording();
    expect(capture.isPaused, isTrue);
    expect(capture.offlineMuted, isTrue);
    final mutedRevision = SharedPreferencesUtil().capturePolicy.revision;
    capture.onAppResumed();
    link.emitFixtureFrames(20, firstFrameIndex: 20);
    await world.settle();
    expect(socket.sentBinary.length, beforeMute);
    expect(SharedPreferencesUtil().capturePolicy.revision, mutedRevision);

    await capture.resumeDeviceRecording();
    final resumedSocket = world.socket!;
    final beforeResume = resumedSocket.sentBinary.length;
    link.emitFixtureFrames(20, firstFrameIndex: 40);
    await world.settle();
    expect(resumedSocket.sentBinary.length, greaterThan(beforeResume));
    expect(capture.isPaused, isFalse);
  });

  test('wearable batch mute survives a new recording, stop and app reconstruction', () async {
    final capture = world.controller;
    await capture.streamDeviceRecording(device: pendant);
    expect(await capture.setBatchMode(true), isTrue);
    await capture.toggleOfflineMute();
    final muted = SharedPreferencesUtil().capturePolicy;
    expect(muted.muted, isTrue);
    capture.startNewOfflineRecording();
    expect(SharedPreferencesUtil().capturePolicy, muted);
    await capture.stopStreamDeviceRecording();
    expect(SharedPreferencesUtil().capturePolicy, muted);

    world.disposeController();
    await world.reconstructProcess();
    expect(world.controller.isPaused, isTrue);
    expect(world.controller.offlineMuted, isTrue);
    expect(SharedPreferencesUtil().capturePolicy, muted);
  });
}
