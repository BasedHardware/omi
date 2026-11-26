import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/services/capture/capture_system_surface.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

class _Surface implements CaptureSystemSurfaceSink {
  late Future<Map<String, Object?>> Function(Map<String, Object?>) action;
  final states = <Map<String, Object?>>[];
  bool closed = false;
  bool fail = false;
  @override
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action) async {
    this.action = action;
  }

  @override
  Future<void> publish(Map<String, Object?> state) async {
    if (fail) throw StateError('Presentation unavailable');
    states.add(state);
  }

  @override
  Future<void> close() async {
    closed = true;
  }
}

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  late CaptureSystemSurface presentation;
  late _Surface sink;

  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<void> recordWithPendant() async {
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    world.deviceConnection!.emitAudio();
    await world.settle();
    expect(presentation.snapshot['source'], 'pendant');
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi_live_activity_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    sink = _Surface();
    presentation = CaptureSystemSurface(world.controller, sink, now: world.clock.now);
    await presentation.start();
    await recordWithPendant();
  });

  tearDown(() async {
    await presentation.close();
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  Map<String, Object?> request(String action) => {
        'recordingId': presentation.snapshot['recordingId'],
        'conversationRevision': presentation.snapshot['conversationRevision'],
        'action': action,
      };

  test('a repeated Pause does not issue a second mute intent', () async {
    final pause = request('pause');
    await sink.action(pause);
    final revision = SharedPreferencesUtil().capturePolicy.revision;
    await sink.action(pause);
    expect(SharedPreferencesUtil().capturePolicy.revision, revision);
  });

  test('star is not a system surface action', () async {
    expect(presentation.snapshot.containsKey('canStar'), false);
    await expectLater(sink.action(request('star')), throwsStateError);
    expect(world.controller.isConversationMarkedForStarring, false);
  });

  test('silence timeout does not publish a false pause to the Live Activity', () async {
    await world.elapse(const Duration(seconds: 120));
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(presentation.snapshot['paused'], false);
    expect(presentation.snapshot['status'], 'listening');
    expect(presentation.snapshot['canPause'], true);
  });

  test('an Omi call holding the pendant reads as an interruption, without Stop or Start', () async {
    world.omiCall.value = PhoneCallState.active;
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(world.controller.pendantPausedForCall, isTrue);
    expect(presentation.snapshot['active'], true);
    expect(presentation.snapshot['status'], 'interrupted');
    expect(presentation.snapshot['paused'], true);
    expect(presentation.snapshot['canPause'], false);
    await expectLater(sink.action(request('resume')), throwsStateError);

    world.omiCall.value = PhoneCallState.ended;
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(presentation.snapshot['paused'], false);
    expect(presentation.snapshot['canPause'], true);
  });
}
