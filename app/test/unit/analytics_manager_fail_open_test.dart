import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/firmware_update_telemetry.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '2.3.4',
      buildNumber: '567',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('init returns when the analytics SDK hangs', () async {
    final adapter = _FakeAnalyticsAdapter(hangInit: true);
    AnalyticsManager.configure(adapter);

    final elapsed = Stopwatch()..start();
    await AnalyticsManager.init(timeout: const Duration(milliseconds: 10));
    elapsed.stop();

    expect(adapter.isInitialized, isFalse);
    expect(elapsed.elapsed, lessThan(const Duration(milliseconds: 250)));
  });

  test('track queues events and flushes them after init', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);

    AnalyticsManager().track('Queued Event', properties: {'count': 1, 'ignored': null});
    expect(adapter.events, isEmpty);
    expect(AnalyticsManager.queuedEventCountForTesting, 1);

    await AnalyticsManager.init();
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, hasLength(1));
    expect(adapter.events.single.eventName, 'Queued Event');
    expect(adapter.events.single.properties, {
      'count': 1,
      'app_platform': 'unknown',
      'app_version': '2.3.4',
      'app_build': '567',
    });
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });

  test('page opens register context for native interaction events', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().pageOpened('Settings');

    expect(adapter.interactionContexts, [const _InteractionContext(screenName: 'Settings', target: 'screen')]);
  });

  test('canonical app context cannot be overridden by a call site', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().track(
      'Context Event',
      properties: {'app_platform': 'bad-value', 'app_version': '0.0.0', 'app_build': '0'},
    );
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.single.properties, containsPair('app_platform', 'unknown'));
    expect(adapter.events.single.properties, containsPair('app_version', '2.3.4'));
    expect(adapter.events.single.properties, containsPair('app_build', '567'));
  });

  test('recording upload lifecycle keeps one correlation schema through the analytics boundary', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final analytics = AnalyticsManager();

    analytics.recordingUploadStarted(
      attemptId: 'attempt-1',
      recordingId: 'recording-1',
      fileCount: 2,
      totalBytes: 4096,
      claimsLiveCapture: true,
    );
    analytics.recordingUploadCompleted(
      attemptId: 'attempt-1',
      recordingId: 'recording-1',
      fileCount: 2,
      totalBytes: 4096,
      claimsLiveCapture: true,
      durationSeconds: 1.25,
      result: 'accepted',
    );
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.map((event) => event.eventName), ['Recording Upload Started', 'Recording Upload Completed']);
    expect(adapter.events.first.properties, {
      'upload_attempt_id': 'attempt-1',
      'recording_id': 'recording-1',
      'file_count': 2,
      'total_bytes': 4096,
      'claims_live_capture': true,
      'upload_source': 'offline_audio_queue',
      'app_platform': 'unknown',
      'app_version': '2.3.4',
      'app_build': '567',
    });
    expect(adapter.events.last.properties, {
      ...adapter.events.first.properties,
      'duration_seconds': 1.25,
      'result': 'accepted',
    });
  });

  test('track retries adapter failures without throwing through the caller', () async {
    final adapter = _FakeAnalyticsAdapter(trackFailuresBeforeSuccess: 1);
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().track('Retry Event');
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, isEmpty);
    expect(AnalyticsManager.queuedEventCountForTesting, 1);

    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, hasLength(1));
    expect(adapter.events.single.eventName, 'Retry Event');
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });

  test('retry delay sequence starts with the first backoff slot', () {
    expect(AnalyticsManager.retryDelayForTesting(0), const Duration(seconds: 1));
    expect(AnalyticsManager.retryDelayForTesting(1), const Duration(seconds: 5));
    expect(AnalyticsManager.retryDelayForTesting(2), const Duration(seconds: 30));
    expect(AnalyticsManager.retryDelayForTesting(3), const Duration(seconds: 30));
    expect(AnalyticsManager.retryDelayForTesting(4), const Duration(seconds: 30));
  });

  test('queue is bounded and drops oldest events under pressure', () {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);

    for (var i = 0; i < 205; i++) {
      AnalyticsManager().track('Queued Event $i');
    }

    expect(AnalyticsManager.queuedEventCountForTesting, 200);
    expect(AnalyticsManager.droppedEventCountForTesting, 5);
  });

  test('account creation uses the first-auth credential boundary', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().accountCreated(authProvider: 'google');
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.single.eventName, 'Account Created');
    expect(adapter.events.single.properties, {
      'is_first_auth': true,
      'auth_provider': 'google',
      'acquisition_source': 'mobile_oauth',
      'app_platform': 'unknown',
      'app_version': '2.3.4',
      'app_build': '567',
    });
  });

  test('search events share a content-free result schema', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().searchQueryEntered('  two   words  ', 3);
    AnalyticsManager().memorySearched('one', 1);
    AnalyticsManager().conversationDetailSearchQueryEntered(
      conversationId: 'conversation-1',
      query: 'three word query',
      resultsCount: 4,
      activeTab: 'Transcript',
    );
    AnalyticsManager().appsSearched(searchTerm: 'private app name', resultCount: 2);
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, hasLength(4));
    for (final event in adapter.events) {
      expect(
        event.properties.keys,
        containsAll(['query_length', 'query_word_count', 'results_count', 'search_surface']),
      );
      expect(event.properties, isNot(contains('query')));
      expect(event.properties, isNot(contains('search_query')));
      expect(event.properties, isNot(contains('search_term')));
    }
    expect(adapter.events.first.properties, containsPair('query_word_count', 2));
    expect(adapter.events.last.properties, containsPair('search_surface', 'apps'));
  });

  test('firmware update telemetry emits one terminal outcome', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final attempt = FirmwareUpdateTelemetry.start(
      device: BtDevice(id: 'transport-id', name: 'Omi', type: DeviceType.omi, rssi: -50, firmwareRevision: '3.1.0'),
      protocol: 'mcumgr',
    );

    attempt.completed(toVersion: '3.2.0');
    attempt.failed(failureClass: 'late_error');
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.map((event) => event.eventName), ['Firmware Update Started', 'Firmware Update Completed']);
    expect(adapter.events.last.properties, containsPair('from_version', '3.1.0'));
    expect(adapter.events.last.properties, containsPair('to_version', '3.2.0'));
    expect(adapter.events.last.properties, isNot(contains('transport-id')));
  });

  test('firmware update telemetry normalizes an unavailable firmware revision', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    FirmwareUpdateTelemetry.start(
      device: BtDevice(id: 'transport-id', name: 'Omi', type: DeviceType.omi, rssi: -50),
      protocol: 'mcumgr',
    );
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.single.properties, containsPair('from_version', 'unknown'));
  });

  test('memory telemetry carries the recording device firmware context', () {
    final device = BtDevice(id: 'device-id', name: 'Omi', type: DeviceType.omi, rssi: -50, firmwareRevision: '3.2.1');

    expect(AnalyticsManager.recordingDeviceProperties(device), {
      'recording_hardware_type': 'omi',
      'recording_firmware_revision': '3.2.1',
    });
    expect(AnalyticsManager.recordingDeviceProperties(null), {
      'recording_hardware_type': 'phone',
      'recording_firmware_revision': 'not_applicable',
    });
  });

  test('successful upgrade records the subscription transition', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().upgradeSucceeded(previousPlan: 'basic', newPlan: 'plus', billingInterval: 'year');
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.map((event) => event.eventName), ['Subscription Plan Changed', 'Upgrade Succeeded']);
    expect(adapter.events.first.properties, {
      'previous_plan': 'basic',
      'new_plan': 'plus',
      'billing_interval': 'year',
      'change_source': 'mobile_checkout',
      'app_platform': 'unknown',
      'app_version': '2.3.4',
      'app_build': '567',
    });
  });
}

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  _FakeAnalyticsAdapter({this.hangInit = false, this.trackFailuresBeforeSuccess = 0});

  final bool hangInit;
  int trackFailuresBeforeSuccess;
  final List<_RecordedEvent> events = [];
  final List<_InteractionContext> interactionContexts = [];
  bool _initialized = false;

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    if (hangInit) {
      await Completer<void>().future;
    }
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    if (trackFailuresBeforeSuccess > 0) {
      trackFailuresBeforeSuccess--;
      throw StateError('analytics unavailable');
    }
    events.add(_RecordedEvent(eventName, properties ?? const {}));
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {
    interactionContexts.add(_InteractionContext(screenName: screenName, target: target));
  }

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}

class _RecordedEvent {
  const _RecordedEvent(this.eventName, this.properties);

  final String eventName;
  final Map<String, Object> properties;
}

class _InteractionContext {
  const _InteractionContext({required this.screenName, required this.target});

  final String? screenName;
  final String target;

  @override
  bool operator ==(Object other) =>
      other is _InteractionContext && other.screenName == screenName && other.target == target;

  @override
  int get hashCode => Object.hash(screenName, target);
}
