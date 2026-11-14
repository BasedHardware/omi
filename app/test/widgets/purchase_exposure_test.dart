import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/pages/settings/widgets/yearly_switch.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/ui/components/omi_locked_preview.dart';
import 'package:provider/provider.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/purchase_exposure.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import '../support/recording_analytics.dart';

UserSubscriptionResponse snapshot(
        {bool paid = false, String reason = 'plan_within_allowance', bool chatAllowed = true}) =>
    UserSubscriptionResponse(
        subscription:
            Subscription(plan: paid ? PlanType.unlimitedV2 : PlanType.basic, status: SubscriptionStatus.active),
        chatQuotaAllowed: chatAllowed,
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 100,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        transcriptionAllowance: TranscriptionAllowanceSnapshot(
            mode: reason == 'plan_within_allowance' ? 'managed' : 'on_device', reason: reason, remainingSeconds: 0));

class _FailingCheckoutUsage extends UsageProvider {
  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession(
          {required String priceId, String? promotionCode, int? trialDays}) async =>
      null;
}

class _StorefrontUsage extends UsageProvider {
  @override
  Future<void> loadAvailablePlans() async {}
}

class _StorefrontApi extends PlanStorefrontApi {
  _StorefrontApi(this.response) : super(baseUrl: 'http://127.0.0.1:9/');
  final Future<ApiResult<PlanStorefront>> Function() response;
  @override
  Future<ApiResult<PlanStorefront>> load({required String source, String trigger = '', required String locale}) =>
      response();
}

class _StorefrontHost extends StatefulWidget {
  const _StorefrontHost(this.api, {this.initial});
  final PlanStorefrontApi api;
  final PlanStorefront? initial;
  @override
  State<_StorefrontHost> createState() => _StorefrontHostState();
}

class _StorefrontHostState extends State<_StorefrontHost> with TickerProviderStateMixin {
  late final animation = AnimationController(vsync: this);
  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
      waveController: animation,
      notesController: animation,
      arrowController: animation,
      arrowAnimation: animation,
      storefrontApi: widget.api,
      initialStorefront: widget.initial,
      readStorefrontGate: () async => true);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late RecordingAnalytics recording;
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Test', packageName: 'dev.omi.test', version: '1', buildNumber: '1', buildSignature: '');
    await SharedPreferencesUtil.init();
    recording = RecordingAnalytics();
    AnalyticsManager.configure(recording.adapter);
    await AnalyticsManager.init();
  });
  tearDown(AnalyticsManager.resetForTesting);
  Future<void> flush() async {
    await AnalyticsManager.flushPending(force: true);
  }

  testWidgets('one view per mount, none on rebuild, hidden or removed before commit', (tester) async {
    Widget surface({bool enabled = true, Key? key}) => PaywallViewedOnce(
        key: key,
        enabled: enabled,
        source: 'usage_page',
        surface: PaywallViewedSurface.plansSheet,
        child: const SizedBox());
    await tester.pumpWidget(surface(enabled: false));
    await flush();
    expect(recording.names, isNot(contains('Subscription Paywall Viewed')));
    await tester.pumpWidget(surface());
    await flush();
    await tester.pumpWidget(surface());
    await tester.pump();
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(surface(key: const ValueKey('next')));
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(2));
  });

  wire.GeneratedYearlySwitchResponse yearlyOffer({String? price = 'fixture', bool eligible = true}) =>
      wire.GeneratedYearlySwitchResponse(
          eligible: eligible,
          reason: 'eligible',
          planId: 'unlimited_v2',
          priceId: price,
          currency: 'usd',
          amountDueToday: 100,
          yearlyAmount: 30000,
          renewsAt: 1900000000,
          prorationDate: 1800000000);

  Widget yearlyHost(YearlySwitchLoader load) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: YearlySwitchSheet(surface: YearlySwitchSurface.plans, load: load)));

  testWidgets('yearly preview waits for a valid rendered offer and counts once', (tester) async {
    final response = Completer<wire.GeneratedYearlySwitchResponse?>();
    await tester.pumpWidget(yearlyHost(({bool preview = false}) => response.future));
    await flush();
    expect(find.byKey(const Key('yearly_switch_loading')), findsOneWidget);
    expect(recording.propertiesOf('Subscription Paywall Viewed'), isEmpty);
    response.complete(yearlyOffer());
    await tester.pump();
    await tester.pump();
    await flush();
    expect(find.byKey(const Key('yearly_switch_preview')), findsOneWidget);
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.pump();
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('yearly error, refused and missing price never expose a purchase offer', (tester) async {
    for (final offer in [
      null,
      yearlyOffer(eligible: false),
      yearlyOffer(price: null),
      yearlyOffer(price: ''),
      yearlyOffer(price: '  ')
    ]) {
      await tester.pumpWidget(yearlyHost(({bool preview = false}) async => offer));
      await tester.pump();
      await tester.pump();
      await flush();
      expect(recording.propertiesOf('Subscription Paywall Viewed'), isEmpty);
      await tester.pumpWidget(const SizedBox());
    }
  });

  Map<String, dynamic> storefrontJson() =>
      jsonDecode(File('test/fixtures/storefront_v2/single_plan_omi_pro.json').readAsStringSync())
          as Map<String, dynamic>;

  Future<void> storefrontHost(WidgetTester tester, PlanStorefrontApi api, {PlanStorefront? initial}) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _StorefrontUsage();
    addTearDown(usage.dispose);
    usage.debugSetSubscription(snapshot());
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(body: _StorefrontHost(api, initial: initial)))));
    await tester.pump();
    await tester.pump();
  }

  testWidgets('storefront loading does not consume the eventual offer view', (tester) async {
    final response = Completer<ApiResult<PlanStorefront>>();
    await storefrontHost(tester, _StorefrontApi(() => response.future));
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), isEmpty);
    response.complete(ApiSuccess(PlanStorefront.fromJson(storefrontJson())));
    await tester.pump();
    await tester.pump();
    await flush();
    expect(find.byKey(const Key('storefront_buy_unlimited_v2')), findsOneWidget);
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.pump();
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('storefront failure, hidden, empty, legacy and invalid offers never count', (tester) async {
    for (final state in ['failure', 'hidden', 'empty', 'legacy', 'invalid']) {
      final json = storefrontJson();
      if (state == 'hidden') json['show_subscription_ui'] = false;
      if (state == 'empty') json['tiers'] = [];
      if (state == 'legacy') {
        json['current']['legacy'] = true;
        json['current']['legacy_note'] = 'Legacy plan';
      }
      if (state == 'invalid') {
        for (final tier in json['tiers']) {
          for (final price in tier['prices']) {
            price['price_id'] = null;
          }
        }
      }
      await storefrontHost(
          tester,
          _StorefrontApi(() async => state == 'failure'
              ? const ApiFailure(ApiProblem(ApiProblemKind.transport))
              : ApiSuccess(PlanStorefront.fromJson(json))));
      await tester.pump();
      await tester.pump();
      await flush();
      expect(recording.propertiesOf('Subscription Paywall Viewed'), isEmpty, reason: state);
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('collapsed and unselected storefront offers wait until actually rendered', (tester) async {
    final json = storefrontJson();
    json['tiers'][0]['recommended'] = false;
    for (final price in json['tiers'][0]['prices']) {
      if (price['interval'] == 'month') price['price_id'] = null;
    }
    final data = PlanStorefront.fromJson(json);
    await storefrontHost(tester, _StorefrontApi(() async => ApiSuccess(data)), initial: data);
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), isEmpty);
    await tester.tap(find.byKey(const Key('storefront_other_plans')));
    await tester.pumpAndSettle();
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), isEmpty);
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.tap(find.byKey(const Key('storefront_month')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    await flush();
    expect(recording.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('block shows once across rebuilds and rearms only after hidden state', (tester) async {
    Widget block(bool shown) => AllowanceBlockShownOnce(
        kind: 'chat', surface: 'chat', reason: 'chat_quota_exhausted', shown: shown, child: const SizedBox());
    await tester.pumpWidget(block(false));
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), isEmpty);
    await tester.pumpWidget(block(true));
    await tester.pumpWidget(block(true));
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), hasLength(1));
    await tester.pumpWidget(block(false));
    await tester.pumpWidget(block(true));
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), hasLength(2));
  });

  test('authoritative allowance excludes unavailability and deduplicates until recovery', () async {
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    usage.debugSetSubscription(snapshot(reason: 'allowance_unavailable'));
    usage.debugSetSubscription(snapshot(reason: 'usage_invalid'));
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached'), isEmpty);
    usage.debugSetSubscription(snapshot(reason: 'plan_allowance_exhausted'));
    usage.debugSetSubscription(snapshot(reason: 'plan_allowance_exhausted'));
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached'), hasLength(1));
    usage.debugSetSubscription(snapshot());
    usage.debugSetSubscription(snapshot(reason: 'plan_allowance_exhausted'));
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached'), hasLength(2));
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), isEmpty);
    usage.debugSetSubscription(snapshot(reason: 'usage_budget_exhausted'));
    await flush();
    expect(
        recording.propertiesOf('Subscription Allowance Reached').last, containsPair('allowance_kind', 'usage_budget'));
    expect(recording.propertiesOf('Subscription Allowance Reached').last, containsPair('reason', 'budget_exhausted'));
  });

  test('shared budget emits once without a false chat cap and rearms after kind changes and recovery', () async {
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    void apply(String reason, {bool chatAllowed = false}) =>
        usage.debugSetSubscription(snapshot(reason: reason, chatAllowed: chatAllowed));
    apply('usage_budget_exhausted');
    apply('usage_budget_exhausted');
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached').map((e) => e['allowance_kind']), ['usage_budget']);
    apply('plan_allowance_exhausted'); // Distinct capture and chat allowances are real.
    apply('plan_allowance_exhausted');
    apply('usage_budget_exhausted');
    apply('plan_within_allowance', chatAllowed: true);
    apply('usage_budget_exhausted');
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached').map((e) => e['allowance_kind']),
        ['usage_budget', 'transcription', 'chat', 'usage_budget', 'usage_budget']);
    expect(recording.propertiesOf('Subscription Allowance Reached').map((e) => e['reason']), [
      'budget_exhausted',
      'plan_allowance_exhausted',
      'chat_quota_exhausted',
      'budget_exhausted',
      'budget_exhausted'
    ]);
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), isEmpty);
  });

  test('restore results use fresh server outcome, never stale paid state', () async {
    final outcomes = <UserSubscriptionResponse?>[snapshot(paid: true), snapshot(), null];
    final usage = UsageProvider(subscriptionRequest: () async => outcomes.removeAt(0));
    addTearDown(usage.dispose);
    for (var i = 0; i < 3; i++) {
      usage.debugSetSubscription(snapshot(paid: true));
      await observePurchaseRestore(usage, 'onboarding');
    }
    await flush();
    expect(recording.propertiesOf('Subscription Restore Attempted'), hasLength(3));
    expect(recording.propertiesOf('Subscription Restore Result').map((e) => e['result']),
        ['succeeded', 'no_entitlement', 'failed']);
    expect(recording.propertiesOf('Subscription Checkout Completed'), isEmpty);
  });

  test('purchase dimensions project only closed values and omit unknown inputs', () async {
    final analytics = AnalyticsManager();
    analytics.paywallViewed('https://private.invalid/secret',
        surface: PaywallViewedSurface.plansSheet, currentPlan: 'private', catalogTier: 'private');
    analytics.upgradePlanSelected(plan: 'private', billingInterval: 'private', source: 'private');
    await flush();
    recording.expectSingle(
        'Subscription Upgrade Tapped', {'plan': 'unknown', 'billing_interval': 'unknown', 'source': 'unknown'});
    recording.expectSingle(
        'Subscription Paywall Viewed', {'source': 'unknown', 'current_plan': 'unknown', 'catalog_tier': 'unknown'});
    expect(recording.names, isNot(contains('Subscription Checkout Opened')));
    expect(recording.names, isNot(contains('Subscription Checkout Completed')));
  });
  testWidgets('trial and outline actual surfaces each view once across page rebuilds', (tester) async {
    tester.view.physicalSize = const Size(430, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    usage.debugSetSubscription(snapshot());
    const offer = PaywallOffer(
        tierId: 'unlimited_v2',
        monthly: PaywallPrice(priceId: 'fixture', interval: 'month', amountMinor: 3000, currency: 'usd'),
        yearly: null);
    Widget host(Widget page) => ChangeNotifierProvider.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: page));
    for (final page in [
      const TrialPaywallPage(source: 'onboarding', offer: offer),
      const OutlinePaywallPage(source: 'onboarding', offer: offer)
    ]) {
      await tester.pumpWidget(host(page));
      await tester.pump();
      await tester.pumpWidget(host(page));
      await flush();
    }
    expect(recording.propertiesOf('Subscription Paywall Viewed').map((e) => e['surface']),
        ['trial_paywall', 'outline_paywall']);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('failed URL acquisition records intent but never opens or completes checkout', (tester) async {
    final usage = _FailingCheckoutUsage();
    addTearDown(usage.dispose);
    usage.debugSetSubscription(snapshot());
    late BuildContext purchaseContext;
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(body: Builder(builder: (context) {
              purchaseContext = context;
              return const SizedBox();
            })))));
    final outcome = await PaywallCheckout.start(purchaseContext,
        priceId: 'fixture', plan: 'unlimited_v2', interval: 'month', source: 'usage_page');
    expect(outcome, PaywallCheckoutOutcome.failed);
    await flush();
    expect(recording.propertiesOf('Subscription Upgrade Tapped'), hasLength(1));
    expect(recording.propertiesOf('Subscription Checkout Opened'), isEmpty);
    expect(recording.propertiesOf('Subscription Checkout Completed'), isEmpty);
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('the rendered locked preview CTA records intent without inventing checkout', (tester) async {
    var taps = 0;
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: OmiLockedPreview(
                label: 'Upgrade',
                purchaseSource: 'held_audio',
                onPressed: () {
                  taps++;
                },
                child: const SizedBox(width: 200, height: 100)))));
    await tester.pump();
    await tester.tap(find.byKey(const Key('locked_preview_action')));
    await flush();
    expect(taps, 1);
    recording.expectSingle(
        'Subscription Upgrade Tapped', {'source': 'held_audio', 'plan': 'unknown', 'billing_interval': 'unknown'});
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), hasLength(1));
    expect(recording.propertiesOf('Subscription Checkout Opened'), isEmpty);
    await tester.pumpWidget(const SizedBox());
  });

  test('chat budget reads deduplicate independently of whether block UI mounts', () async {
    final messages = MessageProvider();
    addTearDown(messages.dispose);
    const cap = ChatAtCap(title: 'Server cap', body: 'Server cap body', resetLine: 'Server reset', resetAt: 4102444800);
    messages.applyChatAtCap(cap);
    messages.applyChatAtCap(cap);
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached'), hasLength(1));
    expect(recording.propertiesOf('Subscription Allowance Block Shown'), isEmpty);
    messages.applyChatAtCap(null);
    messages.applyChatAtCap(cap);
    await flush();
    expect(recording.propertiesOf('Subscription Allowance Reached'), hasLength(2));
  });
}
