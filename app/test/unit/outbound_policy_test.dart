import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/outbound_policy.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/crashlytics_recorder.dart';

/// Omi's third-party services (analytics, crash reporting, support chat, push) report to Omi's
/// vendors, keyed to Omi accounts. While the app talks to a backend that is not Omi's they must
/// stay off, so activity on someone else's server is never reported to Omi.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() => Env.init(_TestEnv()));
  tearDown(() {
    OutboundPolicy.debugThirdPartyServicesAllowed = true;
    Env.clearApiBaseUrlOverrideForTesting();
  });

  test("only Omi's own HTTPS API hosts count as Omi's backend", () {
    for (final url in ['https://api.omi.me/', 'https://api.omiapi.com/', 'https://API.OMI.ME/v1/']) {
      expect(OutboundPolicy.isOmiBackend(url), isTrue, reason: url);
    }
    for (final url in [
      null,
      '',
      'http://api.omi.me/',
      'https://api.omi.me.example.test/',
      'https://omi.example.test/',
      'http://127.0.0.1:8000/',
      'https://my-omi.tailnet.ts.net/',
    ]) {
      expect(OutboundPolicy.isOmiBackend(url), isFalse, reason: '$url');
    }
  });

  group('resolve at boot', () {
    test('a saved custom backend turns third-party services off and is live before they start', () async {
      SharedPreferences.setMockInitialValues({'customBackendUrl': 'https://omi.example.test'});

      await OutboundPolicy.resolve();

      expect(Env.apiBaseUrl, 'https://omi.example.test/');
      expect(OutboundPolicy.thirdPartyServicesAllowed, isFalse);
    });

    test("a saved override that is Omi's own backend leaves them on", () async {
      SharedPreferences.setMockInitialValues({'customBackendUrl': 'https://api.omi.me'});

      await OutboundPolicy.resolve();

      expect(OutboundPolicy.thirdPartyServicesAllowed, isTrue);
    });
  });

  group('analytics', () {
    late _RecordingAdapter adapter;

    setUp(() async {
      AnalyticsManager.resetForTesting();
      PackageInfo.setMockInitialValues(
        appName: 'Omi',
        packageName: 'com.example.omi',
        version: '1.0.0',
        buildNumber: '1',
        buildSignature: '',
      );
      SharedPreferences.setMockInitialValues({'deviceIdHash': 'hash'});
      await SharedPreferencesUtil.init();
      adapter = _RecordingAdapter();
      AnalyticsManager.configure(adapter);
    });
    tearDown(AnalyticsManager.resetForTesting);

    test('does not start against a backend that is not Omi\'s', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      await PlatformManager.initializeServices();
      await pumpEventQueue();

      expect(adapter.inits, 0);
    });

    test("starts against Omi's backend", () async {
      await PlatformManager.initializeServices();
      await pumpEventQueue();

      expect(adapter.inits, 1);
    });
  });

  group('crash reporting', () {
    late CrashlyticsRecorder recorder;

    setUpAll(() async => recorder = await installCrashlyticsRecorder());
    setUp(() => recorder.reset());

    test('collection is switched off, persistently, and nothing is set up', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      await CrashlyticsManager.init();

      final enabled = recorder.calls.where((c) => c.method == 'Crashlytics#setCrashlyticsCollectionEnabled');
      expect(enabled.map((c) => (c.arguments as Map)['enabled']), [false]);
      expect(recorder.calls.map((c) => c.method), everyElement('Crashlytics#setCrashlyticsCollectionEnabled'));
    });

    test("against Omi's backend it is set up as before", () async {
      await CrashlyticsManager.init();

      expect(recorder.calls.map((c) => c.method), contains('Crashlytics#setCustomKey'));
    });
  });

  group('push', () {
    final messaging = <String>[];

    setUpAll(() async {
      await installCrashlyticsRecorder(); // a Firebase app for FirebaseMessaging.instance
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/firebase_messaging'),
        (call) async {
          messaging.add(call.method);
          return call.method == 'Messaging#getToken' ? {'token': 'fcm-token'} : null;
        },
      );
    });
    setUp(messaging.clear);

    test('no push token is requested against a backend that is not Omi\'s', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      createNotificationService().saveNotificationToken();
      await pumpEventQueue();

      expect(messaging, isEmpty);
    });

    test("against Omi's backend the token is requested as before", () async {
      createNotificationService().saveNotificationToken();
      await pumpEventQueue();

      expect(messaging, contains('Messaging#getToken'));
    });
  });
}

class _TestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _RecordingAdapter implements AnalyticsAdapter {
  int inits = 0;

  @override
  bool get isInitialized => inits > 0;

  @override
  Future<void> init() async => inits++;

  @override
  void track({required String eventName, Map<String, Object>? properties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
