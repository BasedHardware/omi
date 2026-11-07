import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_pause_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  });
  tearDown(() async {
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  for (final deviceControl in [false, true]) {
    test('pendant pause closes socket and resume opens it (device control: $deviceControl)', () async {
      final socket = world.socket!;
      if (deviceControl) {
        await world.controller.pauseDeviceRecording();
      } else {
        await world.controller.pauseCapture();
      }
      await world.settle();
      expect(socket.closeCalls, 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 0);
      expect(world.controller.keepAliveScheduledForTesting, false);
      final count = world.sockets.length;
      await world.controller.onTranscriptionSettingsChanged();
      await world.controller.changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16);
      await world.controller.streamDeviceRecording(device: pendant);
      await world.elapse(const Duration(seconds: 30));
      expect(world.sockets.length, count);
      expect(world.controller.isPaused, true);
      await world.controller.resumeDeviceRecording();
      await world.settle();
      expect(world.sockets.length, count + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
    });
  }

  test('batch-mode pause freezes the card timer and resume does not count the paused time', () async {
    // The setUp world owns process-global state (SharedPreferences backing
    // store, path_provider handler, WAL handles). Dispose it before booting a
    // second world, or the harness retargets the first one onto the new state.
    await world.dispose();
    final timerDirectory = await Directory.systemTemp.createTemp('capture_timer_');
    final timerWorld = await CaptureReplayWorld.boot(
      tempDir: timerDirectory,
      initialPrefs: {'batchModeEnabled': true},
    );
    timerWorld.deviceConnection = ScriptedDeviceConnection();
    try {
      await timerWorld.controller.streamDeviceRecording(device: pendant);
      await timerWorld.settle();

      await timerWorld.elapse(const Duration(seconds: 5));
      final running = timerWorld.controller.offlineRecordingElapsedSeconds;
      expect(running, isNotNull, reason: 'a live session must expose elapsed seconds');

      await timerWorld.controller.toggleOfflineMute();
      await timerWorld.settle();
      final frozen = timerWorld.controller.offlineRecordingElapsedSeconds;
      expect(frozen, isNotNull);

      await timerWorld.elapse(const Duration(seconds: 20));
      expect(
        timerWorld.controller.offlineRecordingElapsedSeconds,
        frozen,
        reason: 'the timer must stay frozen while muted',
      );

      await timerWorld.controller.toggleOfflineMute();
      await timerWorld.settle();
      expect(
        timerWorld.controller.offlineRecordingElapsedSeconds,
        frozen,
        reason: 'the paused interval must not be added to the elapsed time',
      );

      await timerWorld.elapse(const Duration(seconds: 3));
      expect(
        timerWorld.controller.offlineRecordingElapsedSeconds,
        frozen! + 3,
        reason: 'the timer resumes from the frozen value',
      );
    } finally {
      await timerWorld.dispose();
      // The temp directory is left for the OS to reclaim: the WAL writer can
      // still be flushing after dispose returns, and deleting underneath it
      // fails the test with an unrelated PathNotFoundException.
    }
  });

  test('pendant batch mode pause sets recordingState to pause, freezes elapsed timer, and resume restores deviceRecord',
      () async {
    SharedPreferencesUtil().batchModeEnabled = true;
    world.controller.updateRecordingState(RecordingState.deviceRecord);
    expect(world.controller.offlineMuted, false);

    await world.controller.toggleOfflineMute();
    await world.settle();

    expect(world.controller.offlineMuted, true);
    expect(world.controller.recordingState, RecordingState.pause);
    expect(world.controller.isPaused, true);

    await world.controller.toggleOfflineMute();
    await world.settle();

    expect(world.controller.offlineMuted, false);
    expect(world.controller.recordingState, RecordingState.deviceRecord);
    expect(world.controller.isPaused, false);
  });

  test('relaunch while pendant is paused restores paused pendant ownership and keeps Pause/Resume controls available',
      () async {
    await world.controller.pauseCapture();
    await world.settle();
    expect(world.controller.isPaused, isTrue);
    expect(world.controller.recordingState, RecordingState.pause);

    world.killProcess();
    await world.reconstructProcess();
    world.deviceConnection = ScriptedDeviceConnection();

    // Before streamDeviceRecording runs, connected Omi pendant while paused is restorable,
    // whereas an unsupported device type (e.g. limitless) is not pause-capable.
    expect(world.controller.liveCaptureSource, isNull);
    expect(EpisodePresentation.hasActiveOrPausedPendantCapture(world.controller, connectedDevice: pendant), isTrue);
    expect(EpisodePresentation.canPause(world.controller, connectedDevice: pendant), isTrue);
    final limitless = pendant.copyWith(type: DeviceType.limitless);
    expect(EpisodePresentation.canPause(world.controller, connectedDevice: limitless), isFalse);

    // Foregrounding while capturePolicy.muted is true must not auto-start an idle pendant.
    world.controller.updateRecordingDevice(pendant);
    world.controller.onAppForegrounded();
    await world.settle();
    expect(world.controller.liveCaptureSource, isNull);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);

    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();

    expect(world.controller.isPaused, isTrue);
    expect(world.controller.recordingState, RecordingState.pause);
    expect(world.controller.liveCaptureSource, 'omi');
    expect(EpisodePresentation.canPause(world.controller), isTrue);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);

    await world.controller.resumeCapture();
    await world.settle();

    expect(world.controller.isPaused, isFalse);
    expect(world.controller.recordingState, RecordingState.deviceRecord);
    expect(world.controller.liveCaptureSource, 'omi');
    expect(EpisodePresentation.canPause(world.controller), isTrue);
    expect(world.deviceConnection!.openAudioSubscriptions, 1);

    await world.controller.stopStreamDeviceRecording();
    await world.settle();
    world.controller.updateRecordingDevice(pendant);
    expect(world.controller.liveCaptureSource, isNull);
    expect(world.controller.isPaused, isFalse);
    expect(EpisodePresentation.hasActiveOrPausedPendantCapture(world.controller, connectedDevice: pendant), isFalse);
    expect(EpisodePresentation.canPause(world.controller, connectedDevice: pendant), isFalse);
  });

  test('capabilityNormalizedDevice ignores empty or disconnected pairedDevice sentinel on relaunch', () {
    final deviceProvider = DeviceProvider();
    addTearDown(deviceProvider.dispose);

    deviceProvider.pairedDevice = BtDevice.empty();
    deviceProvider.connectedDevice = null;
    expect(deviceProvider.capabilityNormalizedDevice, isNull);

    deviceProvider.pairedDevice = pendant;
    deviceProvider.connectedDevice = null;
    expect(deviceProvider.capabilityNormalizedDevice, isNull);

    deviceProvider.connectedDevice = pendant;
    deviceProvider.pairedDevice = BtDevice.empty();
    expect(deviceProvider.capabilityNormalizedDevice?.id, pendant.id);

    final glass = pendant.copyWith(type: DeviceType.openglass);
    deviceProvider.pairedDevice = glass;
    expect(deviceProvider.capabilityNormalizedDevice?.type, DeviceType.openglass);
  });
}
