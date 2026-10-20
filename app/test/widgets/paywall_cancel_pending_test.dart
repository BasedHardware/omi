import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _Usage extends UsageProvider {
  final List<String> sessions = [];
  Map<String, dynamic>? sessionResult;
  Object? sessionError;

  @override
  Future<void> loadAvailablePlans() async {}

  @override
  Future<void> fetchSubscription() async {}

  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession(
      {required String priceId, String? promotionCode, int? trialDays}) async {
    sessions.add(priceId);
    if (sessionError != null) throw sessionError!;
    return sessionResult;
  }
}

_Usage _plusPending({String currentPriceId = 'price_plus_m', bool includeCurrent = true}) {
  final usage = _Usage();
  usage.debugSetSubscription(
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: PlanType.plus,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: currentPriceId,
        currentPeriodEnd: DateTime.utc(2026, 11, 3).millisecondsSinceEpoch ~/ 1000,
        cancelAtPeriodEnd: true,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ),
  );
  usage.debugSetAvailablePlans({
    'plans': <dynamic>[
      if (includeCurrent)
        {'id': 'price_plus_m', 'plan_id': 'plus', 'interval': 'month', 'unit_amount': 1999, 'currency': 'usd'},
      {'id': 'price_u_m', 'plan_id': 'unlimited_v2', 'interval': 'month', 'unit_amount': 2999, 'currency': 'usd'},
      {'id': 'price_u_y', 'plan_id': 'unlimited_v2', 'interval': 'year', 'unit_amount': 26991, 'currency': 'usd'},
    ],
  });
  return usage;
}

Future<void> _openPage(
  WidgetTester tester,
  _Usage usage, {
  Future<PaywallCheckoutOutcome> Function(BuildContext, PaywallPrice, String)? checkout,
  VoidCallback? onOpenPlans,
}) async {
  tester.view.physicalSize = const Size(430, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(usage.dispose);
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: OutlinePaywallPage(source: 'usage_page', checkout: checkout, onOpenPlans: onOpenPlans),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(PlatformManager.initializeForLocalHarness);

  testWidgets('a cancel-pending Plus user is offered Resubscribe on the current price', (tester) async {
    final sent = <String>[];
    await _openPage(
      tester,
      _plusPending(),
      checkout: (_, price, tier) async {
        sent.add('$tier:${price.priceId}');
        return PaywallCheckoutOutcome.cancelled;
      },
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(OutlinePaywallPage)));
    expect(find.text(l10n.resubscribe), findsOneWidget);
    expect(find.text(l10n.upgradeToUnlimited), findsNothing);
    await tester.tap(find.byKey(const Key('outline_paywall_cta')));
    await tester.pump();
    expect(sent, ['plus:price_plus_m']);
  });

  testWidgets('a missing current price shows the blocked line and opens the plans sheet', (tester) async {
    var opened = 0;
    var checkouts = 0;
    await _openPage(
      tester,
      _plusPending(includeCurrent: false),
      checkout: (_, __, ___) async {
        checkouts++;
        return PaywallCheckoutOutcome.purchased;
      },
      onOpenPlans: () => opened++,
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(OutlinePaywallPage)));
    expect(find.text(l10n.resubscribeFirstToChangePlans), findsOneWidget);
    expect(find.text(l10n.upgradeToUnlimited), findsNothing);
    expect(find.byKey(const Key('outline_paywall_open_plans')), findsOneWidget);
    await tester.tap(find.byKey(const Key('outline_paywall_open_plans')));
    await tester.pump();
    expect(opened, 1);
    expect(checkouts, 0);
  });

  testWidgets('checkout reports the blocked line, the renew confirmation, and a thrown error inline', (tester) async {
    final usage = _plusPending();
    addTearDown(usage.dispose);
    final messages = <String>[];
    late BuildContext pageContext;
    await tester.pumpWidget(
      ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body: Builder(
              builder: (context) {
                pageContext = context;
                return const SizedBox.shrink();
              },
            ),
          ),
        ),
      ),
    );
    final l10n = AppLocalizations.of(pageContext);

    final blocked = await PaywallCheckout.start(
      pageContext,
      priceId: 'price_u_m',
      plan: 'unlimited_v2',
      interval: 'month',
      source: 'outline_paywall',
      surface: messages.add,
    );
    expect(blocked, PaywallCheckoutOutcome.failed);
    expect(messages, [l10n.resubscribeFirstToChangePlans]);
    expect(usage.sessions, isEmpty);

    final periodEnd = DateTime.utc(2026, 11, 3).millisecondsSinceEpoch ~/ 1000;
    usage.sessionResult = {
      'status': 'reactivated',
      'next_billing_date': periodEnd,
    };
    messages.clear();
    final renewed = await PaywallCheckout.start(
      pageContext,
      priceId: 'price_plus_m',
      plan: 'plus',
      interval: 'month',
      source: 'outline_paywall',
      surface: messages.add,
    );
    expect(renewed, PaywallCheckoutOutcome.purchased);
    final date = OmiDateFormat.of(pageContext).date(DateTime.fromMillisecondsSinceEpoch(periodEnd * 1000));
    expect(messages.single, l10n.yourPlanWillRenewOn('Plus', date));

    usage.sessionError = Exception('stripe down');
    messages.clear();
    final failed = await PaywallCheckout.start(
      pageContext,
      priceId: 'price_plus_m',
      plan: 'plus',
      interval: 'month',
      source: 'outline_paywall',
      surface: messages.add,
    );
    expect(failed, PaywallCheckoutOutcome.failed);
    expect(messages, [l10n.anErrorOccurredTryAgain]);
  });
}
