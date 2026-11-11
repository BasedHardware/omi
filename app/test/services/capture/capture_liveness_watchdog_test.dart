import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/widgets.dart';
import 'dart:async';
import 'package:omi/utils/enums.dart';
import 'package:omi/services/capture/capture_coordinator.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/capture/capture_liveness_watchdog.dart';

import 'capture_coordinator_test.dart' show environment, HarnessPorts;
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
    final transition = transitionCapture(live(), failure, environment(live(), transcriptReady: true));
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
  test('both no frames and a dead socket prefer reconnect without restarting the mic', () {
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(live(), start, socketReady: false);
    final failure = watchdog.check(live(), start.add(const Duration(seconds: 45)), socketReady: false)!;
    expect(failure.reason, CaptureLivenessReason.socketDown);
    final transition = transitionCapture(live(), failure, environment(live(), socketConnected: false));
    expect(transition.effects[1], isA<WalFinalize>());
    expect((transition.effects.last as RunStage).stage, isA<ReconnectPhoneStage>());
    expect(transition.effects.whereType<RunStage>().any((effect) => effect.stage is RestartLiveMicStage), false);
  });

  test('socket failure queued before keepalive restored readiness is discarded on apply', () async {
    final fake = HarnessPorts();
    var ready = true;
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
        ports: fake.ports,
        readEnvironment: () => environment(coordinator.state, socketConnected: ready, transcriptReady: ready));
    addTearDown(coordinator.dispose);
    await coordinator.dispatch(const PhoneStartRequested());
    ready = false;
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(coordinator.state, start, socketReady: false);
    final failure = watchdog.check(coordinator.state, start.add(const Duration(seconds: 45)), socketReady: false)!;
    fake.log.clear();
    final held = fake.hold = Completer<void>();
    final head = coordinator.dispatch(const SocketError('held behind an existing effect'));
    final queued = coordinator.dispatch(failure);
    ready = true; // The keepalive has restored the socket before apply.
    held.complete();
    await head;
    await queued;
    expect(fake.log, ['stage:SocketErrorStage']);
    expect(coordinator.state.phase, CapturePhase.phoneLive);
  });

  test('no-frame failure reconnects if the socket died before reducer application', () {
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(live(), start, socketReady: true);
    final failure = watchdog.check(live(), start.add(const Duration(seconds: 45)), socketReady: true)!;
    expect(failure.reason, CaptureLivenessReason.noFrames);
    final transition = transitionCapture(live(), failure, environment(live(), socketConnected: false));
    expect((transition.effects.last as RunStage).stage, isA<ReconnectPhoneStage>());
  });

  test('keepalive restoration during WAL persistence drops the remaining reconnect', () async {
    final fake = HarnessPorts();
    var ready = true;
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
        ports: fake.ports,
        readEnvironment: () => environment(coordinator.state, socketConnected: ready, transcriptReady: ready));
    addTearDown(coordinator.dispose);
    await coordinator.dispatch(const PhoneStartRequested());
    ready = false;
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(coordinator.state, start, socketReady: false);
    final failure = watchdog.check(coordinator.state, start.add(const Duration(seconds: 45)), socketReady: false)!;
    fake.log.clear();
    final held = Completer<void>();
    final recovery = coordinator.dispatch(failure);
    fake.hold = held;
    await Future<void>.delayed(Duration.zero);
    expect(fake.log, ['stage:FlushPhoneFramesStage', 'wal:finalize']);
    ready = true;
    held.complete();
    await recovery;
    expect(fake.log, ['stage:FlushPhoneFramesStage', 'wal:finalize']);
  });

  test('socket death during the WAL write switches mic recovery to reconnect', () async {
    final fake = HarnessPorts();
    var ready = true;
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
        ports: fake.ports,
        readEnvironment: () => environment(coordinator.state, socketConnected: ready, transcriptReady: ready));
    addTearDown(coordinator.dispose);
    await coordinator.dispatch(const PhoneStartRequested());
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(coordinator.state, start, socketReady: true);
    final failure = watchdog.check(coordinator.state, start.add(const Duration(seconds: 45)), socketReady: true)!;
    fake.log.clear();
    final held = Completer<void>();
    final recovery = coordinator.dispatch(failure);
    fake.hold = held;
    await Future<void>.delayed(Duration.zero);
    ready = false;
    held.complete();
    await recovery;
    expect(fake.log, ['stage:FlushPhoneFramesStage', 'wal:finalize', 'stage:ReconnectPhoneStage']);
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
    final failure = CaptureLivenessFailure(
        sessionKey: 'phone-1',
        reason: CaptureLivenessReason.noFrames,
        gapStartedAt: start,
        observedAt: start.add(const Duration(seconds: 45)),
        observationEpoch: 0);
    final successor = live(key: 'phone-2');
    expect(transitionCapture(successor, failure, environment(successor)).effects, isEmpty);
  });
  test('paused, interrupted, batch and pendant phases never get live recovery effects', () {
    final failure = CaptureLivenessFailure(
        sessionKey: 'phone-1',
        reason: CaptureLivenessReason.noFrames,
        gapStartedAt: start,
        observedAt: start.add(const Duration(seconds: 45)),
        observationEpoch: 0);
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
  test('observed stall window overlapping suspension is discarded by the reducer', () {
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(live(), start, socketReady: true);
    final failure = watchdog.check(live(), start.add(const Duration(seconds: 75)), socketReady: true)!;
    expect(failure.gapStartedAt, start);
    expect(failure.observedAt, start.add(const Duration(seconds: 75)));
    final env = environment(live(),
        appSuspendedAt: start.add(const Duration(seconds: 10)), appResumedAt: start.add(const Duration(seconds: 74)));
    expect(transitionCapture(live(), failure, env).effects, isEmpty);
    expect(transitionCapture(live(), failure, environment(live(), appSuspended: true)).effects, isEmpty);
  });

  test('resume during WAL persistence invalidates the not-yet-issued mic recovery', () async {
    final fake = HarnessPorts();
    var epoch = 0;
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
        ports: fake.ports,
        readEnvironment: () => environment(coordinator.state, livenessEpoch: epoch, transcriptReady: true));
    addTearDown(coordinator.dispose);
    await coordinator.dispatch(const PhoneStartRequested());
    final watchdog = CaptureLivenessWatchdog();
    watchdog.check(coordinator.state, start, socketReady: true);
    final failure = watchdog.check(coordinator.state, start.add(const Duration(seconds: 75)), socketReady: true)!;
    fake.log.clear();
    final held = Completer<void>();
    final recovery = coordinator.dispatch(failure);
    fake.hold = held; // The synchronous flush started; hold the next WAL write.
    await Future<void>.delayed(Duration.zero);
    expect(fake.log, ['stage:FlushPhoneFramesStage', 'wal:finalize']);
    epoch++;
    held.complete();
    await recovery;
    expect(fake.log, ['stage:FlushPhoneFramesStage', 'wal:finalize']);
    expect(coordinator.state.phase, CapturePhase.phoneLive);
  });

  test('check queued during a 75-second freeze then onAppResumed never restarts the mic', () async {
    final dir = await Directory.systemTemp.createTemp('watchdog_freeze_');
    addTearDown(() => dir.delete(recursive: true));
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    addTearDown(world.dispose);
    await world.startLiveCapture();
    // Hold an existing reconnect so the watchdog observation queues behind it.
    world.controller.updateRecordingState(RecordingState.interrupted);
    final held = world.hostApi.holdNextStart = Completer<void>();
    world.controller.onConnected();
    await world.settle();
    final starts = world.hostApi.startCalls;
    final stops = world.hostApi.stopCalls;
    // No running event: the native three-second timer is unarmed. The real
    // independent watchdog queues check() after the frozen wall-clock gap.
    await world.elapse(const Duration(seconds: 75));
    world.controller.onAppResumed();
    held.complete();
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(world.hostApi.startCalls, starts, reason: 'the queued freeze observation is retired before application');
    expect(world.hostApi.stopCalls, stops);
    expect(world.controller.liveCaptureSource, 'phone');
  });

  test('lifecycle suspension preserves native capture and foreground gives fresh grace', () async {
    final dir = await Directory.systemTemp.createTemp('watchdog_lifecycle_');
    addTearDown(() => dir.delete(recursive: true));
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    addTearDown(world.dispose);
    await world.startLiveCapture();
    final starts = world.hostApi.startCalls;
    final stops = world.hostApi.stopCalls;
    world.controller.onAppLifecycleChanged(AppLifecycleState.paused);
    await world.elapse(const Duration(seconds: 75));
    world.controller.onAppLifecycleChanged(AppLifecycleState.resumed);
    await world.controller.pendingSourceSwitch;
    await world.elapse(const Duration(seconds: 30));
    expect(world.hostApi.startCalls, starts);
    expect(world.hostApi.stopCalls, stops);
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
