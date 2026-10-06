import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/sockets/pure_socket.dart';
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

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('tiered_capture_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    await connect();
  });
  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  test('default 120 second deadline pauses BLE and socket, finalizes once, and stays paused on reconnect', () async {
    final socket = world.socket!;
    await elapse(const Duration(seconds: 119));
    expect(world.controller.isPaused, false);
    await elapse(const Duration(seconds: 1));
    expect(world.controller.silencePaused, true);
    expect(world.controller.isPaused, true);
    expect(socket.closeCalls, 1);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
    expect(world.processCalls, 1);
    final sockets = world.sockets.length;
    world.controller.updateRecordingDevice(null);
    await world.settle();
    await connect();
    await world.controller.streamDeviceRecording(); // Home's check-only start
    await elapse(const Duration(seconds: 150));
    expect(world.controller.isPaused, true);
    expect(world.sockets.length, sockets);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
  });

  for (final foreground in [false, true]) {
    for (final control in ['resume', 'doubleTap', 'liveActivity']) {
      test('resume during reconnect drain restores uplink (foreground=$foreground, control=$control)', () async {
        await elapse(const Duration(seconds: 120));
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

  test('speech resets the configured deadline, audio packets do not', () async {
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
    expect(world.controller.silencePaused, true);
  });

  for (final charging in [false, true]) {
    test('${charging ? 'charging' : 'foreground'} resumes silence as a fresh session but respects manual mute',
        () async {
      await elapse(const Duration(seconds: 120));
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
    await elapse(const Duration(seconds: 120));
    await world.controller.pauseCapture();
    expect(world.controller.silencePaused, false);
    await world.controller.resumeAfterSilence();
    expect(world.controller.isPaused, true);
  });

  test('late transcript delivery cannot reopen an expired capture', () async {
    await elapse(const Duration(seconds: 120));
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
