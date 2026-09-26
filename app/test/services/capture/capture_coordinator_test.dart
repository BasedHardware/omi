import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
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
  bool batchSuspended = false,
  bool call = false,
}) =>
    CaptureEnvironment(
      policyMuted: muted,
      paused: muted,
      batchModeEnabled: batch,
      batchModeSuspendedForOnboarding: batchSuspended,
      deviceSupportsTranscribeLater: true,
      networkConnected: true,
      signedIn: () => true,
      phoneMicSupportsBatch: true,
      transcriptReady: false,
      socketConnected: state.phoneOwns || state.pendantOwns,
      deviceServiceReady: state.connectedDevice != null || state.phoneOwns,
      callActive: call,
      deviceRecording: state.phase == CapturePhase.pendantLive,
      micCapturing: state.phase == CapturePhase.phoneLive || state.phase == CapturePhase.audioInterrupted,
    );

class HarnessPorts {
  String? snapshot = CaptureCoordinatorState.idle().encode();
  bool muted = false;
  bool batch = false;
  bool batchSuspended = false;
  bool permitPhone = true;
  bool prefetchedGrant = false;
  int permissionGrantClears = 0;
  bool failNextPhoneStart = false;
  bool ble = false;
  bool devicePresent = false;
  bool mic = false;
  bool socket = false;
  int opens = 0;
  int nextId = 0;
  String? recordingId;
  Completer<void>? hold;
  bool failNextOpen = false;
  bool failNextSnapshot = false;
  bool supersedeNextPolicy = false;
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
        checkPhonePermission: () async {
          await _record('permission:check');
          prefetchedGrant = permitPhone;
          return permitPhone;
        },
        clearPhonePermissionGrant: () {
          prefetchedGrant = false;
          permissionGrantClears++;
        },
        writePolicy: (value) async {
          await _record('policy:$value');
          if (supersedeNextPolicy) {
            supersedeNextPolicy = false;
            muted = !value;
            return const PolicyWriteOutcome(revision: 1, superseded: true);
          }
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
        mintRecordingId: (key, source) {
          final minted = recordingId = '${source}_${++nextId}';
          log.add('mint:$key:$minted');
          return minted;
        },
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
          if (stage is UpdateRecordingDeviceStage) devicePresent = stage.device != null;
          if (stage is StopDeviceSessionStage && stage.cleanDevice) devicePresent = false;
          if ((stage is StartDeviceSessionStage ||
                  stage is ResumeSuspendedPendantStage ||
                  stage is ResumeDeviceTailStage) &&
              devicePresent) {
            ble = !muted;
            socket = !batch;
          }
          if (stage is SuspendPendantStage) socket = false;
          if (stage is StartPhoneSessionStage) {
            if (failNextPhoneStart) {
              failNextPhoneStart = false;
              recordingId = null;
              return const CaptureStageFailure('synthetic native start failed');
            }
            if (socket && stage.mode == CaptureTransport.live) throw StateError('two open sockets at phone handoff');
            mic = true;
            socket = stage.mode == CaptureTransport.live;
          }
          if (stage is BatchModeStage) {
            if (batch == stage.enabled) return true;
            batch = stage.enabled;
            if (stage.rolledPhoneMode != null) {
              mic = false;
              socket = false;
              recordingId = null;
            }
          }
          if (stage is OnboardingBatchStage) {
            if (stage.suspended && batch) {
              batch = false;
              batchSuspended = true;
            } else if (!stage.suspended && batchSuspended) {
              batch = true;
              batchSuspended = false;
            }
          }
          if (stage is SocketClosedStage) socket = false;
          if (stage is StopPhoneLiveStage || stage is StopPhoneBatchStage) {
            mic = false;
            socket = false;
            recordingId = null;
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
        28 => 'kill-and-launch',
        29 => 'phone-stop-await-onboarding',
        _ => 'unknown-$code',
      };
}

CaptureEvent eventForStep(int code) => switch (code) {
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
      11 => SocketError(StateError('injected socket error')),
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
      29 => const PhoneStopRequested(reason: 'user_stopped', userStop: true, resumeSuspendedPendant: false),
      _ => throw StateError('unknown effect event: $code'),
    };

class SequenceModel {
  CaptureCoordinatorState state = CaptureCoordinatorState.idle();
  bool muted = false;
  bool batch = false;
  bool batchSuspended = false;
  bool call = false;
  final seenSessions = <String>{};

  void step(ScriptStep step) {
    if (step.code == 28) {
      state = CaptureCoordinatorState.tryParse(state.encode())!.sanitizedForLaunch();
      call = false;
    }
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
      29 => const PhoneStopRequested(reason: 'user_stopped', userStop: true, resumeSuspendedPendant: false),
      _ => throw StateError('unknown event'),
    };
    final before = state;
    final transition = transitionCapture(
        before, event, environment(before, muted: muted, batch: batch, batchSuspended: batchSuspended, call: call));
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
    if (step.code == 20 && batch) {
      batch = false;
      batchSuspended = true;
    }
    if (step.code == 21 && batchSuspended) {
      batch = true;
      batchSuspended = false;
    }
    if (next.suspended.length > 1 || next.suspended.any((entry) => entry.source != CaptureSource.pendant)) {
      throw StateError('invalid pendant suspension stack');
    }
    final debt = next.pendantSuspension;
    if (debt?.reason == SuspendReason.call && !next.callActive) throw StateError('call debt without call');
    if (debt?.reason == SuspendReason.phone && !next.phoneOwns && !next.awaitingPhoneResume) {
      throw StateError('phone debt without owner or onboarding return');
    }
    if (next.awaitingPhoneResume && (next.phoneOwns || debt?.reason != SuspendReason.phone)) {
      throw StateError('onboarding return without phone suspension');
    }
    if (next.phase == CapturePhase.idle && next.active != null) throw StateError('idle still owns session');
    if (next.active != null && next.active!.source != (next.phoneOwns ? CaptureSource.phone : CaptureSource.pendant)) {
      throw StateError('source/phase mismatch');
    }
    if (next.active != null &&
        before.active?.sessionKey != next.active!.sessionKey &&
        !seenSessions.contains(next.active!.sessionKey) &&
        before.pendantSuspension?.sessionKey != next.active!.sessionKey) {
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

class FaultCoverage {
  int snapshot = 0;
  int socketOpen = 0;
  int policySuperseded = 0;
  int failedPhoneStart = 0;
  int recoveredPhoneStart = 0;
  int heldSocketError = 0;
  int heldBleDrop = 0;
  int kills = 0;
  int batchToggles = 0;
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

Future<String?> effectFailureFor(List<ScriptStep> steps, {required int seed, FaultCoverage? coverage}) async {
  final fake = HarnessPorts();
  final faults = XorShift32(seed ^ 0x9e3779b9);
  var call = false;
  final recordingIds = <String, String>{};
  final seenRecordingIds = <String>{};
  late CaptureCoordinator coordinator;
  CaptureCoordinator boot() => CaptureCoordinator(
        ports: fake.ports,
        readEnvironment: () => environment(coordinator.state,
            muted: fake.muted, batch: fake.batch, batchSuspended: fake.batchSuspended, call: call),
      );
  coordinator = boot();
  void verify(ScriptStep step) {
    final state = coordinator.state;
    final active = state.active;
    if (state.suspended.length > 1) throw StateError('multiple pendant suspensions');
    if (state.pendantSuspension?.reason == SuspendReason.call && !state.callActive) {
      throw StateError('call suspension without call');
    }
    if (state.pendantSuspension?.reason == SuspendReason.phone && !state.phoneOwns && !state.awaitingPhoneResume) {
      throw StateError('phone suspension without taker');
    }
    if (active != null) {
      final id = active.recordingId;
      if (id == null) throw StateError('owner has no recording id');
      final prior = recordingIds[active.sessionKey];
      if (prior == null) {
        if (!seenRecordingIds.add(id)) throw StateError('recording id reused across source sessions');
        recordingIds[active.sessionKey] = id;
      } else if (prior != id) {
        throw StateError('recording id changed within source session');
      }
      if (fake.recordingId != id) throw StateError('owner and telemetry recording ids differ');
    }
    if (state.phase == CapturePhase.phonePaused && fake.mic) {
      throw StateError('live phone mic open while paused');
    }
    if (state.phase == CapturePhase.phoneBatchPaused && (!fake.mic || !fake.muted)) {
      throw StateError(
          'batch phone writer must remain open but policy-muted in the same file: step=$step phase=${state.phase} mic=${fake.mic} muted=${fake.muted} log=${fake.log.length > 12 ? fake.log.skip(fake.log.length - 12).toList() : fake.log}');
    }
    if (state.phoneOwns && fake.ble) throw StateError('BLE open under phone owner');
    if (state.pendantSuspension != null && fake.ble) throw StateError('BLE open while suspended');
    if ((state.phase == CapturePhase.pendantPaused || state.phase == CapturePhase.pendantBatchPaused) && fake.ble) {
      throw StateError('BLE open while pendant paused');
    }
    if (state.phase == CapturePhase.pendantLive && !fake.ble) throw StateError('live pendant has no BLE stream');
    if ((state.phase == CapturePhase.idle || state.phase == CapturePhase.callActive) &&
        (fake.mic || fake.ble || fake.socket)) {
      throw StateError('physical capture open without an owner');
    }
    if (CaptureCoordinatorState.tryParse(fake.snapshot)?.encode() != state.encode()) {
      throw StateError('port snapshot differs from committed state');
    }
  }

  try {
    for (final step in steps) {
      if (step.code == 28) {
        if (coverage != null) coverage.kills++;
        coordinator.dispose();
        fake.mic = false;
        fake.ble = false;
        fake.socket = false;
        fake.devicePresent = false;
        fake.recordingId = null;
        call = false;
        coordinator = boot();
        if (coordinator.state.phase != CapturePhase.idle) throw StateError('launch resurrected a capture owner');
      }
      if (step.code == 6) call = true;
      if (step.code == 7) call = false;
      final event = eventForStep(step.code);
      if (coverage != null && (step.code == 16 || step.code == 17)) coverage.batchToggles++;
      final before = coordinator.state.encode();
      final transition = transitionCapture(
          coordinator.state,
          event,
          environment(coordinator.state,
              muted: fake.muted, batch: fake.batch, batchSuspended: fake.batchSuspended, call: call));
      final fault = faults.nextInt(8);
      if (fault == 0 && transition.state.encode() != before) {
        fake.failNextSnapshot = true;
        if (coverage != null) coverage.snapshot++;
      }
      if (fault == 1 && step.code == 3 && coordinator.state.phoneOwns) {
        fake.supersedeNextPolicy = true;
        if (coverage != null) coverage.policySuperseded++;
      }
      if (fault == 2 && step.code == 5 && coordinator.state.phase == CapturePhase.phonePaused) {
        fake.socket = false;
        fake.failNextOpen = true;
        if (coverage != null) coverage.socketOpen++;
      }
      final injectPhoneStart = fault == 4 &&
          step.code == 2 &&
          transition.effects.any((effect) => effect is RunStage && effect.stage is StartPhoneSessionStage);
      if (injectPhoneStart) fake.failNextPhoneStart = true;
      CaptureDispatchOutcome outcome;
      if (fault == 3 && transition.effects.isNotEmpty) {
        final held = fake.hold = Completer<void>();
        final first = coordinator.dispatch(event);
        final bleDrop = faults.nextInt(2) == 0;
        final queued = coordinator.dispatch(
            bleDrop ? const DeviceUpdated(null) : SocketError(StateError('socket error queued behind held effect')));
        if (coverage != null) {
          if (bleDrop) {
            coverage.heldBleDrop++;
          } else {
            coverage.heldSocketError++;
          }
        }
        await Future<void>.delayed(Duration.zero);
        if (coordinator.state.encode() != before) throw StateError('published owner before held effect completed');
        held.complete();
        outcome = await first;
        await queued;
      } else {
        outcome = await coordinator.dispatch(event);
      }
      final recoveredPendant = outcome.failed &&
          step.code == 2 &&
          coordinator.state.pendantOwns &&
          coordinator.state.suspended.isEmpty &&
          (coordinator.state.phase == CapturePhase.pendantPaused ? (!fake.ble && fake.muted) : fake.ble) &&
          !fake.mic &&
          coordinator.state.active?.recordingId == fake.recordingId;
      if (outcome.failed && coordinator.state.phase != CapturePhase.idle && !recoveredPendant) {
        throw StateError(
            'failed effect left an unowned or unrecovered capture: step=$step before=$before after=${coordinator.state.encode()} mic=${fake.mic} ble=${fake.ble} muted=${fake.muted} error=${outcome.error}');
      }
      if (injectPhoneStart) {
        if (fake.failNextPhoneStart || !outcome.failed) throw StateError('seeded phone-start fault was not exercised');
        if (coverage != null) coverage.failedPhoneStart++;
        if (recoveredPendant && coverage != null) coverage.recoveredPhoneStart++;
      }
      fake.failNextPhoneStart = false;
      fake.failNextOpen = false;
      fake.failNextSnapshot = false;
      fake.supersedeNextPolicy = false;
      verify(step);
    }
  } catch (error) {
    return error.toString();
  } finally {
    coordinator.dispose();
  }
  return null;
}

Future<List<ScriptStep>> shrinkEffects(List<ScriptStep> failing, String failure, int seed) async {
  var result = List<ScriptStep>.of(failing);
  var width = result.length ~/ 2;
  while (width >= 1) {
    var changed = false;
    for (var start = 0; start + width <= result.length; start++) {
      final candidate = [...result.take(start), ...result.skip(start + width)];
      if (await effectFailureFor(candidate, seed: seed) == failure) {
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
  test('128 seeded effect-port sequences inject held, failed and superseded effects across the event alphabet',
      () async {
    const codes = [
      0,
      0,
      1,
      2,
      2,
      2,
      3,
      3,
      4,
      4,
      5,
      5,
      6,
      7,
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      15,
      16,
      17,
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25,
      26,
      27,
      28,
      29
    ];
    const baseSeed = 0x5ca562;
    final coverage = FaultCoverage();
    for (var sequence = 0; sequence < 128; sequence++) {
      final seed = baseSeed + sequence;
      final random = XorShift32(seed);
      final events = List.generate(50 + random.nextInt(70), (_) => ScriptStep(codes[random.nextInt(codes.length)]));
      final failure = await effectFailureFor(events, seed: seed, coverage: coverage);
      if (failure != null) {
        final minimized = await shrinkEffects(events, failure, seed);
        fail('seed=$seed sequence=$sequence error=$failure\nminimized=${minimized.join(' -> ')}');
      }
    }
    expect(coverage.snapshot, greaterThan(0));
    expect(coverage.socketOpen, greaterThan(0));
    expect(coverage.policySuperseded, greaterThan(0));
    expect(coverage.failedPhoneStart, greaterThan(0));
    expect(coverage.recoveredPhoneStart, greaterThan(0));
    expect(coverage.heldSocketError, greaterThan(0));
    expect(coverage.heldBleDrop, greaterThan(0));
    expect(coverage.kills, greaterThan(0));
    expect(coverage.batchToggles, greaterThan(0));
  });

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
                    : 17 + draw % 13;
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
    (name: 'explicit phone restart mints a new conversation', steps: [2, 2], phase: CapturePhase.phoneLive),
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
    (
      name: 'speech-profile interim stop retains pendant until restarted phone finishes',
      steps: [0, 2, 29, 2, 3],
      phase: CapturePhase.pendantLive
    ),
    (
      name: 'speech-profile hold survives Omi call end without reopening pendant',
      steps: [0, 2, 29, 6, 7],
      phase: CapturePhase.idle
    ),
    (name: 'pause during an OS interruption survives its end', steps: [2, 13, 4, 14], phase: CapturePhase.phonePaused),
    (name: 'deferred Omi call does not pause a live phone mic', steps: [2, 6], phase: CapturePhase.phoneLive),
    (name: 'phone interruption restores the same owner', steps: [2, 13, 14], phase: CapturePhase.phoneLive),
    (name: 'no resumed pendant after disconnect during phone handoff', steps: [0, 2, 1, 3], phase: CapturePhase.idle),
    (
      name: 'Grok fixed: phone batch stop resumes a pendant connected mid-session',
      steps: [26, 0, 3],
      phase: CapturePhase.pendantLive
    ),
    (
      name: 'Grok fixed: transcription settings cannot hand phone socket to pendant',
      steps: [0, 2, 18],
      phase: CapturePhase.phoneLive
    ),
    (
      name: 'Grok fixed: suspended pendant honors latest resume intent',
      steps: [0, 6, 24, 25, 7],
      phase: CapturePhase.pendantLive
    ),
    (name: 'unowned device stop cannot tear down phone microphone', steps: [0, 2, 23], phase: CapturePhase.phoneLive),
    (
      name: 'deferred shared batch policy remains phone-owned while paused',
      steps: [16, 26, 4],
      phase: CapturePhase.phoneBatchPaused
    ),
  ]) {
    test(episode.name, () async {
      final model = SequenceModel();
      final fake = HarnessPorts();
      var call = false;
      late CaptureCoordinator coordinator;
      coordinator = CaptureCoordinator(
        ports: fake.ports,
        readEnvironment: () => environment(coordinator.state,
            muted: fake.muted, batch: fake.batch, batchSuspended: fake.batchSuspended, call: call),
      );
      try {
        for (final code in episode.steps) {
          model.step(ScriptStep(code));
          if (code == 6) call = true;
          if (code == 7) call = false;
          final event = eventForStep(code);
          final transition = transitionCapture(
              coordinator.state,
              event,
              environment(coordinator.state,
                  muted: fake.muted, batch: fake.batch, batchSuspended: fake.batchSuspended, call: call));
          final start = fake.log.length;
          final outcome = await coordinator.dispatch(event);
          expect(outcome.failed, isFalse, reason: '${episode.name}: event $code failed');
          final emitted = fake.log.skip(start).toList();
          for (final effect in transition.effects) {
            if (effect is RunStage) expect(emitted, contains('stage:${effect.stage.runtimeType}'));
            if (effect is MintRecording) {
              expect(emitted.where((line) => line.startsWith('mint:${effect.sessionKey}:')), hasLength(1));
            }
            if (effect is PolicyWrite) expect(emitted, contains('policy:${effect.muted}'));
          }
          expect(CaptureCoordinatorState.tryParse(fake.snapshot)?.encode(), coordinator.state.encode());
          if (coordinator.state.active case final active?) {
            expect(active.recordingId, isNotNull);
            expect(fake.recordingId, active.recordingId, reason: '${episode.name}: telemetry id at $code');
          }
          if (coordinator.state.pendantSuspension != null) expect(fake.ble, isFalse);
        }
        expect(coordinator.state.phase, episode.phase);
        expect(coordinator.state.sessionSeq, model.state.sessionSeq);
        expect(coordinator.state.active?.sessionKey, model.state.active?.sessionKey);
        expect(coordinator.state.suspended.length, model.state.suspended.length);
        expect(coordinator.state.pendantSuspension?.reason, model.state.pendantSuspension?.reason);
        expect(coordinator.state.callActive, model.state.callActive);
        expect(coordinator.state.awaitingPhoneResume, model.state.awaitingPhoneResume);
        if (coordinator.state.phase == CapturePhase.phonePaused) expect(fake.mic, isFalse);
        if (coordinator.state.phase == CapturePhase.pendantLive) expect(fake.ble, isTrue);
      } finally {
        coordinator.dispose();
      }
    });
  }

  test('a call during an interim onboarding stop cannot consume or duplicate pendant debt', () {
    final model = SequenceModel();
    for (final code in [2, 0, 29, 6, 3]) {
      model.step(ScriptStep(code));
    }
    expect(model.state.callActive, isTrue);
    expect(model.state.pendantOwns, isFalse);
    expect(model.state.suspended, hasLength(1));
    model.step(const ScriptStep(0));
    expect(model.state.suspended, hasLength(1));
    model.step(const ScriptStep(2));
    expect(model.state.suspended, hasLength(1));
  });

  test('call end cannot consume the speech-profile pendant hold', () async {
    final fake = HarnessPorts();
    var call = false;
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted, call: call),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    await coordinator.dispatch(const PhoneStartRequested());
    await coordinator
        .dispatch(const PhoneStopRequested(reason: 'user_stopped', userStop: true, resumeSuspendedPendant: false));
    expect(coordinator.state.awaitingPhoneResume, isTrue);
    final logBeforeCall = fake.log.length;
    call = true;
    await coordinator.dispatch(const CallStateChanged());
    call = false;
    await coordinator.dispatch(const CallStateChanged());
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(coordinator.state.awaitingPhoneResume, isTrue);
    expect(coordinator.state.pendantSuspension?.reason, SuspendReason.phone);
    expect(fake.ble, isFalse);
    expect(fake.log.skip(logBeforeCall).where((line) => line == 'ble:start' || line == 'stage:StartDeviceSessionStage'),
        isEmpty);
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(coordinator.state.awaitingPhoneResume, isTrue);
    expect(coordinator.state.suspended, hasLength(1));
    expect(fake.ble, isFalse);
    await coordinator.dispatch(const PhoneStartRequested());
    expect(coordinator.state.phase, CapturePhase.phoneLive);
    await coordinator.dispatch(const PhoneStopRequested(reason: 'user_stopped', userStop: true));
    expect(coordinator.state.phase, CapturePhase.pendantLive);
    expect(coordinator.state.suspended, isEmpty);
    expect(fake.ble, isTrue);
    expect(fake.recordingId, coordinator.state.active?.recordingId);
    coordinator.dispose();
  });

  test('snapshot failure after pendant takeover restores a fresh pendant recording', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    final originalId = fake.recordingId;
    fake.failNextSnapshot = true;
    final result = await coordinator.dispatch(const PhoneStartRequested());
    expect(result.failed, isTrue);
    expect(coordinator.state.phase, CapturePhase.pendantLive);
    expect(coordinator.state.suspended, isEmpty);
    expect(fake.ble, isTrue);
    expect(fake.mic, isFalse);
    expect(fake.recordingId, isNot(originalId));
    expect(fake.recordingId, coordinator.state.active?.recordingId);
    expect(CaptureCoordinatorState.tryParse(fake.snapshot)?.encode(), coordinator.state.encode());
    coordinator.dispose();
  });

  test('failed phone restart over onboarding debt never releases the held pendant', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    await coordinator.dispatch(const PhoneStartRequested());
    await coordinator
        .dispatch(const PhoneStopRequested(reason: 'user_stopped', userStop: true, resumeSuspendedPendant: false));
    final logBefore = fake.log.length;
    fake.failNextPhoneStart = true;
    final result = await coordinator.dispatch(const PhoneStartRequested());
    expect(result.failed, isTrue);
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(coordinator.state.awaitingPhoneResume, isTrue);
    expect(coordinator.state.pendantSuspension?.reason, SuspendReason.phone);
    expect(fake.ble, isFalse);
    expect(fake.log.skip(logBefore).where((line) => line == 'ble:start' || line == 'stage:StartDeviceSessionStage'),
        isEmpty);
    coordinator.dispose();
  });

  test('batch roll permission denial does not persist the new mode or stop the live phone', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted, batch: fake.batch),
    );
    await coordinator.dispatch(const PhoneStartRequested());
    final before = coordinator.state.encode();
    final id = fake.recordingId;
    final logBefore = fake.log.length;
    fake.permitPhone = false;
    final result = await coordinator.dispatch(const BatchModeSetRequested(enabled: true));
    expect(result.failed, isFalse);
    expect(result.result, isFalse);
    expect(coordinator.state.encode(), before);
    expect(fake.batch, isFalse);
    expect(fake.mic, isTrue);
    expect(fake.recordingId, id);
    expect(fake.log.skip(logBefore).where((line) => line == 'stage:BatchModeStage'), isEmpty);
    coordinator.dispose();
  });

  test('unowned non-user phone stop with resume intent consumes onboarding debt once', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    await coordinator.dispatch(const PhoneStartRequested());
    await coordinator
        .dispatch(const PhoneStopRequested(reason: 'user_stopped', userStop: true, resumeSuspendedPendant: false));
    final result = await coordinator
        .dispatch(const PhoneStopRequested(reason: 'temporary_stop', userStop: false, resumeSuspendedPendant: true));
    expect(result.failed, isFalse);
    expect(coordinator.state.phase, CapturePhase.pendantLive);
    expect(coordinator.state.suspended, isEmpty);
    expect(coordinator.state.awaitingPhoneResume, isFalse);
    expect(fake.ble, isTrue);
    expect(fake.recordingId, coordinator.state.active?.recordingId);
    coordinator.dispose();
  });

  test('identical batch toggle leaves session, telemetry and physical mic untouched', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted, batch: fake.batch),
    );
    await coordinator.dispatch(const PhoneStartRequested());
    await coordinator.dispatch(const BatchModeSetRequested(enabled: true));
    final before = coordinator.state.encode();
    final id = fake.recordingId;
    final logLength = fake.log.length;
    expect((await coordinator.dispatch(const BatchModeSetRequested(enabled: true))).result, isTrue);
    expect(coordinator.state.encode(), before);
    expect(fake.recordingId, id);
    expect(fake.log.skip(logLength).where((entry) => entry.startsWith('stage:') || entry == 'mic:start'), isEmpty);
    coordinator.dispose();
  });

  test('idle resume with only a connected device cannot stream without claiming ownership', () {
    final initial = transitionCapture(
            CaptureCoordinatorState.idle(), DeviceUpdated(pendant), environment(CaptureCoordinatorState.idle()))
        .state;
    expect(initial.phase, CapturePhase.idle);
    expect(initial.connectedDevice, isNotNull);
    final resumed = transitionCapture(initial, const ResumeCaptureRequested(), environment(initial, muted: true));
    expect(resumed.state.phase, CapturePhase.idle);
    expect(resumed.effects.whereType<RunStage>().where((effect) => effect.stage is ResumeDeviceTailStage), isEmpty);
    expect(resumed.effects.whereType<BleStreamStart>(), isEmpty);
  });

  test('interrupted phone user pause emits mute and mic stop and survives interruption end', () {
    final model = SequenceModel();
    model.step(const ScriptStep(2));
    model.step(const ScriptStep(13));
    final id = model.state.active?.sessionKey;
    final transition =
        transitionCapture(model.state, const PauseCaptureRequested(), environment(model.state, muted: model.muted));
    expect(transition.state.phase, CapturePhase.phonePaused);
    expect(transition.effects.whereType<NativeMicStop>(), hasLength(1));
    expect(transition.effects.whereType<PolicyWrite>().single.muted, isTrue);
    model.step(const ScriptStep(4));
    model.step(const ScriptStep(14));
    expect(model.state.phase, CapturePhase.phonePaused);
    expect(model.state.active?.sessionKey, id);
  });

  test('permission denial leaves the live pendant and its recording unprocessed', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    final before = coordinator.state.encode();
    final id = fake.recordingId;
    fake.permitPhone = false;
    final logLength = fake.log.length;
    final outcome = await coordinator.dispatch(const PhoneStartRequested());
    expect(outcome.failed, isFalse);
    expect(outcome.result, isFalse);
    expect(coordinator.state.encode(), before);
    expect(fake.recordingId, id);
    expect(fake.ble, isTrue);
    expect(fake.log.skip(logLength), isNot(contains('stage:SuspendPendantStage')));
    coordinator.dispose();
  });

  test('native phone start failure restores a suspended pendant under a fresh recording', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    final oldId = fake.recordingId;
    fake.failNextPhoneStart = true;
    final result = await coordinator.dispatch(const PhoneStartRequested());
    expect(result.failed, isTrue);
    expect(coordinator.state.phase, CapturePhase.pendantLive);
    expect(coordinator.state.suspended, isEmpty);
    expect(fake.ble, isTrue);
    expect(fake.mic, isFalse);
    expect(coordinator.state.active?.recordingId, fake.recordingId);
    expect(fake.recordingId, isNot(oldId));
    coordinator.dispose();
  });

  test('superseded stop cannot expose the paused batch writer under an unmuted policy', () async {
    final fake = HarnessPorts()..batch = true;
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted, batch: fake.batch),
    );
    await coordinator.dispatch(const PhoneStartRequested());
    await coordinator.dispatch(const PauseCaptureRequested());
    expect(coordinator.state.phase, CapturePhase.phoneBatchPaused);
    expect(fake.mic, isTrue);
    expect(fake.muted, isTrue);
    fake.supersedeNextPolicy = true;
    final result = await coordinator.dispatch(const PhoneStopRequested(reason: 'user_stopped', userStop: true));
    expect(result.failed, isTrue);
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(fake.mic, isFalse);
    expect(fake.ble, isFalse);
    expect(fake.socket, isFalse);
    expect(CaptureCoordinatorState.tryParse(fake.snapshot)?.phase, CapturePhase.idle);
    coordinator.dispose();
  });

  test('abandoned permission preflight clears its grant before the next event', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    fake.permitPhone = false;
    final denied = await coordinator.dispatch(const PhoneStartRequested());
    expect(denied.result, isFalse);
    expect(fake.prefetchedGrant, isFalse);
    expect(fake.permissionGrantClears, 1);
    fake.permitPhone = true;
    final started = await coordinator.dispatch(const PhoneStartRequested());
    expect(started.result, isTrue);
    expect(fake.prefetchedGrant, isFalse);
    expect(fake.permissionGrantClears, 2);
    coordinator.dispose();
  });

  test('a no-op keepalive never writes a snapshot or fails closed on a stale injected prefs fault', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(const PhoneStartRequested());
    final snapshots = fake.log.where((entry) => entry == 'snapshot').length;
    fake.failNextSnapshot = true;
    final result = await coordinator.dispatch(const KeepAliveTick());
    expect(result.failed, isFalse);
    expect(coordinator.state.phase, CapturePhase.phoneLive);
    expect(fake.log.where((entry) => entry == 'snapshot'), hasLength(snapshots));
    expect(fake.mic, isTrue);
    fake.failNextSnapshot = false;
    coordinator.dispose();
  });

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

  test('a superseded finish never tears down the phone or resumes its pendant', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    await coordinator.dispatch(const PhoneStartRequested());
    expect(fake.mic, isTrue);
    final previous = coordinator.state.active?.recordingId;
    fake.supersedeNextPolicy = true;
    final outcome = await coordinator.dispatch(const FinishRequested());
    expect(outcome.result, isFalse);
    expect(coordinator.state.phase, CapturePhase.phoneLive);
    expect(coordinator.state.active?.recordingId, previous);
    expect(coordinator.state.pendantSuspension?.reason, SuspendReason.phone);
    expect(fake.ble, isFalse);
    expect(fake.mic, isTrue);
    coordinator.dispose();
  });

  test('BLE drop queued during a delayed pendant pause cannot stream until resumed', () async {
    final fake = HarnessPorts();
    late CaptureCoordinator coordinator;
    coordinator = CaptureCoordinator(
      ports: fake.ports,
      readEnvironment: () => environment(coordinator.state, muted: fake.muted),
    );
    await coordinator.dispatch(DeviceStartRequested(device: pendant));
    final held = fake.hold = Completer<void>();
    final pause = coordinator.dispatch(const DevicePauseRequested());
    final drop = coordinator.dispatch(const DeviceUpdated(null));
    await Future<void>.delayed(Duration.zero);
    expect(fake.log.last, 'policy:true');
    held.complete();
    expect((await pause).failed, isFalse);
    expect((await drop).failed, isFalse);
    expect(coordinator.state.phase, CapturePhase.idle);
    expect(fake.ble, isFalse);
    expect(fake.socket, isFalse);
    coordinator.dispose();
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

  Future<void> withReviewWorld(Future<void> Function(CaptureReplayWorld world) body) async {
    final directory = await Directory.systemTemp.createTemp('capture_coordinator_review_');
    final world = await CaptureReplayWorld.boot(tempDir: directory);
    try {
      await body(world);
    } finally {
      await world.dispose();
      if (directory.existsSync()) directory.deleteSync(recursive: true);
    }
  }

  test('real controller rejects denied phone permission before touching the pendant', () async {
    await withReviewWorld((world) async {
      world.deviceConnection = ScriptedDeviceConnection();
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      final id = world.controller.activeRecordingId;
      final sockets = world.socketCreates;
      world.allowMic = false;
      await expectLater(world.controller.streamRecording(), throwsA(isA<StateError>()));
      await world.settle();
      expect(world.controller.liveCaptureSource, 'omi');
      expect(world.controller.activeRecordingId, id);
      expect(world.controller.pendantPausedForPhone, isFalse);
      expect(world.hostApi.startCalls, 0);
      expect(world.socketCreates, sockets);
      expect(world.processCalls, 0);
    });
  });

  test('denied speech-profile phone resume keeps pendant suspended until an admitted stop', () async {
    await withReviewWorld((world) async {
      final connection = world.deviceConnection = ScriptedDeviceConnection();
      await world.controller.streamDeviceRecording(device: pendant);
      await world.controller.streamRecording();
      await world.controller.stopStreamRecording(resumeHandedOffPendant: false);
      await world.settle();
      expect(world.controller.liveCaptureSource, isNull);
      expect(world.controller.pendantPausedForPhone, isTrue);
      expect(connection.openAudioSubscriptions, 0);
      world.allowMic = false;
      await expectLater(world.controller.streamRecording(), throwsA(isA<StateError>()));
      await world.settle();
      expect(world.controller.liveCaptureSource, isNull);
      expect(world.controller.pendantPausedForPhone, isTrue);
      expect(connection.openAudioSubscriptions, 0);
      world.allowMic = true;
      await world.controller.streamRecording();
      await world.controller.stopStreamRecording();
      await world.settle();
      expect(world.controller.liveCaptureSource, 'omi');
      expect(world.controller.pendantPausedForPhone, isFalse);
      expect(connection.openAudioSubscriptions, 1);
    });
  });

  test('native mic startup failure restores the pendant with a new recording', () async {
    await withReviewWorld((world) async {
      world.deviceConnection = ScriptedDeviceConnection();
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      final oldId = world.controller.activeRecordingId;
      world.hostApi.nextStartError = () => StateError('injected native start failure');
      await expectLater(world.controller.streamRecording(), throwsA(isA<StateError>()));
      await world.settle();
      expect(world.controller.liveCaptureSource, 'omi');
      expect(world.controller.pendantPausedForPhone, isFalse);
      expect(world.controller.activeRecordingId, isNot(oldId));
      expect(world.controller.activeRecordingId, isNotNull);
      expect(world.hostApi.nativeRecording, isFalse);
    });
  });

  test('muted pendant connect retains a telemetry recording id across resume', () async {
    await withReviewWorld((world) async {
      await world.controller.pauseDeviceRecording();
      world.deviceConnection = ScriptedDeviceConnection();
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      final pausedId = world.controller.activeRecordingId;
      expect(pausedId, isNotNull);
      expect(world.controller.liveCaptureSource, 'omi');
      await world.controller.resumeDeviceRecording();
      await world.settle();
      expect(world.controller.activeRecordingId, pausedId);
      expect(world.controller.liveCaptureSource, 'omi');
    });
  });

  test('real mode change mints a different recording id and identical toggles do not roll', () async {
    await withReviewWorld((world) async {
      await world.startLiveCapture();
      world.emitNativeState(PhoneMicCaptureState.running);
      await world.settle();
      final liveId = world.controller.activeRecordingId;
      expect(liveId, isNotNull);
      expect(await world.controller.setBatchMode(true), isTrue);
      await world.settle();
      final batchId = world.controller.activeRecordingId;
      expect(batchId, isNotNull);
      expect(batchId, isNot(liveId));
      expect(world.hostApi.lastStartMode, PhoneMicCaptureMode.batch);
      final startCalls = world.hostApi.startCalls;
      expect(await world.controller.setBatchMode(true), isTrue);
      expect(world.controller.activeRecordingId, batchId);
      expect(world.hostApi.startCalls, startCalls);
      expect(await world.controller.setBatchMode(false), isTrue);
      expect(world.controller.activeRecordingId, isNot(batchId));
    });
  });

  test('public controller getters publish owner only after a held native start completes', () async {
    await withReviewWorld((world) async {
      final hold = world.hostApi.holdNextStart = Completer<void>();
      final entered = world.hostApi.nextStartEntered = Completer<void>();
      final start = world.controller.streamRecording();
      try {
        await entered.future.timeout(const Duration(seconds: 15));
        expect(world.hostApi.startCalls, 1);
        expect(world.controller.liveCaptureSource, isNull);
        expect(world.controller.isPhoneMicPaused, isFalse);
        expect(world.controller.isPhoneMicBatchRecording, isFalse);
        hold.complete();
        await start;
        expect(world.controller.liveCaptureSource, 'phone');
      } finally {
        if (!hold.isCompleted) hold.complete();
        await start;
      }
    });
  });

  test('real stall restart is joined by queued pause and cannot reopen the mic afterward', () async {
    await withReviewWorld((world) async {
      await world.startLiveCapture();
      world.emitNativeState(PhoneMicCaptureState.running);
      world.injectAudioFrames(1, sessionId: world.hostApi.lastStartSessionId!);
      await world.settle();
      final hold = world.hostApi.holdNextStart = Completer<void>();
      final entered = world.hostApi.nextStartEntered = Completer<void>();
      final stall = world.elapse(const Duration(seconds: 4));
      try {
        await entered.future.timeout(const Duration(seconds: 15));
        expect(world.hostApi.startCalls, 2);
        final pause = world.controller.pauseCapture();
        hold.complete();
        await stall;
        await pause;
        await world.settle();
        expect(world.controller.isPhoneMicPaused, isTrue);
        expect(world.hostApi.nativeRecording, isFalse);
        expect(world.hostApi.startCalls, 2);
        await pumpEventQueue();
        expect(world.hostApi.nativeRecording, isFalse);
      } finally {
        if (!hold.isCompleted) hold.complete();
        await stall;
      }
    });
  });

  test('normal pendant connect and same-device refresh keep sending BLE audio to the socket', () async {
    await withReviewWorld((world) async {
      final connection = world.deviceConnection = ScriptedDeviceConnection();
      world.controller.updateRecordingDevice(pendant);
      await world.controller.pendingSourceSwitch;
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      final transport = world.socket;
      expect(transport, isNotNull);
      expect(connection.openAudioSubscriptions, 1);
      connection.emitAudio(value: 1);
      expect(transport!.sentBinary, hasLength(1));
      world.controller.updateRecordingDevice(pendant);
      await world.controller.pendingSourceSwitch;
      connection.emitAudio(value: 2);
      expect(transport.sentBinary, hasLength(2), reason: 'same-id metadata must not retire installed audio');
      world.controller.updateRecordingDevice(pendant.copyWith(type: DeviceType.openglass));
      await world.controller.pendingSourceSwitch;
      connection.emitAudio(value: 3);
      expect(transport.sentBinary, hasLength(3), reason: 'post-getDeviceInfo normalization must preserve audio');
      expect(world.controller.liveCaptureSource, 'openglass');
      expect(connection.openAudioSubscriptions, 1);
    });
  });

  test('settings and reconnect under an Omi call never open a pendant socket', () async {
    await withReviewWorld((world) async {
      world.deviceConnection = ScriptedDeviceConnection();
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      world.omiCall.value = PhoneCallState.active;
      await world.controller.pendingSourceSwitch;
      final sockets = world.socketCreates;
      world.controller.updateRecordingDevice(pendant);
      await world.controller.onTranscriptionSettingsChanged();
      world.controller.onConnected();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.liveCaptureSource, isNull);
      expect(world.controller.pendantPausedForCall, isTrue);
      expect(world.socketCreates, sockets);
    });
  });

  test('real call mutes the Transcribe Later pendant writer and resumes its recording', () async {
    await withReviewWorld((world) async {
      expect(await world.controller.setBatchMode(true), isTrue);
      world.deviceConnection = ScriptedDeviceConnection();
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      final id = world.controller.activeRecordingId;
      expect(id, isNotNull);
      expect(world.controller.isPendantBatchRecording, isTrue);
      world.omiCall.value = PhoneCallState.active;
      await world.controller.pendingSourceSwitch;
      expect(world.controller.pendantPausedForCall, isTrue);
      expect(SharedPreferencesUtil().capturePolicy.muted, isTrue);
      world.omiCall.value = PhoneCallState.ended;
      await world.controller.pendingSourceSwitch;
      expect(world.controller.isPendantBatchRecording, isTrue);
      expect(SharedPreferencesUtil().capturePolicy.muted, isFalse);
      expect(world.controller.activeRecordingId, id);
    });
  });

  test('real killed phone pause restores policy and never resurrects an owner', () async {
    await withReviewWorld((world) async {
      await world.startLiveCapture();
      await world.controller.pauseCapture();
      await world.settle();
      expect(world.controller.isPhoneMicPaused, isTrue);
      world.killProcess();
      await world.reconstructProcess();
      await world.controller.pendingSourceSwitch;
      expect(world.controller.liveCaptureSource, isNull);
      expect(world.hostApi.nativeRecording, isFalse);
      expect(SharedPreferencesUtil().capturePolicy.muted, isFalse);
    });
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
