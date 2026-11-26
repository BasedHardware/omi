import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_policy.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

/// A pendant muted before the app process ended must come back as a visible,
/// resumable paused session. Before this contract the cold start refused audio
/// (correctly), never marked the session paused, failed `capture_unavailable`,
/// and fell back to idle: no live row, no Resume, and double-press resume had
/// nothing to resume, so only an app-icon Mute-then-Unmute could recover it.
void main() {
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  final persistedMute = <String, Object>{
    SharedPreferencesUtil.capturePolicyKey: const CapturePolicy(revision: 3, muted: true).encode(),
  };

  late Directory directory;
  late CaptureReplayWorld world;
  bool? reportedMute;
  final muteWrites = <bool>[];
  void Function(bool muted)? onMuteWrite;

  Future<void> boot({required bool? firmwareMuted, bool batchMode = false}) async {
    directory = await Directory.systemTemp.createTemp('capture_cold_mute_');
    reportedMute = firmwareMuted;
    muteWrites.clear();
    onMuteWrite = null;
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      startTime: DateTime.utc(2026, 3, 1, 12),
      pendantCodec: BleAudioCodec.opus,
      initialPrefs: {...persistedMute, if (batchMode) 'batchModeEnabled': true},
      deviceMuteReader: (_) async => reportedMute,
      deviceMuteWriter: (id, muted) async {
        expect(id, pendant.id);
        muteWrites.add(muted);
        if (reportedMute != null) reportedMute = muted;
        onMuteWrite?.call(muted);
      },
    );
    world.deviceConnection = ScriptedDeviceConnection();
  }

  tearDown(() async {
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  String snapshotPhase() => jsonDecode(SharedPreferencesUtil().getString('captureCoordinatorSnapshot'))['phase'];

  Future<void> coldConnect() async {
    expect(world.controller.recordingState, RecordingState.stop, reason: 'a cold process starts stopped');
    expect(world.controller.isPaused, isTrue, reason: 'the mute survived the restart');
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  }

  for (final firmwareMuted in <bool?>[true, null]) {
    group('cold start with a persisted mute (firmware mute readable: ${firmwareMuted != null})', () {
      test('commits a visible paused pendant session without audio', () async {
        await boot(firmwareMuted: firmwareMuted);
        await coldConnect();

        expect(world.controller.recordingState, RecordingState.pause);
        expect(world.controller.liveCaptureSource, 'omi');
        expect(world.controller.activeRecordingId, isNotNull);
        expect(snapshotPhase(), 'pendantPaused');
        expect(world.deviceConnection!.openAudioSubscriptions, 0, reason: 'mute is still enforced');
        expect(world.sockets, isEmpty, reason: 'no transcription socket while muted');
        expect(muteWrites, isEmpty, reason: 'connecting must never unmute');
      });

      for (final deviceControl in [false, true]) {
        test('resume unmutes and starts capture (device control: $deviceControl)', () async {
          await boot(firmwareMuted: firmwareMuted);
          await coldConnect();
          final recordingId = world.controller.activeRecordingId;

          if (deviceControl) {
            await world.controller.resumeDeviceRecording();
          } else {
            await world.controller.resumeCapture();
          }
          await world.settle();

          expect(muteWrites, [false]);
          expect(world.controller.isPaused, isFalse);
          expect(world.controller.recordingState, RecordingState.deviceRecord);
          expect(world.controller.activeRecordingId, recordingId);
          expect(world.deviceConnection!.openAudioSubscriptions, 1);
          final socket = world.socket!;
          final frames = socket.sentBinary.length;
          world.deviceConnection!.emitAudio();
          await world.settle();
          expect(socket.sentBinary.length, frames + 1);
        });
      }
    });
  }

  test('batch mode cold start with a persisted mute is also resumable', () async {
    await boot(firmwareMuted: true, batchMode: true);
    await coldConnect();

    expect(world.controller.recordingState, RecordingState.pause);
    expect(snapshotPhase(), 'pendantBatchPaused');
    expect(world.deviceConnection!.openAudioSubscriptions, 0);

    await world.controller.resumeDeviceRecording();
    await world.settle();

    expect(muteWrites, [false]);
    expect(world.controller.isPaused, isFalse);
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
  });

  for (final deviceControl in [false, true]) {
    test('resume from an idle muted pendant unmutes and starts capture (device control: $deviceControl)', () async {
      await boot(firmwareMuted: true);
      world.controller.updateRecordingDevice(pendant);
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.liveCaptureSource, isNull, reason: 'no session owns the pendant yet');
      expect(world.controller.isPaused, isTrue);

      if (deviceControl) {
        await world.controller.resumeDeviceRecording();
      } else {
        await world.controller.resumeCapture();
      }
      await world.settle();

      expect(muteWrites, [false]);
      expect(world.controller.isPaused, isFalse);
      expect(world.controller.liveCaptureSource, 'omi');
      expect(world.controller.recordingState, RecordingState.deviceRecord);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
    });
  }

  test('a sync-only pass that starts mid-resume defers the start and replays it when the pass ends', () async {
    await boot(firmwareMuted: true);
    world.controller.updateRecordingDevice(pendant);
    await world.controller.pendingSourceSwitch;
    await world.settle();

    // The resume fence waits out a pass that is already running; this pass
    // begins after that check, while the unmute is being written.
    final pass = Completer<void>();
    Future<void>? scope;
    onMuteWrite = (muted) {
      if (!muted) scope = SyncWakeScope.run(() => pass.future);
    };
    final replayCommitted = Completer<void>();
    void onCaptureChanged() {
      if (!replayCommitted.isCompleted && world.controller.liveCaptureSource != null) {
        replayCommitted.complete();
      }
    }

    world.controller.addListener(onCaptureChanged);
    addTearDown(() => world.controller.removeListener(onCaptureChanged));
    try {
      await world.controller.resumeCapture();
      await world.settle();
      expect(scope, isNotNull);
      expect(muteWrites, [false]);
      expect(world.deviceConnection!.openAudioSubscriptions, 0, reason: 'the pass fences live capture');
    } finally {
      pass.complete();
      await scope;
    }
    // The scope can finish before the deferred start reaches the coordinator.
    // Ownership is published only after the coordinator persists the snapshot.
    await replayCommitted.future.timeout(
      const Duration(seconds: 10),
      onTimeout: () => fail('the deferred pendant start never committed'),
    );
    await world.controller.pendingSourceSwitch;

    expect(world.controller.isPaused, isFalse);
    expect(world.controller.liveCaptureSource, 'omi');
    expect(snapshotPhase(), 'pendantLive');
    expect(world.deviceConnection!.openAudioSubscriptions, 1, reason: 'the deferred start replays after the pass');
  });

  // Existing contract (device_mute_sync.dart): the pendant's persisted mute bit
  // is the authority on reconnect; the phone value is only the fallback.
  test('a firmware unmute overrides the persisted phone mute on cold start', () async {
    await boot(firmwareMuted: false);
    await coldConnect();

    expect(world.controller.isPaused, isFalse);
    expect(world.controller.recordingState, RecordingState.deviceRecord);
    expect(snapshotPhase(), 'pendantLive');
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
  });
}
