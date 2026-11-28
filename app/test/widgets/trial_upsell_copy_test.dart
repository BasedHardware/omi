import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_upsell_sheet.dart';
import 'package:omi/providers/usage_provider.dart';

const _offer = PaywallOffer(
  tierId: 'unlimited_v2',
  monthly: PaywallPrice(priceId: 'price_fixture_month', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'price_fixture_year', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

void main() {
  testWidgets('the 30-day offer says it is a trial that needs a card, with price terms unchanged', (tester) async {
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>(
      create: (_) => UsageProvider(deviceTimeZone: () async => 'UTC'),
      child: MaterialApp(
        locale: const Locale('en'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: TrialUpsellContent(
            source: 'onboarding',
            offer: _offer,
            price: _offer.yearly!,
            checkout: (_, __, ___) async => PaywallCheckoutOutcome.cancelled,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Try Omi Pro free for 30 days'), findsOneWidget);
    expect(
      find.text('Add a card to start. You pay nothing today. After 30 days, your paid plan starts at the price below '
          'unless you cancel first. Cancel in Settings > Plan & Usage.'),
      findsOneWidget,
    );
    // No promise of a reminder: it rides on a push that some buyers never get.
    expect(find.textContaining('remind'), findsNothing);
    expect(find.textContaining('upgraded'), findsNothing);
    expect(find.textContaining('on us'), findsNothing);
    // Unchanged: the price terms line and the Claim button.
    expect(find.text(r'30 days free, then US$269.91/year'), findsOneWidget);
    expect(find.text('Claim my 30-day trial'), findsOneWidget);
  });

  test('every locale names the trial length and keeps no stray placeholder', () async {
    for (final locale in AppLocalizations.supportedLocales) {
      final l10n = await AppLocalizations.delegate.load(locale);
      expect(l10n.trialUpsellTitle(30), contains('30'), reason: '$locale title');
      expect(l10n.trialUpsellBody(30), isNot(contains('{')), reason: '$locale body');
      // Names the real cancel path, in that locale's own words for Settings and Plan & Usage.
      expect(l10n.trialUpsellBody(30), contains(l10n.planAndUsage), reason: '$locale cancel path');
      expect(l10n.trialUpsellBody(30), contains('30'), reason: '$locale trial end');
      expect(l10n.trialUpsellTitle(30) + l10n.trialUpsellBody(30), isNot(matches(RegExp('[–—]'))),
          reason: '$locale dashes');
    }
  });
}
