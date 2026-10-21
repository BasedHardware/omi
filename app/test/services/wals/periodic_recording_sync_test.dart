import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/wals/periodic_recording_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final trigger in [WakeTrigger.periodic, WakeTrigger.deviceConnected]) {
    // Only the OS periodic window fences live capture; a start it swallows is
    // replayed when the fence drops. A reconnect pass never fences (2026-10-20).
    final fenced = trigger == WakeTrigger.periodic;
    test('background $trigger wake drains backlog and leaves a connected pendant capturing', () async {
      final directory = await Directory.systemTemp.createTemp('periodic_sync_');
      final world = await CaptureReplayWorld.boot(tempDir: directory);
      final pendant = BtDevice(id: 'omi', name: 'Omi', type: DeviceType.omi, rssi: -40);
      world.deviceConnection = ScriptedDeviceConnection();
      var discoveries = 0;
      var drains = 0;
      var holds = 0;
      var releases = 0;
      final coordinator = RecordingTransferCoordinator(
        reconcile: () async {},
        refreshPending: () async {},
        discover: () async {
          discoveries++;
          expect(SyncWakeScope.syncOnly, fenced);
          // A BLE connect observer and Home both attempt their normal starts.
          await world.controller.streamDeviceRecording(device: pendant);
          await world.controller.streamDeviceRecording();
          if (fenced) expect(world.sockets, isEmpty, reason: 'the fenced window opens no live capture');
        },
        drain: () async {
          drains++;
          expect(SyncWakeScope.syncOnly, fenced);
          return const RecordingTransferDrainResult(attempted: true, failed: false, needsReconciliation: false);
        },
        drainLiveCapture: () async => throw StateError('must drain the backlog'),
        autoUploadEnabled: () => true,
        onTransferStarted: () async {
          holds++;
        },
        onTransferFinished: () async {
          releases++;
        },
      )..setForeground(false);
      await coordinator.wake(trigger);
      await coordinator.waitUntilIdle();
      await world.settle();
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(discoveries, 1);
      expect(drains, 1);
      expect(holds, 1);
      expect(releases, 1);
      expect(world.sockets, isNotEmpty);
      expect(world.socket!.status, PureSocketStatus.connected);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      expect(coordinator.nextCooldownAt, isNull);
      expect(SyncWakeScope.syncOnly, false);
      coordinator.dispose();
      await world.dispose();
      directory.deleteSync(recursive: true);
    });
  }

  test('background wake storms stop after two fenced passes; failures schedule a bounded retry', () async {
    var discoveries = 0;
    var drains = 0;
    var holds = 0;
    var releases = 0;
    var cooldowns = 0;
    late RecordingTransferCoordinator coordinator;
    coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      refreshPending: () async {},
      discover: () async {
        discoveries++;
        expect(SyncWakeScope.syncOnly, true);
        // Coalesce a burst, even during the final allowed pass.
        for (var i = 0; i < 5; i++) {
          unawaited(coordinator.wake(WakeTrigger.periodic));
        }
      },
      drain: () async {
        drains++;
        expect(SyncWakeScope.syncOnly, true);
        throw StateError('retryable upload failure');
      },
      drainLiveCapture: () async => throw StateError('must drain the backlog'),
      autoUploadEnabled: () => true,
      scheduleCooldown: (_, __) => cooldowns++,
      onTransferStarted: () async {
        holds++;
      },
      onTransferFinished: () async {
        releases++;
      },
    )..setForeground(false);
    addTearDown(coordinator.dispose);
    await coordinator.wake(WakeTrigger.periodic);
    await coordinator.waitUntilIdle();
    expect(discoveries, 2);
    expect(drains, 2);
    expect(holds, 1);
    expect(releases, 1);
    expect(cooldowns, 2, reason: 'background retries are bounded, no longer dropped');
    expect(coordinator.nextCooldownAt, isNotNull);
    expect(SyncWakeScope.syncOnly, false);
  });

  test('expiration fences discovery before upload and releases the sync-only scope', () async {
    final discovered = Completer<void>();
    final finishDiscovery = Completer<void>();
    var drains = 0;
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      refreshPending: () async {},
      discover: () async {
        discovered.complete();
        await finishDiscovery.future;
      },
      drain: () async {
        drains++;
        return const RecordingTransferDrainResult.skipped();
      },
      autoUploadEnabled: () => true,
    )..setForeground(false);
    final wake = coordinator.wake(WakeTrigger.periodic);
    await discovered.future;
    coordinator.cancelPeriodicWake();
    finishDiscovery.complete();
    await wake;
    expect(drains, 0);
    expect(SyncWakeScope.syncOnly, false);
    coordinator.dispose();
  });

  test('native bridge schedules, awaits drain completion, and cancels on expiration', () async {
    var scheduled = 0;
    var drained = 0;
    var cancelled = 0;
    final drainStarted = Completer<void>();
    final finishDrain = Completer<void>();
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        drained++;
        drainStarted.complete();
        await finishDrain.future;
        return const RecordingTransferDrainResult.skipped();
      },
      autoUploadEnabled: () => true,
    )..setForeground(false);
    final bridge = PeriodicRecordingSync(coordinator: coordinator, cancel: () => cancelled++, isIOS: true);
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, (call) async {
      expect(call.method, 'schedule');
      scheduled++;
      return null;
    });

    await bridge.start();
    expect(scheduled, 1);
    final wake = _nativeCall('wake');
    await drainStarted.future;
    // iOS expires the window while the drain it started is still running.
    await _nativeCall('expire');
    expect(cancelled, 1);
    finishDrain.complete();
    expect(await wake, true);
    expect(drained, 1);
    bridge.dispose();
    coordinator.dispose();
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, null);
  });

  test('expiration does not cancel a Transfer to Phone the window did not start', () async {
    var drains = 0;
    var cancelled = 0;
    final discovering = Completer<void>();
    final finishDiscovery = Completer<void>();
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      refreshPending: () async {},
      // Discovery is slow while the user's transfer holds the device link.
      discover: () async {
        discovering.complete();
        await finishDiscovery.future;
      },
      // That transfer owns the WAL stack, so this window's drain could only contend.
      drain: () async {
        drains++;
        return const RecordingTransferDrainResult.contended();
      },
      autoUploadEnabled: () => true,
    )..setForeground(false);
    final bridge = PeriodicRecordingSync(coordinator: coordinator, cancel: () => cancelled++, isIOS: true);
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, (call) async => null);

    await bridge.start();
    final wake = _nativeCall('wake');
    await discovering.future;
    await _nativeCall('expire');
    // In the app `cancel` is WalSyncs.cancelSync(), which would stop the user's transfer.
    expect(cancelled, 0);
    finishDiscovery.complete();
    expect(await wake, true);
    expect(drains, 0);
    bridge.dispose();
    coordinator.dispose();
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, null);
  });

  test('expiration does not cancel a sync that was already draining when the window opened', () async {
    var drains = 0;
    var cancelled = 0;
    final drainStarted = Completer<void>();
    final finishDrain = Completer<void>();
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        drains++;
        drainStarted.complete();
        await finishDrain.future;
        return const RecordingTransferDrainResult(attempted: true, failed: false, needsReconciliation: false);
      },
      autoUploadEnabled: () => true,
    );
    final bridge = PeriodicRecordingSync(coordinator: coordinator, cancel: () => cancelled++, isIOS: true);
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, (call) async => null);

    await bridge.start();
    // The user taps Sync, then leaves the app while the device drain runs.
    final userSync = coordinator.wake(WakeTrigger.userRetry);
    await drainStarted.future;
    coordinator.setForeground(false);
    // iOS opens a refresh window that joins that drain, then expires it first.
    final wake = _nativeCall('wake');
    await _nativeCall('expire');
    expect(cancelled, 0);
    finishDrain.complete();
    await userSync;
    expect(await wake, true);
    expect(drains, 1);
    bridge.dispose();
    coordinator.dispose();
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, null);
  });
}

/// Delivers [method] to the bridge as the iOS side does and returns Dart's reply.
Future<Object?> _nativeCall(String method) async {
  final completed = Completer<Object?>();
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.handlePlatformMessage(
      PeriodicRecordingSync.channel.name, const StandardMethodCodec().encodeMethodCall(MethodCall(method)), (reply) {
    completed.complete(const StandardMethodCodec().decodeEnvelope(reply!));
  });
  return completed.future;
}
