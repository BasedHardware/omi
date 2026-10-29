import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/usage_provider.dart';

// The page runs one operation at a time: while a checkout is in flight, Restore and dismissal do
// nothing, and a checkout that settles after the page was dismissed never navigates again.

const _offer = PaywallOffer(
  tierId: 'unlimited',
  monthly: PaywallPrice(priceId: 'm', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'y', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

class _Usage extends UsageProvider {
  int restores = 0;

  @override
  Future<void> fetchSubscription() async {
    restores++;
  }
}

class _Pops extends NavigatorObserver {
  final results = <Object?>[];

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    results.add(route.settings.name);
  }
}

Future<(_Usage, _Pops)> _pump(WidgetTester tester,
    {required Future<PaywallCheckoutOutcome> Function() checkout}) async {
  final usage = _Usage();
  final pops = _Pops();
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        navigatorObservers: [pops],
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<bool>(
                settings: const RouteSettings(name: 'paywall'),
                builder: (_) => TrialPaywallPage(
                  source: 'onboarding',
                  offer: _offer,
                  now: DateTime(2026, 10, 18),
                  checkout: (_, __, ___) => checkout(),
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
  return (usage, pops);
}

void main() {
  testWidgets('Restore and dismiss are ignored while a checkout is in flight', (tester) async {
    final pending = Completer<PaywallCheckoutOutcome>();
    final (usage, pops) = await _pump(tester, checkout: () => pending.future);
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('trial_paywall_restore')), warnIfMissed: false);
    // The free-plan dismissal now uses the close control; also exercise system back.
    await tester.binding.handlePopRoute();
    await tester.tap(find.byKey(const Key('trial_paywall_close')), warnIfMissed: false);
    await tester.pump();
    expect(usage.restores, 0, reason: 'restore must not run concurrently with a checkout');
    expect(pops.results, isEmpty, reason: 'the page stays until the checkout settles');
    expect(find.byType(TrialPaywallPage), findsOneWidget);
    pending.complete(PaywallCheckoutOutcome.cancelled);
    await tester.pumpAndSettle();
    expect(find.byType(TrialPaywallPage), findsOneWidget, reason: 'a cancelled checkout keeps the page');
  });

  testWidgets('a purchase that settles after a dismissal does not navigate again', (tester) async {
    final pending = Completer<PaywallCheckoutOutcome>();
    final (_, pops) = await _pump(tester, checkout: () => pending.future);
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pump();
    // The route is removed from outside the page (the host navigates away) while the checkout
    // future is still pending; the late completion must not pop whatever is now on top.
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pop();
    await tester.pumpAndSettle();
    expect(find.byType(TrialPaywallPage), findsNothing);
    final popsBefore = pops.results.length;
    pending.complete(PaywallCheckoutOutcome.purchased);
    await tester.pumpAndSettle();
    expect(pops.results.length, popsBefore, reason: 'no second pop after the page is gone');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a purchase settling during the exit animation of an external pop does not pop the host', (tester) async {
    final pending = Completer<PaywallCheckoutOutcome>();
    final (_, pops) = await _pump(tester, checkout: () => pending.future);
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pump();
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pop();
    await tester.pump(); // exit animation started; the page is still mounted
    expect(find.byType(TrialPaywallPage), findsOneWidget);
    final popsBefore = pops.results.length;
    pending.complete(PaywallCheckoutOutcome.purchased);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(pops.results.length, popsBefore, reason: 'the host route beneath must not be popped');
    expect(find.text('open'), findsOneWidget, reason: 'the host page is still there');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a purchase pops the page exactly once', (tester) async {
    final (_, pops) = await _pump(tester, checkout: () async => PaywallCheckoutOutcome.purchased);
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pumpAndSettle();
    expect(find.byType(TrialPaywallPage), findsNothing);
    expect(pops.results.where((r) => r == 'paywall').length, 1);
  });
}
