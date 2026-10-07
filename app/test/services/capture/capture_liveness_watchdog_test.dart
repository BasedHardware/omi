import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_coordinator.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/capture/capture_liveness_watchdog.dart';

import 'capture_coordinator_test.dart' show environment;
import '../../support/capture/capture_replay_world.dart';

CaptureCoordinatorState live({String key = 'phone-1', CapturePhase phase = CapturePhase.phoneLive}) =>
    CaptureCoordinatorState(
      phase: phase,
      active: ActiveCaptureSession(source: CaptureSource.phone, mode: CaptureTransport.live, sessionKey: key),
    );

void main() {
  final start = DateTime.utc(2026, 10, 7);
  test('connected socket with no frames forces a bounded WAL boundary recovery', () {
    final watchdog = CaptureLivenessWatchdog();
    expect(watchdog.check(live(), start, socketReady: true), isNull);
    expect(watchdog.check(live(), start.add(const Duration(seconds: 44)), socketReady: true), isNull);
    final failure = watchdog.check(live(), start.add(const Duration(seconds: 45)), socketReady: true)!;
    expect(failure.reason, CaptureLivenessReason.noFrames);
    final transition = transitionCapture(live(), failure, environment(live()));
    expect(transition.effects[0], isA<RunStage>().having((e) => e.stage, 'stage', isA<FlushPhoneFramesStage>()));
    expect(transition.effects[1], isA<WalFinalize>());
    expect(transition.effects[2], isA<RunStage>().having((e) => e.stage, 'stage', isA<RestartLiveMicStage>()));
    expect(transition.state.active!.sessionKey, 'phone-1');
    expect(watchdog.check(live(), start.add(const Duration(seconds: 60)), socketReady: true), isNull);
    expect(watchdog.check(live(), start.add(const Duration(seconds: 105)), socketReady: true), isNotNull);
  });
  test('socket down with flowing frames recovers without releasing the mic', () {
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(live(), start, socketReady: false);
    watchdog.observeFrame(start.add(const Duration(seconds: 44)));
    final failure = watchdog.check(live(), start.add(const Duration(seconds: 45)), socketReady: false)!;
    expect(failure.reason, CaptureLivenessReason.socketDown);
    final transition = transitionCapture(live(), failure, environment(live()));
    expect(transition.effects[1], isA<WalFinalize>());
    expect((transition.effects.last as RunStage).stage, isA<ReconnectPhoneStage>());
    expect(transition.effects.whereType<NativeMicStop>(), isEmpty);
    expect(transition.effects.whereType<SocketClose>(), isEmpty);
  });
  test('healthy frames and socket stay healthy beyond 70 minutes', () {
    final watchdog = CaptureLivenessWatchdog();
    for (var second = 0; second <= 4200; second += 15) {
      final now = start.add(Duration(seconds: second));
      watchdog.observeFrame(now);
      expect(watchdog.check(live(), now, socketReady: true), isNull);
    }
  });
  test('queued recovery cannot act on a successor session', () {
    const failure = CaptureLivenessFailure(sessionKey: 'phone-1', reason: CaptureLivenessReason.noFrames);
    final successor = live(key: 'phone-2');
    expect(transitionCapture(successor, failure, environment(successor)).effects, isEmpty);
  });
  test('paused, interrupted, batch and pendant phases never get live recovery effects', () {
    const failure = CaptureLivenessFailure(sessionKey: 'phone-1', reason: CaptureLivenessReason.noFrames);
    for (final phase in CapturePhase.values.where((p) => p != CapturePhase.phoneLive)) {
      final state = live(phase: phase);
      expect(transitionCapture(state, failure, environment(state)).effects, isEmpty, reason: phase.name);
      final watchdog = CaptureLivenessWatchdog();
      expect(watchdog.check(state, start, socketReady: false), isNull);
      expect(watchdog.check(state, start.add(const Duration(hours: 2)), socketReady: false), isNull);
    }
  });
  test('native mic stalls also preserve the WAL tail before restarting', () {
    final transition = transitionCapture(live(), const NativeMicStalled(), environment(live()));
    expect((transition.effects.first as RunStage).stage, isA<FlushPhoneFramesStage>());
    expect(transition.effects[1], isA<WalFinalize>());
  });
  test('foreground rearm gives the native recovery time to produce frames', () {
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(live(), start, socketReady: true);
    watchdog.reset();
    expect(watchdog.check(live(), start.add(const Duration(hours: 1)), socketReady: true), isNull);
  });
  test('real socket-down watchdog makes flowing phone audio durable without stopping the mic', () async {
    final dir = await Directory.systemTemp.createTemp('audio_loss_socket_');
    addTearDown(() => dir.delete(recursive: true));
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    addTearDown(world.dispose);
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    final starts = world.hostApi.startCalls;
    final stops = world.hostApi.stopCalls;
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    for (var i = 0; i < 60; i++) {
      world.injectAudioFrames(100, sessionId: world.hostApi.lastStartSessionId!);
      await world.elapse(const Duration(seconds: 1));
    }
    final wals = await world.wal.syncs.phone.getAllWals();
    expect(wals, isNotEmpty);
    await world.controller.pendingSourceSwitch;
    final paths = await Future.wait(wals.where((w) => w.filePath != null).map((w) => Wal.getFilePath(w.filePath)));
    expect(paths.any((path) => path != null && File(path).existsSync()), isTrue);
    expect(world.hostApi.startCalls, starts);
    expect(world.hostApi.stopCalls, stops);
  });

  test('real controller watchdog recovers live capture and preserves the session', () async {
    final dir = await Directory.systemTemp.createTemp('audio_loss_watchdog_');
    addTearDown(() => dir.delete(recursive: true));
    final world = await CaptureReplayWorld.boot(tempDir: dir, initialPrefs: {'unlimitedLocalStorageEnabled': true});
    addTearDown(world.dispose);
    await world.startLiveCapture();
    expect(world.controller.liveCaptureSource, 'phone');
    final recordingId = world.controller.activeRecordingId;
    final starts = world.hostApi.startCalls;
    world.injectAudioFrames(100, sessionId: world.hostApi.lastStartSessionId!);
    for (var i = 0; i < 5; i++) {
      await world.elapse(const Duration(seconds: 15));
      await world.controller.pendingSourceSwitch;
    }
    expect(world.hostApi.startCalls, greaterThan(starts));
    expect(world.controller.activeRecordingId, recordingId);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty);
    world.disposeController();
    await world.settle();
    // Lifetime cancellation includes the independent watchdog.
    expect(world.scheduler.pendingTimerLabels.where((label) => label == 'periodic(0:00:15.000000)'), isEmpty);
  });
}
