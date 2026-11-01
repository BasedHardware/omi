import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/onboarding/onboarding_resume_state.dart';
import 'package:omi/pages/onboarding/variants/pocket/pocket_onboarding_flow.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/experiments/onboarding_variant_gate.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

// Killing the app mid-onboarding and opening it again resumes where the reader was: the sign-up
// trial paywall they answered does not come back, and the onboarding-variant arm they were first
// given stays, however the flag reads on the next launch. Another account on the same phone starts
// clean.

/// PostHog stand-in: the flags a launch reads, and every event the app sends.
class _Analytics implements AnalyticsAdapter, AnalyticsFeatureFlagAdapter {
  final flags = <String, String?>{};
  final payloads = <String, Object?>{};
  final variantReads = <String>[];
  final events = <(String, Map<String, Object>)>[];
  bool _initialized = false;

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, Map.of(properties ?? const {})));

  @override
  Future<String?> getFeatureFlagVariant(String key) async {
    variantReads.add(key);
    return flags[key];
  }

  @override
  Future<Object?> getFeatureFlagPayload(String key) async => payloads[key];

  @override
  Future<bool> reloadFeatureFlags() async => true;

  @override
  Future<bool> isFeatureEnabled(String key) async => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => null;

  List<Map<String, Object>> named(String event) => [
        for (final (name, properties) in events)
          if (name == event) properties
      ];

  List<Object?> armsShown() => [for (final properties in named('Onboarding Variant Shown')) properties['variant']];
}

final class _SignedIn implements AuthTokenGateway {
  const _SignedIn(this.uid);

  final String uid;

  @override
  AuthUserSnapshot? get currentUser => AuthUserSnapshot(uid: uid, email: '$uid@example.com', displayName: 'Alex');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

class _QuietHome extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}

class _QuietAuth extends AuthenticationProvider {
  _QuietAuth() : super(initializeListeners: false);
}

class _QuietPairing extends OnboardingProvider {
  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}

  @override
  void cancelActiveScan() {}
}

/// A new free reader who can still start a trial, with today's catalog (the downsell needs prices).
class _TrialEligible extends UsageProvider {
  _TrialEligible() {
    debugSetSubscription(UserSubscriptionResponse(
      trialEligible: true,
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: true,
    ));
  }

  @override
  Map<String, dynamic>? get availablePlans => const {
        'plans': [
          {'plan_id': 'unlimited_v2', 'interval': 'month', 'id': 'price_m', 'unit_amount': 2999, 'currency': 'usd'},
          {'plan_id': 'unlimited_v2', 'interval': 'year', 'id': 'price_y', 'unit_amount': 26991, 'currency': 'usd'},
        ],
      };

  @override
  Future<void> fetchSubscription() async {}

  @override
  Future<void> loadAvailablePlans() async {}
}

const _paywall = Key('trial_paywall_close');
const _downsellDecline = Key('trial_upsell_decline');
const _nameStep = Key('onboarding_name_continue');
const _languageStep = Key('onboarding_language_continue');

/// Signed in with consent given (the first session got that far), on this phone.
void _signIn(String uid) {
  SharedPreferencesUtil().uid = uid;
  SharedPreferencesUtil().aiConsentGiven = true;
  AuthService.installLocalHarnessTokenGateway(_SignedIn(uid));
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 400));
  }
}

/// Pocket's Permissions step reads it. Shared and never disposed: its dispose needs the app's services.
final _pairing = _QuietPairing();

/// Opens the app the way a cold start does: nothing in memory survives, the phone's preferences do.
Future<void> _launch(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  OnboardingVariantGate.resetForTesting();
  PaywallExperiment.resetForTesting();
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<HomeProvider>(create: (_) => _QuietHome()),
      ChangeNotifierProvider<AuthenticationProvider>(create: (_) => _QuietAuth()),
      ChangeNotifierProvider<UsageProvider>(create: (_) => _TrialEligible()),
      ChangeNotifierProvider<OnboardingProvider>.value(value: _pairing),
    ],
    child: MaterialApp(
      theme: buildOmiTheme(brightness: Brightness.light),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const OnboardingWrapper(),
    ),
  ));
  await _settle(tester);
}

Future<void> _tap(WidgetTester tester, Key key) async {
  expect(find.byKey(key), findsOneWidget);
  await tester.tap(find.byKey(key));
  await _settle(tester);
}

Future<void> _quit(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(seconds: 1));
}

void main() {
  late _Analytics analytics;

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.0', buildNumber: '1', buildSignature: '');
    await SharedPreferencesUtil.init();
    analytics = _Analytics();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    AnalyticsManager().bindIdentity('u1');
    await pumpEventQueue();
    _signIn('u1');
  });

  tearDown(AnalyticsManager.resetForTesting);

  void trialPaywallAtSignUp() {
    analytics.flags[PaywallExperiment.enabledFlag] = 'trial';
    analytics.payloads[PaywallExperiment.enabledFlag] = {'onboarding_paywall': true};
  }

  testWidgets('a relaunch after the sign-up paywall resumes at the next step, three times, with no second paywall',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    trialPaywallAtSignUp();
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'control';

    await _launch(tester);
    expect(find.byType(TrialPaywallPage), findsOneWidget);
    await _tap(tester, _paywall);
    expect(find.byKey(_nameStep), findsOneWidget);

    // Killed on Name, the step right after the paywall.
    await _launch(tester);
    expect(find.byType(TrialPaywallPage), findsNothing);
    expect(find.byKey(_nameStep), findsOneWidget);

    // Killed again twice after reaching Language.
    await SharedPreferencesUtil().saveInt('onboarding/resumeStep/u1', OnboardingProgressStepsForTest.steps[1]);
    for (var relaunch = 2; relaunch <= 3; relaunch++) {
      await _launch(tester);
      expect(find.byType(TrialPaywallPage), findsNothing, reason: 'relaunch $relaunch');
      expect(find.byKey(_languageStep), findsOneWidget, reason: 'relaunch $relaunch');
    }

    expect(analytics.named('Paywall Opened'), hasLength(1));
    expect(analytics.named('Paywall Variant Shown'), hasLength(1));
    expect(analytics.armsShown(), ['control', 'control', 'control', 'control']);
    await _quit(tester);
  });

  testWidgets('a paywall the app was killed on is offered again, then never after it is answered', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    trialPaywallAtSignUp();
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'control';

    await _launch(tester);
    expect(find.byType(TrialPaywallPage), findsOneWidget);

    await _launch(tester);
    expect(find.byType(TrialPaywallPage), findsOneWidget, reason: 'never answered');
    await _tap(tester, _paywall);

    await _launch(tester);
    expect(find.byType(TrialPaywallPage), findsNothing);
    expect(find.byKey(_nameStep), findsOneWidget);
    await _quit(tester);
  });

  testWidgets('the arm stays control across relaunches when the flag later reads pocket', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'control';

    await _launch(tester);
    expect(find.byKey(_nameStep), findsOneWidget);

    // The next reads say pocket (the first one fell back to control, or the split changed).
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'pocket';
    for (var relaunch = 1; relaunch <= 3; relaunch++) {
      await _launch(tester);
      expect(find.byType(PocketOnboardingFlow), findsNothing, reason: 'relaunch $relaunch');
      expect(find.byKey(_nameStep), findsOneWidget, reason: 'relaunch $relaunch');
    }

    expect(analytics.armsShown(), ['control', 'control', 'control', 'control']);
    expect(analytics.variantReads.where((key) => key == OnboardingVariantGate.enabledFlag), hasLength(1),
        reason: 'a relaunch never reads the flag again, so it records no other arm');
    await _quit(tester);
  });

  testWidgets('pocket stays pocket when the flag later reads control; paywall and 30-day downsell are offered once',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    trialPaywallAtSignUp();
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'pocket';

    await _launch(tester);
    await _tap(tester, _paywall);
    await _tap(tester, _downsellDecline);
    expect(find.byType(PocketOnboardingFlow), findsOneWidget);

    analytics.flags[OnboardingVariantGate.enabledFlag] = 'control';
    for (var relaunch = 1; relaunch <= 2; relaunch++) {
      await _launch(tester);
      expect(find.byType(TrialPaywallPage), findsNothing, reason: 'relaunch $relaunch');
      expect(find.byKey(_downsellDecline), findsNothing, reason: 'relaunch $relaunch');
      expect(find.byType(PocketOnboardingFlow), findsOneWidget, reason: 'relaunch $relaunch');
    }

    expect(analytics.named('Paywall Opened'), hasLength(1));
    expect(analytics.named('Trial Upsell Shown'), hasLength(1));
    expect(analytics.armsShown(), ['pocket', 'pocket', 'pocket']);
    await _quit(tester);
  });

  testWidgets('another account on the same phone starts clean: its own paywall and its own arm', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    trialPaywallAtSignUp();
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'control';

    await _launch(tester);
    await _tap(tester, _paywall);
    expect(find.byKey(_nameStep), findsOneWidget);

    // u1's answers stay on the phone; u2 signs in and its flag reads pocket.
    _signIn('u2');
    analytics.flags[OnboardingVariantGate.enabledFlag] = 'pocket';
    await _launch(tester);
    expect(find.byType(TrialPaywallPage), findsOneWidget, reason: 'u2 never answered the paywall');
    await _tap(tester, _paywall);
    await _tap(tester, _downsellDecline);
    expect(find.byType(PocketOnboardingFlow), findsOneWidget, reason: "u2's own arm, not u1's");

    expect(OnboardingResumeState.arm('u1'), OnboardingArm.control);
    expect(OnboardingResumeState.signupPaywall('u1'), SignupPaywallAnswer.closed);
    expect(OnboardingResumeState.arm('u2'), OnboardingArm.pocket);
    expect(OnboardingResumeState.signupPaywall('u2'), SignupPaywallAnswer.closed);
    await _quit(tester);
  });
}
