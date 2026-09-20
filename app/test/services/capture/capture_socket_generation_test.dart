import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
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

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/virtual_capture_time.dart';
import '../../spine/c1_async_boundaries_test.dart' show HeldLocation;
import '../../spine/c1_location_completion_test.dart' show PhoneSpy, WalSpy;

CaptureDependencies _deps({
  CaptureReplayWorld? world,
  CaptureConversationSocketOpen? open,
  Future<BleAudioCodec> Function(String)? codec,
  ConversationLocationCapture? location,
  CaptureAuthBoundary? auth,
  CaptureSessionOwner? owner,
  LocalSegmentStore? localSegments,
  RecordingTransferCoordinator? coordinator,
}) {
  final clock = world?.clock ?? VirtualClock(DateTime.utc(2026));
  return CaptureDependencies(
    ensureDeviceConnection: (_) async => null,
    wal: world?.wal ?? _InertWal(),
    phoneMic: world?.mic ?? _InertMic(),
    batchSupported: false,
    auth: auth ?? CaptureAuthBoundary(isSignedIn: () => true, refreshIdToken: () async => null),
    connectivity: CaptureConnectivityBoundary(
      initiallyConnected: true,
      changes: const Stream.empty(),
      isConnected: () => true,
    ),
    now: clock.now,
    scheduling: world?.scheduler ?? ManualScheduler(clock: clock),
    preferences: SharedPreferencesUtil(),
    ble: _NoopBle(),
    openSocket: ({
      required codec,
      required sampleRate,
      required language,
      required force,
      source,
      clientConversationId,
      customSttConfig,
    }) async =>
        null,
    openConversationSocket: open,
    owner: owner ??
        CaptureSessionOwner(
          coordinator: coordinator ??
              RecordingTransferCoordinator(
                reconcile: () async {},
                discover: () async {},
                refreshPending: () async {},
                drain: () async => const RecordingTransferDrainResult.skipped(),
                autoUploadEnabled: () => true,
              ),
          startForeground: () async {},
          stopForeground: () async {},
        ),
    location: location ??
        ConversationLocationCapture(
          isLocationServiceEnabled: () async => false,
          checkPermission: () async => LocationPermission.denied,
          requestPermission: () async => LocationPermission.denied,
          upload: (_) async => false,
          now: clock.now,
        ),
    localSegments: localSegments ?? LocalSegmentStore.disabled(),
    codec: codec ?? (_) async => BleAudioCodec.pcm16,
    microphonePermission: () async => true,
    refreshConversation: () async {},
    telemetry: RecordingLifecycleTelemetry(emitter: (_, __) {}, idFactory: () => 'synthetic', clock: clock.now),
  );
}

class _InertWal implements IWalService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected WAL operation: ${i.memberName}');
}

class _InertMic implements IMicRecorderService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected mic operation: ${i.memberName}');
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _ImmediateLocation extends ConversationLocationCapture {
  _ImmediateLocation(this.fix)
      : super(
          isLocationServiceEnabled: () async => true,
          checkPermission: () async => LocationPermission.always,
          requestPermission: () async => LocationPermission.always,
          upload: (_) async => true,
        );
  final Geolocation fix;
  @override
  Future<Geolocation?> capture({bool promptIfDenied = true}) async => fix;
}

class HeldStore implements LocalSegmentStore {
  @override
  bool get enabled => true;
  final gate = Completer<void>();
  final calls = <String>[];
  final writes = <String>[];
  @override
  Future<void> replaceSession(String id, List<TranscriptSegment> segments) async {
    final text = segments.single.text;
    calls.add(text);
    if (calls.length == 1) await gate.future;
    writes.add('$id:$text');
  }

  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected store effect: ${i.memberName}');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('real provider coalesces concurrent reconnects into one socket open', () async {
    final dir = await Directory.systemTemp.createTemp('c1-join-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final gate = Completer<void>();
      var opens = 0;
      final deps = _deps(
        world: world,
        open: ({
          required codec,
          required sampleRate,
          required language,
          required force,
          source,
          clientConversationId,
          customSttConfig,
          geolocation,
        }) async {
          opens++;
          await gate.future;
          return null;
        },
      );
      final p = composeCaptureProvider(deps);
      p.updateRecordingState(RecordingState.systemAudioRecord);
      final a = p.reconnectActiveCaptureForTesting();
      final b = p.reconnectActiveCaptureForTesting();
      await pumpEventQueue();
      expect(opens, 1);
      gate.complete();
      await Future.wait([a, b]);
      expect(opens, 1);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('real provider keepalive tick during an in-flight connect does not open a second socket', () async {
    final dir = await Directory.systemTemp.createTemp('c1-keepalive-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final gate = Completer<void>();
      var opens = 0;
      final transports = <ScriptedPureSocket>[];
      final deps = _deps(
        world: world,
        open: ({
          required codec,
          required sampleRate,
          required language,
          required force,
          source,
          clientConversationId,
          customSttConfig,
          geolocation,
        }) async {
          opens++;
          await gate.future;
          final transport = ScriptedPureSocket();
          transports.add(transport);
          final socket = TranscriptSegmentSocketService.withSocket(sampleRate, codec, language, transport);
          await socket.start();
          return socket;
        },
      );
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
      transports.single.emitClose();
      await pumpEventQueue();
      world.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(opens, 2);
      p.dispose();
      await pumpEventQueue();
      await world.wal.stop();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('codec fetch started under generation N does not open after same-id ABA', () async {
    final dir = await Directory.systemTemp.createTemp('c1-aba-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final gate = Completer<BleAudioCodec>();
      var opens = 0;
      final deps = _deps(
        world: world,
        codec: (_) => gate.future,
        open: ({
          required codec,
          required sampleRate,
          required language,
          required force,
          source,
          clientConversationId,
          customSttConfig,
          geolocation,
        }) async {
          opens++;
          return null;
        },
      );
      final p = composeCaptureProvider(deps);
      final device = BtDevice(id: 'synthetic-device', name: 'fixture', type: DeviceType.omi, rssi: -50);
      p.updateRecordingDevice(device);
      p.updateRecordingState(RecordingState.deviceRecord);
      final before = deps.owner.token;
      final pending = p.reconnectActiveCaptureForTesting();
      await pumpEventQueue();
      p.updateRecordingDevice(null);
      p.updateRecordingDevice(device);
      p.updateRecordingState(RecordingState.deviceRecord);
      expect(deps.owner.isCurrent(before), isFalse);
      gate.complete(BleAudioCodec.pcm16);
      await pending;
      expect(opens, 0);
      await p.reconnectActiveCaptureForTesting();
      expect(opens, 1);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('location fix from an obsolete session does not start compatibility upload', () async {
    final dir = await Directory.systemTemp.createTemp('c1-location-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final location = HeldLocation();
      final deps = _deps(world: world, location: location);
      final p = composeCaptureProvider(deps);
      await p.streamRecording();
      await pumpEventQueue();
      expect(location.captures, 1);
      deps.owner.replaceSession('different-account');
      location.fix.complete(Geolocation(latitude: 1, longitude: 2, time: world.clock.now()));
      location.upload.complete();
      await pumpEventQueue();
      expect(location.uploads, 0);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('old upload completion cannot publish geolocation into a new capture WAL', () async {
    final dir = await Directory.systemTemp.createTemp('c1-upload-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final location = HeldLocation();
      final d = _deps(world: world, location: location);
      final phone = PhoneSpy(world.wal.getSyncs().phone);
      final deps = CaptureDependencies(
        wal: WalSpy(phone),
        phoneMic: d.phoneMic,
        batchSupported: d.batchSupported,
        auth: d.auth,
        connectivity: d.connectivity,
        now: d.now,
        scheduling: d.scheduling,
        preferences: d.preferences,
        ble: d.ble,
        openSocket: d.openSocket,
        openConversationSocket: d.openConversationSocket,
        owner: d.owner,
        location: location,
        localSegments: d.localSegments,
        codec: d.codec,
        microphonePermission: d.microphonePermission,
        refreshConversation: d.refreshConversation,
        telemetry: d.telemetry,
        ensureDeviceConnection: d.ensureDeviceConnection,
      );
      final p = composeCaptureProvider(deps);
      await p.streamRecording();
      await pumpEventQueue();
      expect(location.captures, 1);
      location.fix.complete(Geolocation(latitude: 1, longitude: 2, time: world.clock.now()));
      await pumpEventQueue();
      expect(location.uploads, 1);
      d.owner.replaceSession('new-generation');
      location.upload.complete();
      await pumpEventQueue();
      expect(phone.published.whereType<Geolocation>(), isEmpty);
      await p.streamRecording();
      await pumpEventQueue();
      expect(location.captures, 2);
      expect(phone.published.whereType<Geolocation>().single.latitude, 1);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('queued replaceSession drops after a generation roll but keeps the issued write', () async {
    final dir = await Directory.systemTemp.createTemp('c1-store-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final store = HeldStore();
      final deps = _deps(world: world, localSegments: store);
      final p = composeCaptureProvider(deps);
      deps.telemetry.prepare(source: 'phone_live');
      void publish(String text) {
        p.segments = [
          TranscriptSegment(
            id: 's',
            text: text,
            speaker: 'SPEAKER_00',
            isUser: false,
            personId: null,
            start: 0,
            end: 1,
            translations: [],
          ),
        ];
        p.updateRecordingState(RecordingState.record);
      }

      publish('issued');
      await pumpEventQueue();
      expect(store.calls, ['issued']);
      publish('queued-old');
      deps.owner.replaceSession('new-user/new-session');
      store.gate.complete();
      await p.pendingLiveSegmentWrite;
      expect(store.calls, ['issued']);
      expect(store.writes, ['synthetic:issued']);
      publish('current');
      await p.pendingLiveSegmentWrite;
      expect(store.calls, ['issued', 'current']);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('pending auth refresh cannot reconnect after capture generation changes', () async {
    final dir = await Directory.systemTemp.createTemp('c1-auth-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final refresh = Completer<Object?>();
      var refreshes = 0;
      var opens = 0;
      final deps = _deps(
        world: world,
        auth: CaptureAuthBoundary(
          isSignedIn: () => true,
          refreshIdToken: () {
            refreshes++;
            return refresh.future;
          },
        ),
        open: ({
          required codec,
          required sampleRate,
          required language,
          required force,
          source,
          clientConversationId,
          customSttConfig,
          geolocation,
        }) async {
          opens++;
          return null;
        },
      );
      final p = composeCaptureProvider(deps);
      p.updateRecordingState(RecordingState.systemAudioRecord);
      p.onClosed(4001);
      await pumpEventQueue();
      expect(refreshes, 1);
      deps.owner.replaceSession('different-account');
      refresh.complete(null);
      world.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(opens, 0);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('coordinator wake started under generation N does not drain after N+1', () async {
    final dir = await Directory.systemTemp.createTemp('c1-wake-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      var drains = 0;
      final coordinator = RecordingTransferCoordinator(
        reconcile: () async {},
        discover: () async {},
        refreshPending: () async {},
        autoUploadEnabled: () => true,
        drain: () async {
          drains++;
          return const RecordingTransferDrainResult.skipped();
        },
      );
      addTearDown(coordinator.dispose);
      final owner = CaptureSessionOwner(
        coordinator: coordinator,
        startForeground: () async {},
        stopForeground: () async {},
      );
      final phone = PhoneSpy(world.wal.getSyncs().phone);
      final d = _deps(
        world: world,
        owner: owner,
        open: ({
          required codec,
          required sampleRate,
          required language,
          required force,
          source,
          clientConversationId,
          customSttConfig,
          geolocation,
        }) async {
          final socket = TranscriptSegmentSocketService.withSocket(
            sampleRate,
            codec,
            language,
            ScriptedPureSocket(),
          );
          await socket.start();
          return socket;
        },
      );
      final deps = CaptureDependencies(
        wal: WalSpy(phone),
        phoneMic: d.phoneMic,
        batchSupported: d.batchSupported,
        auth: d.auth,
        connectivity: d.connectivity,
        now: d.now,
        scheduling: d.scheduling,
        preferences: d.preferences,
        ble: d.ble,
        openSocket: d.openSocket,
        openConversationSocket: d.openConversationSocket,
        owner: owner,
        location: d.location,
        localSegments: d.localSegments,
        codec: d.codec,
        microphonePermission: d.microphonePermission,
        refreshConversation: d.refreshConversation,
        telemetry: d.telemetry,
        ensureDeviceConnection: d.ensureDeviceConnection,
      );
      final p = composeCaptureProvider(deps);
      await p.changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);
      phone.finalizeGate = Completer<void>();
      p.onMessageEventReceived(
        ConversationProcessingStartedEvent(
          memory: ServerConversation(
            id: 'synthetic',
            createdAt: world.clock.now(),
            structured: Structured('fixture', 'fixture'),
          ),
        ),
      );
      world.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(drains, 0);
      owner.replaceSession('new-session');
      phone.finalizeGate!.complete();
      await pumpEventQueue();
      await coordinator.waitUntilIdle();
      expect(drains, 0);
      await owner.wakeIfCurrent(owner.token, WakeTrigger.userRetry);
      await coordinator.waitUntilIdle();
      expect(drains, 1);
      p.dispose();
      await owner.close();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('composeCaptureProvider socket open receives the captured session geolocation', () async {
    final dir = await Directory.systemTemp.createTemp('c1-geo-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final geo = Geolocation(latitude: 37.5, longitude: -122.3, time: world.clock.now());
      final received = <Geolocation?>[];
      final deps = _deps(
        world: world,
        location: _ImmediateLocation(geo),
        open: ({
          required codec,
          required sampleRate,
          required language,
          required force,
          source,
          clientConversationId,
          customSttConfig,
          geolocation,
        }) async {
          received.add(geolocation);
          return null;
        },
      );
      final p = composeCaptureProvider(deps);
      await p.streamRecording();
      await pumpEventQueue();
      p.updateRecordingState(RecordingState.systemAudioRecord);
      await p.reconnectActiveCaptureForTesting();
      expect(received.where((value) => value?.latitude == 37.5 && value?.longitude == -122.3), isNotEmpty);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });
}
