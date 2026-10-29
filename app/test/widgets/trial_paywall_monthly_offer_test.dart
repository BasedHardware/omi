import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

// A reader who leaves the yearly checkout without buying is offered the monthly plan once per
// paywall: priced from the catalog, with the free trial only when the backend still offers one,
// and its button opens the same checkout as the Monthly card.

const _offer = PaywallOffer(
  tierId: 'unlimited_v2',
  monthly: PaywallPrice(priceId: 'price_month', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'price_year', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

const _title = 'Not ready for a year?';
const _trialTerms = 'Start monthly instead. Same 7 days free, then US\$29.99 a month. Cancel anytime.';

UserSubscriptionResponse _subscription({PlanType plan = PlanType.basic, bool trialEligible = true}) =>
    UserSubscriptionResponse(
      trialEligible: trialEligible,
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: true,
    );

/// The page refetches the subscription before it offers monthly; [server] is what that returns.
class _Usage extends UsageProvider {
  _Usage(this.server) {
    debugSetSubscription(server);
  }

  UserSubscriptionResponse server;
  int fetches = 0;
  Future<void>? refresh;

  @override
  String? get error => refreshError;
  String? refreshError;

  @override
  Future<void> fetchSubscription() async {
    fetches++;
    await refresh;
    debugSetSubscription(server);
  }
}

/// Stands in for Stripe Checkout: records each price it opened and answers with the next outcome.
class _Checkout {
  _Checkout(this.outcomes);

  final List<PaywallCheckoutOutcome> outcomes;
  final opened = <PaywallPrice>[];

  Future<PaywallCheckoutOutcome> call(BuildContext context, PaywallPrice price, String tierId) async {
    opened.add(price);
    return outcomes.removeAt(0);
  }
}

class _Events implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];

  /// The offer's events with only their own properties (the manager adds app-wide ones).
  List<(String, Map<String, Object>)> get offer => [
        for (final (name, properties) in events)
          if (name.startsWith('Paywall Monthly Fallback'))
            (
              name,
              {
                for (final key in const ['trial', 'outcome'])
                  if (properties.containsKey(key)) key: properties[key]!
              }
            ),
      ];

  @override
  bool get isInitialized => true;
  @override
  Future<void> init() async {}
  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}
  @override
  void alias({required String newUserId}) {}
  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, properties ?? const {}));
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

Future<void> _open(WidgetTester tester, _Usage usage, _Checkout checkout, {PaywallOffer offer = _offer}) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<bool>(
                builder: (_) => TrialPaywallPage(
                  source: 'onboarding',
                  offer: offer,
                  now: DateTime(2026, 10, 29),
                  checkout: checkout.call,
                ),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _tapCta(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('trial_paywall_cta')));
  await tester.pumpAndSettle();
}

Future<void> _chooseMonthlyCard(WidgetTester tester) async {
  final card = find.byKey(const Key('trial_paywall_monthly'));
  final page = find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down);
  await tester.scrollUntilVisible(card, 200, scrollable: page.first);
  await tester.pumpAndSettle();
  await tester.tap(card);
  await tester.pumpAndSettle();
}

String _terms(WidgetTester tester) => tester.widget<Text>(find.byKey(const Key('trial_paywall_price_terms'))).data!;

void main() {
  late _Events analytics;

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    analytics = _Events();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  Future<List<(String, Map<String, Object>)>> offerEvents(WidgetTester tester) async {
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    return analytics.offer;
  }

  testWidgets('leaving the yearly checkout offers monthly with the trial, once per paywall', (tester) async {
    final usage = _Usage(_subscription());
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled, PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);

    await _tapCta(tester);
    expect(checkout.opened, [_offer.yearly], reason: 'Yearly is preselected');
    expect(usage.fetches, 1, reason: 'the server is asked before a second plan is offered');
    expect(find.text(_title), findsOneWidget);
    expect(find.text(_trialTerms), findsOneWidget);
    expect(find.text('Try monthly free'), findsOneWidget);
    expect(find.text('Not now'), findsOneWidget);

    await tester.tap(find.byKey(const Key('trial_paywall_monthly_offer_decline')));
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);
    expect(checkout.opened, hasLength(1), reason: 'Not now buys nothing');
    expect(_terms(tester), '7 days free, then US\$269.91/year', reason: 'the selection is left alone');

    // Leaving the yearly checkout again does not bring the sheet back.
    await _tapCta(tester);
    expect(checkout.opened, [_offer.yearly, _offer.yearly]);
    expect(find.text(_title), findsNothing);
    expect(usage.fetches, 1);

    final events = await offerEvents(tester);
    expect(events.map((e) => e.$1), ['Paywall Monthly Fallback Shown', 'Paywall Monthly Fallback Dismissed']);
    expect(events.map((e) => e.$2['trial']), [true, true]);
  });

  testWidgets('"Try monthly free" opens the Monthly card checkout and reports its outcome', (tester) async {
    final usage = _Usage(_subscription());
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled, PaywallCheckoutOutcome.purchased]);
    await _open(tester, usage, checkout);

    await _tapCta(tester);
    expect(await offerEvents(tester), hasLength(1), reason: 'Shown only; nothing is accepted on sight');
    await tester.tap(find.byKey(const Key('trial_paywall_monthly_offer_accept')));
    await tester.pumpAndSettle();

    expect(checkout.opened, [_offer.yearly, _offer.monthly]);
    expect(identical(checkout.opened.last, _offer.monthly), isTrue, reason: 'the Monthly card price, not a new one');
    expect(find.byType(TrialPaywallPage), findsNothing, reason: 'a purchase closes the paywall');
    final events = await offerEvents(tester);
    expect(events.map((e) => e.$1), ['Paywall Monthly Fallback Shown', 'Paywall Monthly Fallback Accepted']);
    expect(events.last.$2, {'trial': true, 'outcome': 'purchased'});
  });

  testWidgets('leaving the monthly checkout from the sheet selects Monthly and offers nothing more', (tester) async {
    final usage = _Usage(_subscription());
    final checkout = _Checkout([
      PaywallCheckoutOutcome.cancelled,
      PaywallCheckoutOutcome.cancelled,
      PaywallCheckoutOutcome.cancelled,
    ]);
    await _open(tester, usage, checkout);

    await _tapCta(tester);
    await tester.tap(find.byKey(const Key('trial_paywall_monthly_offer_accept')));
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);
    expect(_terms(tester), '7 days free, then US\$29.99/month');

    await _tapCta(tester);
    expect(checkout.opened, [_offer.yearly, _offer.monthly, _offer.monthly]);
    expect(find.text(_title), findsNothing);
    final events = await offerEvents(tester);
    expect(events.map((e) => e.$1), ['Paywall Monthly Fallback Shown', 'Paywall Monthly Fallback Accepted']);
    expect(events.last.$2['outcome'], 'cancelled');
  });

  testWidgets('leaving a monthly checkout offers nothing', (tester) async {
    final usage = _Usage(_subscription());
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);

    await _chooseMonthlyCard(tester);
    await _tapCta(tester);
    expect(checkout.opened, [_offer.monthly]);
    expect(find.text(_title), findsNothing);
    expect(usage.fetches, 0);
    expect(await offerEvents(tester), isEmpty);
  });

  testWidgets('a completed or failed yearly checkout offers nothing', (tester) async {
    final usage = _Usage(_subscription());
    final checkout = _Checkout([PaywallCheckoutOutcome.failed, PaywallCheckoutOutcome.purchased]);
    await _open(tester, usage, checkout);

    await _tapCta(tester); // e.g. Checkout refused before it opened
    expect(find.text(_title), findsNothing);
    await _tapCta(tester);
    expect(find.byType(TrialPaywallPage), findsNothing, reason: 'purchased');
    expect(find.text(_title), findsNothing);
    expect(usage.fetches, 0);
    expect(await offerEvents(tester), isEmpty);
  });

  testWidgets('a reader the server now shows as paying is not offered a second plan', (tester) async {
    final usage = _Usage(_subscription());
    // The checkout finished but the app never saw the success page; the webhook already landed.
    usage.server = _subscription(plan: PlanType.unlimitedV2, trialEligible: false);
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);

    await _tapCta(tester);
    expect(usage.fetches, 1);
    expect(find.text(_title), findsNothing);
    expect(await offerEvents(tester), isEmpty);
  });

  testWidgets('without a trial the sheet promises none', (tester) async {
    final usage = _Usage(_subscription());
    usage.server = _subscription(trialEligible: false);
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled, PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);

    await _tapCta(tester);
    expect(find.text(_title), findsOneWidget);
    final terms = tester.widget<Text>(find.byKey(const Key('trial_paywall_monthly_offer_terms'))).data!;
    expect(terms, 'Start monthly instead. US\$29.99 a month. Cancel anytime.');
    expect(terms, isNot(contains('free')));
    expect(find.text('Choose monthly'), findsOneWidget);
    expect(find.text('Try monthly free'), findsNothing);

    await tester.tap(find.text('Choose monthly'));
    await tester.pumpAndSettle();
    expect(checkout.opened, [_offer.yearly, _offer.monthly]);
    final events = await offerEvents(tester);
    expect(events.first.$2, {'trial': false});
    expect(events.last.$2, {'trial': false, 'outcome': 'cancelled'});
  });

  testWidgets('a reader without a trial cannot open checkout under the free-trial button', (tester) async {
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled]);
    await _open(tester, _Usage(_subscription(trialEligible: false)), checkout);
    await _tapCta(tester);
    expect(checkout.opened, isEmpty);
    expect(find.text(_title), findsNothing);
    expect(await offerEvents(tester), isEmpty);
  });

  testWidgets('a failed subscription refresh does not offer another checkout', (tester) async {
    final usage = _Usage(_subscription())..refreshError = 'offline';
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);
    await _tapCta(tester);
    expect(find.text(_title), findsNothing);
    expect(await offerEvents(tester), isEmpty);
    expect(checkout.opened, [_offer.yearly]);
  });

  testWidgets('a timed-out subscription refresh does not offer another checkout', (tester) async {
    final refresh = Completer<void>();
    final usage = _Usage(_subscription())..refresh = refresh.future;
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);
    expect(await offerEvents(tester), isEmpty);
    refresh.complete();
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing, reason: 'a late refresh cannot reopen the offer');
  });

  testWidgets('the price is the catalog price, in its own currency', (tester) async {
    const yen = PaywallOffer(
      tierId: 'unlimited_v2',
      monthly: PaywallPrice(priceId: 'price_month_jpy', interval: 'month', amountMinor: 4500, currency: 'jpy'),
      yearly: PaywallPrice(priceId: 'price_year_jpy', interval: 'year', amountMinor: 40500, currency: 'jpy'),
    );
    final usage = _Usage(_subscription());
    await _open(tester, usage, _Checkout([PaywallCheckoutOutcome.cancelled]), offer: yen);

    await _tapCta(tester);
    expect(find.text('Start monthly instead. Same 7 days free, then ¥4,500 a month. Cancel anytime.'), findsOneWidget);
  });

  testWidgets('system back closes the sheet like Not now', (tester) async {
    final usage = _Usage(_subscription());
    final checkout = _Checkout([PaywallCheckoutOutcome.cancelled]);
    await _open(tester, usage, checkout);

    await _tapCta(tester);
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);
    expect(find.byType(TrialPaywallPage), findsOneWidget, reason: 'back closes the sheet, not the paywall');
    expect(checkout.opened, [_offer.yearly]);
    final events = await offerEvents(tester);
    expect(events.map((e) => e.$1), ['Paywall Monthly Fallback Shown', 'Paywall Monthly Fallback Dismissed']);
  });
}
