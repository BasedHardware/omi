import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/enums.dart';

import '../support/capture/capture_replay_world.dart';
import '../support/capture/virtual_capture_time.dart';
import '../support/spine/contract.dart';

class MemoryPrefs implements SharedPreferencesUtil {
  @override
  bool get deviceMuted => true;
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected preferences read: ${i.memberName}');
}

class InertWal implements IWalService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Construction must not start WAL: ${i.memberName}');
}

class InertMic implements IMicRecorderService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Construction must not start mic: ${i.memberName}');
}

class TrackedBle implements CaptureBleListeners {
  final callbacks = <void Function(String)>[];
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) => callbacks.add(callback);
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) => callbacks.remove(callback);
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected BLE effect: ${i.memberName}');
}

RecordingTransferCoordinator coordinator() => RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async => const RecordingTransferDrainResult.skipped(),
      autoUploadEnabled: () => false,
    );

CaptureDependencies dependencies(
    {CaptureReplayWorld? world,
    CaptureSocketOpen? open,
    Future<BleAudioCodec> Function(String)? codec,
    SharedPreferencesUtil? preferences,
    TrackedBle? ble,
    StreamController<bool>? changes,
    ConversationLocationCapture? location,
    CaptureAuthBoundary? auth,
    CaptureSessionOwner? owner}) {
  final clock = world?.clock ?? VirtualClock(DateTime.utc(2026));
  return CaptureDependencies(
    ensureDeviceConnection: (_) async => null,
    wal: world?.wal ?? InertWal(),
    phoneMic: world?.mic ?? InertMic(),
    batchSupported: false,
    auth: auth ?? CaptureAuthBoundary(isSignedIn: () => true, refreshIdToken: () async => null),
    connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true, changes: changes?.stream ?? const Stream.empty(), isConnected: () => true),
    now: clock.now,
    scheduling: world?.scheduler ?? ManualScheduler(clock: clock),
    preferences: preferences ?? MemoryPrefs(),
    ble: ble ?? TrackedBle(),
    openSocket: open ??
        (
                {required codec,
                required sampleRate,
                required language,
                required force,
                source,
                clientConversationId,
                customSttConfig}) async =>
            null,
    owner: owner ??
        CaptureSessionOwner(
            coordinator: world?.coordinator ?? coordinator(),
            startForeground: () async {},
            stopForeground: () async {}),
    location: location ??
        ConversationLocationCapture(
            isLocationServiceEnabled: () async => false,
            checkPermission: () async => LocationPermission.denied,
            requestPermission: () async => LocationPermission.denied,
            upload: (_) async => false,
            now: clock.now),
    localSegments: LocalSegmentStore.disabled(),
    codec: codec ?? (_) async => BleAudioCodec.pcm16,
    microphonePermission: () async => true,
    refreshConversation: () async {},
    telemetry: RecordingLifecycleTelemetry(emitter: (_, __) {}, idFactory: () => 'synthetic', clock: clock.now),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 production composition refuses flutter test before resolving defaults', () {
    Object? refusal;
    try {
      composeProductionCaptureProvider();
    } catch (error) {
      refusal = error;
    }
    expect(refusal.runtimeType, UnsupportedError);
    expect(refusal.toString(), contains('FLUTTER_TEST'));
  });

  contractTest('C1 production provider constructs with every seam and no initialized globals', () async {
    // Deliberately no preferences init, ServiceManager, Firebase or plugin registration.
    final ble = TrackedBle();
    final changes = StreamController<bool>.broadcast(sync: true);
    final deps = dependencies(ble: ble, changes: changes);
    final provider = composeCaptureProvider(deps);
    expect(provider.runtimeType, CaptureProvider);
    expect(identical(provider.localSegmentStore, deps.localSegments), isTrue);
    expect(provider.isPaused, isTrue); // proves preference forwarding, not just no throw
    expect(ble.callbacks, hasLength(1));
    expect(changes.hasListener, isTrue);
    changes.add(false);
    expect(provider.isConnected, isFalse);
    provider.dispose();
    await pumpEventQueue();
    expect(ble.callbacks, isEmpty);
    expect(changes.hasListener, isFalse);
    expect((deps.scheduling as ManualScheduler).pendingTimers, isEmpty);
    await changes.close();
  });

  contractTest('C1 production provider drops ABA device codec completion before opening socket', () async {
    final dir = await Directory.systemTemp.createTemp('c1-replay-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final gate = Completer<BleAudioCodec>();
      var opens = 0;
      final deps = dependencies(
          world: world,
          preferences: SharedPreferencesUtil(),
          codec: (_) => gate.future,
          open: (
              {required codec,
              required sampleRate,
              required language,
              required force,
              source,
              clientConversationId,
              customSttConfig}) async {
            opens++;
            return null;
          });
      final p = composeCaptureProvider(deps);
      final device = BtDevice(id: 'synthetic-device', name: 'fixture', type: DeviceType.omi, rssi: -50);
      p.updateRecordingDevice(device);
      p.updateRecordingState(RecordingState.deviceRecord);
      final before = deps.owner.token;
      final pending = p.reconnectActiveCaptureForTesting();
      await pumpEventQueue();
      p.updateRecordingDevice(null);
      p.updateRecordingDevice(device); // same id after disconnect defeats an id-only fence
      p.updateRecordingState(RecordingState.deviceRecord);
      expect(deps.owner.isCurrent(before), isFalse);
      gate.complete(BleAudioCodec.pcm16);
      await pending;
      expect(opens, 0);
      await p.reconnectActiveCaptureForTesting();
      expect(opens, 1); // don't satisfy by disabling reconnect
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  contractTest('C1 real provider joins keepalive reconnect and disposes all newly scheduled timers', () async {
    final dir = await Directory.systemTemp.createTemp('c1-replay-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final gate = Completer<void>();
      var opens = 0;
      final transports = <ScriptedPureSocket>[];
      final deps = dependencies(
          world: world,
          preferences: SharedPreferencesUtil(),
          open: (
              {required codec,
              required sampleRate,
              required language,
              required force,
              source,
              clientConversationId,
              customSttConfig}) async {
            opens++;
            await gate.future;
            final transport = ScriptedPureSocket();
            transports.add(transport);
            final socket = TranscriptSegmentSocketService.withSocket(sampleRate, codec, language, transport);
            await socket.start();
            return socket;
          });
      final p = composeCaptureProvider(deps);
      p.updateRecordingState(RecordingState.systemAudioRecord);
      p.onClosed();
      expect(p.keepAliveScheduledForTesting, isTrue);
      final connect = p.reconnectActiveCaptureForTesting();
      await pumpEventQueue();
      world.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(opens, 1);
      gate.complete();
      await connect;
      expect(transports, hasLength(1));
      // Positive control: keepalive itself must reconnect, with no explicit call.
      p.onClosed();
      world.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(opens, 2);
      expect(transports, hasLength(2));
      p.dispose();
      await pumpEventQueue();
      final calls = opens;
      world.scheduler.elapse(const Duration(minutes: 1));
      await pumpEventQueue();
      expect(opens, calls);
      // WAL owns its own timers; stop it before checking whole-world quiescence.
      await world.wal.stop();
      expect(world.scheduler.pendingTimers, isEmpty);
      expect(transports.map((socket) => socket.closeCalls), everyElement(1));
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });
}
