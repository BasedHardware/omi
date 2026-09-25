import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';

import '../support/capture/capture_replay_world.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_mute_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  test('normal mute blocks real capture callback; only explicit new start admits audio', () async {
    await world.startLiveCapture();
    final oldSession = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(20, sessionId: oldSession);
    await world.settle();
    final socket = world.socket!;
    final beforeMute = socket.sentBinary.length;
    expect(beforeMute, greaterThan(0));

    // This is the same production method invoked by the regular Omi mute UI.
    await world.controller.pauseDeviceRecording();
    expect(world.controller.isPaused, isTrue);
    expect(world.controller.offlineMuted, isTrue);
    world.injectAudioFrames(20, sessionId: oldSession, firstFrameIndex: 20);
    await world.settle();
    expect(socket.sentBinary.length, beforeMute);

    // A non-user restart cannot override mute.
    final starts = world.hostApi.startCalls;
    await world.controller.streamRecording(resumeCapture: false);
    expect(world.hostApi.startCalls, starts);
    expect(world.controller.isPaused, isTrue);

    await world.stopLiveCapture();
    world.clock.advanceTo(world.clock.now().add(const Duration(minutes: 2)));
    await world.startLiveCapture();
    expect(world.controller.offlineRecordingStartedAt, isNull);
    final newSession = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    final resumedSocket = world.socket!;
    final beforeUnmuteAudio = resumedSocket.sentBinary.length;
    world.injectAudioFrames(20, sessionId: newSession, firstFrameIndex: 40);
    await world.settle();
    expect(resumedSocket.sentBinary.length, greaterThan(beforeUnmuteAudio));
    expect(world.controller.isPaused, isFalse);
  });

  test('batch mute survives stop, new recording cut and controller reconstruction', () async {
    await world.startBatchCapture();
    await world.controller.toggleOfflineMute();
    final muted = SharedPreferencesUtil().capturePolicy;
    expect(muted.muted, isTrue);
    world.controller.startNewOfflineRecording();
    expect(SharedPreferencesUtil().capturePolicy, muted);
    await world.stopLiveCapture(reason: 'mode_changed');
    expect(SharedPreferencesUtil().capturePolicy, muted);

    world.disposeController();
    await world.reconstructProcess();
    expect(world.controller.isPaused, isTrue);
    expect(world.controller.offlineMuted, isTrue);
    expect(SharedPreferencesUtil().capturePolicy, muted);
  });
}
