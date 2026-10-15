import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

/// Uses the real coordinator's coalescing and depth-zero crossings, not a
/// replacement fence whose lifetime is conveniently the whole wake.
class _Drain {
  _Drain({this.yieldAtDrop = false});
  final bool yieldAtDrop;
  final entered = [Completer<void>(), Completer<void>()];
  final release = [Completer<void>(), Completer<void>()];
  late final coordinator = RecordingTransferCoordinator(
    reconcile: () async {},
    discover: () async {},
    refreshPending: () async {},
    drain: () async {
      final pass = passes++;
      entered[pass].complete();
      await release[pass].future;
      return const RecordingTransferDrainResult.skipped();
    },
    autoUploadEnabled: () => true,
  )..setForeground(false);
  int passes = 0;
  late Future<void> wake;
  Future<void> start() async {
    wake = runZoned(
      () => coordinator.wake(WakeTrigger.deviceConnected),
      // Async await continuations may otherwise chain inline on this VM.
      // Yield the producer once at depth zero, allowing the consumer to dispatch
      // before pass 2 rises. The real coordinator, fence and effects all run.
      zoneSpecification: ZoneSpecification(registerUnaryCallback: <R, T>(self, parent, zone, callback) {
        return parent.registerUnaryCallback<R, T>(zone, (value) {
          if (yieldAtDrop && !SyncWakeScope.syncOnly && passes == 1 && R == dynamic) {
            return Future.microtask(() => callback(value)) as R;
          }
          return callback(value);
        });
      }),
    );
    await entered[0].future;
  }

  Future<void> finish() async {
    for (final gate in release) {
      if (!gate.isCompleted) gate.complete();
    }
    await wake;
    coordinator.dispose();
  }
}

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  final writes = <Map<String, Object>>[];

  Future<void> settle() async {
    await world.settle();
    await world.controller.pendingSourceSwitch;
    await world.settle();
    // Reconciliation runs outside the dispatcher's pendingSourceSwitch. Wait
    // for observable completion of its async WAL/transport I/O after scope drop,
    // rather than mistaking coordinator quiescence for transport quiescence.
    if (!SyncWakeScope.syncOnly && !world.controller.isPaused) {
      final deadline = Stopwatch()..start();
      while (!world.controller.keepAliveScheduledForTesting ||
          (world.socket?.status == PureSocketStatus.connected && world.deviceConnection!.openAudioSubscriptions != 1)) {
        if (deadline.elapsed > const Duration(seconds: 5)) {
          throw StateError('scope-drop transport reconciliation did not settle');
        }
        await Future<void>.delayed(const Duration(milliseconds: 1));
        await world.settle();
      }
    }
  }

  void expectLive() {
    expect(SyncWakeScope.syncOnly, false);
    expect(world.controller.isPaused, false);
    expect(world.controller.silencePaused, false);
    expect(world.socket!.status, PureSocketStatus.connected);
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
    expect(world.controller.keepAliveScheduledForTesting, true);
  }

  Future<_Drain> drain({bool yieldAtDrop = false}) async {
    final drain = _Drain(yieldAtDrop: yieldAtDrop);
    await drain.start();
    addTearDown(drain.finish);
    return drain;
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('resume_sync_fence_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    // Seed the persisted #20837 marker; current firmware can no longer trigger
    // a silence pause. Exercise upgrade recovery against the real sync fence.
    await world.controller.pauseCapture();
    await SharedPreferencesUtil().saveBool('uplinkSilencePaused', true);
    await settle();
    expect(world.controller.silencePaused, true);
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, args) async {
      if (method == 'setMuted') writes.add(Map.of(args));
      return null;
    };
    writes.clear();
  });
  tearDown(() async {
    SharedPreferencesUtil.capturePolicyBridgeForTesting = null;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  test('case 1: resume without a fence opens the live uplink immediately', () async {
    await world.controller.resumeCapture();
    await settle();
    expectLive();
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
  });

  test('case 2: resume during one fenced pass opens the uplink after its drop', () async {
    final draining = await drain();
    final resume = world.controller.resumeCapture();
    await world.settle();
    expect(world.controller.silencePaused, true);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
    expect(world.controller.keepAliveScheduledForTesting, false);
    await draining.finish();
    await resume;
    await settle();
    expectLive();
  });

  test('case 3: resume in pass 1 survives the coalesced second pass and final drop', () async {
    final draining = await drain(yieldAtDrop: true);
    final before = world.sockets.length;
    final resume = world.controller.resumeCapture();
    await world.settle();
    // Coalesce BEFORE releasing pass 1; idle resolves before pass 2 starts.
    unawaited(draining.coordinator.wake(WakeTrigger.deviceConnected));
    draining.release[0].complete();
    await draining.entered[1].future;
    await settle();
    expect(SyncWakeScope.syncOnly, true);
    expect(world.controller.silencePaused, false, reason: 'resume committed during pass 2');
    expect(world.sockets.length, before);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
    await draining.finish();
    await resume;
    await settle();
    expect(draining.passes, 2);
    expectLive();
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
  });

  test('failed scope-drop socket attempt re-arms existing keepalive', () async {
    final before = world.sockets.length;
    final draining = await drain(yieldAtDrop: true);
    final resume = world.controller.resumeCapture();
    await world.settle();
    unawaited(draining.coordinator.wake(WakeTrigger.deviceConnected));
    draining.release[0].complete();
    await draining.entered[1].future;
    await settle();
    world.nextConnectFailsOnce = true;
    await draining.finish();
    await resume;
    await settle();
    expect(world.sockets.length, before + 1, reason: 'all blocked attempts coalesce into one re-drive');
    expect(world.socket!.status, PureSocketStatus.notConnected);
    expect(world.controller.keepAliveScheduledForTesting, true);
    await world.elapse(const Duration(seconds: 15));
    await settle();
    expectLive();
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
  });

  test('case 4: double-tap and charging in one drain commit once; live resume is a no-op', () async {
    final draining = await drain();
    final before = world.sockets.length;
    final oldRecording = world.controller.activeRecordingId;
    final recordings = <String?>{};
    void observe() {
      final recording = world.controller.activeRecordingId;
      if (recording != oldRecording) recordings.add(recording);
    }

    world.controller.addListener(observe);
    SharedPreferencesUtil().doubleTapAction = 1;
    world.controller.handleButtonEventForTesting(pendant.id, 2);
    world.controller.onChargingStarted();
    await world.settle();
    await draining.finish();
    await settle();
    expectLive();
    expect(recordings, hasLength(1));
    expect(world.sockets.length, before + 1);
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
    // The connected-device catch-all must also be a no-op when already unmuted.
    await world.controller.resumeCapture();
    await settle();
    expect(recordings, hasLength(1));
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
    expect(world.sockets.length, before + 1);
    world.controller.removeListener(observe);
  });

  test('case 5: disposal while resume waits prevents dispatch and keepalive', () async {
    final draining = await drain();
    final before = world.sockets.length;
    final resume = world.controller.resumeCapture();
    await world.settle();
    world.disposeController();
    await draining.finish();
    await resume;
    await world.settle();
    expect(writes, isEmpty);
    expect(world.sockets.length, before);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
    expect(world.controller.keepAliveScheduledForTesting, false);
  });

  test('case 6: later scopes re-fence a committed session and re-drive without another mint', () async {
    await world.controller.resumeCapture();
    await settle();
    expectLive();
    final recording = world.controller.activeRecordingId;
    final subscriptions = world.deviceConnection!.audioSubscriptionsOpened;
    final before = world.sockets.length;
    final draining = await drain();
    world.controller.onChargingStarted(); // Already live: no new policy/session.
    world.socket!.emitClose();
    await world.controller.reconnectActiveCaptureForTesting();
    await settle();
    expect(world.sockets.length, before);

    // Raise another unrelated scope DURING the scope-drop re-drive's STT await.
    // Reconciliation must register again instead of losing its single demand.
    final entered = Completer<void>();
    final release = Completer<void>();
    Future<void>? laterScope;
    var raise = true;
    SttModeResolver.instance = SttModeResolver(flagReader: () {
      if (raise) {
        raise = false;
        laterScope = SyncWakeScope.run(() async {
          entered.complete();
          await release.future;
        });
      }
      return false;
    });
    addTearDown(() async {
      if (!release.isCompleted) release.complete();
      await laterScope;
    });
    await draining.finish();
    await entered.future;
    await settle();
    expect(world.sockets.length, before);
    release.complete();
    await laterScope;
    await settle();
    expectLive();
    expect(world.controller.activeRecordingId, recording);
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
    expect(world.sockets.length, before + 1);
    expect(world.deviceConnection!.audioSubscriptionsOpened, subscriptions,
        reason: 'an already active BLE subscription is not duplicated');
  });

  test('case 7: authorized first charging sample inside a scope consumes one deferred edge', () async {
    ConnectivityPlatform.instance = _NoConnectivityPlatform();
    await ServiceManager.init();
    final transport = _ChargingTransport();
    final connection = OmiDeviceConnection(pendant, transport);
    final capture = _ChargingCapture(world.controller.onChargingStarted);
    final provider = DeviceProvider(chargingConnectionLoader: (_) async => connection)
      ..connectedDevice = pendant
      ..captureProvider = capture;
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    addTearDown(capture.dispose);
    // Failed read outside the scope: this connection IS allowed to resume on
    // its first actual observation, even if a later scope fences the callback.
    await provider.initiateChargingStatusListener(allowCaptureResume: true);
    final draining = await drain();
    transport.notifications.add([1]);
    transport.notifications.add([1]);
    expect(capture.edges, 1);
    await world.settle();
    expect(world.controller.silencePaused, true);
    expect(writes, isEmpty);
    await draining.finish();
    await settle();
    expectLive();
    expect(capture.edges, 1);
    expect(writes.where((w) => w['muted'] == false), hasLength(1));
  });

  test('case 8: sync-only wake without resume opens zero sockets and zero BLE subscriptions', () async {
    final before = world.sockets.length;
    final subscriptions = world.deviceConnection!.audioSubscriptionsOpened;
    final draining = await drain(yieldAtDrop: true);
    await world.controller.streamDeviceRecording(device: pendant);
    unawaited(draining.coordinator.wake(WakeTrigger.deviceConnected));
    draining.release[0].complete();
    await draining.entered[1].future;
    await world.controller.streamDeviceRecording();
    await draining.finish();
    await settle();
    expect(world.controller.silencePaused, true);
    expect(writes, isEmpty);
    expect(world.sockets.length, before);
    expect(world.deviceConnection!.audioSubscriptionsOpened, subscriptions);
    expect(world.deviceConnection!.openAudioSubscriptions, 0);
    expect(world.controller.keepAliveScheduledForTesting, false);
    // periodic_recording_sync_test also covers cold/unowned periodic + reconnect
    // wakes, discovery, the two-pass bound, zero sockets and zero subscriptions.
  });
}

class _ChargingCapture extends ChangeNotifier implements CaptureProvider {
  _ChargingCapture(this.resume);
  final void Function() resume;
  int edges = 0;
  @override
  void onChargingStarted() {
    edges++;
    resume();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _ChargingTransport implements DeviceTransport {
  final notifications = StreamController<List<int>>.broadcast(sync: true);
  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();
  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async =>
      throw StateError('GATT read failed');
  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => notifications.stream;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _NoConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];
  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}
