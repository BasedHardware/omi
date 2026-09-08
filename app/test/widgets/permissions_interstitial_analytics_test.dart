import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const permissionsChannel = MethodChannel('flutter.baseflow.com/permissions/methods');

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(permissionsChannel, (
      call,
    ) async {
      if (call.method == 'checkServiceStatus') return 0;
      if (call.method == 'requestPermissions') {
        return {for (final permission in call.arguments as List<dynamic>) permission: 0};
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      permissionsChannel,
      null,
    );
    AnalyticsManager.resetForTesting();
  });

  testWidgets('tracks shown once per permissions interstitial presentation before completion', (tester) async {
    final analytics = _TestAnalyticsAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    final provider = OnboardingProvider();

    Widget app() => ChangeNotifierProvider.value(
          value: provider,
          child: const MaterialApp(
            localizationsDelegates: [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: AppLocalizations.supportedLocales,
            home: PermissionsInterstitialPage(),
          ),
        );

    await tester.pumpWidget(app());
    provider.setLoading(true);
    provider.setLoading(false);
    await tester.pump();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Continue'));
    await tester.idle();
    await AnalyticsManager.flushPending(force: true);

    expect(analytics.events, ['Permissions Interstitial Shown', 'Permissions Interstitial Completed']);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(app());
    await AnalyticsManager.flushPending(force: true);

    expect(analytics.events, [
      'Permissions Interstitial Shown',
      'Permissions Interstitial Completed',
      'Permissions Interstitial Shown',
    ]);
  });
}

class _TestAnalyticsAdapter implements AnalyticsAdapter {
  final List<String> events = [];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add(eventName);

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
