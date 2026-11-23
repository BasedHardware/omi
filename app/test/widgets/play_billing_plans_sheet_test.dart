// Google Play Billing on the plans sheet: Play prices, Play purchase flow, no Stripe webview,
// Play subscription center for Play subscribers, and iOS left exactly on today's Stripe sheet.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/play_billing_api.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/pages/settings/widgets/plans/play_plans_content.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/pages/settings/widgets/plans/prepaid_code_sheet.dart';
import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/billing/play_billing.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/pages/paywall/web_paywall_page.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/fake_play_billing.dart';

UserSubscriptionResponse _response({
  PlanType plan = PlanType.basic,
  String? provider,
  String? stripeId,
  bool trialEligible = true,
  bool cancelAtPeriodEnd = false,
  PlayBillingConfig? play = playConfig,
  bool prepaidCodeRedeem = false,
  bool prepaid = false,
}) =>
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: plan,
        status: SubscriptionStatus.active,
        provider: provider,
        stripeSubscriptionId: stripeId,
        cancelAtPeriodEnd: cancelAtPeriodEnd,
        currentPeriodEnd: plan.isPaid ? 1893456000 : null,
        prepaid: prepaid,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      trialEligible: trialEligible,
      playBilling: play,
      prepaidCodeRedeem: prepaidCodeRedeem,
    );

class _Usage extends UsageProvider {
  _Usage({required super.subscriptionRequest, required super.playBilling, super.usageRequest, super.deviceTimeZone});

  int checkoutSessions = 0;

  @override
  Future<void> loadAvailablePlans() async {}

  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession({
    required String priceId,
    String? promotionCode,
    int? trialDays,
  }) async {
    checkoutSessions++;
    return {'url': 'https://checkout.stripe.com/session'};
  }
}

class _Harness extends StatefulWidget {
  const _Harness();

  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> with TickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(vsync: this);

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
        waveController: _animation,
        notesController: _animation,
        arrowController: _animation,
        arrowAnimation: _animation,
        readStorefrontGate: () async => false,
      );
}

class _World {
  _World(this.responses, {FakePlayPlatform? platform}) : platform = platform ?? FakePlayPlatform();

  final List<UserSubscriptionResponse> responses;
  final FakePlayPlatform platform;
  final server = FakePlayServer();
  late final billing = PlayBilling(platform: () => platform, verify: server.call, store: MemoryTokenStore());
  late final usage = _Usage(
    subscriptionRequest: () async => responses.length > 1 ? responses.removeAt(0) : responses.first,
    playBilling: billing,
  );
}

Future<_World> _pump(
  WidgetTester tester,
  List<UserSubscriptionResponse> responses, {
  Widget? child,
  bool fetchFirst = true,
}) async {
  tester.view.physicalSize = const Size(430, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final world = _World(responses);
  addTearDown(world.billing.dispose);
  addTearDown(world.usage.dispose);
  world.usage.debugSetAvailablePlans({
    'plans': [
      {
        'id': 'price_year',
        'plan_id': 'unlimited_v2',
        'title': 'Unlimited Annual',
        'interval': 'year',
        'unit_amount': 26991,
        'currency': 'usd',
        'price_string': r'$269.91/yr',
        'is_active': false,
      },
    ],
  });
  if (fetchFirst) await world.usage.fetchSubscription();
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: world.usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: child ?? const _Harness()),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return world;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TranscriptionAllowanceCache.clear();
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
    PlatformManager.initializeForLocalHarness();
  });

  tearDown(() {
    Env.clearApiBaseUrlOverrideForTesting();
  });

  testWidgets('Android Play-billed reader sees Play prices and buys through Play, never the Stripe webview',
      (tester) async {
    final world = await _pump(tester, [_response(), _response(plan: PlanType.unlimitedV2, provider: 'play')]);
    expect(world.usage.playBilledPurchaser, isTrue);
    expect(find.byType(PlayPlansContent), findsOneWidget);
    expect(find.textContaining('₹22,500.00'), findsWidgets);
    expect(find.textContaining('₹2,500.00'), findsWidgets);
    expect(find.textContaining('US\$'), findsNothing);
    expect(find.textContaining('7 days free'), findsOneWidget);
    // No Stripe-only offers: no code field, no yearly switch.
    expect(find.byType(TextField), findsNothing);

    world.platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    await tester.tap(find.byKey(const Key('play_subscribe')));
    await tester.pumpAndSettle();

    expect(world.platform.launched.single.offerToken, 'token-yearly-trial');
    expect(world.platform.launched.single.applicationUserName, 'acct-hash');
    expect(world.server.received, ['omi_pro:purchase-token']);
    expect(world.usage.checkoutSessions, 0);
    expect(find.byType(PaymentWebViewPage), findsNothing);
    expect(world.usage.subscription!.subscription.billedByPlay, isTrue);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('monthly selection buys the monthly base plan', (tester) async {
    final world = await _pump(tester, [_response(trialEligible: false)]);
    expect(find.textContaining('days free'), findsNothing);
    await tester.tap(find.byKey(const Key('play_plan_monthly')));
    await tester.pumpAndSettle();
    world.platform.onLaunch = [playPurchase(PurchaseStatus.canceled)];
    await tester.tap(find.byKey(const Key('play_subscribe')));
    await tester.pumpAndSettle();
    expect(world.platform.launched.single.offerToken, 'token-monthly');
    expect(world.server.received, isEmpty);
    expect(find.byType(PaymentWebViewPage), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('pending Play payment says so and grants nothing yet', (tester) async {
    final world = await _pump(tester, [_response()]);
    world.server.answer = (_, __) => const PlayVerifyResult('pending');
    world.platform.onLaunch = [playPurchase(PurchaseStatus.pending)];
    await tester.tap(find.byKey(const Key('play_subscribe')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('play_purchase_pending')), findsOneWidget);
    final button = tester.widget<OmiButton>(find.byKey(const Key('play_subscribe')));
    expect(button.onPressed, isNull, reason: 'no second purchase while the first is pending');
    expect(world.server.received, ['omi_pro:purchase-token'],
        reason: 'the server learns the uid before Google clears it');
    expect(world.usage.subscription!.subscription.plan, PlanType.basic);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('Restore sends the owned Play purchase to the server', (tester) async {
    final world = await _pump(tester, [_response(), _response(plan: PlanType.unlimitedV2, provider: 'play')]);
    world.platform.owned = [playPurchase(PurchaseStatus.restored, token: 'owned')];
    await tester.tap(find.byKey(const Key('play_restore')));
    await tester.pumpAndSettle();
    expect(world.server.received, ['omi_pro:owned']);
    expect(find.byKey(const Key('play_manage_subscription')), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('Play trial copy follows Play: no trial offer for this Google account, no trial promised',
      (tester) async {
    final world = _World([_response()]);
    addTearDown(world.usage.dispose);
    world.platform.details
      ..clear()
      ..addAll(omiProDetails(withTrial: false));
    await world.usage.fetchSubscription();
    await tester.pump();
    expect(world.usage.subscription!.trialEligible, isFalse);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('Play subscriber manages the subscription in Google Play', (tester) async {
    final opened = <Uri>[];
    await _pump(
      tester,
      [_response(plan: PlanType.unlimitedV2, provider: 'play')],
      child: PlayPlansContent(
          analyticsSource: 'test',
          openUrl: (uri) async {
            opened.add(uri);
            return true;
          }),
    );
    expect(find.text('Billed by Google Play'), findsOneWidget);
    await tester.tap(find.byKey(const Key('play_manage_subscription')));
    await tester.pump();
    expect(opened.single.host, 'play.google.com');
    expect(opened.single.queryParameters['sku'], 'omi_pro');
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a Stripe subscriber on Android keeps the Stripe plans sheet', (tester) async {
    final world = await _pump(tester, [_response(plan: PlanType.unlimitedV2, stripeId: 'sub_1')]);
    expect(world.usage.playBilledPurchaser, isFalse);
    expect(find.byType(PlayPlansContent), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('iOS ignores the Play block entirely and keeps Stripe pricing', (tester) async {
    final world = await _pump(tester, [_response()]);
    expect(world.usage.playBilling, isNull);
    expect(world.usage.playBilledPurchaser, isFalse);
    expect(world.platform.launched, isEmpty);
    expect(find.byType(PlayPlansContent), findsNothing);
    final offer = PaywallOffer.forUsage(world.usage)!;
    expect(offer.yearly!.priceId, 'price_year');
    expect(offer.yearly!.formatted, 'US\$269.91');
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    testWidgets('trial paywall for a Stripe-billed ${platform.name} reader keeps the 7-day timeline', (tester) async {
      await _pump(tester, [_response(play: null)],
          child: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)));
      expect(find.byKey(const Key('trial_paywall_timeline')), findsOneWidget);
      expect(find.text('In 7 days'), findsOneWidget);
      expect(find.byKey(const Key('trial_paywall_timeline_pending')), findsNothing);
    }, variant: TargetPlatformVariant.only(platform));
  }

  testWidgets('trial paywall shows Play prices, hides the Stripe code hint, and buys the Play trial offer',
      (tester) async {
    final world = await _pump(
      tester,
      [_response(), _response(plan: PlanType.unlimitedV2, provider: 'play')],
      child: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
    );
    expect(find.textContaining('₹22,500.00'), findsWidgets);
    expect(find.textContaining('US\$'), findsNothing);
    expect(find.byKey(const Key('trial_paywall_code_hint')), findsNothing);
    world.platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pumpAndSettle();
    expect(world.platform.launched.single.offerToken, 'token-yearly-trial');
    expect(world.usage.checkoutSessions, 0);
    expect(find.byType(PaymentWebViewPage), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('trial paywall: Play disclosure, Play price strings, no computed was or saving', (tester) async {
    await _pump(tester, [_response()], child: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)));
    expect(find.byKey(const Key('play_renewal_terms')), findsOneWidget);
    expect(find.text('Billed by Google Play'), findsOneWidget);
    expect(find.text('Cancel anytime. No fees, no penalties.'), findsNothing);
    final yearly = find.byKey(const Key('trial_paywall_yearly'));
    expect(find.descendant(of: yearly, matching: find.text('₹22,500.00')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('trial_paywall_monthly')), matching: find.text('₹2,500.00')),
        findsOneWidget);
    expect(find.textContaining('Save '), findsNothing);
    expect(find.textContaining('₹30,000'), findsNothing); // 12 x monthly, app-computed
    expect(find.text('Try for Free'), findsOneWidget); // Play's own trial-phase string
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  for (final page in ['outline', 'trial']) {
    testWidgets('$page paywall: Play offers unavailable shows the plans-sheet Retry, which recovers', (tester) async {
      final world = _World([_response()], platform: FakePlayPlatform(available: false));
      addTearDown(world.usage.dispose);
      await world.usage.fetchSubscription();
      await tester.pump();
      tester.view.physicalSize = const Size(430, 2400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: world.usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: page == 'outline'
              ? const OutlinePaywallPage(source: 'test')
              : TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('play_plans_error')), findsOneWidget);
      expect(find.textContaining('US\$'), findsNothing);
      // No trial length, date or timeline in the error state.
      expect(find.byKey(const Key('trial_paywall_timeline')), findsNothing);
      expect(find.text('In 7 days'), findsNothing);
    }, variant: TargetPlatformVariant.only(TargetPlatform.android));
  }

  for (final page in ['outline', 'trial']) {
    testWidgets('$page paywall: a failed subscription read stays failed after a usage read clears the shared error',
        (tester) async {
      var calls = 0;
      final world = _World([_response()]);
      final usage = _Usage(
        subscriptionRequest: () async => ++calls == 1 ? null : _response(),
        playBilling: world.billing,
        usageRequest: ({required period, required timeZone}) async => UserUsageResponse(history: []),
        deviceTimeZone: () async => 'UTC',
      );
      addTearDown(usage.dispose);
      await usage.fetchSubscription();
      await usage.fetchUsageStats(period: 'monthly');
      expect(usage.error, isNull); // the usage read cleared the shared error...
      expect(usage.billingProviderFailed, isTrue); // ...but the subscription read is still known to have failed
      expect(usage.billingProviderPending, isFalse);
      tester.view.physicalSize = const Size(430, 2400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: page == 'outline'
              ? const OutlinePaywallPage(source: 'test')
              : TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('play_plans_error')), findsOneWidget);
      expect(find.byKey(const Key('trial_paywall_timeline_pending')), findsNothing);
      // A successful subscription read clears it.
      await usage.fetchSubscription();
      expect(calls, 2);
      expect(usage.billingProviderFailed, isFalse);
      expect(usage.billingProviderUnknown, isFalse);
    }, variant: TargetPlatformVariant.only(TargetPlatform.android));
  }

  testWidgets('outline paywall: a failed subscription read shows Retry instead of a skeleton forever', (tester) async {
    var calls = 0;
    final world = _World([_response()]);
    final usage = _Usage(
      subscriptionRequest: () async => ++calls == 1 ? null : _response(),
      playBilling: world.billing,
    );
    addTearDown(usage.dispose);
    await usage.fetchSubscription();
    expect(usage.billingProviderFailed, isTrue);
    tester.view.physicalSize = const Size(430, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: OutlinePaywallPage(source: 'test'),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('play_plans_error')), findsOneWidget);
    await tester.tap(find.descendant(of: find.byKey(const Key('play_plans_error')), matching: find.byType(OmiButton)));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.byKey(const Key('play_plans_error')), findsNothing);
    expect(find.textContaining('₹22,500.00'), findsWidgets);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('trial paywall: no trial length while the billing provider is unknown or its read failed',
      (tester) async {
    var calls = 0;
    final gate = Completer<UserSubscriptionResponse?>();
    final world = _World([_response()]);
    final usage = _Usage(
      subscriptionRequest: () => ++calls == 1 ? gate.future : Future.value(_response(play: null)),
      playBilling: world.billing,
    );
    addTearDown(usage.dispose);
    tester.view.physicalSize = const Size(430, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    unawaited(usage.fetchSubscription());
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
      ),
    ));
    await tester.pump();
    // Read in flight: the reader may turn out to be Play-billed, so no constant trial promise yet.
    expect(usage.billingProviderPending, isTrue);
    expect(find.byKey(const Key('trial_paywall_timeline_pending')), findsOneWidget);
    expect(find.byKey(const Key('trial_paywall_timeline')), findsNothing);
    expect(find.text('In 7 days'), findsNothing);
    // The read fails: Retry, still no trial length or date.
    gate.complete(null);
    await tester.pumpAndSettle();
    expect(usage.billingProviderFailed, isTrue);
    expect(find.byKey(const Key('play_plans_error')), findsOneWidget);
    expect(find.byKey(const Key('trial_paywall_timeline')), findsNothing);
    expect(find.byKey(const Key('trial_paywall_timeline_pending')), findsNothing);
    expect(find.text('In 7 days'), findsNothing);
    // Retry lands on a Stripe-billed reader: the 7-day timeline is back.
    await tester.tap(find.descendant(of: find.byKey(const Key('play_plans_error')), matching: find.byType(OmiButton)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('trial_paywall_timeline')), findsOneWidget);
    expect(find.text('In 7 days'), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('before the billing provider is known, Android shows loading and never a price', (tester) async {
    final gate = Completer<UserSubscriptionResponse?>();
    final world = _World([_response()]);
    final usage = _Usage(subscriptionRequest: () => gate.future, playBilling: world.billing);
    addTearDown(usage.dispose);
    usage.debugSetAvailablePlans({
      'plans': [
        {'id': 'price_year', 'plan_id': 'unlimited_v2', 'interval': 'year', 'unit_amount': 26991, 'currency': 'usd'},
      ],
    });
    tester.view.physicalSize = const Size(430, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: Scaffold(body: _Harness()),
      ),
    ));
    await tester.pump();
    expect(find.byKey(const Key('plans_provider_loading')), findsOneWidget);
    expect(find.textContaining('US\$'), findsNothing);
    expect(PaywallOffer.forUsage(usage), isNull);
    gate.complete(_response());
    await tester.pumpAndSettle();
    expect(find.byType(PlayPlansContent), findsOneWidget);
    expect(find.textContaining('US\$'), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('Play purchase screens show auto-renewal, cancel-in-Play, Terms and Privacy', (tester) async {
    final opened = <Uri>[];
    await _pump(tester, [_response()],
        child: PlayPlansContent(
            analyticsSource: 'test',
            openUrl: (uri) async {
              opened.add(uri);
              return true;
            }));
    expect(
        find.text('Renews automatically at the price shown until you cancel. Manage or cancel anytime in Google Play.'),
        findsOneWidget);
    await tester.tap(find.byKey(const Key('play_terms')));
    await tester.tap(find.byKey(const Key('play_privacy')));
    expect(opened.map((u) => u.path), ['/pages/terms-of-service', '/pages/privacy']);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('outline paywall shows the Play disclosure to a Play-billed reader', (tester) async {
    await _pump(tester, [_response()], child: const OutlinePaywallPage(source: 'test'));
    expect(find.byKey(const Key('play_renewal_terms')), findsOneWidget);
    expect(find.byKey(const Key('play_terms')), findsOneWidget);
    expect(find.textContaining('US\$'), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('the hosted web paywall is never chosen for a Play-billed reader', (tester) async {
    final world = await _pump(tester, [_response()], child: const SizedBox());
    final context = tester.element(find.byType(SizedBox).first);
    unawaited(PaywallRouter.openVariant(
      context,
      source: 'usage_page',
      config: PaywallExperimentConfig(variant: PaywallVariant.web, webUrl: Uri.parse('https://example.com/p')),
      record: (_, __) => true,
    ));
    await tester.pumpAndSettle();
    expect(find.byType(WebPaywallPage), findsNothing);
    expect(find.byType(OutlinePaywallPage), findsOneWidget);
    expect(world.usage.playBilledPurchaser, isTrue);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('trial paywall with no Play trial offer sells the base plan without trial wording', (tester) async {
    final world = _World([_response()]);
    world.platform.details
      ..clear()
      ..addAll(omiProDetails(withTrial: false));
    addTearDown(world.usage.dispose);
    await world.usage.fetchSubscription();
    await tester.pump();
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: world.usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byType(PlayPlansContent), findsOneWidget);
    expect(find.textContaining('free'), findsNothing);
    expect(find.textContaining('₹22,500.00'), findsWidgets);
    world.platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    await tester.tap(find.byKey(const Key('play_subscribe')));
    await tester.pumpAndSettle();
    expect(world.platform.launched.single.offerToken, 'token-yearly');
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  Future<_World> pumpTrialPage(WidgetTester tester, List<GooglePlayProductDetails> details) async {
    tester.view.physicalSize = const Size(430, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final world = _World([_response()]);
    world.platform.details
      ..clear()
      ..addAll(details);
    addTearDown(world.usage.dispose);
    await world.usage.fetchSubscription();
    await tester.pump();
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: world.usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
      ),
    ));
    await tester.pumpAndSettle();
    return world;
  }

  testWidgets('trial paywall uses Play\'s own trial length (3 days), never the 7-day constant', (tester) async {
    final world = await pumpTrialPage(tester, omiProDetails(trialPeriod: 'P3D'));
    expect(find.text('In 3 days'), findsOneWidget);
    expect(find.text('Nov 25, 2026'), findsOneWidget); // the day the charge starts
    expect(find.textContaining('7 days'), findsNothing);
    expect(find.text('3 days free, then ₹22,500.00/year'), findsWidgets);
    world.platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pumpAndSettle();
    expect(world.platform.launched.single.offerToken, 'token-yearly-trial');
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a plan with no Play free-trial phase gets the plain plans: price, Subscribe, disclosure, no trial',
      (tester) async {
    final world = await pumpTrialPage(tester, omiProDetails(yearlyTrial: false));
    expect(find.byType(PlayPlansContent), findsOneWidget);
    expect(find.byKey(const Key('trial_paywall_cta')), findsNothing);
    expect(find.text('In 7 days'), findsNothing);
    expect(find.byKey(const Key('play_renewal_terms')), findsOneWidget);
    // Yearly is selected and has no trial phase: no trial line, a plain Subscribe of the base plan.
    expect(find.textContaining('days free'), findsNothing);
    world.platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    await tester.tap(find.byKey(const Key('play_subscribe')));
    await tester.pumpAndSettle();
    expect(world.platform.launched.single.offerToken, 'token-yearly');
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a Play client that never answers ends in Retry, not a skeleton forever', (tester) async {
    tester.view.physicalSize = const Size(430, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final world = _World([_response()], platform: FakePlayPlatform(hang: true));
    addTearDown(world.usage.dispose);
    await world.usage.fetchSubscription();
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: world.usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 22)),
      ),
    ));
    await tester.pump();
    expect(find.byKey(const Key('play_plans_error')), findsNothing);
    // While Play's offers load: a skeleton, never the constant trial length or its date.
    expect(find.byKey(const Key('trial_paywall_timeline_pending')), findsOneWidget);
    expect(find.byKey(const Key('trial_paywall_timeline')), findsNothing);
    expect(find.text('In 7 days'), findsNothing);
    await tester.pump(playQueryTimeout + const Duration(seconds: 1));
    await tester.pump();
    expect(world.usage.playOffersLoading, isFalse);
    expect(find.byKey(const Key('play_plans_error')), findsOneWidget);
    expect(find.byKey(const Key('trial_paywall_timeline_pending')), findsNothing);
    expect(find.byKey(const Key('trial_paywall_timeline')), findsNothing);
    expect(find.text('In 7 days'), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('Restore says when the purchase belongs to another Omi account', (tester) async {
    final world = await _pump(tester, [_response()]);
    world.server.answer = (_, __) => const PlayVerifyResult('error', code: 'purchase_owned_elsewhere');
    world.platform.owned = [playPurchase(PurchaseStatus.restored, token: 'theirs')];
    await tester.tap(find.byKey(const Key('play_restore')));
    await tester.pumpAndSettle();
    expect(find.text('This Google Play purchase belongs to another Omi account.'), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a Play subscriber on iOS sees Managed in Google Play, not Stripe', (tester) async {
    final world = await _pump(tester, [_response(plan: PlanType.unlimitedV2, provider: 'play', play: null)]);
    expect(world.usage.playBilling, isNull);
    expect(find.byKey(const Key('play_manage_subscription')), findsOneWidget);
    expect(find.text('Billed by Google Play'), findsOneWidget);
    expect(world.usage.checkoutSessions, 0);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  test('server refusal codes map to plain messages', () async {
    final l10n = await AppLocalizations.delegate.load(const Locale('en'));
    expect(playRefusalMessage(l10n, 'purchase_owned_elsewhere'), contains('another Omi account'));
    expect(playRefusalMessage(l10n, null), contains("couldn't confirm"));
    expect(const PlayVerifyResult('active').retryable, isFalse);
  });

  // ---- prepaid code entry (switch on) -----------------------------------------------------------------

  testWidgets('switch on: a Play-billed reader sees no code entry on the plans sheet, trial or outline paywall',
      (tester) async {
    final world = await _pump(tester, [_response(prepaidCodeRedeem: true)]);
    expect(world.usage.playBilledPurchaser, isTrue);
    expect(world.usage.canRedeemPrepaidCode, isFalse);
    expect(find.byType(PlayPlansContent), findsOneWidget);
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);

    await _pump(tester, [_response(prepaidCodeRedeem: true)],
        child: TrialPaywallPage(source: 'test', now: DateTime(2026, 11, 23)));
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);
    expect(find.byKey(const Key('trial_paywall_code_hint')), findsNothing);

    await _pump(tester, [_response(prepaidCodeRedeem: true)], child: const OutlinePaywallPage(source: 'test'));
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('switch on: Android before the billing provider is known shows no code entry', (tester) async {
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    expect(usage.billingProviderUnknown, isTrue);
    expect(usage.canRedeemPrepaidCode, isFalse);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('switch on, Stripe reader on Android: one code row, and a discount code moves to the promo field',
      (tester) async {
    final world = await _pump(tester, [_response(play: null, prepaidCodeRedeem: true)]);
    expect(world.usage.canRedeemPrepaidCode, isTrue);
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsOneWidget);
    expect(find.text('Promo code'), findsNothing);
    prepaidCodeRedeemer =
        (code) async => const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 400, detail: 'not_prepaid'));
    addTearDown(() => prepaidCodeRedeemer = redeemPrepaidCode);
    await tester.tap(find.byKey(const ValueKey('prepaid_code_entry')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('prepaid_code_field')), 'SAVE50');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('prepaid_code_redeem')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('prepaid_code_field')), findsNothing);
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);
    expect(find.byKey(const ValueKey('plans_sheet_promo_code')), findsOneWidget);
    expect(find.text('SAVE50'), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('switch off: the plans sheet keeps only today\'s promo row', (tester) async {
    await _pump(tester, [_response(play: null)]);
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);
    expect(find.text('Promo code'), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a prepaid plan shows only its end date: no resubscribe, upgrade, cancel or payment method',
      (tester) async {
    await _pump(tester, [
      _response(
          play: null,
          plan: PlanType.unlimitedV2,
          stripeId: 'sub_prepaid',
          cancelAtPeriodEnd: true,
          prepaid: true,
          prepaidCodeRedeem: true)
    ]);
    expect(find.byKey(const ValueKey('plans_sheet_prepaid')), findsOneWidget);
    expect(find.byKey(const ValueKey('plans_sheet_prepaid_ends')), findsOneWidget);
    expect(find.textContaining('ends'), findsOneWidget);
    expect(find.textContaining('Resubscribe'), findsNothing);
    expect(find.byKey(const ValueKey('plans_sheet_cancel_reassurance')), findsNothing);
    expect(find.byKey(const ValueKey('plans_sheet_upgrade_button')), findsNothing);
    expect(find.textContaining('payment method'), findsNothing);
    expect(find.textContaining('Cancel'), findsNothing);
    expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);
  }, variant: TargetPlatformVariant.all());
}
