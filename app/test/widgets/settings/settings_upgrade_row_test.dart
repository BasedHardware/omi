import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';

// Pocket's Upgrade row: on the Settings sheet only for a free reader who can still start a trial.
// A paid reader, a reader whose trial is used up, or a build hiding subscription UI never sees it.

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';
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

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get hasNativeBackgroundStreamRoute => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Usage extends ChangeNotifier implements UsageProvider {
  _Usage(this._response);
  final UserSubscriptionResponse? _response;

  @override
  UserSubscriptionResponse? get subscription => _response;

  @override
  bool get showSubscriptionUI => _response?.showSubscriptionUi ?? true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

UserSubscriptionResponse _response({required String plan, required bool trialEligible, bool showUi = true}) =>
    UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.fromWire(plan), status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: showUi,
      trialEligible: trialEligible,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'givenName': 'Ada',
      'email': 'ada@example.com',
      'uid': 'uid-1234567',
      'deviceIdHash': 'test-device-hash',
    });
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi',
      packageName: 'com.friend.ios',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await PlatformManager.initializeServices();
  });

  Future<void> pump(WidgetTester tester, UserSubscriptionResponse? response) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
          ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage(response)),
          ChangeNotifierProvider<CaptureProvider>(create: (_) => _Capture()),
          ChangeNotifierProvider<AppearanceProvider>(create: (_) => AppearanceProvider()),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: Locale('en'),
          home: Scaffold(body: SettingsDrawer()),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  final row = find.byKey(const Key('settings_row_upgrade'));

  testWidgets('a trial-eligible free reader sees Upgrade above Plan & Usage', (tester) async {
    await pump(tester, _response(plan: 'basic', trialEligible: true));
    expect(row, findsOneWidget);
    expect(find.text('Start your 7-day free trial'), findsOneWidget);
    final upgradeY = tester.getTopLeft(row).dy;
    final planY = tester.getTopLeft(find.byKey(const Key('settings_row_planAndUsage'))).dy;
    expect(upgradeY, lessThan(planY));
  });

  testWidgets('no row for a paid reader', (tester) async {
    await pump(tester, _response(plan: 'unlimited_v2', trialEligible: true));
    expect(row, findsNothing);
    expect(find.byKey(const Key('settings_row_planAndUsage')), findsOneWidget);
  });

  testWidgets('no row when the trial is used up', (tester) async {
    await pump(tester, _response(plan: 'basic', trialEligible: false));
    expect(row, findsNothing);
    expect(find.byKey(const Key('settings_row_planAndUsage')), findsOneWidget);
  });

  testWidgets('no row when the build hides subscription UI', (tester) async {
    await pump(tester, _response(plan: 'basic', trialEligible: true, showUi: false));
    expect(row, findsNothing);
    expect(find.byKey(const Key('settings_row_planAndUsage')), findsOneWidget);
  });

  testWidgets('no row before the subscription has loaded', (tester) async {
    await pump(tester, null);
    expect(row, findsNothing);
    expect(find.byKey(const Key('settings_row_planAndUsage')), findsOneWidget);
  });
}
