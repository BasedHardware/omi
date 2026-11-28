import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/capture_system_surface.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:omi/services/telemetry/finish_home_sli_telemetry.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

class _Surface implements CaptureSystemSurfaceSink {
  late Future<Map<String, Object?>> Function(Map<String, Object?>) action;

  @override
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action) async {
    this.action = action;
  }

  @override
  Future<void> publish(Map<String, Object?> state) async {}

  @override
  Future<void> close() async {}
}

/// The Finish → Home SLI cut's source is the action the user took, not whether the request names a
/// live conversation (SCA-4489).
void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  late String owner;
  var ownerSeq = 0;

  List<ClientTelemetryObservation> cuts() => FinishHomeSliTelemetry.instance.outbox
      .pending(owner)
      .where((observation) => observation.family == 'finish_cut')
      .toList();

  setUp(() async {
    owner = 'finish-cut-source-owner-${ownerSeq++}';
    final wasTestFlight = Env.isTestFlight;
    Env.isTestFlight = true;
    addTearDown(() => Env.isTestFlight = wasTestFlight);
    final telemetry = FinishHomeSliTelemetry.instance;
    final (enabled, ownerId, platform) = (telemetry.testFlightEnabled, telemetry.ownerId, telemetry.platform);
    telemetry
      ..testFlightEnabled = (() => true)
      ..ownerId = (() => owner)
      ..platform = (() => 'ios');
    addTearDown(() => telemetry
      ..testFlightEnabled = enabled
      ..ownerId = ownerId
      ..platform = platform);

    directory = await Directory.systemTemp.createTemp('finish_cut_source_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  test('a Live Activity Finish names no live conversation and is still the app\'s cut', () async {
    final sink = _Surface();
    final presentation = CaptureSystemSurface(world.controller, sink, now: world.clock.now);
    await presentation.start();
    addTearDown(presentation.close);
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!);
    await world.settle();
    final processCallsBefore = world.processCalls;

    await sink.action({
      'recordingId': presentation.snapshot['recordingId'],
      'conversationRevision': presentation.snapshot['conversationRevision'],
      'action': 'finish',
    });
    await world.settle();

    expect(world.processCalls, processCallsBefore + 1, reason: 'the Live Activity Finish processes the capture');
    expect(cuts(), hasLength(1));
    expect(cuts().single.attributes['source'], 'app');
  });

  test('an id-less coordinator Finish from the pendant\'s capture is the app\'s cut', () async {
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(
      device: BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40),
    );
    await world.settle();

    // The live page's Finish button: the phone asks, though the pendant is recording.
    await world.controller.finishCapture();
    await world.settle();

    expect(cuts(), hasLength(1));
    expect(cuts().single.attributes['source'], 'app');
  });

  test('a pendant double tap is the pendant\'s cut', () async {
    final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    final processCallsBefore = world.processCalls;

    SharedPreferencesUtil().doubleTapAction = 0; // End conversation and process.
    world.controller.handleButtonEventForTesting(pendant.id, 2);
    await world.settle();

    expect(world.processCalls, processCallsBefore + 1, reason: 'the double tap processes the conversation');
    expect(cuts(), hasLength(1));
    expect(cuts().single.attributes['source'], 'pendant');
  });
}
