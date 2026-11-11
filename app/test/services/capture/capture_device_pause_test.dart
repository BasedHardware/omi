import 'dart:io';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  bool rejectMuteWrite = false;
  bool? reportedMute;
  final muteWrites = <bool>[];

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_pause_');
    rejectMuteWrite = false;
    reportedMute = null;
    muteWrites.clear();
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      pendantCodec: BleAudioCodec.opus,
      deviceMuteReader: (_) async => reportedMute,
      deviceMuteWriter: (id, muted) async {
        expect(id, pendant.id);
        // The pendant must acknowledge before the app claims the new state.
        expect(SharedPreferencesUtil().capturePolicy.muted, !muted);
        if (rejectMuteWrite) throw StateError('pendant refused mute');
        muteWrites.add(muted);
        if (reportedMute != null) reportedMute = muted;
      },
    );
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
      expect(muteWrites, [true]);
      await world.controller.resumeDeviceRecording();
      await world.settle();
      expect(world.sockets.length, count + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      expect(muteWrites, [true, false]);
    });
  }

  test('device pause failure reaches the UI caller without confirming pause', () async {
    rejectMuteWrite = true;
    await expectLater(world.controller.pauseCapture(), throwsStateError);
    expect(muteWrites, isEmpty);
    expect(world.controller.isPaused, false);
  });

  test('a refused device unmute keeps the durable local mute', () async {
    await world.controller.pauseCapture();
    rejectMuteWrite = true;
    await expectLater(world.controller.resumeCapture(), throwsStateError);
    expect(muteWrites, [true]);
    expect(world.controller.isPaused, true);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
  });
  for (final deviceMuted in [false, true]) {
    for (final deviceControl in [false, true]) {
      test('reconnect reconciles mute $deviceMuted then controls work (device control: $deviceControl)', () async {
        if (!deviceMuted) await world.controller.pauseCapture();
        world.controller.updateRecordingDevice(null);
        await world.controller.pendingSourceSwitch;
        reportedMute = deviceMuted;
        muteWrites.clear();
        await world.controller.streamDeviceRecording(device: pendant);
        await world.settle();
        expect(world.controller.isPaused, deviceMuted);
        final snapshot = jsonDecode(SharedPreferencesUtil().getString('captureCoordinatorSnapshot'));
        expect(snapshot['phase'], deviceMuted ? 'pendantPaused' : 'pendantLive');
        expect(world.deviceConnection!.openAudioSubscriptions, deviceMuted ? 0 : 1);
        final recordingId = world.controller.activeRecordingId;
        if (deviceMuted) {
          if (deviceControl) {
            await world.controller.resumeDeviceRecording();
          } else {
            await world.controller.resumeCapture();
          }
        } else {
          if (deviceControl) {
            await world.controller.pauseDeviceRecording();
          } else {
            await world.controller.pauseCapture();
          }
        }
        await world.settle();
        expect(world.controller.activeRecordingId, recordingId);
        expect(muteWrites, [!deviceMuted]);
        expect(world.controller.isPaused, !deviceMuted);
        expect(world.deviceConnection!.openAudioSubscriptions, deviceMuted ? 1 : 0);
        if (deviceMuted) {
          final socket = world.socket!;
          final frames = socket.sentBinary.length;
          world.deviceConnection!.emitAudio();
          await world.settle();
          expect(socket.sentBinary.length, frames + 1);
        }
      });
    }
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
}
