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

    test('a saved value of the wrong type does not stop the boot', () async {
      SharedPreferences.setMockInitialValues({'customBackendUrl': 42});

      await OutboundPolicy.resolve();

      expect(Env.hasApiBaseUrlOverride, isFalse);
    });

    test("a saved override that is Omi's own backend leaves them on", () async {
      SharedPreferences.setMockInitialValues({'customBackendUrl': 'https://api.omi.me'});

      await OutboundPolicy.resolve();

      expect(OutboundPolicy.thirdPartyServicesAllowed, isTrue);
    });
  });

  group('a backend change while the app runs', () {
    test("switching away from Omi's backend turns them off at once", () {
      Env.overrideApiBaseUrl('https://omi.example.test/');

      expect(OutboundPolicy.backendChanged(), isTrue);
      expect(OutboundPolicy.thirdPartyServicesAllowed, isFalse);
    });

    test("switching back to Omi's backend leaves them off until the next launch", () {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;
      Env.overrideApiBaseUrl('https://api.omi.me/');

      expect(OutboundPolicy.backendChanged(), isFalse);
      expect(OutboundPolicy.thirdPartyServicesAllowed, isFalse);
    });

    test("staying on Omi's backend changes nothing", () {
      Env.overrideApiBaseUrl('https://api.omi.me/');

      expect(OutboundPolicy.backendChanged(), isFalse);
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

    test('a running session stops sending when the backend changes away from Omi', () async {
      await AnalyticsManager.init();

      AnalyticsManager.suspendForSession();
      AnalyticsManager().track('After Switch');
      await AnalyticsManager.flushPending(force: true);

      expect(adapter.disables, 1);
      expect(adapter.events, isEmpty);
    });
  });

  group('crash reporting', () {
    late CrashlyticsRecorder recorder;

    setUpAll(() async => recorder = await installCrashlyticsRecorder());
    setUp(() => recorder.reset());

    test('collection is switched off, stored reports are deleted, and nothing is set up', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      await CrashlyticsManager.init();

      expect(recorder.calls.map((c) => c.method), [
        'Crashlytics#setCrashlyticsCollectionEnabled',
        'Crashlytics#deleteUnsentReports',
      ]);
      expect((recorder.calls.first.arguments as Map)['enabled'], isFalse);
    });

    test('identity, logs and reports never reach the SDK, so nothing is stored to upload later', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;
      final crashlytics = CrashlyticsManager();

      crashlytics.identifyUser('me@example.test', 'Me', 'uid-1');
      crashlytics.logInfo('hello');
      crashlytics.setUserAttribute('k', 'v');
      await crashlytics.reportCrash(StateError('x'), StackTrace.current, userAttributes: {'url': 'https://x/'});
      await crashlytics.reportNonFatal(StateError('y'), StackTrace.current);

      expect(recorder.calls, isEmpty);
    });

    test('stopping the services for a backend change deletes stored reports', () async {
      AnalyticsManager.resetForTesting();
      await PlatformManager.stopThirdPartyServices();

      expect(recorder.calls.map((c) => c.method), [
        'Crashlytics#setCrashlyticsCollectionEnabled',
        'Crashlytics#deleteUnsentReports',
      ]);
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
  int disables = 0;
  final events = <String>[];

  @override
  bool get isInitialized => inits > 0;

  @override
  Future<void> init() async => inits++;

  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add(eventName);

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
  void disable() => disables++;

  @override
  void reset() {}
}
