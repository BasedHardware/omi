import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/capture_coordinator.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

CaptureEnvironment environment(
  CaptureCoordinatorState state, {
  bool muted = false,
  bool batch = false,
  bool call = false,
}) =>
    CaptureEnvironment(
      policyMuted: muted,
      paused: muted,
      batchModeEnabled: batch,
      batchModeSuspendedForOnboarding: false,
      deviceSupportsTranscribeLater: true,
      networkConnected: true,
      signedIn: true,
      phoneMicSupportsBatch: true,
      transcriptReady: false,
      socketConnected: state.phoneOwns || state.pendantOwns,
      deviceServiceReady: state.connectedDevice != null || state.phoneOwns,
      callActive: call,
      deviceRecording: state.phase == CapturePhase.pendantLive,
      micCapturing: state.phase == CapturePhase.phoneLive || state.phase == CapturePhase.audioInterrupted,
    );

class HarnessPorts {
  String? snapshot;
  bool muted = false;
  bool ble = false;
  bool mic = false;
  bool socket = false;
  int opens = 0;
  int nextId = 0;
  String? recordingId;
  Completer<void>? hold;
  bool failNextOpen = false;
  bool failNextSnapshot = false;
  final log = <String>[];

  Future<void> _record(String name) async {
    log.add(name);
    if (hold != null) {
      final pending = hold!;
      hold = null;
      await pending.future;
    }
  }

  CaptureEffectPorts get ports => CaptureEffectPorts(
        writePolicy: (value) async {
          await _record('policy:$value');
          muted = value;
          return const PolicyWriteOutcome(revision: 1, superseded: false);
        },
        stopBleStream: ({bool disableNativeBackground = false}) async {
          await _record('ble:stop');
          ble = false;
        },
        startBleStream: () async {
          await _record('ble:start');
          ble = true;
        },
        openSocket: (spec) async {
          await _record('socket:open');
          if (failNextOpen) {
            failNextOpen = false;
            throw StateError('synthetic socket failure');
          }
          if (socket && !spec.ensureOnly) throw StateError('two open sockets');
          socket = true;
          opens++;
        },
        closeSocket: (reason) async {
          await _record('socket:close');
          socket = false;
        },
        startNativeMic: (mode) async {
          await _record('mic:start');
          mic = true;
        },
        stopNativeMic: () async {
          await _record('mic:stop');
          mic = false;
        },
        setNativeWriterGate: (source, admitted) => _record('gate:${source.name}:$admitted'),
        finalizeWal: () => _record('wal:finalize'),
        rollSession: (identity) => _record('wal:roll'),
        mintRecordingId: (key, source) => recordingId = '${source}_${++nextId}',
        currentRecordingId: () => recordingId,
        readSnapshot: () => snapshot,
        persistSnapshot: (encoded) async {
          await _record('snapshot');
          if (failNextSnapshot) {
            failNextSnapshot = false;
            throw StateError('synthetic snapshot failure');
          }
          snapshot = encoded;
        },
        runStage: (stage) async {
          await _record('stage:${stage.runtimeType}');
          if (stage is StartDeviceSessionStage ||
              stage is ResumeSuspendedPendantStage ||
              stage is ResumeDeviceTailStage) {
            ble = !muted;
            socket = true;
          }
          if (stage is StartPhoneSessionStage) {
            mic = true;
            socket = stage.mode == CaptureTransport.live;
          }
          if (stage is StopPhoneLiveStage || stage is StopPhoneBatchStage) {
            mic = false;
            socket = false;
          }
          if (stage is StartPhoneBatchStage) mic = true;
          if (stage is PauseDeviceTailStage || stage is SuspendPendantStage || stage is StopDeviceSessionStage) {
            ble = false;
          }
          return null;
        },
      );
}

class ScriptStep {
  const ScriptStep(this.code);
  final int code;
  @override
  String toString() => switch (code) {
        0 => 'device-start',
        1 => 'device-disconnect',
        2 => 'phone-start',
        3 => 'phone-stop',
        4 => 'pause',
        5 => 'resume',
        6 => 'call-start',
        7 => 'call-end',
        8 => 'finish',
        9 => 'socket-close',
        10 => 'socket-connect',
        11 => 'socket-error',
        12 => 'mic-stall',
        13 => 'interrupt-start',
        14 => 'interrupt-end',
        15 => 'keepalive',
        16 => 'batch-on',
        17 => 'batch-off',
        18 => 'settings',
        19 => 'profile',
        20 => 'onboarding-suspend',
        21 => 'onboarding-restore',
        22 => 'app-resume',
        23 => 'device-stop',
        24 => 'device-pause',
        25 => 'device-resume',
        26 => 'batch-phone-start',
        27 => 'offline-mute',
        28 => 'launch',
        _ => 'unknown-$code',
      };
}

class SequenceModel {
  CaptureCoordinatorState state = CaptureCoordinatorState.idle();
  bool muted = false;
  bool batch = false;
  bool call = false;
  final seenSessions = <String>{};

  void step(ScriptStep step) {
    if (step.code == 6) call = true;
    if (step.code == 7) call = false;
    final event = switch (step.code) {
      0 => DeviceStartRequested(device: pendant),
      1 => const DeviceUpdated(null),
      2 => const PhoneStartRequested(),
      3 => const PhoneStopRequested(reason: 'user_stopped', userStop: true),
      4 => const PauseCaptureRequested(),
      5 => const ResumeCaptureRequested(),
      6 || 7 => const CallStateChanged(),
      8 => const FinishRequested(),
      9 => const SocketClosed(),
      10 => const SocketConnected(),
      11 => SocketError(StateError('synthetic socket error')),
      12 => const NativeMicStalled(),
      13 => const MicInterruptionChanged(began: true),
      14 => const MicInterruptionChanged(began: false),
      15 => const KeepAliveTick(),
      16 => const BatchModeSetRequested(enabled: true),
      17 => const BatchModeSetRequested(enabled: false),
      18 => const TranscriptionSettingsChanged(),
      19 => const RecordProfileChanged(),
      20 => const OnboardingBatchChanged(suspended: true),
      21 => const OnboardingBatchChanged(suspended: false),
      22 => const AppForegrounded(),
      23 => const DeviceStopRequested(cleanDevice: true),
      24 => const DevicePauseRequested(),
      25 => const DeviceResumeRequested(),
      26 => const PhoneBatchStartRequested(),
      27 => const OfflineMuteToggled(),
      28 => const LaunchRecovery(markerPending: true, mutedBefore: false),
      _ => throw StateError('unknown event'),
    };
    final before = state;
    final transition = transitionCapture(before, event, environment(before, muted: muted, batch: batch, call: call));
    final next = transition.state;
    for (final effect in transition.effects) {
      if (effect is PolicyWrite) muted = effect.muted;
      if (effect is MintRecording && !seenSessions.add(effect.sessionKey)) {
        throw StateError('recording minted twice for session ${effect.sessionKey}');
      }
      if (effect is NativeMicStart && !next.phoneOwns) throw StateError('mic starts without phone owner');
      if (effect is BleStreamStart && !next.pendantOwns) throw StateError('BLE starts without pendant owner');
    }
    if (step.code == 16) batch = true;
    if (step.code == 17) batch = false;
    if (next.phoneOwns && next.pendantOwns) throw StateError('two live owners');
    if (next.phase == CapturePhase.idle && next.active != null) throw StateError('idle still owns session');
    if (next.active != null && next.active!.source != (next.phoneOwns ? CaptureSource.phone : CaptureSource.pendant)) {
      throw StateError('source/phase mismatch');
    }
    if (next.active != null &&
        before.active?.sessionKey != next.active!.sessionKey &&
        !seenSessions.contains(next.active!.sessionKey) &&
        step.code != 6 &&
        step.code != 7) {
      throw StateError('new session without minted recording id');
    }
    if (before.phoneOwns &&
        next.phoneOwns &&
        before.active?.sessionKey != next.active?.sessionKey &&
        !transition.effects.any((effect) =>
            effect is RunStage &&
            (effect.stage is StopPhoneLiveStage ||
                effect.stage is StopPhoneBatchStage ||
                effect.stage is BatchModeStage))) {
      throw StateError('phone session replaced without stopping old mic');
    }
    final parsed = CaptureCoordinatorState.tryParse(next.encode());
    if (parsed?.encode() != next.encode()) throw StateError('snapshot round-trip mismatch');
    if (step.code == 3 &&
        before.pendantSuspension?.reason == SuspendReason.phone &&
        next.connectedDevice != null &&
        next.pendantSuspension?.reason == SuspendReason.phone) {
      throw StateError('phone stop stranded suspended pendant');
    }
    if (step.code == 7 &&
        before.pendantSuspension?.reason == SuspendReason.call &&
        next.connectedDevice != null &&
        next.pendantSuspension?.reason == SuspendReason.call) {
      throw StateError('call end stranded suspended pendant');
    }
    state = next;
  }
}

class XorShift32 {
  XorShift32(this.value);
  int value;
  int next() {
    var x = value;
    x ^= (x << 13) & 0xffffffff;
    x ^= x >> 17;
    x ^= (x << 5) & 0xffffffff;
    value = x & 0xffffffff;
    return value;
  }

  int nextInt(int upper) => next() % upper;
}

String? failureFor(List<ScriptStep> steps) {
  final model = SequenceModel();
  try {
    for (final step in steps) {
      model.step(step);
    }
  } catch (error) {
    return error.toString();
  }
  return null;
}

List<ScriptStep> shrink(List<ScriptStep> failing, String expectedFailure) {
  var result = List<ScriptStep>.of(failing);
  var width = result.length ~/ 2;
  while (width >= 1) {
    var changed = false;
    for (var start = 0; start + width <= result.length; start++) {
      final candidate = [...result.take(start), ...result.skip(start + width)];
      if (failureFor(candidate) == expectedFailure) {
        result = candidate;
        changed = true;
        break;
      }
    }
    if (!changed) width ~/= 2;
  }
  return result;
}

void main() {
  test('2000 seeded ownership sequences (OMI_CAPTURE_SOAK_SEQUENCES overrides)', () {
    final budget = int.tryParse(Platform.environment['OMI_CAPTURE_SOAK_SEQUENCES'] ?? '') ?? 2000;
    expect(budget, inInclusiveRange(1, 1000000));
    const baseSeed = 0x5ca561;
    for (var sequence = 0; sequence < budget; sequence++) {
      final seed = baseSeed + sequence;
      final random = XorShift32(seed);
      final length = 50 + random.nextInt(151);
      final events = List.generate(length, (_) {
        final draw = random.nextInt(100);
        final code = draw < 20
            ? draw % 6
            : draw < 45
                ? 2 + draw % 7
                : draw < 70
                    ? 6 + draw % 11
                    : 17 + draw % 12;
        return ScriptStep(code);
      });
      final failure = failureFor(events);
      if (failure != null) {
        final minimized = shrink(events, failure);
        fail('seed=$seed sequence=$sequence error=$failure\nminimized=${minimized.join(' -> ')}');
      }
    }
  });

  for (final episode in <({String name, List<int> steps, CapturePhase phase})>[
    (name: 'phone pause/resume preserves its conversation', steps: [2, 4, 5], phase: CapturePhase.phoneLive),
    (name: 'phone stop restores a live pendant', steps: [0, 2, 3], phase: CapturePhase.pendantLive),
    (
      name: 'phone stop keeps a previously paused pendant paused',
      steps: [0, 4, 2, 3],
      phase: CapturePhase.pendantPaused
    ),
    (
      name: 'phone takeover with a call in flight waits until phone finishes',
      steps: [0, 6, 2, 7, 3],
      phase: CapturePhase.pendantLive
    ),
    (name: 'call pauses live pendant and gives it back', steps: [0, 6, 7], phase: CapturePhase.pendantLive),
    (name: 'call does not unpause a user-paused pendant', steps: [0, 4, 6, 7], phase: CapturePhase.pendantPaused),
    (
      name: 'BLE drop and reconnect under a call stays suspended',
      steps: [0, 6, 1, 0, 7],
      phase: CapturePhase.pendantLive
    ),
    (
      name: 'socket drop and stall during phone pause do not start the mic',
      steps: [2, 4, 9, 12],
      phase: CapturePhase.phonePaused
    ),
    (
      name: 'socket reconnect and settings while phone paused keep pause',
      steps: [2, 4, 10, 18],
      phase: CapturePhase.phonePaused
    ),
    (name: 'batch-mode setting while phone paused keeps its mode', steps: [2, 4, 16, 5], phase: CapturePhase.phoneLive),
    (
      name: 'batch pendant cannot be taken over without native per-source gate',
      steps: [16, 0, 2],
      phase: CapturePhase.pendantBatchLive
    ),
    (
      name: 'batch pendant suspended for call cannot be taken by phone without native gate',
      steps: [16, 0, 6, 0, 2, 7],
      phase: CapturePhase.pendantBatchLive
    ),
    (
      name: 'call end while phone owns does not resume pendant early',
      steps: [0, 6, 2, 7],
      phase: CapturePhase.phoneLive
    ),
    (name: 'phone stop resumes a pendant connected during capture', steps: [2, 0, 3], phase: CapturePhase.pendantLive),
    (name: 'deferred Omi call does not pause a live phone mic', steps: [2, 6], phase: CapturePhase.phoneLive),
    (name: 'phone interruption restores the same owner', steps: [2, 13, 14], phase: CapturePhase.phoneLive),
    (name: 'no resumed pendant after disconnect during phone handoff', steps: [0, 2, 1, 3], phase: CapturePhase.idle),
  ]) {
    test(episode.name, () {
      final model = SequenceModel();
      for (final code in episode.steps) {
        model.step(ScriptStep(code));
      }
      expect(model.state.phase, episode.phase);
    });
  }

  test('finish processes phone conversation before opening suspended pendant', () {
    final model = SequenceModel();
    model.step(const ScriptStep(0));
    model.step(const ScriptStep(2));
    final transition =
        transitionCapture(model.state, const FinishRequested(), environment(model.state, muted: model.muted));
    final stages = transition.effects.whereType<RunStage>().map((effect) => effect.stage).toList();
    final process = stages.indexWhere((stage) => stage is ProcessConversationStage);
    final reopen = stages.indexWhere((stage) => stage is StartDeviceSessionStage);
    expect(process, greaterThanOrEqualTo(0));
    expect(reopen, greaterThan(process));
  });

  test('launch never reopens hardware, and an orphaned phone pause restores admission', () {
    final saved = CaptureCoordinatorState(
      phase: CapturePhase.phonePaused,
      active:
          const ActiveCaptureSession(source: CaptureSource.phone, mode: CaptureTransport.live, sessionKey: 'phone-17'),
      sessionSeq: 17,
    );
    final restored = CaptureCoordinatorState.tryParse(saved.encode())!.sanitizedForLaunch();
    expect(restored.phase, CapturePhase.idle);
    expect(restored.sessionSeq, 17);
    final transition = transitionCapture(
        restored, const LaunchRecovery(markerPending: true, mutedBefore: false), environment(restored, muted: true));
    expect(transition.effects.whereType<PolicyWrite>().single.muted, isFalse);
    expect(transition.effects.whereType<NativeMicStart>(), isEmpty);
    expect(transition.effects.whereType<BleStreamStart>(), isEmpty);
  });

  test('invalid snapshots reject malformed stack, phase and version rather than dropping data', () {
    expect(CaptureCoordinatorState.tryParse('{"version":999}'), isNull);
    expect(
        CaptureCoordinatorState.tryParse(
            CaptureCoordinatorState.idle().encode().replaceFirst('"suspended":[]', '"suspended":[3]')),
        isNull);
    expect(
        CaptureCoordinatorState.tryParse(
            CaptureCoordinatorState.idle().encode().replaceFirst('"phase":"idle"', '"phase":"phoneLive"')),
        isNull);
  });

  test('socket error during a delayed pause cannot restart the mic', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    expect((await coordinator.dispatch(const PhoneStartRequested())).failed, isFalse);
    final held = fake.hold = Completer<void>();
    final pause = coordinator.dispatch(const PauseCaptureRequested());
    final socketError = coordinator.dispatch(SocketError(StateError('socket dropped during pause')));
    final reconnect = coordinator.dispatch(const SocketConnected());
    await Future<void>.delayed(Duration.zero);
    expect(fake.log.last, 'policy:true');
    held.complete();
    expect((await pause).failed, isFalse);
    expect((await socketError).failed, isFalse);
    expect((await reconnect).failed, isFalse);
    expect(coordinator.state.phase, CapturePhase.phonePaused);
    expect(fake.mic, isFalse);
    expect(fake.log.where((line) => line == 'mic:start'), hasLength(0));
    expect(fake.socket, isTrue);
    coordinator.dispose();
  });

  test('failed socket reopen and failed snapshot both deny physical capture before idle', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(const PhoneStartRequested());
    await coordinator.dispatch(const PauseCaptureRequested());
    fake.socket = false;
    fake.failNextOpen = true;
    final failedSocket = await coordinator.dispatch(const ResumeCaptureRequested());
    expect(failedSocket.failed, isTrue);
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(fake.mic, isFalse);
    expect(fake.ble, isFalse);
    expect(fake.socket, isFalse);
    expect(CaptureCoordinatorState.tryParse(fake.snapshot)?.phase, CapturePhase.idle);
    fake.failNextSnapshot = true;
    final failedSnapshot = await coordinator.dispatch(const PhoneStartRequested());
    expect(failedSnapshot.failed, isTrue);
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(fake.mic, isFalse);
    expect(fake.socket, isFalse);
    expect(CaptureCoordinatorState.tryParse(fake.snapshot)?.phase, CapturePhase.idle);
    coordinator.dispose();
  });

  for (final episode in <({String name, List<int> steps})>[
    (name: 'phone-pause', steps: [2, 4, 5, 3]),
    (name: 'pendant-handoff', steps: [0, 2, 3]),
    (name: 'call-suspension', steps: [0, 6, 7]),
    (name: 'reconnect-under-phone', steps: [2, 0, 3]),
  ]) {
    test('real CaptureController agrees with reducer: ${episode.name}', () async {
      final directory = await Directory.systemTemp.createTemp('capture_coordinator_conformance_');
      final world = await CaptureReplayWorld.boot(tempDir: directory);
      final model = SequenceModel();
      try {
        for (final code in episode.steps) {
          switch (code) {
            case 0:
              world.deviceConnection = ScriptedDeviceConnection();
              await world.controller.streamDeviceRecording(device: pendant);
            case 2:
              await world.startLiveCapture();
              world.emitNativeState(PhoneMicCaptureState.running);
            case 3:
              await world.stopLiveCapture();
            case 4:
              await world.controller.pauseCapture();
            case 5:
              await world.controller.resumeCapture();
            case 6:
              world.omiCall.value = PhoneCallState.active;
              await world.controller.pendingSourceSwitch;
            case 7:
              world.omiCall.value = PhoneCallState.ended;
              await world.controller.pendingSourceSwitch;
          }
          await world.settle();
          model.step(ScriptStep(code));
          final state = model.state;
          expect(
              world.controller.liveCaptureSource,
              state.phoneOwns
                  ? 'phone'
                  : state.pendantOwns
                      ? 'omi'
                      : null,
              reason: '${episode.name} after ${ScriptStep(code)}');
          expect(world.controller.pendantPausedForPhone, state.pendantSuspension?.reason == SuspendReason.phone,
              reason: '${episode.name} after ${ScriptStep(code)}');
          expect(world.controller.pendantPausedForCall, state.pendantSuspension?.reason == SuspendReason.call,
              reason: '${episode.name} after ${ScriptStep(code)}');
          if (state.phase == CapturePhase.phonePaused) {
            expect(world.controller.isPhoneMicPaused, isTrue);
            expect(world.hostApi.stopCalls, greaterThan(0));
          }
        }
      } finally {
        await world.dispose();
        if (directory.existsSync()) directory.deleteSync(recursive: true);
      }
    });
  }

  test('serialized dispatch waits for the earlier effect and survives a failing port', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator =
        CaptureCoordinator(ports: fake.ports, readEnvironment: () => environment(coordinator.state, muted: fake.muted));
    final held = fake.hold = Completer<void>();
    final start = coordinator.dispatch(DeviceStartRequested(device: pendant));
    final pause = coordinator.dispatch(const PauseCaptureRequested());
    await Future<void>.delayed(Duration.zero);
    expect(fake.log.length, 1);
    held.complete();
    expect((await start).failed, isFalse);
    expect((await pause).failed, isFalse);
    expect(coordinator.state.phase, CapturePhase.pendantPaused);
    fake.failNextOpen = true;
    final retry = await coordinator.dispatch(const ResumeCaptureRequested());
    expect(retry.failed, isFalse);
    coordinator.dispose();
    expect((await coordinator.dispatch(const PauseCaptureRequested())).admitted, isFalse);
  });
}
