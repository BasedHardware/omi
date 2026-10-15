import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/capture/capture_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  Future<void> connect() async {
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  }

  Future<void> elapse(Duration duration) async {
    await world.elapse(duration);
    await world.controller.pendingSourceSwitch;
    await world.settle();
  }

  // Historical state from #20837. New capture never creates this marker;
  // recovery must remain covered for users upgrading from that version.
  Future<void> legacySilencePause() async {
    await world.controller.pauseCapture();
    await SharedPreferencesUtil().saveBool('uplinkSilencePaused', true);
    await world.settle();
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('tiered_capture_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
    await connect();
  });
  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  test('silence beyond the deadline keeps every packet flowing through BLE, socket and WAL', () async {
    world.uploads.failAll = true;
    final socket = world.socket!;
    final recording = world.controller.activeRecordingId;
    for (var second = 0; second < 300; second++) {
      world.deviceConnection!.emitAudio(value: second & 255);
      await elapse(const Duration(seconds: 1));
    }
    expect(world.controller.silencePaused, false);
    expect(world.controller.isPaused, false);
    expect(world.controller.activeRecordingId, recording);
    expect(socket.closeCalls, 0);
    expect(socket.sentBinary, hasLength(300));
    for (var i = 0; i < 300; i++) {
      expect(socket.sentBinary[i], List<int>.filled(80, i & 255));
    }
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
    expect(world.processCalls, 0);
    final retained = await world.wal.syncs.phone.getAllWals();
    expect(retained.fold<int>(0, (count, wal) => count + wal.totalFrames), 300);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    await connect();
    expect(world.controller.isPaused, false);
    expect(world.socket!.status, PureSocketStatus.connected);
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
  });

  test('queued silence event cannot change ownership or run pause effects', () {
    final state = CaptureCoordinatorState.idle().copyWith(phase: CapturePhase.pendantLive);
    final transition = transitionCapture(
        state,
        const UplinkSilenceElapsed(null),
        CaptureEnvironment(
            policyMuted: false,
            paused: false,
            batchModeEnabled: false,
            batchModeSuspendedForOnboarding: false,
            deviceSupportsTranscribeLater: false,
            networkConnected: true,
            signedIn: () => true,
            phoneMicSupportsBatch: false,
            transcriptReady: true,
            socketConnected: true,
            deviceServiceReady: true,
            callActive: false,
            deviceRecording: true,
            micCapturing: false,
            uplinkSilenceExpired: true));
    expect(transition.state, same(state));
    expect(transition.effects, isEmpty);
  });

  test('upgrade clears a persisted automatic pause, while explicit mute still survives restart', () async {
    await legacySilencePause();
    world.disposeController();
    await world.reconstructProcess();
    expect(world.controller.silencePaused, false);
    expect(world.controller.isPaused, false);
    await connect();
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
    await world.controller.pauseCapture();
    world.disposeController();
    await world.reconstructProcess();
    expect(world.controller.isPaused, true);
    expect(world.controller.silencePaused, false);
  });

  test('shared WAL/socket payload owns bytes before the BLE producer reuses its buffer', () async {
    final raw = [1, 0, 0, ...List<int>.generate(80, (i) => i)];
    world.deviceConnection!.emitRawAudio(raw);
    final saved = world.wal.syncs.phone.testFrames.last;
    expect(identical(saved.payload, world.socket!.sentBinary.last), true);
    raw.fillRange(0, raw.length, 255);
    expect(saved.payload, List<int>.generate(80, (i) => i));
    expect(world.socket!.sentBinary.last, saved.payload);
    await world.wal.syncs.phone.finalizeCurrentSession();
    final wals = await world.wal.syncs.phone.getAllWals();
    final disk = wals.where((w) => w.storage == WalStorage.disk).single;
    final bytes = await File('${directory.path}/${disk.filePath}').readAsBytes();
    expect(bytes, [80, 0, 0, 0, ...List<int>.generate(80, (i) => i)]);
  });

  for (final foreground in [false, true]) {
    for (final control in ['resume', 'doubleTap', 'liveActivity']) {
      test('resume during reconnect drain restores uplink (foreground=$foreground, control=$control)', () async {
        await legacySilencePause();
        expect(world.controller.silencePaused, true);
        expect(world.controller.keepAliveScheduledForTesting, false);
        final socketCount = world.sockets.length;
        final draining = Completer<void>();
        final release = Completer<void>();
        final coordinator = RecordingTransferCoordinator(
          reconcile: () async {},
          discover: () async {},
          refreshPending: () async {},
          drain: () async {
            draining.complete();
            await release.future;
            return const RecordingTransferDrainResult.skipped();
          },
          autoUploadEnabled: () => true,
        )..setForeground(foreground);
        final wake = coordinator.wake(WakeTrigger.deviceConnected);
        await draining.future;
        Future<void>? resume;
        try {
          expect(SyncWakeScope.syncOnly, true);
          if (control == 'doubleTap') {
            SharedPreferencesUtil().doubleTapAction = 1;
            world.controller.handleButtonEventForTesting(pendant.id, 2);
          } else if (control == 'liveActivity') {
            resume = world.controller.performSystemSurfaceAction(
              'resume',
              recordingId: world.controller.activeRecordingId!,
              conversationRevision: world.controller.systemSurfaceConversationRevision,
            );
          } else {
            resume = world.controller.resumeCapture();
          }
          await world.settle();
          expect(world.controller.silencePaused, true);
          expect(world.controller.isPaused, true);
          expect(world.controller.keepAliveScheduledForTesting, false);
          expect(world.sockets.length, socketCount);
          expect(world.deviceConnection!.openAudioSubscriptions, 0);
        } finally {
          release.complete();
          await wake;
          coordinator.dispose();
        }
        await resume;
        await world.settle();
        await world.controller.pendingSourceSwitch;
        expect(world.controller.silencePaused, false);
        expect(world.controller.isPaused, false);
        expect(world.sockets.length, socketCount + 1);
        expect(world.socket!.status, PureSocketStatus.connected);
        expect(world.deviceConnection!.openAudioSubscriptions, 1);
        expect(world.controller.keepAliveScheduledForTesting, true);
      });
    }
  }

  test('changing silence timeout and speech cannot arm an automatic pause', () async {
    SharedPreferencesUtil().conversationSilenceDuration = 300;
    await connect();
    await elapse(const Duration(seconds: 200));
    world.controller.onSegmentReceived([
      TranscriptSegment(
          id: 'speech',
          text: 'hello',
          speaker: 'SPEAKER_0',
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: []),
    ]);
    await world.settle();
    await elapse(const Duration(seconds: 200));
    expect(world.controller.isPaused, false);
    world.deviceConnection!.emitAudio();
    await elapse(const Duration(seconds: 100));
    expect(world.controller.silencePaused, false);
  });

  for (final charging in [false, true]) {
    test('${charging ? 'charging' : 'foreground'} resumes silence as a fresh session but respects manual mute',
        () async {
      await legacySilencePause();
      final recording = world.controller.activeRecordingId;
      final sockets = world.sockets.length;
      if (charging) {
        world.controller.onChargingStarted();
      } else {
        world.controller.onAppResumed();
      }
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.isPaused, false);
      expect(world.controller.silencePaused, false);
      expect(world.controller.activeRecordingId, isNot(recording));
      expect(world.sockets.length, sockets + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      await world.controller.pauseCapture();
      world.controller.onChargingStarted();
      world.controller.onAppResumed();
      await world.settle();
      expect(world.controller.isPaused, true);
      expect(world.sockets.length, sockets + 1);
    });
  }

  test('manual pause takes over silence reason and prevents auto resume', () async {
    await legacySilencePause();
    await world.controller.pauseCapture();
    expect(world.controller.silencePaused, false);
    await world.controller.resumeAfterSilence();
    expect(world.controller.isPaused, true);
  });

  test('late transcript delivery cannot reopen a manually paused capture', () async {
    await world.controller.pauseCapture();
    await world.controller.pendingSourceSwitch;
    world.controller.onSegmentReceived([
      TranscriptSegment(
          id: 'late',
          text: 'still speaking',
          speaker: null,
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: []),
    ]);
    await world.settle();
    expect(world.controller.isPaused, true);
  });
}
