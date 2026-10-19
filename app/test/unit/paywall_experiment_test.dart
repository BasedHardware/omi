import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';

// The paywall A/B gate is fail-closed: anything but a well-formed variant read means the shipped
// PlansSheet. The arm is cached for the session so a reader never flips paywalls mid-session.

void main() {
  setUp(PaywallExperiment.resetForTesting);

  test('flag key is the registered PostHog key', () {
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

  group('resolve', () {
    test('reads the variant then the payload and caches the arm for the session', () async {
      final variantReads = <String>[];
      final payloadReads = <String>[];
      Future<String?> readVariant(String key) async {
        variantReads.add(key);
        return 'outline';
      }

      Future<Object?> readPayload(String key) async {
        payloadReads.add(key);
        return {'onboarding_paywall': true};
      }

      final first =
          await PaywallExperiment.resolve(identity: () => 'u', readVariant: readVariant, readPayload: readPayload);
      expect(first.variant, PaywallVariant.outline);
      expect(first.onboardingPaywall, isTrue);
      final second = await PaywallExperiment.resolve(
        identity: () => 'u',
        readVariant: (_) async => 'web',
        readPayload: (_) async => {'url': 'https://x.example'},
      );
      expect(second, first, reason: 'the session keeps its first arm');
      expect(variantReads, ['paywall-variant']);
      expect(payloadReads, ['paywall-variant']);
    });

    test('control skips the payload read', () async {
      var payloadReads = 0;
      final config = await PaywallExperiment.resolve(
        identity: () => 'u',
        readVariant: (_) async => 'control',
        readPayload: (_) async {
          payloadReads++;
          return null;
        },
      );
      expect(config, PaywallExperimentConfig.control);
      expect(payloadReads, 0);
    });

    test('an unresolved read is control but not cached', () async {
      final unresolved = await PaywallExperiment.resolve(identity: () => 'u', readVariant: (_) async => null);
      expect(unresolved, PaywallExperimentConfig.control);
      final later = await PaywallExperiment.resolve(
        identity: () => 'u',
        readVariant: (_) async => 'outline',
        readPayload: (_) async => null,
      );
      expect(later.variant, PaywallVariant.outline);
    });

    test('a flag read error is control (fail closed)', () async {
      final config = await PaywallExperiment.resolve(
        identity: () => 'u',
        readVariant: (_) => Future.error(StateError('no sdk')),
      );
      expect(config, PaywallExperimentConfig.control);
    });
  });

  group('identity', () {
    test('the held arm belongs to one identity; another identity reads again', () async {
      final a = await PaywallExperiment.resolve(
        identity: () => 'user-a',
        readVariant: (_) async => 'outline',
        readPayload: (_) async => null,
      );
      expect(a.variant, PaywallVariant.outline);
      final b = await PaywallExperiment.resolve(
        identity: () => 'user-b',
        readVariant: (_) async => 'web',
        readPayload: (_) async => {'url': 'https://x.example'},
      );
      expect(b.variant, PaywallVariant.web, reason: 'user-b must not inherit user-a\'s arm');
      var reads = 0;
      final aAgain = await PaywallExperiment.resolve(
        identity: () => 'user-a',
        readVariant: (_) async {
          reads++;
          return 'control';
        },
      );
      expect(aAgain, PaywallExperimentConfig.control);
      expect(reads, 1, reason: 'the hold was replaced by user-b, so user-a reads again');
    });

    test('an account switch while the reads are in flight yields control and holds nothing', () async {
      // Asked once before the reads (user-a) and once after (user-b, the account switched).
      final identities = ['user-a', 'user-b'];
      final switched = await PaywallExperiment.resolve(
        identity: () => identities.length > 1 ? identities.removeAt(0) : identities.first,
        readVariant: (_) async => 'outline',
        readPayload: (_) async => null,
      );
      expect(switched, PaywallExperimentConfig.control);
      var reads = 0;
      await PaywallExperiment.resolve(
        identity: () => 'user-b',
        readVariant: (_) async {
          reads++;
          return 'control';
        },
      );
      expect(reads, 1, reason: 'nothing was held for user-b');
    });

    test('no identity yet means control and no read', () async {
      var reads = 0;
      final config = await PaywallExperiment.resolve(
        identity: () => null,
        readVariant: (_) async {
          reads++;
          return 'outline';
        },
      );
      expect(config, PaywallExperimentConfig.control);
      expect(reads, 0);
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
    });

    test('prefers the Unlimited tier and derives the yearly saving from its own prices', () {
      final offer = PaywallOffer.fromCatalog(catalog)!;
      expect(offer.tierId, 'unlimited_v2');
      expect(offer.monthly!.priceId, 'price_u_m');
      expect(offer.yearly!.priceId, 'price_u_y');
      expect(offer.yearly!.perMonthMinor, 2249);
      expect(offer.yearlySavingPercent, 25);
    });

    test('a single-tier legacy catalog and an empty catalog', () {
      final legacy = PaywallOffer.fromCatalog({
        'plans': [
          {'id': 'p_m', 'interval': 'month', 'unit_amount': 1999},
          {'id': 'p_y', 'interval': 'year', 'unit_amount': 19999},
        ],
      })!;
      expect(legacy.tierId, 'unlimited');
      expect(legacy.monthly!.currency, 'usd');
      expect(legacy.yearlySavingPercent, 17);
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
