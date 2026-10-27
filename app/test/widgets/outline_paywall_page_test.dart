import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/providers/usage_provider.dart';

// The Outline paywall renders the catalog's Unlimited prices, sends the selected price to the
// shared checkout, and always leaves a way out (Use Free Plan) that never charges.

const _offer = PaywallOffer(
  tierId: 'unlimited_v2',
  monthly: PaywallPrice(priceId: 'price_month', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'price_year', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

typedef _Checkout = Future<PaywallCheckoutOutcome> Function(BuildContext context, PaywallPrice price, String tierId);

Future<void> _open(WidgetTester tester, {required _Checkout checkout, required void Function(Object?) onClosed}) async {
  // The provider sits above the navigator: the page is a pushed route, not part of `home`.
  await tester.pumpWidget(
    ChangeNotifierProvider(
      create: (_) => UsageProvider(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              final result = await Navigator.of(context).push<Object?>(
                MaterialPageRoute(
                  builder: (_) => OutlinePaywallPage(source: 'usage_page', offer: _offer, checkout: checkout),
                ),
              );
              onClosed(result);
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the catalog prices, the yearly saving and both exits', (tester) async {
    await _open(tester, checkout: (_, __, ___) async => PaywallCheckoutOutcome.cancelled, onClosed: (_) {});
    expect(find.text('Never miss a word again.'), findsOneWidget);
    expect(find.text(r'$22.49'), findsOneWidget, reason: 'yearly shown per month');
    expect(find.text(r'$269.91'), findsOneWidget, reason: 'yearly total');
    expect(find.text(r'$29.99'), findsNWidgets(2), reason: 'monthly price and subtitle');
    expect(find.text('SAVE ~25%'), findsOneWidget);
    expect(find.text('Upgrade to Omi Pro'), findsOneWidget);
    expect(find.text('Use Free Plan'), findsOneWidget);
    expect(find.text('Cancel anytime.'), findsOneWidget);
    expect(find.byKey(const Key('outline_paywall_close')), findsOneWidget);
  });

  testWidgets('the button sends the yearly price by default and closes on purchase', (tester) async {
    final sent = <String>[];
    Object? closed = 'unset';
    await _open(
      tester,
      checkout: (_, price, tierId) async {
        sent.add('$tierId:${price.priceId}');
        return PaywallCheckoutOutcome.purchased;
      },
      onClosed: (result) => closed = result,
    );
    await tester.tap(find.byKey(const Key('outline_paywall_cta')));
    await tester.pumpAndSettle();
    expect(sent, ['unlimited_v2:price_year']);
    expect(closed, isTrue);
  });

  testWidgets('selecting monthly sends the monthly price and a cancelled checkout keeps the page', (tester) async {
    final sent = <String>[];
    Object? closed = 'unset';
    await _open(
      tester,
      checkout: (_, price, __) async {
        sent.add(price.priceId);
        return PaywallCheckoutOutcome.cancelled;
      },
      onClosed: (result) => closed = result,
    );
    await tester.tap(find.byKey(const Key('outline_paywall_monthly')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('outline_paywall_cta')));
    await tester.pumpAndSettle();
    expect(sent, ['price_month']);
    expect(closed, 'unset');
    expect(find.text('Upgrade to Omi Pro'), findsOneWidget);
  });

  testWidgets('Use Free Plan closes without charging', (tester) async {
    var checkouts = 0;
    Object? closed = 'unset';
    await _open(
      tester,
      checkout: (_, __, ___) async {
        checkouts++;
        return PaywallCheckoutOutcome.purchased;
      },
      onClosed: (result) => closed = result,
    );
    await tester.tap(find.byKey(const Key('outline_paywall_free')));
    await tester.pumpAndSettle();
    expect(checkouts, 0);
    expect(closed, isFalse);
    expect(find.text('open'), findsOneWidget);
  });
}
