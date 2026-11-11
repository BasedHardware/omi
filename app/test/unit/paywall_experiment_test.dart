import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';

// Free readers get the trial paywall with its sign-up placement. parse() serves the debug-build
// override, where anything but a well-formed variant means the shipped PlansSheet.

void main() {
  test('readers get trial without any flag read; the key stays registered', () {
    expect(PaywallExperiment.current, PaywallExperimentConfig.trial);
    expect(PaywallExperiment.current.onboardingPaywall, isTrue);
    expect(PaywallExperiment.enabledFlag, 'paywall-variant');
    expect(PaywallExperiment.debugOverrideActive, isFalse);
  });

  group('parse', () {
    test('control, null and unknown variants are control', () {
      expect(PaywallExperiment.parse(variant: 'control'), PaywallExperimentConfig.control);
      expect(PaywallExperiment.parse(variant: null), PaywallExperimentConfig.control);
      expect(PaywallExperiment.parse(variant: 'aurora'), PaywallExperimentConfig.control);
    });

    test('outline reads the onboarding placement from a map or a JSON string', () {
      expect(PaywallExperiment.parse(variant: 'outline').onboardingPaywall, isFalse);
      expect(
          PaywallExperiment.parse(variant: 'outline', payload: {'onboarding_paywall': true}).onboardingPaywall, isTrue);
      expect(PaywallExperiment.parse(variant: 'outline', payload: '{"onboarding_paywall": true}').onboardingPaywall,
          isTrue);
      expect(PaywallExperiment.parse(variant: 'outline', payload: 'not json').variant, PaywallVariant.outline);
    });

    test('trial reads the onboarding placement like outline', () {
      expect(PaywallExperiment.parse(variant: 'trial').variant, PaywallVariant.trial);
      expect(PaywallExperiment.parse(variant: 'trial').onboardingPaywall, isFalse);
      expect(
          PaywallExperiment.parse(variant: 'trial', payload: {'onboarding_paywall': true}).onboardingPaywall, isTrue);
    });

    test('web needs an https URL, otherwise control', () {
      final ok = PaywallExperiment.parse(variant: 'web', payload: {'url': 'https://omi-paywall.vercel.app/'});
      expect(ok.variant, PaywallVariant.web);
      expect(ok.webUrl, Uri.parse('https://omi-paywall.vercel.app/'));
      expect(PaywallExperiment.parse(variant: 'web', payload: {'url': 'http://example.com'}),
          PaywallExperimentConfig.control);
      expect(PaywallExperiment.parse(variant: 'web', payload: {}), PaywallExperimentConfig.control);
      expect(PaywallExperiment.parse(variant: 'web', payload: {'url': 'nope'}), PaywallExperimentConfig.control);
    });
  });

  test('exposure records the flag key and the arm', () {
    final recorded = <String>[];
    final sent = PaywallExperiment.recordExposure(
      const PaywallExperimentConfig(variant: PaywallVariant.outline),
      record: (key, variant) {
        recorded.add('$key=$variant');
        return true;
      },
    );
    expect(sent, isTrue);
    expect(recorded, ['paywall-variant=outline']);
  });

  group('PaywallOffer.fromCatalog', () {
    const catalog = {
      'plans': [
        {'id': 'price_plus_m', 'plan_id': 'plus', 'interval': 'month', 'unit_amount': 1999, 'currency': 'usd'},
        {'id': 'price_u_m', 'plan_id': 'unlimited_v2', 'interval': 'month', 'unit_amount': 2999, 'currency': 'usd'},
        {'id': 'price_u_y', 'plan_id': 'unlimited_v2', 'interval': 'year', 'unit_amount': 26991, 'currency': 'usd'},
      ],
    };

    test('a pending cancellation offers the current price instead of Unlimited', () {
      final offer = PaywallOffer.fromCatalog(
        catalog,
        cancelAtPeriodEnd: true,
        currentPriceId: 'price_plus_m',
      )!;
      expect(offer.resubscribe, isTrue);
      expect(offer.tierId, 'plus');
      expect(offer.monthly!.priceId, 'price_plus_m');
      expect(offer.yearly, isNull);
      expect(
        PaywallOffer.fromCatalog(catalog, cancelAtPeriodEnd: true, currentPriceId: 'missing'),
        isNull,
      );
      // A current price without a plan id never guesses a (retired) tier.
      expect(
        PaywallOffer.fromCatalog({
          'plans': [
            {'id': 'p_m', 'interval': 'month', 'unit_amount': 1999},
          ],
        }, cancelAtPeriodEnd: true, currentPriceId: 'p_m'),
        isNull,
      );
    });

    test('prefers the Unlimited tier and derives the yearly saving from its own prices', () {
      final offer = PaywallOffer.fromCatalog(catalog)!;
      expect(offer.tierId, 'unlimited_v2');
      expect(offer.monthly!.priceId, 'price_u_m');
      expect(offer.yearly!.priceId, 'price_u_y');
      expect(offer.yearly!.perMonthMinor, 2249);
      expect(offer.yearlySavingPercent, 25);
    });

    test('a single-plan Omi Pro catalog renders one complete offer', () {
      // 2026-10-24 ruling: a new buyer on mobile/web sees only unlimited_v2.
      // The paywall must resolve that one tier into both intervals — no empty
      // offer, no fallback to a missing tier.
      final offer = PaywallOffer.fromCatalog({
        'plans': [
          {'id': 'price_pro_m', 'plan_id': 'unlimited_v2', 'interval': 'month', 'unit_amount': 2999, 'currency': 'usd'},
          {'id': 'price_pro_y', 'plan_id': 'unlimited_v2', 'interval': 'year', 'unit_amount': 26991, 'currency': 'usd'},
        ],
      })!;
      expect(offer.tierId, 'unlimited_v2');
      expect(offer.monthly!.priceId, 'price_pro_m');
      expect(offer.yearly!.priceId, 'price_pro_y');
      expect(offer.yearly!.amountMinor, 26991);
      expect(offer.yearlySavingPercent, 25);
    });

    test('never falls back to a retired tier, and an empty catalog', () {
      // Omi Pro is the only plan sold: a catalog of retired tiers (or untagged prices) offers nothing.
      expect(
          PaywallOffer.fromCatalog({
            'plans': [
              {'id': 'p_m', 'interval': 'month', 'unit_amount': 1999},
              {'id': 'neo_m', 'plan_id': 'unlimited', 'interval': 'month', 'unit_amount': 1999},
              {'id': 'arch_m', 'plan_id': 'architect', 'interval': 'month', 'unit_amount': 39999},
            ],
          }),
          isNull);
      expect(PaywallOffer.fromCatalog(null), isNull);
      expect(PaywallOffer.fromCatalog({'plans': []}), isNull);
      expect(
          PaywallOffer.fromCatalog({
            'plans': [
              {'id': 'x', 'interval': 'month'}
            ]
          }),
          isNull);
    });
  });
}
