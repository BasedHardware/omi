// One live source at a time (David, 2026-09-25): the pendant, the phone mic and an Omi call never
// capture together, a pause keeps its conversation, and a source that another one paused comes
// back on its own. Each scenario drives the real CaptureController over the replay world.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_one_source_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<ScriptedDeviceConnection> connectPendant() async {
    final link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    return link;
  }

  /// Bytes the current socket receives when the pendant sends [packets] packets.
  Future<int> pendantBytesReaching(ScriptedDeviceConnection link, {int packets = 5}) async {
    final socket = world.socket!;
    final before = socket.sentBinary.length;
    for (var i = 0; i < packets; i++) {
      link.emitAudio();
    }
    await world.settle();
    return socket.sentBinary.length - before;
  }

  Future<void> callSwitch() async {
    await world.controller.pendingSourceSwitch;
    await world.settle();
  }

  group('(d) an Omi call pauses the pendant and gives it back', () {
    test('pendant audio stops during the call and flows again after it', () async {
      final link = await connectPendant();
      expect(await pendantBytesReaching(link), greaterThan(0));

      world.omiCall.value = PhoneCallState.active;
      await callSwitch();
      expect(world.controller.pendantPausedForCall, isTrue);
      expect(link.openAudioSubscriptions, 0);
      expect(await pendantBytesReaching(link), 0);

      world.omiCall.value = PhoneCallState.ended;
      await callSwitch();
      expect(link.openAudioSubscriptions, 1);
      expect(world.controller.recordingState, RecordingState.deviceRecord);
      expect(await pendantBytesReaching(link), greaterThan(0));
    });

    test('a pendant that drops and reconnects during the call stays off, with its transcript', () async {
      final link = await connectPendant();
      world.omiCall.value = PhoneCallState.active;
      await callSwitch();
      final recording = world.controller.activeRecordingId;

      world.controller.updateRecordingDevice(null);
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();

      expect(world.controller.pendantPausedForCall, isTrue);
      expect(link.openAudioSubscriptions, 0);
      expect(world.controller.activeRecordingId, recording, reason: 'the reconnect must not start a new session');

      world.omiCall.value = PhoneCallState.idle;
      await callSwitch();
      expect(link.openAudioSubscriptions, 1);
    });

    test('a call does not unpause a pendant the user paused', () async {
      final link = await connectPendant();
      await world.controller.pauseCapture();
      await world.settle();
      world.omiCall.value = PhoneCallState.active;
      await callSwitch();
      world.omiCall.value = PhoneCallState.idle;
      await callSwitch();
      expect(world.controller.isPaused, isTrue);
      expect(link.openAudioSubscriptions, 0);
    });
  });
}
