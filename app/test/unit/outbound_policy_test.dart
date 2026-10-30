import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/env/outbound_policy.dart';
import 'package:omi/flavors.dart';
import 'package:omi/utils/logger.dart';
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

  group('the rule', () {
    test("production and beta builds on their own backend are Omi's data plane", () {
      for (final profile in [AppEnvironmentProfile.production, AppEnvironmentProfile.mobileBeta]) {
        expect(
          OutboundPolicy.decide(profile: profile, hasOverride: false, baseUrl: profile.defaultApiBaseUrl),
          isTrue,
          reason: profile.name,
        );
      }
    });

    test("local_prod keeps them: production identity on a local backend is still Omi's plane", () {
      expect(
        OutboundPolicy.decide(
          profile: AppEnvironmentProfile.localProd,
          hasOverride: false,
          baseUrl: 'http://127.0.0.1:8000/',
        ),
        isTrue,
      );
    });

    test("the Auth emulator's accounts are not Omi's, whatever the backend", () {
      expect(
        OutboundPolicy.decide(
            profile: AppEnvironmentProfile.localDev, hasOverride: false, baseUrl: 'https://api.omi.me/'),
        isFalse,
      );
    });

    test("a custom backend from Developer Settings turns them off unless it is Omi's API", () {
      expect(
        OutboundPolicy.decide(
          profile: AppEnvironmentProfile.localProd,
          hasOverride: true,
          baseUrl: 'https://omi.example.test/',
        ),
        isFalse,
      );
      expect(
        OutboundPolicy.decide(
            profile: AppEnvironmentProfile.localProd, hasOverride: true, baseUrl: 'https://api.omi.me/'),
        isTrue,
      );
    });
  });

  group('resolve at boot (production profile)', () {
    late Environment flavor;

    setUp(() {
      flavor = F.env;
      F.env = Environment.prod;
    });
    tearDown(() => F.env = flavor);

    test('decides from the saved backend: none or Omi\'s keeps them on, another turns them off', () async {
      SharedPreferences.setMockInitialValues({});
      await OutboundPolicy.resolve();
      expect(OutboundPolicy.thirdPartyServicesAllowed, isTrue);

      SharedPreferences.setMockInitialValues({'customBackendUrl': 'https://api.omi.me'});
      await OutboundPolicy.resolve();
      expect(OutboundPolicy.thirdPartyServicesAllowed, isTrue);

      SharedPreferences.setMockInitialValues({'customBackendUrl': 'https://omi.example.test'});
      await OutboundPolicy.resolve();
      expect(OutboundPolicy.thirdPartyServicesAllowed, isFalse);
    });
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

      await expectLater(OutboundPolicy.resolve(), completes);
      expect(Env.hasApiBaseUrlOverride, isFalse);
    });
  });

  group('a backend change while the app runs', () {
    test('a change without an override (cleared field) changes nothing', () {
      expect(OutboundPolicy.backendChanged(), isFalse);
      expect(OutboundPolicy.thirdPartyServicesAllowed, isTrue);
    });

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
    final healthPolicy = <bool>[];

    setUpAll(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('com.omi/device_health_policy'),
        (call) async {
          if (call.method == 'setPolicy') healthPolicy.add((call.arguments as Map)['enabled'] as bool);
          return null;
        },
      );
    });
    tearDownAll(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('com.omi/device_health_policy'),
        null,
      );
    });

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

    test('does not start against a backend that is not Omi\'s, and nothing is held for later', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      await PlatformManager.initializeServices();
      await pumpEventQueue();
      healthPolicy.clear();
      AnalyticsManager().bindIdentity('uid-1');
      AnalyticsManager().track('Later');
      await pumpEventQueue();

      expect(adapter.inits, 0);
      expect(AnalyticsManager.queuedEventCountForTesting, 0);
      // Device-health stats are recorded natively and uploaded later; the native store stays off.
      expect(healthPolicy, isNotEmpty);
      expect(healthPolicy, everyElement(isFalse));
      expect(AnalyticsManager.deviceHealthRecordingEnabled, isFalse);
    });

    test("starts against Omi's backend", () async {
      await PlatformManager.initializeServices();
      await pumpEventQueue();

      expect(adapter.inits, 1);
    });

    test("the SDK's persisted opt-out from a switch is undone at the next launch back on Omi", () async {
      await AnalyticsManager.init();
      AnalyticsManager.suspendForSession();
      await pumpEventQueue();

      AnalyticsManager.resetForTesting();
      final next = _RecordingAdapter();
      AnalyticsManager.configure(next);
      await AnalyticsManager.init();

      expect(next.enables, 1);
      expect((await SharedPreferences.getInstance()).getBool('analytics_suspended_for_backend'), isNull);
    });

    test('a launch that was never suspended does not touch the SDK opt-out', () async {
      await AnalyticsManager.init();

      expect(adapter.enables, 0);
    });

    test('a running session stops sending when the backend changes away from Omi', () async {
      await AnalyticsManager.init();
      final identities = <(String?, bool)>[];
      AnalyticsManager.identityChanged = (id, enabled) => identities.add((id, enabled));
      healthPolicy.clear();

      AnalyticsManager.suspendForSession();
      await pumpEventQueue();
      AnalyticsManager().track('After Switch');
      await AnalyticsManager.flushPending(force: true);

      expect(adapter.disables, 1);
      expect(adapter.events, isEmpty);
      // Session replay follows the settled identity; the native device-health store its policy.
      expect(identities, [(null, false)]);
      expect(healthPolicy, [false]);
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

    testWidgets('saving a custom backend in Developer Settings stops them at once', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: Scaffold()));
      AnalyticsManager.resetForTesting();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      final provider = DeveloperModeProvider()..customBackendUrl.text = 'https://omi.example.test';

      final saved = await tester.runAsync(provider.saveSettings);

      expect(saved, isNotNull, reason: 'saveSettings completed instead of throwing');
      expect(OutboundPolicy.thirdPartyServicesAllowed, isFalse);
      expect(recorder.calls.map((c) => c.method), contains('Crashlytics#deleteUnsentReports'));
      expect(provider.savingSettingsLoading, isFalse);
    });

    testWidgets('a vendor SDK failure while stopping does not wedge Save', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: Scaffold()));
      AnalyticsManager.resetForTesting();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/firebase_crashlytics'),
        (call) async => throw PlatformException(code: 'boom'),
      );
      addTearDown(() async => recorder = await installCrashlyticsRecorder());
      final provider = DeveloperModeProvider()..customBackendUrl.text = 'https://omi.example.test';

      final saved = await tester.runAsync(provider.saveSettings);

      expect(saved, isNotNull, reason: 'saveSettings completed instead of throwing');
      expect(provider.savingSettingsLoading, isFalse);
    });

    test('logged errors do not reach Crashlytics', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      Logger.instance.talker.handle(StateError('x'), StackTrace.current);
      await pumpEventQueue();

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

    test('a token refresh is not uploaded against a backend that is not Omi\'s', () async {
      OutboundPolicy.debugThirdPartyServicesAllowed = false;

      await createNotificationService().saveFcmToken('refreshed');

      expect(messaging, isEmpty);
    });

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
  int enables = 0;
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
  void enable() => enables++;

  @override
  void disable() => disables++;

  @override
  void reset() {}
}
