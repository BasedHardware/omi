import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/onboarding/signup_offers.dart';
import 'package:omi/pages/onboarding/variants/pocket/pocket_onboarding_flow.dart';
import 'package:omi/pages/onboarding/variants/pocket/pocket_pairing_step.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/services.dart';

// A relaunch mid-onboarding, through the real wrapper: once the reader has left the sign-up paywall,
// it is not shown again and Pocket resumes at pairing. A first launch still shows it.

const _uid = 'u1';

final class _SignedInGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: _uid);

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

final _plans = <String, dynamic>{
  'plans': [
    {'id': 'price_month', 'plan_id': 'unlimited_v2', 'interval': 'month', 'unit_amount': 2999, 'currency': 'usd'},
    {'id': 'price_year', 'plan_id': 'unlimited_v2', 'interval': 'year', 'unit_amount': 26991, 'currency': 'usd'},
  ],
};

/// No network in tests: the speaker-profile check the wrapper and the pairing page start does nothing.
class _OfflineHomeProvider extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}

UsageProvider _trialEligibleFreeReader() => UsageProvider()
  ..debugSetSubscription(UserSubscriptionResponse(
    trialEligible: true,
    subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 18000,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
    showSubscriptionUi: true,
  ))
  ..debugSetAvailablePlans(_plans);

Future<void> _launchMidOnboarding(WidgetTester tester, Map<String, Object> stored) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  SharedPreferencesUtil().uid = _uid;
  SharedPreferencesUtil().aiConsentGiven = true;
  SharedPreferencesUtil().onboardingCompleted = false;
  await SharedPreferencesUtil().saveInt('onboarding/pocket/resumeStep/$_uid', 1); // Pocket's pairing step
  for (final entry in stored.entries) {
    final value = entry.value;
    if (value is bool) await SharedPreferencesUtil().saveBool(entry.key, value);
    if (value is String) await SharedPreferencesUtil().saveString(entry.key, value);
  }
  AuthService.installLocalHarnessTokenGateway(_SignedInGateway());
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<UsageProvider>.value(value: _trialEligibleFreeReader()),
      ChangeNotifierProvider<HomeProvider>(create: (_) => _OfflineHomeProvider()),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => DeviceProvider()),
      ChangeNotifierProvider<OnboardingProvider>(create: (_) => OnboardingProvider()),
      ChangeNotifierProvider<AuthenticationProvider>(create: (_) => AuthenticationProvider(initializeListeners: false)),
    ],
    child: MaterialApp(
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const OnboardingWrapper(),
    ),
  ));
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {
      // No connectivity plugin in tests; the services the pairing page reads are created first.
    }
  });

  testWidgets('relaunch after leaving the sign-up paywall and the downsell: no paywall, back on pairing',
      (tester) async {
    await _launchMidOnboarding(tester, {
      SignupOffers.paywallKey(_uid): 'closed',
      SignupOffers.upsellKey(_uid): true,
    });
    expect(find.byType(TrialPaywallPage), findsNothing);
    expect(find.byType(PocketOnboardingFlow), findsOneWidget);
    expect(find.byType(PocketPairingStep), findsOneWidget);
  });

  testWidgets('first launch with nothing stored still shows the sign-up paywall', (tester) async {
    await _launchMidOnboarding(tester, {});
    expect(find.byType(TrialPaywallPage), findsOneWidget);
    expect(find.byType(PocketOnboardingFlow), findsNothing);
  });

  group('what a closed sign-up paywall counts as', () {
    test('a page that could not load the plans is not stored, so the next launch shows it', () {
      expect(OnboardingWrapper.signupPaywallAnswerForTesting(shown: true, purchased: false, plans: null), isNull);
      expect(
          OnboardingWrapper.signupPaywallAnswerForTesting(shown: true, purchased: false, plans: {'plans': []}), isNull);
    });

    test('a page with prices that was closed is stored as left', () {
      expect(OnboardingWrapper.signupPaywallAnswerForTesting(shown: true, purchased: false, plans: _plans), isFalse);
    });

    test('a purchase is always stored; no page shown is never stored', () {
      expect(OnboardingWrapper.signupPaywallAnswerForTesting(shown: true, purchased: true, plans: null), isTrue);
      expect(OnboardingWrapper.signupPaywallAnswerForTesting(shown: false, purchased: false, plans: _plans), isNull);
    });
  });
}
