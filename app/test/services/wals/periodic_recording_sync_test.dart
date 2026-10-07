import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/periodic_recording_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final trigger in [WakeTrigger.periodic, WakeTrigger.deviceConnected]) {
    test('background $trigger wake discovers and drains backlog without opening live capture', () async {
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
          expect(SyncWakeScope.syncOnly, true);
          // A BLE connect observer and Home both attempt their normal starts.
          await world.controller.streamDeviceRecording(device: pendant);
          await world.controller.streamDeviceRecording();
        },
        drain: () async {
          drains++;
          expect(SyncWakeScope.syncOnly, true);
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
      await world.controller.pendingSourceSwitch;
      expect(discoveries, 1);
      expect(drains, 1);
      expect(holds, 1);
      expect(releases, 1);
      expect(world.sockets, isEmpty);
      expect(world.deviceConnection!.openAudioSubscriptions, 0);
      expect(coordinator.nextCooldownAt, isNull);
      expect(SyncWakeScope.syncOnly, false);
      coordinator.dispose();
      await world.dispose();
      directory.deleteSync(recursive: true);
    });
  }

  test('background reconnect storms stop after two fenced passes, including failures', () async {
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
          unawaited(coordinator.wake(WakeTrigger.deviceConnected));
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
    await coordinator.wake(WakeTrigger.deviceConnected);
    await coordinator.waitUntilIdle();
    expect(discoveries, 2);
    expect(drains, 2);
    expect(holds, 1);
    expect(releases, 1);
    expect(cooldowns, 0);
    expect(coordinator.nextCooldownAt, isNull);
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
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        drained++;
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
    Future<Object?> nativeCall(String method) async {
      final completed = Completer<Object?>();
      messenger.handlePlatformMessage(
          PeriodicRecordingSync.channel.name, const StandardMethodCodec().encodeMethodCall(MethodCall(method)),
          (reply) {
        completed.complete(const StandardMethodCodec().decodeEnvelope(reply!));
      });
      return completed.future;
    }

    await bridge.start();
    expect(scheduled, 1);
    expect(await nativeCall('wake'), true);
    expect(drained, 1);
    await nativeCall('expire');
    expect(cancelled, 1);
    bridge.dispose();
    coordinator.dispose();
    messenger.setMockMethodCallHandler(PeriodicRecordingSync.channel, null);
  });
}
