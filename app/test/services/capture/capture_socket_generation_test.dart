import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:omi/services/capture/capture_ingress_health.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:geolocator/geolocator.dart';
import 'package:omi/backend/http/shared.dart' show accountDeletionWebSocketCloseCode;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/capture_system_surface.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';
import '../../support/capture/virtual_capture_time.dart';
import '../../spine/c1_async_boundaries_test.dart' show HeldLocation;
import '../../spine/c1_location_completion_test.dart' show PhoneSpy, WalSpy;

CaptureDependencies _deps({
  CaptureReplayWorld? world,
  CaptureBleListeners? ble,
  RecordingLifecycleTelemetry? telemetry,
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
    ensureDeviceConnection: (_) async => world?.deviceConnection,
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
    ble: ble ?? _NoopBle(),
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
    telemetry:
        telemetry ?? RecordingLifecycleTelemetry(emitter: (_, __) {}, idFactory: () => 'synthetic', clock: clock.now),
  );
}

class _NoCard implements CaptureSystemSurfaceSink {
  @override
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action) async {}
  @override
  Future<void> publish(Map<String, Object?> snapshot) async {}
  @override
  Future<void> close() async {}
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

class _IngressBle extends ChangeNotifier implements CaptureBleListeners, CaptureIngressPort {
  CaptureIngressHealth? health;
  final authorizations = <bool>[];
  @override
  bool get supportsIngressHealth => true;
  @override
  CaptureIngressHealth? ingressHealth(String deviceId) => health;
  @override
  void addIngressListener(VoidCallback listener) => addListener(listener);
  @override
  void removeIngressListener(VoidCallback listener) => removeListener(listener);
  @override
  Future<void> setCaptureAuthorized(String deviceId, bool authorized) async => authorizations.add(authorized);
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

  test('Android CCCD recovery preserves intent, hides listening and only exhaustion shows a banner', () async {
    final previousPlatform = debugDefaultTargetPlatformOverride;
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final dir = await Directory.systemTemp.createTemp('capture-cccd-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final bridge = BleBridge.instance;
    var retries = 0;
    final previousMonitor = CaptureWedgeMonitor.instance;
    final monitor = CaptureWedgeMonitor(
      now: world.clock.now,
      featureGate: () async => true,
      track: (_, __) {},
      bleRetry: (_) async => retries++,
      appBuild: () => 'test',
      platform: () => 'android',
    );
    CaptureWedgeMonitor.instance = monitor;
    const id = 'synthetic-device';
    void report(bool exhausted) => bridge.onCaptureHealth(
          id,
          jsonEncode({
            'phase': exhausted ? 'actionRequired' : 'recovering',
            'generation': 'android-gatt',
            'reason': CaptureIngressHealth.cccdRecoveryReason,
            'valid_until_ms': 0,
            'subscription_confirmed': false,
            'unverified_since_ms': world.clock.now().millisecondsSinceEpoch,
            'recovery_outcome': exhausted ? 'failed' : 'none',
            'recovery_spent': exhausted,
            'reconnect_spent': exhausted,
          }),
        );
    try {
      world.disposeController();
      world.deviceConnection = ScriptedDeviceConnection();
      report(true); // A background service may report exhaustion before capture binds its listeners.
      final p = composeCaptureProvider(_deps(world: world, ble: const BleBridgeCaptureListeners()));
      try {
        final device = BtDevice(id: id, name: 'Omi', type: DeviceType.omi, rssi: -50);
        await p.streamDeviceRecording(device: device);
        expect(monitor.visiblePrompt, isNotNull, reason: 'binding replays the stored terminal failure');
        expect(p.pendantCaptureVerified, isFalse);
        bridge.onCaptureHealth(id, 'null');
        expect(p.pendantCaptureVerified, isTrue, reason: 'healthy Android keeps its existing policy');
        expect(p.liveCaptureStartedAt, isNotNull);
        report(false);
        bridge.onPeripheralDisconnected(id, 'cccd_timeout');
        expect(bridge.preservesCaptureIntent(id), isTrue);
        expect(p.liveCaptureSource, 'omi');
        expect(p.pendantCaptureVerified, isFalse);
        expect(p.liveCaptureStartedAt, isNull);
        expect(monitor.visiblePrompt, isNull);
        bridge.onDeviceReady(id, []);
        expect(p.pendantCaptureVerified, isFalse, reason: 'ready alone cannot acknowledge a CCCD');
        report(true);
        bridge.onPeripheralDisconnected(id, 'cccd_timeout_exhausted');
        expect(bridge.preservesCaptureIntent(id), isTrue);
        expect(p.liveCaptureSource, 'omi');
        expect(p.pendantCaptureVerified, isFalse);
        expect(p.liveCaptureStartedAt, isNull);
        expect(monitor.visiblePrompt!.trigger, CaptureWedgeMonitor.triggerIngressRecoveryFailed);
        monitor.retryVisibleEpisode();
        await pumpEventQueue();
        expect(retries, 0, reason: 'shared recovery must not bypass the native budget');
        bridge.onDeviceReady(id, []);
        expect(monitor.visiblePrompt, isNotNull, reason: 'a fresh link still needs an ACK');
        bridge.onCaptureHealth(id, 'null'); // Native publishes this only after a current, successful ACK.
        expect(monitor.visiblePrompt, isNull);
        expect(p.pendantCaptureVerified, isTrue);
        expect(p.liveCaptureStartedAt, isNotNull);
        report(true);
        await p.pauseCapture();
        expect(monitor.visiblePrompt, isNull, reason: 'pause releases recovery presentation');
        report(true);
        expect(monitor.visiblePrompt, isNull, reason: 'a late native result cannot re-open a paused capture');
      } finally {
        p.dispose();
      }
    } finally {
      bridge.onCaptureHealth(id, 'null');
      bridge.onPeripheralDisconnected(id, 'unmanaged');
      CaptureWedgeMonitor.instance = previousMonitor;
      monitor.dispose();
      debugDefaultTargetPlatformOverride = previousPlatform;
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('real provider authorizes ingress but waits for audio before Recording Started and timer', () async {
    final dir = await Directory.systemTemp.createTemp('capture-ingress-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final ble = _IngressBle();
    final events = <String>[];
    try {
      world.disposeController();
      world.deviceConnection = ScriptedDeviceConnection();
      final p = composeCaptureProvider(
        _deps(
          world: world,
          ble: ble,
          telemetry: RecordingLifecycleTelemetry(
            emitter: (event, _) => events.add(event),
            clock: world.clock.now,
            idFactory: () => 'ingress',
          ),
        ),
      );
      addTearDown(p.dispose);
      final device = BtDevice(id: 'synthetic-device', name: 'Omi', type: DeviceType.omi, rssi: -50);
      await p.streamDeviceRecording(device: device);
      expect(ble.authorizations, contains(true));
      expect(p.pendantCaptureVerified, isFalse);
      world.deviceConnection!.emitSubscriptionFailure();
      expect(events, contains('Recording Subscription Failed'));
      expect(p.liveCaptureStartedAt, isNull);
      expect(events, isNot(contains(RecordingLifecycleTelemetry.startedEvent)));
      ble.health = CaptureIngressHealth(
        phase: 'flowing',
        generation: 'fresh',
        reason: 'audio_observed',
        validUntilMs: world.clock.now().millisecondsSinceEpoch + 30000,
        subscriptionConfirmed: true,
        unverifiedSinceMs: 0,
      );
      ble.notifyListeners();
      expect(p.pendantCaptureVerified, isTrue);
      final verifiedAt = world.clock.now();
      expect(p.liveCaptureStartedAt, verifiedAt);
      expect(events.where((e) => e == RecordingLifecycleTelemetry.startedEvent), hasLength(1));

      // A lease expiry is a verification lapse, not a new recording: the first
      // verified time must survive so the timer continues instead of
      // restarting at zero when audio returns.
      world.clock.advanceTo(verifiedAt.add(const Duration(seconds: 35)));
      expect(p.pendantCaptureVerified, isFalse);
      expect(p.liveCaptureStartedAt, isNull, reason: 'unverified is still hidden');
      ble.health = CaptureIngressHealth(
        phase: 'flowing',
        generation: 'fresh',
        reason: 'audio_observed',
        validUntilMs: world.clock.now().millisecondsSinceEpoch + 30000,
        subscriptionConfirmed: true,
        unverifiedSinceMs: 0,
      );
      ble.notifyListeners();
      expect(p.pendantCaptureVerified, isTrue);
      expect(p.liveCaptureStartedAt, verifiedAt, reason: 'audio returning must not restart the timer');
      expect(events.where((e) => e == RecordingLifecycleTelemetry.startedEvent), hasLength(1));

      ble.health = null; // ready replay invalidates proof
      ble.notifyListeners();
      expect(p.liveCaptureStartedAt, isNull);
      await p.pauseCapture();
      expect(ble.authorizations.last, isFalse);
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

  test('the Live Activity card claims neither Listening nor a time until pendant audio is verified', () async {
    final dir = await Directory.systemTemp.createTemp('capture-ingress-card-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final ble = _IngressBle();
    try {
      world.disposeController();
      world.deviceConnection = ScriptedDeviceConnection();
      final p = composeCaptureProvider(_deps(world: world, ble: ble));
      addTearDown(p.dispose);
      final card = CaptureSystemSurface(p, _NoCard(), now: world.clock.now);
      await p.streamDeviceRecording(
        device: BtDevice(id: 'synthetic-device', name: 'Omi', type: DeviceType.omi, rssi: -50),
      );
      expect(p.pendantCaptureVerified, isFalse);
      expect(card.snapshot['status'], 'unverified');
      expect(card.snapshot['canPause'], isTrue, reason: 'Pause stays on the card, as in the app');
      // Audio takes a while to arrive; that wait is not capture time.
      world.clock.advanceTo(world.clock.now().add(const Duration(seconds: 12)));
      expect(card.snapshot['status'], 'unverified');

      ble.health = CaptureIngressHealth(
        phase: 'flowing',
        generation: 'fresh',
        reason: 'audio_observed',
        validUntilMs: world.clock.now().millisecondsSinceEpoch + 30000,
        subscriptionConfirmed: true,
        unverifiedSinceMs: 0,
      );
      ble.notifyListeners();
      expect(p.pendantCaptureVerified, isTrue);
      expect(card.snapshot['status'], isNot('unverified'));
      expect(card.snapshot['paused'], isFalse);
      expect(card.snapshot['elapsed'], 0, reason: 'waiting for audio was not capture time');

      final verifiedAt = world.clock.now();
      world.clock.advanceTo(verifiedAt.add(const Duration(seconds: 20)));
      expect(card.snapshot['elapsed'], 20);

      // A lapse hides the claim again and stops the clock until audio is verified again.
      world.clock.advanceTo(verifiedAt.add(const Duration(seconds: 35)));
      expect(p.pendantCaptureVerified, isFalse);
      expect(card.snapshot['status'], 'unverified');
      expect(card.snapshot['paused'], isTrue);
      expect(card.snapshot['elapsed'], 35);
      world.clock.advanceTo(verifiedAt.add(const Duration(seconds: 50)));
      expect(card.snapshot['elapsed'], 35);
      ble.health = CaptureIngressHealth(
        phase: 'flowing',
        generation: 'fresh',
        reason: 'audio_observed',
        validUntilMs: world.clock.now().millisecondsSinceEpoch + 30000,
        subscriptionConfirmed: true,
        unverifiedSinceMs: 0,
      );
      ble.notifyListeners();
      expect(card.snapshot['paused'], isFalse);
      world.clock.advanceTo(verifiedAt.add(const Duration(seconds: 55)));
      expect(card.snapshot['elapsed'], 40);
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });

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
      world.deviceConnection = ScriptedDeviceConnection();
      final gate = Completer<BleAudioCodec>();
      var opens = 0;
      var holdCodec = false;
      final deps = _deps(
        world: world,
        codec: (_) => holdCodec ? gate.future : Future.value(BleAudioCodec.pcm16),
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
      await p.streamDeviceRecording(device: device);
      expect(p.liveCaptureSource, 'omi');
      final initialOpens = opens;
      holdCodec = true;
      final before = deps.owner.token;
      final pending = p.reconnectActiveCaptureForTesting();
      await pumpEventQueue();
      p.updateRecordingDevice(null);
      p.updateRecordingDevice(device);
      expect(deps.owner.isCurrent(before), isTrue);
      gate.complete(BleAudioCodec.pcm16);
      await pending;
      await p.pendingSourceSwitch;
      expect(opens, initialOpens);
      expect(deps.owner.isCurrent(before), isFalse);
      holdCodec = false;
      await p.streamDeviceRecording(device: device);
      expect(opens, initialOpens + 1);
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

  test('websocket close 4005 (account deletion in progress) ends the session instead of reconnecting', () async {
    final dir = await Directory.systemTemp.createTemp('c1-auth-deleted-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      var refreshes = 0;
      var expirations = 0;
      var opens = 0;
      final deps = _deps(
        world: world,
        auth: CaptureAuthBoundary(
          isSignedIn: () => true,
          refreshIdToken: () async {
            refreshes++;
            return null;
          },
          expireDeletedAccountSession: () async => expirations++,
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
      p.onClosed(accountDeletionWebSocketCloseCode);
      await pumpEventQueue();
      expect(expirations, 1);
      expect(refreshes, 0, reason: 'a deleted account is not a stale token');
      // The same close twice (primary and secondary sockets) still asks the
      // idempotent AuthService.expireSession; nothing else fires.
      p.onClosed(accountDeletionWebSocketCloseCode);
      await pumpEventQueue();
      expect(expirations, 2);
      expect(opens, 0);
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

  group('capture wedge detection through the real provider', () {
    CaptureWedgeMonitor installMonitor(List<Map<String, Object>> detected) {
      final monitor = CaptureWedgeMonitor(
        featureGate: () async => true,
        track: (event, properties) {
          if (event == 'Capture Wedge Detected') detected.add(properties);
        },
        bleRetry: (_) async {},
        appBuild: () => '1',
        platform: () => 'ios',
      );
      final previous = CaptureWedgeMonitor.instance;
      CaptureWedgeMonitor.instance = monitor;
      addTearDown(() => CaptureWedgeMonitor.instance = previous);
      return monitor;
    }

    CaptureDependencies wedgeDeps(CaptureReplayWorld world, List<ScriptedPureSocket> transports) {
      return _deps(
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
          final transport = ScriptedPureSocket();
          transports.add(transport);
          final socket = TranscriptSegmentSocketService.withSocket(
            sampleRate,
            codec,
            language,
            transport,
            source: source,
          );
          await socket.start();
          return socket;
        },
      );
    }

    test('three connected zero-byte pendant socket sessions declare a wedge', () async {
      final dir = await Directory.systemTemp.createTemp('c1-wedge-');
      final world = await CaptureReplayWorld.boot(tempDir: dir);
      try {
        world.disposeController();
        world.deviceConnection = ScriptedDeviceConnection();
        final detected = <Map<String, Object>>[];
        final monitor = installMonitor(detected);
        final transports = <ScriptedPureSocket>[];
        final p = composeCaptureProvider(wedgeDeps(world, transports));
        final device = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -50);
        await p.streamDeviceRecording(device: device);
        expect(p.liveCaptureSource, 'omi');

        for (var i = 0; i < 3; i++) {
          if (i != 0) await p.reconnectActiveCaptureForTesting();
          expect(transports, hasLength(i + 1));
          transports.last.emitClose();
          await pumpEventQueue();
        }
        await pumpEventQueue();

        expect(detected, hasLength(1));
        expect(detected.single['source'], 'omi');
        expect(detected.single['trigger'], 'zero_byte_streak');
        expect(monitor.visiblePrompt, isNotNull);
        p.dispose();
      } finally {
        await world.dispose();
        await dir.delete(recursive: true);
      }
    });

    test('a phone-mic session while a pendant is paired does not feed the detector', () async {
      final dir = await Directory.systemTemp.createTemp('c1-wedge-phone-');
      final world = await CaptureReplayWorld.boot(tempDir: dir);
      try {
        world.disposeController();
        final detected = <Map<String, Object>>[];
        installMonitor(detected);
        final transports = <ScriptedPureSocket>[];
        final p = composeCaptureProvider(wedgeDeps(world, transports));
        final device = BtDevice(id: 'omi-2', name: 'Omi', type: DeviceType.omi, rssi: -50);
        p.updateRecordingDevice(device);

        await p.streamRecording();
        await pumpEventQueue();
        expect(transports, isNotEmpty);

        for (var i = 0; i < 3; i++) {
          transports.last.emitClose();
          await pumpEventQueue();
          world.scheduler.elapse(const Duration(seconds: 30));
          await pumpEventQueue();
        }

        expect(detected, isEmpty);
        p.dispose();
      } finally {
        await world.dispose();
        await dir.delete(recursive: true);
      }
    });
  });
}
