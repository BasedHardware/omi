import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/services.dart';
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

/// Minimal EnvFields stub so Env-backed code paths (e.g. native BLE stream
/// config reading Env.apiBaseUrl) don't hit a LateInitializationError.
class _TestEnvFields implements EnvFields {
  @override
  String? get openAIAPIKey => null;
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get googleMapsApiKey => null;
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
  @override
  String? get stagingApiUrl => null;
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
}
