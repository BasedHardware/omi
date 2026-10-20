import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

/// Live-capture recovery after the 2026-10-20 incident: a server close, a
/// network handover and a reconnect during an upload pass each left a
/// connected pendant uncaptured until a cold start.
void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<void> connect() async {
    world.deviceConnection = ScriptedDeviceConnection(orphanDeviceId: pendant.id);
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  }

  Future<void> disconnect() async {
    world.controller.updateRecordingDevice(null);
    await world.settle();
  }

  bool liveCaptureUp() =>
      world.socket?.status == PureSocketStatus.connected && world.deviceConnection!.openAudioSubscriptions == 1;

  Future<int> persistedFrames() async {
    final wals = await world.wal.syncs.phone.getAllWals();
    return wals.fold<int>(0, (count, wal) => count + wal.totalFrames) + world.wal.syncs.phone.testFrames.length;
  }

  /// Holds a capture-fencing (OS periodic) transfer pass open until released.
  Future<({RecordingTransferCoordinator coordinator, Future<void> wake, Completer<void> release})> holdFencedPass(
      {WakeTrigger trigger = WakeTrigger.periodic}) async {
    final entered = Completer<void>();
    final release = Completer<void>();
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {
        entered.complete();
        await release.future;
      },
      refreshPending: () async {},
      drain: () async => const RecordingTransferDrainResult.skipped(),
      autoUploadEnabled: () => true,
    );
    final wake = coordinator.wake(trigger);
    await entered.future;
    return (coordinator: coordinator, wake: wake, release: release);
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_live_recovery_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
    await connect();
  });

  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  group('live socket recovery', () {
    test('a normal server close reconnects without waiting for the 15 s keep-alive', () async {
      final before = world.sockets.length;
      world.socket!.emitClose(1000);
      await world.settle();
      await world.elapse(const Duration(seconds: 2));
      expect(world.sockets.length, before + 1);
      expect(world.socket!.status, PureSocketStatus.connected);
    });

    test('repeated closes back off but never stop reconnecting', () async {
      for (var i = 0; i < 6; i++) {
        final before = world.sockets.length;
        world.socket!.emitClose(1001);
        await world.settle();
        await world.elapse(const Duration(seconds: 16));
        expect(world.sockets.length, greaterThan(before), reason: 'close $i');
        expect(world.socket!.status, PureSocketStatus.connected);
      }
    });

    test('a network handover re-arms a keep-alive that had cancelled itself', () async {
      world.signedIn = false;
      world.socket!.emitClose(1000);
      await world.settle();
      // The keep-alive cancels itself permanently on its first signed-out tick.
      await world.elapse(const Duration(seconds: 31));
      world.signedIn = true;
      final before = world.sockets.length;
      await world.elapse(const Duration(seconds: 60));
      expect(world.sockets.length, before, reason: 'nothing re-arms recovery without a trigger');
      world.emitNetworkChange();
      await world.settle();
      await world.elapse(const Duration(seconds: 2));
      expect(world.sockets.length, before + 1);
      expect(world.socket!.status, PureSocketStatus.connected);
    });

    test('app resume re-arms a keep-alive that had cancelled itself', () async {
      world.signedIn = false;
      world.socket!.emitClose(1000);
      await world.settle();
      await world.elapse(const Duration(seconds: 31));
      world.signedIn = true;
      final before = world.sockets.length;
      world.controller.onAppResumed();
      await world.settle();
      await world.elapse(const Duration(seconds: 2));
      expect(world.sockets.length, before + 1);
      expect(world.socket!.status, PureSocketStatus.connected);
    });

    test('a terminal close code does not trigger an immediate reconnect', () async {
      final before = world.sockets.length;
      world.socket!.emitClose(4002);
      await world.settle();
      await world.elapse(const Duration(seconds: 2));
      expect(world.sockets.length, before);
    });
  });

  group('capture start during an upload pass', () {
    test('a pendant reconnect during a fenced pass still yields capture when the pass ends', () async {
      await disconnect();
      final pass = await holdFencedPass();
      expect(SyncWakeScope.syncOnly, true);
      await connect();
      expect(world.controller.recordingState, isNot(RecordingState.deviceRecord));
      pass.release.complete();
      await pass.wake;
      await world.settle();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.recordingState, RecordingState.deviceRecord);
      expect(liveCaptureUp(), true);
      pass.coordinator.dispose();
    });

    test('a hung fenced pass is aborted by its time limit and capture then starts', () async {
      await disconnect();
      final timedOut = <WakeTrigger>[];
      final hang = Completer<void>();
      final coordinator = RecordingTransferCoordinator(
        reconcile: () async {},
        discover: () => hang.future,
        refreshPending: () async {},
        drain: () async => const RecordingTransferDrainResult.skipped(),
        autoUploadEnabled: () => true,
        fencedPassTimeLimit: const Duration(milliseconds: 50),
        onPassTimedOut: (trigger, _) => timedOut.add(trigger),
        scheduleCooldown: (_, __) {},
      );
      final wake = coordinator.wake(WakeTrigger.periodic);
      await pumpEventQueue();
      expect(SyncWakeScope.syncOnly, true);
      await connect();
      await wake;
      expect(timedOut, [WakeTrigger.periodic]);
      expect(SyncWakeScope.syncOnly, false);
      expect(coordinator.hasInFlight, false);
      await world.settle();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(liveCaptureUp(), true);
      coordinator.dispose();
    });

    test('a start swallowed while a phone recording owns capture resumes the pendant after it', () async {
      await disconnect();
      final pass = await holdFencedPass();
      await connect();
      pass.release.complete();
      // The phone takes capture before the fence drops; the replayed start must
      // still register the pendant so the phone stop hands capture back.
      await world.startLiveCapture();
      await pass.wake;
      await world.settle();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.deviceConnection!.openAudioSubscriptions, 0, reason: 'one source at a time');
      await world.stopLiveCapture();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.recordingState, RecordingState.deviceRecord);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      pass.coordinator.dispose();
    });

    test('a reconnect pass no longer fences capture at all', () async {
      await disconnect();
      final pass = await holdFencedPass(trigger: WakeTrigger.deviceConnected);
      expect(SyncWakeScope.syncOnly, false);
      await connect();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(liveCaptureUp(), true);
      pass.release.complete();
      await pass.wake;
      pass.coordinator.dispose();
    });
  });

  group('pendant audio with no capture listener', () {
    test('packets that reach the transport with no listener are persisted for upload', () async {
      await disconnect();
      final pass = await holdFencedPass();
      await connect();
      expect(world.deviceConnection!.openAudioSubscriptions, 0);
      final before = await persistedFrames();
      for (var i = 0; i < 50; i++) {
        world.deviceConnection!.emitAudio(value: i);
      }
      // The first orphan packet primes the WAL (a codec boundary flush to disk)
      // asynchronously; observe completion rather than sleeping a fixed time.
      for (var i = 0; i < 200 && await persistedFrames() < before + 50; i++) {
        await world.settle();
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
      expect(await persistedFrames(), before + 50);
      pass.release.complete();
      await pass.wake;
      pass.coordinator.dispose();
    });

    test('orphan packets never move the WAL off another source\'s codec', () async {
      await disconnect();
      await world.startLiveCapture();
      await world.stopLiveCapture();
      expect(world.wal.syncs.phone.currentCodec, isNot(BleAudioCodec.opus), reason: 'the phone was the last source');
      final pass = await holdFencedPass();
      await connect();
      final before = await persistedFrames();
      for (var i = 0; i < 20; i++) {
        world.deviceConnection!.emitAudio(value: i);
      }
      await world.settle();
      expect(await persistedFrames(), before);
      expect(world.wal.syncs.phone.currentCodec, isNot(BleAudioCodec.opus));
      pass.release.complete();
      await pass.wake;
      pass.coordinator.dispose();
    });

    test('a muted pendant\'s packets stay unrecorded', () async {
      await world.controller.pauseCapture();
      await world.settle();
      expect(SharedPreferencesUtil().capturePolicy.muted, true);
      expect(world.deviceConnection!.openAudioSubscriptions, 0);
      final before = await persistedFrames();
      for (var i = 0; i < 20; i++) {
        world.deviceConnection!.emitAudio(value: i);
      }
      await world.settle();
      expect(await persistedFrames(), before);
    });

    test('a caller stop (voice profile) leaves pendant audio alone', () async {
      await world.controller.stopStreamDeviceRecording();
      await world.settle();
      final before = await persistedFrames();
      final sockets = world.sockets.length;
      for (var i = 0; i < 20; i++) {
        world.deviceConnection!.emitAudio(value: i);
      }
      await world.settle();
      await world.elapse(const Duration(seconds: 31));
      expect(await persistedFrames(), before);
      expect(world.sockets.length, sockets);
      expect(world.controller.recordingState, isNot(RecordingState.deviceRecord));
    });
  });
}
