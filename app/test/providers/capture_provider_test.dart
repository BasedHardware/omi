import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/enums.dart';

/// Fake external actions that tracks people-refresh calls.
class MockCaptureExternalActions extends NoopCaptureExternalActions {
  int setPeopleCallCount = 0;
  int fetchSubscriptionCallCount = 0;
  Completer<void>? _setPeopleCompleter;
  bool? outOfCreditsOverride;
  String? topConversationIdOverride;

  @override
  bool? get isOutOfCredits => outOfCreditsOverride;

  @override
  String? get topConversationId => topConversationIdOverride;

  @override
  Future<void> refreshPeople() async {
    setPeopleCallCount++;
    if (_setPeopleCompleter != null) {
      // Simulate async work - wait for completer
      await _setPeopleCompleter!.future;
    }
  }

  /// Set a completer to control when setPeople completes
  void setSetPeopleCompleter(Completer<void> completer) {
    _setPeopleCompleter = completer;
  }

  @override
  Future<void> fetchSubscription() async {
    fetchSubscriptionCallCount++;
  }
}

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async {
    return [ConnectivityResult.none];
  }

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

TranscriptSegment _segment(String id, String text) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0.0,
    end: 1.0,
    translations: [],
  );
}

BtDevice _device({required String id, required DeviceType type, String name = 'TestDevice'}) =>
    BtDevice(id: id, name: name, type: type, rssi: -50);

/// CaptureProvider whose socket opening is held on a per-call gate, so a
/// connection attempt can be kept in flight while another caller tries to
/// start one, and each attempt can be released independently.
class _GatedSocketCaptureProvider extends CaptureProvider {
  final List<Completer<void>> gates = [];
  final List<_IdentifiedSocketService> sockets = [];
  int? lastSubscribedId;
  bool returnSockets = false;

  int get openCalls => gates.length;

  @override
  Future<TranscriptSegmentSocketService?> openConversationSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
  }) async {
    final gate = Completer<void>();
    gates.add(gate);
    await gate.future;
    if (!returnSockets) return null;
    final socket = _IdentifiedSocketService(gates.length - 1, (id) => lastSubscribedId = id);
    sockets.add(socket);
    return socket;
  }

  void release(int attempt) => gates[attempt].complete();

  void releaseAll() {
    for (final gate in gates) {
      if (!gate.isCompleted) gate.complete();
    }
  }
}

class _NullSocketCaptureProvider extends CaptureProvider {
  @override
  Future<TranscriptSegmentSocketService?> openConversationSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
  }) async =>
      null;
}

class _CountingSocketCaptureProvider extends CaptureProvider {
  _CountingSocketCaptureProvider({super.audioCodecLoader});

  int openCalls = 0;

  @override
  Future<TranscriptSegmentSocketService?> openConversationSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
  }) async {
    openCalls++;
    return null;
  }
}

class _CountingConversationLocationCapture extends ConversationLocationCapture {
  int calls = 0;
  final List<bool> promptIfDeniedArgs = [];

  @override
  Future<Geolocation?> captureAndUpload({bool promptIfDenied = true}) async {
    calls++;
    promptIfDeniedArgs.add(promptIfDenied);
    return Geolocation(latitude: 1, longitude: 2, time: DateTime.utc(2026));
  }
}

class _HangingConversationLocationCapture extends ConversationLocationCapture {
  int calls = 0;
  final Completer<Geolocation?> _done = Completer<Geolocation?>();

  @override
  Future<Geolocation?> captureAndUpload({bool promptIfDenied = true}) async {
    calls++;
    return _done.future;
  }

  @override
  Future<Geolocation?> capture({bool promptIfDenied = true}) async {
    calls++;
    return _done.future;
  }

  @override
  Future<void> uploadCompatibilitySnapshot(Geolocation geolocation) async {}

  void complete() {
    if (!_done.isCompleted) {
      _done.complete(Geolocation(latitude: 1, longitude: 2, time: DateTime.utc(2026)));
    }
  }
}

class _FakeBatchMicRecorder implements IMicRecorderService {
  int startBatchCalls = 0;

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {}

  @override
  Future<void> startBatch({
    Function()? onStop,
    Function(bool began)? onInterruption,
    Function()? onBatchStalled,
    Function(String code, String message)? onError,
  }) async {
    startBatchCalls++;
  }

  @override
  void stop() {}

  @override
  void probeStallAfterForeground() {}
}

class _IdentifiedSocketService extends TranscriptSegmentSocketService {
  _IdentifiedSocketService(this.id, this.onSubscribed)
      : super.withSocket(16000, BleAudioCodec.pcm16, 'en', _TrackingSocket());

  final int id;
  final void Function(int id) onSubscribed;

  @override
  void subscribe(Object context, ITransctiptSegmentSocketServiceListener listener) {
    onSubscribed(id);
    throw StateError('test socket subscribed');
  }
}

class _TrackingSocket implements IPureSocket {
  @override
  PureSocketStatus get status => PureSocketStatus.connected;

  @override
  Future<bool> connect() async => true;

  @override
  Future<void> disconnect() async {}

  @override
  Future<void> stop() async {}

  @override
  void send(dynamic message) {}

  @override
  void setListener(IPureSocketListener listener) {}

  @override
  void onMessage(dynamic message) {}

  @override
  void onConnected() {}

  @override
  void onClosed() {}

  @override
  void onError(Object err, StackTrace trace) {}
}

/// Minimal EnvFields stub so Env-backed code paths (e.g. native BLE stream
/// config reading Env.apiBaseUrl) don't hit a LateInitializationError.
class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return Directory.systemTemp.path;
        return null;
      },
    );
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      Env.init(_TestEnvFields());
    } catch (_) {
      // Env._instance is late final — ignore if already initialized in this isolate.
    }
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  // ------------------------------------------------------------------ //
  // Existing tests (preserved verbatim from the original file)          //
  // ------------------------------------------------------------------ //

  test('removes segments and related state on deletion event', () {
    final provider = CaptureProvider();
    final first = _segment('a', 'one');
    final second = _segment('b', 'two');

    provider.segments = [first, second];
    provider.suggestionsBySegmentId['a'] = SpeakerLabelSuggestionEvent(
      speakerId: 1,
      personId: 'p1',
      personName: 'Test',
      segmentId: 'a',
    );
    provider.taggingSegmentIds = ['a', 'b'];
    provider.hasTranscripts = true;

    provider.onMessageEventReceived(SegmentsDeletedEvent(segmentIds: ['a']));

    expect(provider.segments.length, 1);
    expect(provider.segments.first.id, 'b');
    expect(provider.suggestionsBySegmentId.containsKey('a'), false);
    expect(provider.taggingSegmentIds.contains('a'), false);
    expect(provider.hasTranscripts, true);
  });

  test('first transcript refreshes conversation location without a foreground task', () async {
    final locationCapture = _CountingConversationLocationCapture();
    final provider = CaptureProvider(
      conversationLocationCapture: locationCapture,
      inProgressConversationLoader: () async {},
    );

    provider.onSegmentReceived([_segment('first', 'hello')]);
    await Future<void>.delayed(Duration.zero);

    expect(locationCapture.calls, 1);
    provider.dispose();
  });

  test('streamDeviceRecording does not wait for location capture', () async {
    final locationCapture = _HangingConversationLocationCapture();
    final provider = CaptureProvider(conversationLocationCapture: locationCapture);

    await provider.streamDeviceRecording().timeout(
          const Duration(seconds: 2),
          onTimeout: () => fail('streamDeviceRecording blocked on location capture'),
        );
    expect(locationCapture.calls, 1);
    locationCapture.complete();
    provider.dispose();
  });

  test('phone batch starts native audio before waiting for location metadata', () async {
    await SharedPreferencesUtil().remove('phoneBatchGeolocation');
    final locationCapture = _HangingConversationLocationCapture();
    final micRecorder = _FakeBatchMicRecorder();
    final provider = CaptureProvider(
      conversationLocationCapture: locationCapture,
      microphonePermissionRequester: () async => true,
      phoneMicBatchRecorder: micRecorder,
    );

    await provider.startPhoneMicBatchForTesting().timeout(
          const Duration(seconds: 2),
          onTimeout: () => fail('phone batch start blocked on location capture'),
        );

    expect(micRecorder.startBatchCalls, 1);
    expect(provider.recordingState, RecordingState.record);
    expect(locationCapture.calls, 1);
    var preferences = await SharedPreferences.getInstance();
    expect(preferences.getString('phoneBatchGeolocation'), isNull);

    locationCapture.complete();
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    preferences = await SharedPreferences.getInstance();
    expect(preferences.getString('phoneBatchGeolocation'), isNotNull);
    provider.dispose();
  });

  test('homepage no-device streamDeviceRecording is check-only', () async {
    final locationCapture = _CountingConversationLocationCapture();
    final events = <({String name, Map<String, dynamic> properties})>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-check-only',
    );
    final provider = CaptureProvider(conversationLocationCapture: locationCapture, recordingTelemetry: telemetry);

    await provider.streamDeviceRecording();
    expect(locationCapture.calls, 1);
    expect(locationCapture.promptIfDeniedArgs, [false]);
    expect(events, isEmpty, reason: 'a no-device homepage entry must not emit Recording Start Failed');
    expect(telemetry.recordingId, isNull);
    provider.dispose();
  });

  test('failed device streamDeviceRecording emits capture_unavailable', () async {
    final events = <({String name, Map<String, dynamic> properties})>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-device-fail',
    );
    // Batch mode skips the transcription socket, so this stays hermetic: a
    // device is requested, but no BLE connection exists, so start cannot
    // reach deviceRecord.
    SharedPreferencesUtil().batchModeEnabled = true;
    addTearDown(() => SharedPreferencesUtil().batchModeEnabled = false);
    final provider = CaptureProvider(recordingTelemetry: telemetry);

    await provider.streamDeviceRecording(
      device: _device(id: 'omi-1', type: DeviceType.omi),
    );

    expect(events.single.name, RecordingLifecycleTelemetry.startFailedEvent);
    expect(events.single.properties['failure_class'], 'capture_unavailable');
    expect(events.single.properties['recording_id'], 'recording-device-fail');
    provider.dispose();
  });

  test('active capture identity survives deletion of the first segment', () {
    final provider = CaptureProvider();
    provider.testSessionStartSeconds = 12345;
    provider.segments = [_segment('first', 'one'), _segment('second', 'two')];

    final captureIdentity = provider.activeCaptureSessionId;
    provider.onMessageEventReceived(SegmentsDeletedEvent(segmentIds: ['first']));

    expect(captureIdentity, 'live-12345');
    expect(provider.activeCaptureSessionId, captureIdentity);
    expect(provider.segments.single.id, 'second');
  });

  group('metricsNotifyEnabled', () {
    test('defaults to not notifying on metrics update', () {
      final provider = CaptureProvider();
      // By default, metrics notify is disabled
      // We can verify this by checking that the provider was created successfully
      // and bleReceiveRateKbps/wsSendRateKbps are accessible (default 0)
      expect(provider.bleReceiveRateKbps, 0.0);
      expect(provider.wsSendRateKbps, 0.0);
    });

    test('addMetricsListener() enables metrics notifications on first listener', () {
      final provider = CaptureProvider();
      var notifyCount = 0;
      provider.addListener(() => notifyCount++);

      provider.addMetricsListener();

      // Should notify when first listener is added
      expect(notifyCount, 1);
    });

    test('removeMetricsListener() handles multiple listeners correctly', () {
      final provider = CaptureProvider();
      var notifyCount = 0;
      provider.addListener(() => notifyCount++);

      // Add two listeners
      provider.addMetricsListener();
      provider.addMetricsListener();
      expect(notifyCount, 1); // Only first add triggers notification

      // Remove one listener - metrics should still be enabled
      provider.removeMetricsListener();
      // Provider still has one listener, so metrics are still enabled

      // Remove second listener - metrics now disabled
      provider.removeMetricsListener();

      // Verify count doesn't go negative
      provider.removeMetricsListener();
    });
  });

  group('metricsNotifyEnabled gating', () {
    test('metrics update does NOT call listeners when no metrics listeners registered', () {
      final provider = CaptureProvider();
      var notifyCount = 0;
      provider.addListener(() => notifyCount++);

      // Don't add any metrics listeners - should NOT notify on metrics update
      final initialCount = notifyCount;
      provider.calculateMetricsForTesting();

      // Should not have triggered additional notifications
      expect(notifyCount, initialCount);
    });

    test('metrics update DOES call listeners when at least one metrics listener registered', () {
      final provider = CaptureProvider();
      var notifyCount = 0;
      provider.addListener(() => notifyCount++);

      // Add a metrics listener - this triggers one notification
      provider.addMetricsListener();
      final countAfterAdd = notifyCount;

      // Now metrics update should notify
      provider.calculateMetricsForTesting();

      // Should have triggered an additional notification
      expect(notifyCount, greaterThan(countAfterAdd));
    });
  });

  group('segmentsPhotosVersion', () {
    test('increments on translation event', () {
      final provider = CaptureProvider();
      final segment = _segment('a', 'hello');
      provider.segments = [segment];

      final initialVersion = provider.segmentsPhotosVersion;

      // Simulate translation event
      provider.onMessageEventReceived(
        TranslationEvent(
          segments: [
            TranscriptSegment(
              id: 'a',
              text: 'hello (translated)',
              speaker: 'SPEAKER_00',
              isUser: false,
              personId: null,
              start: 0.0,
              end: 1.0,
              translations: [],
            ),
          ],
        ),
      );

      expect(provider.segmentsPhotosVersion, greaterThan(initialVersion));
    });

    test('increments on segments deleted event', () {
      final provider = CaptureProvider();
      provider.segments = [_segment('a', 'one'), _segment('b', 'two')];

      final initialVersion = provider.segmentsPhotosVersion;

      provider.onMessageEventReceived(SegmentsDeletedEvent(segmentIds: ['a']));

      expect(provider.segmentsPhotosVersion, greaterThan(initialVersion));
    });

    test('increments on new segment received', () {
      final provider = CaptureProvider();
      provider.segments = [_segment('seed', 'seed')];
      final initialVersion = provider.segmentsPhotosVersion;

      provider.onSegmentReceived([_segment('x', 'new')]);

      expect(provider.segmentsPhotosVersion, greaterThan(initialVersion));
    });

    test('increments on photo processing event and updates id', () {
      final provider = CaptureProvider();
      provider.photos = [ConversationPhoto(id: 'temp-photo', base64: 'img', createdAt: DateTime.now())];
      final initialVersion = provider.segmentsPhotosVersion;

      provider.onMessageEventReceived(PhotoProcessingEvent(tempId: 'temp-photo', photoId: 'permanent-photo'));

      expect(provider.photos.first.id, 'permanent-photo');
      expect(provider.segmentsPhotosVersion, greaterThan(initialVersion));
    });

    test('increments on photo described event and updates description', () {
      final provider = CaptureProvider();
      provider.photos = [ConversationPhoto(id: 'photo-1', base64: 'img', createdAt: DateTime.now())];
      final initialVersion = provider.segmentsPhotosVersion;

      provider.onMessageEventReceived(PhotoDescribedEvent(photoId: 'photo-1', description: 'desc', discarded: true));

      expect(provider.photos.first.description, 'desc');
      expect(provider.photos.first.discarded, true);
      expect(provider.segmentsPhotosVersion, greaterThan(initialVersion));
    });
  });

  group('SpeakerLabelSuggestionEvent', () {
    test('ignores event when personId is empty', () {
      final provider = CaptureProvider();
      provider.segments = [_segment('seg1', 'hello')];

      // Empty personId: backend didn't assign, nothing happens
      final event = SpeakerLabelSuggestionEvent(speakerId: 0, personId: '', personName: 'Alice', segmentId: 'seg1');

      provider.onMessageEventReceived(event);

      // Nothing stored, nothing applied
      expect(provider.suggestionsBySegmentId.containsKey('seg1'), false);
      expect(provider.segments.first.personId, isNull);
    });

    test('auto-applies assignment when personId is provided', () {
      final provider = CaptureProvider();
      // Create segment with speakerId 1 to match the event
      final segment = TranscriptSegment(
        id: 'seg1',
        text: 'hello',
        speaker: 'SPEAKER_01',
        isUser: false,
        personId: null,
        start: 0.0,
        end: 1.0,
        translations: [],
      );
      provider.segments = [segment];

      // New app path: personId is provided, auto-apply to segment
      final event = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person-123',
        personName: 'Alice',
        segmentId: 'seg1',
      );

      provider.onMessageEventReceived(event);

      // Suggestion should NOT be stored (auto-applied instead)
      expect(provider.suggestionsBySegmentId.containsKey('seg1'), false);
      // Segment should be updated with personId
      expect(provider.segments.first.personId, 'person-123');
    });

    test('ignores suggestion for segments being tagged', () {
      final provider = CaptureProvider();
      provider.segments = [_segment('seg-tagging', 'text')];
      provider.taggingSegmentIds = ['seg-tagging'];

      final event = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person-456',
        personName: 'Bob',
        segmentId: 'seg-tagging',
      );

      provider.onMessageEventReceived(event);

      // Should not store suggestion for segment being tagged
      expect(provider.suggestionsBySegmentId.containsKey('seg-tagging'), false);
    });

    test('ignores suggestion for already assigned segments', () {
      final provider = CaptureProvider();
      final assignedSegment = TranscriptSegment(
        id: 'seg-assigned',
        text: 'hello',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: 'existing-person',
        start: 0.0,
        end: 1.0,
        translations: [],
      );
      provider.segments = [assignedSegment];

      final event = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'new-person',
        personName: 'NewPerson',
        segmentId: 'seg-assigned',
      );

      provider.onMessageEventReceived(event);

      // Should not store suggestion for already assigned segment
      expect(provider.suggestionsBySegmentId.containsKey('seg-assigned'), false);
    });
  });

  group('People cache refresh', () {
    TranscriptSegment _segmentWithPerson(String id, String? personId) {
      return TranscriptSegment(
        id: id,
        text: 'text',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: personId,
        start: 0.0,
        end: 1.0,
        translations: [],
      );
    }

    test('triggers setPeople when segment has unknown personId', () {
      final provider = CaptureProvider();
      final mockExternalActions = MockCaptureExternalActions();
      provider.updateExternalActions(mockExternalActions);

      // Pre-populate segments to skip platform-specific initialization code
      provider.segments = [_segmentWithPerson('seed', null)];

      // Segment with personId that's not in cache (cachedPeople is empty)
      final segments = [_segmentWithPerson('seg1', 'unknown-person-id')];

      provider.onSegmentReceived(segments);

      // Should have triggered setPeople
      expect(mockExternalActions.setPeopleCallCount, 1);
    });

    test('does not trigger refresh for segments without personId', () {
      final provider = CaptureProvider();
      final mockExternalActions = MockCaptureExternalActions();
      provider.updateExternalActions(mockExternalActions);

      // Pre-populate segments to skip platform-specific initialization code
      provider.segments = [_segmentWithPerson('seed', null)];

      final segments = [_segmentWithPerson('seg2', null)];

      provider.onSegmentReceived(segments);

      // Should NOT trigger setPeople (no personId to check)
      expect(mockExternalActions.setPeopleCallCount, 0);
    });

    test('does not trigger multiple refreshes while one is in-flight', () async {
      final provider = CaptureProvider();
      final mockExternalActions = MockCaptureExternalActions();

      // Set up a completer to control when setPeople completes
      final completer = Completer<void>();
      mockExternalActions.setSetPeopleCompleter(completer);

      provider.updateExternalActions(mockExternalActions);

      // Pre-populate segments to skip platform-specific initialization code
      provider.segments = [_segmentWithPerson('seed', null)];

      // First segment with unknown personId
      final segments1 = [_segmentWithPerson('seg-a', 'unknown-1')];
      provider.onSegmentReceived(segments1);

      // Should trigger first call
      expect(mockExternalActions.setPeopleCallCount, 1);

      // Second segment with different unknown personId while first is still in-flight
      final segments2 = [_segmentWithPerson('seg-b', 'unknown-2')];
      provider.onSegmentReceived(segments2);

      // Should NOT trigger another call (first is still in-flight)
      expect(mockExternalActions.setPeopleCallCount, 1);

      // Complete the first call
      completer.complete();
      await Future.delayed(Duration.zero); // Let the future complete

      // Third segment - now a new call should be allowed
      final segments3 = [_segmentWithPerson('seg-c', 'unknown-3')];
      provider.onSegmentReceived(segments3);

      // Should trigger a new call
      expect(mockExternalActions.setPeopleCallCount, 2);
    });
  });

  group('external actions port', () {
    test('repeated external-action updates do not schedule duplicate startup recovery', () {
      fakeAsync((async) {
        final provider = CaptureProvider();
        final pendingTimersBeforeUpdates = async.pendingTimers.length;

        provider.updateExternalActions(MockCaptureExternalActions());
        provider.updateExternalActions(MockCaptureExternalActions());

        expect(async.pendingTimers, hasLength(pendingTimersBeforeUpdates));
      });
    });

    test('topConversationId delegates through external actions', () {
      final provider = CaptureProvider();
      final mockExternalActions = MockCaptureExternalActions()..topConversationIdOverride = 'conversation-1';

      provider.updateExternalActions(mockExternalActions);

      expect(provider.topConversationId, 'conversation-1');
    });

    test('bare provider does not reset freemium threshold when usage state is unknown', () async {
      final provider = CaptureProvider();
      provider.onMessageEventReceived(
        FreemiumThresholdReachedEvent(remainingSeconds: 120, action: FreemiumAction.setupOnDeviceStt),
      );

      expect(provider.freemiumThresholdReached, isTrue);
      await provider.checkCreditsAndResetThresholdIfNeeded();

      expect(provider.freemiumThresholdReached, isTrue);
    });

    test('resets freemium threshold when wired usage state reports credits restored', () async {
      final provider = CaptureProvider();
      final mockExternalActions = MockCaptureExternalActions()..outOfCreditsOverride = false;
      provider.updateExternalActions(mockExternalActions);
      provider.onMessageEventReceived(
        FreemiumThresholdReachedEvent(remainingSeconds: 120, action: FreemiumAction.setupOnDeviceStt),
      );

      await provider.checkCreditsAndResetThresholdIfNeeded();

      expect(mockExternalActions.fetchSubscriptionCallCount, 1);
      expect(provider.freemiumThresholdReached, isFalse);
    });
  });

  group('onClosed warning snackbar', () {
    Future<void> _pumpAppWithScaffold(WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          navigatorKey: globalNavigatorKey,
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: const Scaffold(body: SizedBox.shrink()),
        ),
      );
      await tester.pump();
    }

    testWidgets('shows reconnecting warning when socket closes during phone mic recording', (tester) async {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.record);

      await _pumpAppWithScaffold(tester);

      provider.onClosed();
      // Prevent keepalive reconnect branch from attempting websocket work in this test.
      provider.updateRecordingState(RecordingState.stop);
      await tester.pump();

      final context = tester.element(find.byType(Scaffold));
      final expectedText = AppLocalizations.of(context).transcriptionPausedReconnecting;

      expect(find.byType(SnackBar), findsOneWidget);
      expect(find.text(expectedText), findsOneWidget);
      provider.dispose();
    });

    testWidgets('does not show reconnecting warning when not phone mic recording', (tester) async {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.stop);

      await _pumpAppWithScaffold(tester);

      provider.onClosed();
      await tester.pump();

      final context = tester.element(find.byType(Scaffold));
      final expectedText = AppLocalizations.of(context).transcriptionPausedReconnecting;

      expect(find.byType(SnackBar), findsNothing);
      expect(find.text(expectedText), findsNothing);
      provider.dispose();
    });
  });

  group('terminal live transcription status', () {
    test('preserves server STT failure across socket close until ready', () {
      final provider = CaptureProvider();
      final failure = MessageServiceStatusEvent(
        status: 'stt_failed',
        outcome: 'upstream_error',
        provider: 'deepgram',
        retryable: true,
        reason: 'connection_lost',
      );

      provider.onMessageEventReceived(failure);
      expect(provider.terminalTranscriptionFailure?.outcome, 'upstream_error');
      expect(provider.terminalTranscriptionFailure?.retryable, isTrue);

      provider.onClosed();
      expect(provider.terminalTranscriptionFailure?.status, 'stt_failed');

      provider.onMessageEventReceived(MessageServiceStatusEvent(status: 'ready'));
      expect(provider.terminalTranscriptionFailure, isNull);
      provider.dispose();
    });

    test('parses legacy and populated service-status payloads additively', () {
      final legacy = MessageServiceStatusEvent.fromJson({'type': 'service_status', 'status': 'ready'});
      final failed = MessageServiceStatusEvent.fromJson({
        'type': 'service_status',
        'status': 'stt_failed',
        'outcome': 'timeout',
        'provider': 'parakeet',
        'retryable': true,
        'reason': 'send_failed',
      });

      expect(legacy.outcome, isNull);
      expect(failed.outcome, 'timeout');
      expect(failed.provider, 'parakeet');
      expect(failed.retryable, isTrue);
      expect(failed.reason, 'send_failed');
    });
  });

  // Regression coverage for issue #6499: before this change, a socket drop
  // during phone-mic recording (e.g. triggered by an iOS audio session
  // interruption from an incoming call) left recordingState stuck at `record`,
  // so the UI kept claiming the session was live while the pipeline was dead.
  group('onClosed recordingState reflection (#6499)', () {
    test('flips record to interrupted when socket drops during phone mic', () {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.record);

      provider.onClosed();

      expect(provider.recordingState, RecordingState.interrupted);
      // Stop the state so the keepalive timer doesn't try to reconnect.
      provider.updateRecordingState(RecordingState.stop);
      provider.dispose();
    });

    test('leaves deviceRecord state untouched when socket drops', () {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.deviceRecord);

      provider.onClosed();

      expect(provider.recordingState, RecordingState.deviceRecord);
      provider.updateRecordingState(RecordingState.stop);
      provider.dispose();
    });

    test('leaves stop state untouched when onClosed fires after user stop', () {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.stop);

      provider.onClosed();

      expect(provider.recordingState, RecordingState.stop);
      expect(provider.keepAliveScheduledForTesting, isFalse);
      provider.dispose();
    });

    test('schedules reconnect only for an active device capture', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      provider.updateRecordingState(RecordingState.deviceRecord);

      provider.onClosed();

      expect(provider.keepAliveScheduledForTesting, isTrue);
      provider.updateRecordingState(RecordingState.stop);
      provider.onClosed();
      expect(provider.keepAliveScheduledForTesting, isFalse);
      provider.dispose();
    });

    test('does not reconnect after device capture stops while codec lookup is pending', () async {
      final codec = Completer<BleAudioCodec>();
      final provider = _CountingSocketCaptureProvider(audioCodecLoader: (_) => codec.future);
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      provider.updateRecordingState(RecordingState.deviceRecord);

      final reconnect = provider.reconnectActiveCaptureForTesting();
      await Future<void>.delayed(Duration.zero);
      provider.updateRecordingState(RecordingState.stop);
      codec.complete(BleAudioCodec.opus);
      await reconnect;

      expect(provider.openCalls, 0);
      provider.dispose();
    });

    test('system audio capture remains eligible for websocket reconnect', () async {
      final provider = _CountingSocketCaptureProvider();
      provider.updateRecordingState(RecordingState.systemAudioRecord);

      await provider.reconnectActiveCaptureForTesting();

      expect(provider.openCalls, 1);
      provider.dispose();
    });

    test('onConnected restores record from interrupted', () {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.record);

      provider.onClosed();
      expect(provider.recordingState, RecordingState.interrupted);

      provider.onConnected();

      expect(provider.recordingState, RecordingState.record);
      provider.updateRecordingState(RecordingState.stop);
      provider.dispose();
    });

    test('onConnected does not alter stop state', () {
      final provider = CaptureProvider();
      provider.onConnectionStateChanged(true);
      provider.updateRecordingState(RecordingState.stop);

      provider.onConnected();

      expect(provider.recordingState, RecordingState.stop);
      provider.dispose();
    });

    test('recordingDeviceServiceReady includes interrupted state', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.interrupted);

      expect(provider.recordingDeviceServiceReady, isTrue);

      provider.updateRecordingState(RecordingState.stop);
      provider.dispose();
    });
  });

  // ------------------------------------------------------------------ //
  // Issue #7548: Background Mode fail-closed guardrail tests           //
  // ------------------------------------------------------------------ //

  group('hasNativeBleAudioRoute', () {
    test('returns false when no device connected', () {
      final provider = CaptureProvider();
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('returns false for empty device id (stale sentinel)', () {
      final provider = CaptureProvider();
      // Simulate an Omi device with empty id — should be rejected to avoid
      // false positive where a sentinel device is treated as available.
      provider.updateRecordingDevice(_device(id: '', type: DeviceType.omi));
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('returns true for Omi device with non-empty id', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      expect(provider.hasNativeBleAudioRoute, isTrue);
      provider.dispose();
    });

    test('returns true for OpenGlass device with non-empty id', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: '11:22:33:44:55:66', type: DeviceType.openglass));
      expect(provider.hasNativeBleAudioRoute, isTrue);
      provider.dispose();
    });

    test('returns true for Friend Pendant device with non-empty id', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.friendPendant));
      expect(provider.hasNativeBleAudioRoute, isTrue);
      provider.dispose();
    });

    test('returns false for Apple Watch', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.appleWatch));
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('returns false for Bee', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.bee));
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('returns false for Fieldy', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.fieldy));
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('returns true for Limitless (flash-drain route) but no background-stream route', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.limitless));
      expect(provider.hasNativeBleAudioRoute, isTrue);
      expect(provider.hasNativeBackgroundStreamRoute, isFalse);
      provider.dispose();
    });

    test('returns false for Plaud', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.plaud));
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });
  });

  group('setBackgroundModeEnabled', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      SharedPreferencesUtil().batchModeEnabled = false;
      SharedPreferencesUtil().backgroundModeEnabled = false;
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
      await SharedPreferencesUtil().remove('nativeBleStreamConfig');
    });

    test('disable clears realtime prefs and stale config when batch mode is off', () async {
      final provider = CaptureProvider();
      // Pre-set prefs to true to verify they get cleared
      SharedPreferencesUtil().backgroundModeEnabled = true;
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', true);
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', true);
      await SharedPreferencesUtil().saveString('nativeBleStreamConfig', '{"test": true}');

      final result = await provider.setBackgroundModeEnabled(false);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleForegroundReady'), isFalse);
      expect(SharedPreferencesUtil().getString('nativeBleStreamConfig'), isEmpty);
      provider.dispose();
    });

    test('disable keeps native config when batch mode still needs it without a live route', () async {
      final provider = CaptureProvider();
      SharedPreferencesUtil().batchModeEnabled = true;
      SharedPreferencesUtil().backgroundModeEnabled = true;
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', true);
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', true);
      await SharedPreferencesUtil().saveString('nativeBleStreamConfig', '{"test": true}');

      final result = await provider.setBackgroundModeEnabled(false);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleForegroundReady'), isFalse);
      expect(SharedPreferencesUtil().getString('nativeBleStreamConfig'), '{"test": true}');
      provider.dispose();
    });

    test('enable rejects when no device connected', () async {
      final provider = CaptureProvider();

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      provider.dispose();
    });

    test('enable rejects for device with no native route (Apple Watch)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.appleWatch));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      provider.dispose();
    });

    test('enable rejects for device with no native route (Bee)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.bee));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      provider.dispose();
    });

    test('enable rejects for device with no native route (Fieldy)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.fieldy));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      provider.dispose();
    });

    test('enable rejects for device with no native route (Limitless)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.limitless));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      provider.dispose();
    });

    test('enable rejects for device with no native route (Plaud)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.plaud));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      provider.dispose();
    });

    test('enable rejects for empty-id Omi device (stale sentinel)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: '', type: DeviceType.omi));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      provider.dispose();
    });

    test('enable accepts for Omi device with valid id', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);
      // Batch mode is off by default, so nativeBleStreamingEnabled should be true
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isTrue);
      provider.dispose();
    });

    test('keeps native Omi background audio disabled when Custom STT raw forwarding is off', () async {
      await SharedPreferencesUtil().saveCustomSttConfig(
        const CustomSttConfig(provider: SttProvider.onDeviceWhisper, sendRawAudioToOmi: false),
      );
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      provider.dispose();
    });

    test('enable preserves foreground-ready when foreground streaming is already active', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', true);

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isTrue);
      expect(SharedPreferencesUtil().getBool('nativeBleForegroundReady'), isTrue);
      provider.dispose();
    });

    test('enable accepts for OpenGlass device with valid id', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: '11:22:33:44:55:66', type: DeviceType.openglass));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isTrue);
      provider.dispose();
    });

    test('enable accepts for Friend Pendant device with valid id', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.friendPendant));

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isTrue);
      provider.dispose();
    });

    test('enable with batch mode on sets backgroundModeEnabled but not nativeBleStreaming', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      SharedPreferencesUtil().batchModeEnabled = true;

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);
      // Batch mode is on, so native streaming should stay false
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      provider.dispose();
    });

    test('rejected enable clears stale config', () async {
      final provider = CaptureProvider();
      // No device connected — should reject
      await SharedPreferencesUtil().saveString('nativeBleStreamConfig', '{"stale": true}');
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', true);
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', true);
      SharedPreferencesUtil().backgroundModeEnabled = true;

      final result = await provider.setBackgroundModeEnabled(true);

      expect(result, isFalse);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      expect(SharedPreferencesUtil().getBool('nativeBleForegroundReady'), isFalse);
      expect(SharedPreferencesUtil().getString('nativeBleStreamConfig'), isEmpty);
      provider.dispose();
    });

    test('enable/disable cycle works for valid device', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));

      // Enable
      expect(await provider.setBackgroundModeEnabled(true), isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isTrue);

      // Disable
      expect(await provider.setBackgroundModeEnabled(false), isTrue);
      expect(SharedPreferencesUtil().backgroundModeEnabled, isFalse);

      provider.dispose();
    });
  });

  group('unsupported Custom STT codec privacy recovery', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      await SharedPreferencesUtil().saveCustomSttConfig(
        const CustomSttConfig(provider: SttProvider.onDeviceWhisper, sendRawAudioToOmi: false),
      );
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', true);
    });

    tearDown(() async {
      await SharedPreferencesUtil().saveCustomSttConfig(CustomSttConfig.defaultConfig);
    });

    test('disables native Omi audio and schedules a websocket retry', () {
      fakeAsync((async) {
        final provider = _NullSocketCaptureProvider();
        provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
        provider.updateRecordingState(RecordingState.deviceRecord);
        final timersBefore = async.pendingTimers.length;
        var completed = false;

        provider.changeAudioRecordProfile(audioCodec: BleAudioCodec.lc3FS1030).then((_) => completed = true);
        async.flushMicrotasks();

        expect(completed, isTrue);
        expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
        expect(async.pendingTimers.length, timersBefore + 1);
        provider.dispose();
      });
    });

    test('does not schedule a websocket retry when capture is idle', () {
      fakeAsync((async) {
        final provider = CaptureProvider();
        final timersBefore = async.pendingTimers.length;

        provider.changeAudioRecordProfile(audioCodec: BleAudioCodec.lc3FS1030);
        async.flushMicrotasks();

        expect(async.pendingTimers.length, timersBefore);
        provider.dispose();
      });
    });
  });

  group('stale reconciliation — hasNativeBleAudioRoute after device switch', () {
    test('switching from valid device to no device clears route', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      expect(provider.hasNativeBleAudioRoute, isTrue);

      provider.updateRecordingDevice(null);
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('switching from Omi to Apple Watch clears route', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      expect(provider.hasNativeBleAudioRoute, isTrue);

      provider.updateRecordingDevice(_device(id: '11:22:33:44:55:66', type: DeviceType.appleWatch));
      expect(provider.hasNativeBleAudioRoute, isFalse);
      provider.dispose();
    });

    test('switching from no-route device to Omi gains route', () {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.fieldy));
      expect(provider.hasNativeBleAudioRoute, isFalse);

      provider.updateRecordingDevice(_device(id: '11:22:33:44:55:66', type: DeviceType.omi));
      expect(provider.hasNativeBleAudioRoute, isTrue);
      provider.dispose();
    });
  });

  group('Background Mode + batch mode interaction', () {
    setUp(() {
      SharedPreferencesUtil().batchModeEnabled = false;
      SharedPreferencesUtil().backgroundModeEnabled = false;
    });

    test('enable background, then enable batch: streaming should be false', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));

      await provider.setBackgroundModeEnabled(true);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isTrue);

      // setBatchMode turns batch on
      await provider.setBatchMode(true);
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      provider.dispose();
    });

    test('batch on, then enable background: streaming should be false (batch wins)', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
      SharedPreferencesUtil().batchModeEnabled = true;

      await provider.setBackgroundModeEnabled(true);
      // setBackgroundModeEnabled with batch mode on should keep nativeBleStreaming false
      expect(SharedPreferencesUtil().getBool('nativeBleStreamingEnabled'), isFalse);
      provider.dispose();
    });
  });

  // ------------------------------------------------------------------ //
  // Device mute persistence: a double-tap mute must survive an app      //
  // kill/restart, otherwise the device silently resumes recording on    //
  // the next reconnect (Featurebase: "If I turn off recording why       //
  // doesn't it stay off?", "Cv1 unmutes on disconnect/reconnect").      //
  // ------------------------------------------------------------------ //
  group('device mute persistence', () {
    setUp(() {
      SharedPreferencesUtil().deviceMuted = false;
    });

    test('constructor restores muted state when deviceMuted pref is set', () {
      SharedPreferencesUtil().deviceMuted = true;

      final provider = CaptureProvider();

      // _isPaused restored from prefs so the reconnect path re-applies the mute
      // instead of resuming capture.
      expect(provider.isPaused, isTrue);
      provider.dispose();
    });

    test('constructor leaves recording unpaused when deviceMuted pref is unset', () {
      SharedPreferencesUtil().deviceMuted = false;

      final provider = CaptureProvider();

      expect(provider.isPaused, isFalse);
      provider.dispose();
    });

    test('pauseDeviceRecording persists the mute to prefs', () async {
      final provider = CaptureProvider();
      provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));

      await provider.pauseDeviceRecording();

      expect(provider.isPaused, isTrue);
      expect(SharedPreferencesUtil().deviceMuted, isTrue);
      provider.dispose();
    });
  });

  // Regression coverage for issue #6311: before this change
  // `transcriptServiceReady` was `_transcriptServiceReady && _isConnected`, so a
  // transient ConnectivityService flicker (WiFi↔cellular handoff, brief DNS
  // hiccup) flipped the header to "Recording, reconnecting" even while the
  // transcript WebSocket was alive and segments were flowing. The socket
  // lifecycle is the authoritative signal; a connectivity change must never
  // change transcript-service readiness.
  group('transcriptServiceReady is socket-driven, not connectivity-driven (#6311)', () {
    test('connectivity flicker does not toggle readiness of a ready socket', () {
      final provider = CaptureProvider();

      // Drive the provider into the socket-subscribed state (the scenario the
      // old getter got wrong): onConnected mirrors the transcript WebSocket
      // subscribing, which sets _transcriptServiceReady = true.
      provider.onConnected();
      expect(provider.transcriptServiceReady, isTrue);

      // A connectivity flicker must not toggle readiness off. Before the fix
      // this ANDed _isConnected=false into the getter and manufactured a false
      // "Recording, reconnecting" over a healthy socket.
      provider.onConnectionStateChanged(false);
      expect(provider.transcriptServiceReady, isTrue, reason: 'ready socket must survive a connectivity flicker');

      // And it must not depend on connectivity coming back either.
      provider.onConnectionStateChanged(true);
      expect(provider.transcriptServiceReady, isTrue);

      // A socket close is the only thing that should end readiness.
      provider.onClosed();
      expect(provider.transcriptServiceReady, isFalse, reason: 'socket close must end transcript readiness');
      provider.dispose();
    });
  });

  // Regression coverage for issue #11305: the keep-alive reconnect callback is
  // async, so a tick could call _initiateWebsocket() again while the previous
  // attempt was still connecting. The capture log showed reconnect attempts 24
  // and 25 overlapping (12s apart, both reaching service-ready), which opens
  // duplicate /v4/listen sessions and races the controller state.
  group('no duplicate transcription connection attempt (#11305)', () {
    Future<void> settle() async {
      for (var i = 0; i < 50; i++) {
        await Future<void>.delayed(Duration.zero);
      }
    }

    setUp(() {
      // Batch mode short-circuits the socket entirely; an earlier test leaves
      // the shared preference on.
      SharedPreferencesUtil().batchModeEnabled = false;
    });

    Future<void> startAttempt(
      _GatedSocketCaptureProvider provider, {
      BleAudioCodec codec = BleAudioCodec.pcm16,
      int sampleRate = 16000,
    }) =>
        provider.changeAudioRecordProfile(
          audioCodec: codec,
          sampleRate: sampleRate,
          source: ConversationSource.phone.name,
        );

    test('drops a reconnect attempt while one is still in flight', () async {
      final provider = _GatedSocketCaptureProvider();

      final first = startAttempt(provider);
      await settle();
      expect(provider.openCalls, 1, reason: 'the first attempt must reach the socket service');

      // Second attempt arrives before the first completes: previously it opened
      // a second socket, now it is dropped.
      await startAttempt(provider);
      expect(provider.openCalls, 1, reason: 'an overlapping attempt must not open a second socket');

      provider.release(0);
      await first;

      // The guard clears once the attempt finishes, so reconnects still work.
      final next = startAttempt(provider);
      await settle();
      expect(provider.openCalls, 2, reason: 'a later attempt must connect again');

      provider.releaseAll();
      await next;
      provider.dispose();
    });

    test('does not drop a forced attempt', () async {
      final provider = _GatedSocketCaptureProvider();

      final first = startAttempt(provider);
      await settle();
      expect(provider.openCalls, 1);

      // Settings/profile changes stop the current socket and must replace it
      // even while an attempt is in flight.
      provider.updateRecordingState(RecordingState.record);
      final forced = provider.onTranscriptionSettingsChanged();
      await settle();
      expect(provider.openCalls, 2, reason: 'a forced reconnect must not be gated');

      provider.releaseAll();
      await first;
      await forced;
      provider.dispose();
    });

    test('does not install a stale socket after a newer forced attempt', () async {
      final provider = _GatedSocketCaptureProvider();
      provider.returnSockets = true;

      final first = startAttempt(provider);
      await settle();
      provider.updateRecordingState(RecordingState.record);
      final forced = provider.onTranscriptionSettingsChanged();
      await settle();
      expect(provider.openCalls, 2);

      provider.release(1);
      try {
        await forced;
      } catch (error) {
        expect(error, isA<StateError>());
      }
      expect(provider.lastSubscribedId, 1);

      provider.release(0);
      await first;
      expect(provider.lastSubscribedId, 1);
      provider.dispose();
    });

    test('stays gated while a forced attempt with the same parameters runs', () async {
      final provider = _GatedSocketCaptureProvider();

      final first = startAttempt(provider);
      await settle();
      expect(provider.openCalls, 1);

      // Same parameters as the attempt in flight, so both share a guard key.
      provider.updateRecordingState(RecordingState.record);
      final forced = provider.onTranscriptionSettingsChanged();
      await settle();
      expect(provider.openCalls, 2);

      // The first attempt finishing must not ungate the forced one still
      // connecting, or the next keep-alive tick opens a third socket.
      provider.release(0);
      await first;

      await startAttempt(provider);
      expect(provider.openCalls, 2, reason: 'a repeat must stay gated while the forced attempt is in flight');

      provider.releaseAll();
      await forced;
      provider.dispose();
    });

    test('does not drop an attempt with different parameters', () async {
      final provider = _GatedSocketCaptureProvider();

      final first = startAttempt(provider);
      await settle();
      expect(provider.openCalls, 1);

      // A different codec is a new intent (e.g. the user starts phone mic while
      // a device reconnect is in flight), not the same attempt repeated.
      final other = startAttempt(provider, codec: BleAudioCodec.opus, sampleRate: 16000);
      await settle();
      expect(provider.openCalls, 2, reason: 'a differently configured attempt must not be gated');

      provider.releaseAll();
      await first;
      await other;
      provider.dispose();
    });
  });

  group('in-progress conversation poll cycle', () {
    // The socket starts this cycle on every connect. Restarting an already
    // running cycle put its attempt counter back to zero, so a connection that
    // reconnects more often than the give-up window kept the app polling
    // GET /v1/conversations?...&statuses=in_progress indefinitely instead of
    // ever reaching the cap.
    test('a reconnect mid-cycle does not reset the attempt counter', () {
      fakeAsync((async) {
        final provider = CaptureProvider(inProgressConversationLoader: () async {});
        provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
        provider.updateRecordingState(RecordingState.deviceRecord);

        provider.startInProgressConversationRefreshForTesting();
        async.elapse(const Duration(seconds: 10));
        async.flushMicrotasks();

        final attemptsBeforeReconnect = provider.inProgressConversationRefreshAttemptsForTesting;
        expect(attemptsBeforeReconnect, greaterThan(0));

        // Simulate a socket reconnect landing while the cycle is still running.
        provider.startInProgressConversationRefreshForTesting();

        expect(
          provider.inProgressConversationRefreshAttemptsForTesting,
          attemptsBeforeReconnect,
          reason: 'a reconnect must not restart an already-running poll cycle',
        );

        provider.dispose();
      });
    });

    test('the cycle self-terminates at its cap when nothing interrupts it', () {
      fakeAsync((async) {
        var loadCalls = 0;
        final provider = CaptureProvider(inProgressConversationLoader: () async => loadCalls++);
        provider.updateRecordingDevice(_device(id: 'AA:BB:CC:DD:EE:FF', type: DeviceType.omi));
        provider.updateRecordingState(RecordingState.deviceRecord);

        provider.startInProgressConversationRefreshForTesting();
        async.elapse(const Duration(seconds: 90));
        async.flushMicrotasks();

        expect(provider.inProgressConversationRefreshActiveForTesting, isFalse);
        expect(loadCalls, 30);

        provider.dispose();
      });
    });
  });
}
