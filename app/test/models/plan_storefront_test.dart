import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';

/// Hand-authored from the coordinator copy deck because origin/lane/sub-w5-presentation-v2
/// did not yet contain backend/tests/fixtures/storefront_v2. When that directory exists,
/// the bytes must match.
Map<String, dynamic> fixture([String name = 'settings']) =>
    jsonDecode(File('test/fixtures/storefront_v2/$name.json').readAsStringSync()) as Map<String, dynamic>;

void main() {
  test('schema version 2 parses deck fields and rejects every other version', () {
    final data = PlanStorefront.fromJson(fixture());
    expect(data.catalogRevision, 1);
    expect(data.header, 'Choose your plan');
    expect(data.current!.line, r"You're on Plus · $19.99/mo · renews Nov 1");
    expect(data.current!.legacyNote, isNull);
    expect(data.yearlyToggleLabel, 'Yearly · 2 months free');
    expect(data.tiers.map((tier) => tier.planId), ['operator', 'basic', 'plus', 'architect']);
    final pro = data.tiers.singleWhere((tier) => tier.recommended);
    expect(pro.name, 'Pro');
    expect(pro.hoursLine, 'About 280 hours of recording a month, enough to wear it all day');
    expect(pro.ctaLabel, 'Upgrade to Pro');
    expect(pro.priceFor('month')!.subline, isNull);
    expect(pro.priceFor('year')!.id, 'fixture_operator_year');
    expect(pro.priceFor('year')!.subline, r'$499.90 billed yearly · 2 months free');
    expect(pro.priceFor('year')!.monthsFree, 2);
    expect(pro.priceFor('year')!.renewalLine, 'Renews yearly until you cancel. Cancel anytime in settings.');
    expect(data.usage!.showBudgetNudge, isFalse);
    for (final version in [1, 3, '2', null]) {
      expect(() => PlanStorefront.fromJson(fixture()..['schema_version'] = version), throwsFormatException);
    }
  });

  test('app fixtures match backend goldens byte for byte when that directory exists', () {
    final backend = Directory('../backend/tests/fixtures/storefront_v2');
    if (!backend.existsSync()) return;
    final app = Directory('test/fixtures/storefront_v2');
    Map<String, File> jsonFiles(Directory directory) => {
          for (final entity in directory.listSync().whereType<File>())
            if (entity.path.endsWith('.json')) entity.uri.pathSegments.last: entity
        };
    final backendFiles = jsonFiles(backend);
    final appFiles = jsonFiles(app);
    expect(appFiles.keys.toSet(), backendFiles.keys.toSet());
    for (final name in appFiles.keys) {
      expect(appFiles[name]!.readAsBytesSync(), backendFiles[name]!.readAsBytesSync(), reason: name);
    }
  });

  for (final entry in {
    'free': 'plus',
    'mcp_cap': 'plus',
    'pro_gate_proactive': 'operator',
    'budget_80': 'operator',
  }.entries) {
    test('preserves server recommendation for ${entry.key}', () {
      final data = PlanStorefront.fromJson(fixture(entry.key));
      expect(data.tiers.singleWhere((tier) => tier.recommended).planId, entry.value);
      if (entry.key == 'mcp_cap') {
        expect(data.header, "You've used today's 100 MCP requests");
        expect(data.tiers.every((tier) => tier.bullets.first.contains('MCP')), isTrue);
      }
      if (entry.key == 'pro_gate_proactive') {
        expect(data.tiers.singleWhere((tier) => tier.planId == 'operator').bullets.first,
            "Omi reminds you of things you said you'd do");
      }
    });
  }

  test('screen gate leads the Pro card with the screen bullet', () {
    final pro =
        PlanStorefront.fromJson(fixture('pro_gate_screen')).tiers.singleWhere((tier) => tier.planId == 'operator');
    expect(pro.bullets.first, "On your Mac, Omi can see what you're working on and help with it");
  });

  test('legacy note is required only for a legacy plan', () {
    final legacy = PlanStorefront.fromJson(fixture('legacy'));
    expect(legacy.current!.legacy, isTrue);
    expect(legacy.current!.legacyNote, 'We don\'t sell this plan anymore, but yours stays exactly as it is.');
    expect(legacy.shouldGate('proactive_agent'), isFalse);
    expect(legacy.showBudgetNudge, isFalse);
    final missing = fixture('legacy');
    missing['current']['legacy_note'] = null;
    expect(() => PlanStorefront.fromJson(missing), throwsFormatException);
    final unexpected = fixture();
    unexpected['current']['legacy_note'] = 'nope';
    expect(() => PlanStorefront.fromJson(unexpected), throwsFormatException);
  });

  test('rejects unknown actions, ambiguous intervals and nonboolean flags', () {
    final action = fixture();
    action['tiers'][0]['action'] = 'redirect';
    expect(() => PlanStorefront.fromJson(action), throwsFormatException);
    final duplicate = fixture();
    duplicate['tiers'][0]['prices'].add(duplicate['tiers'][0]['prices'][0]);
    expect(() => PlanStorefront.fromJson(duplicate), throwsFormatException);
    for (final flag in ['true', 1, null]) {
      final json = fixture();
      json['current']['legacy'] = flag;
      expect(() => PlanStorefront.fromJson(json), throwsFormatException);
      final cancel = fixture();
      cancel['current']['cancel_at_period_end'] = flag;
      expect(() => PlanStorefront.fromJson(cancel), throwsFormatException);
    }
  });

  test('fails closed for malformed prices, duplicate plans and a missing visibility flag', () {
    final price = fixture();
    price['tiers'][0]['prices'][0]['interval'] = 'week';
    expect(() => PlanStorefront.fromJson(price), throwsFormatException);
    final duplicate = fixture();
    duplicate['tiers'][1]['plan_id'] = 'operator';
    expect(() => PlanStorefront.fromJson(duplicate), throwsFormatException);
    final hidden = fixture()..remove('show_subscription_ui');
    expect(PlanStorefront.fromJson(hidden).showSubscriptionUi, isFalse);
    final hours = fixture();
    hours['tiers'][0].remove('hours_line');
    expect(() => PlanStorefront.fromJson(hours), throwsFormatException);
  });

  test('malformed pro gates fail at parse time', () {
    for (final gates in [
      [1],
      ['proactive_agent', null],
      [''],
      'proactive_agent'
    ]) {
      final json = fixture();
      json['usage']['pro_gates'] = gates;
      expect(() => PlanStorefront.fromJson(json), throwsFormatException);
    }
  });

  test('a live Pro or Architect plan is not gated by stale pro gates', () {
    final architect = PlanStorefront.fromJson(fixture('architect'));
    expect(architect.usage!.proGates, containsAll(['proactive_agent', 'screen_context']));
    expect(architect.current!.planId, 'architect');
    expect(architect.shouldGate('proactive_agent'), isFalse);
    expect(architect.shouldGate('screen_context'), isFalse);
    final plus = PlanStorefront.fromJson(fixture());
    expect(plus.shouldGate('proactive_agent'), isTrue);
    expect(plus.shouldGate('proactive_agent', livePlan: PlanType.operator), isFalse);
    expect(plus.shouldGate('screen_context', livePlan: PlanType.architect), isFalse);
  });

  test('non-ladder and unknown plans are not gated', () {
    for (final planId in ['unlimited', 'unlimited_v2', 'future_desktop']) {
      final json = fixture();
      json['current']['plan_id'] = planId;
      json['current']['legacy'] = false;
      final data = PlanStorefront.fromJson(json);
      expect(data.usage!.proGates, contains('proactive_agent'));
      expect(data.shouldGate('proactive_agent'), isFalse, reason: planId);
      expect(data.shouldGate('screen_context'), isFalse, reason: planId);
    }
    final plus = PlanStorefront.fromJson(fixture());
    expect(plus.shouldGate('proactive_agent'), isTrue);
    expect(plus.shouldGate('proactive_agent', livePlan: PlanType.unlimited), isFalse);
    expect(plus.shouldGate('proactive_agent', livePlan: PlanType.unlimitedV2), isFalse);
    expect(plus.shouldGate('proactive_agent', livePlan: PlanType.unknown('future_desktop')), isFalse);
    expect(plus.shouldGate('proactive_agent', livePlan: PlanType.plus), isTrue);
  });

  test('Pro gates follow server decisions and never override legacy access', () {
    final json = fixture();
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isTrue);
    expect(PlanStorefront.fromJson(json).shouldGate('future_feature'), isFalse);
    json['current']['legacy'] = true;
    json['current']['legacy_note'] = 'We don\'t sell this plan anymore, but yours stays exactly as it is.';
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isFalse);
    json['current'] = null;
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isFalse);
    json['show_subscription_ui'] = false;
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isFalse);
  });

  test('budget nudge is the 80 percent band and 100 percent belongs to W4', () {
    expect(PlanStorefront.fromJson(fixture('budget_80')).showBudgetNudge, isTrue);
    expect(PlanStorefront.fromJson(fixture('budget_80')).usage!.nudgeLine, contains('80%'));
    expect(PlanStorefront.fromJson(fixture('budget_100')).showBudgetNudge, isFalse);
    for (final percent in [0, 79, 100, 120]) {
      final json = fixture('budget_80');
      json['usage']['percent'] = percent;
      expect(PlanStorefront.fromJson(json).usage!.showBudgetNudge, isFalse);
    }
    final cleared = fixture('budget_80');
    cleared['current'] = null;
    expect(PlanStorefront.fromJson(cleared).showBudgetNudge, isFalse);
  });

  test('storefrontCheckoutDecision allows only upward moves or same-tier annual', () {
    StorefrontPrice priced(String id, String interval) => StorefrontPrice(
        id: id,
        interval: interval,
        amountMinor: 100,
        currency: 'usd',
        headline: r'$1/month',
        renewalLine: 'Renews monthly until you cancel. Cancel anytime in settings.');
    StorefrontTier tier(String id, List<StorefrontPrice> prices) => StorefrontTier(
        tierId: '$id:ladder_v1',
        planId: id,
        name: id,
        hoursLine: 'About 1 hour of recording a month',
        bullets: const ['Included'],
        recommended: id == 'operator',
        isCurrent: false,
        prices: prices,
        action: 'checkout',
        ctaLabel: 'Continue');
    StorefrontCurrentPlan current(String id, {String? priceId, bool legacy = false, String? interval = 'month'}) =>
        StorefrontCurrentPlan(
            planId: id,
            name: id,
            priceId: priceId,
            interval: interval,
            legacy: legacy,
            cancelAtPeriodEnd: false,
            line: 'You\'re on $id',
            legacyNote: legacy ? 'We don\'t sell this plan anymore, but yours stays exactly as it is.' : null);

    final plusMonth = priced('plus_month', 'month');
    final plusYear = priced('plus_year', 'year');
    final plus = tier('plus', [plusMonth, plusYear]);
    final operatorMonth = priced('operator_month', 'month');
    final operator = tier('operator', [operatorMonth, priced('operator_year', 'year')]);
    final architectMonth = priced('architect_month', 'month');
    final architect = tier('architect', [architectMonth, priced('architect_year', 'year')]);
    final basic = tier('basic', [priced('basic_month', 'month')]);

    final cases = <(
      String,
      StorefrontCheckoutDecision,
      StorefrontCurrentPlan?,
      PlanType?,
      StorefrontTier,
      StorefrontPrice,
      bool,
      bool
    )>[
      (
        'plus monthly to annual',
        StorefrontCheckoutDecision.checkout,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        plus,
        plusYear,
        false,
        false
      ),
      (
        'plus annual to monthly',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusYear.id),
        PlanType.plus,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'same-tier annual interval refuses monthly when the yearly price is omitted',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: 'omitted_plus_year', interval: 'year'),
        PlanType.plus,
        tier('plus', [plusMonth]),
        plusMonth,
        false,
        false
      ),
      (
        'annual interval still checks out a higher monthly tier when the yearly price is omitted',
        StorefrontCheckoutDecision.checkout,
        current('plus', priceId: 'omitted_plus_year', interval: 'year'),
        PlanType.plus,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'plus annual to operator monthly',
        StorefrontCheckoutDecision.checkout,
        current('plus', priceId: plusYear.id),
        PlanType.plus,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'operator to architect',
        StorefrontCheckoutDecision.checkout,
        current('operator', priceId: 'operator_month'),
        PlanType.operator,
        architect,
        architectMonth,
        false,
        false
      ),
      (
        'architect to operator',
        StorefrontCheckoutDecision.refuse,
        current('architect', priceId: 'architect_month'),
        PlanType.architect,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'architect payload blocks operator when live plan is plus',
        StorefrontCheckoutDecision.refuse,
        current('architect', priceId: 'architect_month'),
        PlanType.plus,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'live architect blocks operator when payload says plus',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.architect,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'operator to plus',
        StorefrontCheckoutDecision.refuse,
        current('operator', priceId: operatorMonth.id),
        PlanType.operator,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'usage legacy hides checkout',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        operator,
        operatorMonth,
        true,
        false
      ),
      (
        'live unlimited_v2 refuses even when payload legacy is false',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id, legacy: false),
        PlanType.unlimitedV2,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'live unlimited refuses even when payload legacy is false',
        StorefrontCheckoutDecision.refuse,
        current('basic'),
        PlanType.unlimited,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'payload unlimited_v2 refuses when legacy is false',
        StorefrontCheckoutDecision.refuse,
        current('unlimited_v2', priceId: 'legacy', legacy: false),
        PlanType.plus,
        plus,
        plusYear,
        false,
        false
      ),
      (
        'unrecognized current id refuses plus',
        StorefrontCheckoutDecision.refuse,
        current('future_desktop', priceId: 'future'),
        PlanType.basic,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'unrecognized live plan refuses plus',
        StorefrontCheckoutDecision.refuse,
        current('basic'),
        PlanType.unknown('future_desktop'),
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'pro alias is architect and refuses operator',
        StorefrontCheckoutDecision.refuse,
        current('pro', priceId: 'architect_month'),
        PlanType.architect,
        operator,
        operatorMonth,
        false,
        false
      ),
      (
        'same price without cancellation',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'cancelled current price resubscribes',
        StorefrontCheckoutDecision.resubscribe,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        plus,
        plusMonth,
        false,
        true
      ),
      (
        'cancelled higher tier refuses',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        operator,
        operatorMonth,
        false,
        true
      ),
      (
        'cancelled same-tier yearly refuses',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        plus,
        plusYear,
        false,
        true
      ),
      (
        'cancelled lower tier refuses',
        StorefrontCheckoutDecision.refuse,
        current('operator', priceId: operatorMonth.id),
        PlanType.operator,
        plus,
        plusMonth,
        false,
        true
      ),
      (
        'current legacy refuses',
        StorefrontCheckoutDecision.refuse,
        current('unlimited_v2', priceId: 'legacy', legacy: true),
        PlanType.unlimitedV2,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'basic to plus',
        StorefrontCheckoutDecision.checkout,
        current('basic'),
        PlanType.basic,
        plus,
        plusMonth,
        false,
        false
      ),
      (
        'plus to basic',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        basic,
        basic.prices.single,
        false,
        false
      ),
    ];

    expect(PlanStorefront.fromJson(fixture('legacy')).current!.line, r"You're on Unlimited · $29.99/mo · renews Nov 1");

    for (final entry in cases) {
      final (name, expected, held, live, selectedTier, selectedPrice, usageLegacy, cancelScheduled) = entry;
      expect(
        storefrontCheckoutDecision(held, live, selectedTier, selectedPrice,
            usageLegacy: usageLegacy, cancelScheduled: cancelScheduled),
        expected,
        reason: name,
      );
    }
  });

  test('same-tier yearly CTA is the live-price saving and never Get on the current tier', () {
    final settings = PlanStorefront.fromJson(fixture());
    final plus = settings.tiers.singleWhere((tier) => tier.planId == 'plus');
    expect(storefrontYearlySwitchLabel(plus), r'Switch to yearly · save $39.98');
    expect(plus.ctaLabel, storefrontYearlySwitchLabel(plus));
    expect(
      storefrontActionLabel(
        current: settings.current,
        tier: plus,
        price: plus.priceFor('year')!,
        decision: StorefrontCheckoutDecision.checkout,
      ),
      r'Switch to yearly · save $39.98',
    );
    expect(
      storefrontActionLabel(
        current: settings.current,
        tier: plus,
        price: plus.priceFor('month')!,
        decision: StorefrontCheckoutDecision.refuse,
      ),
      isNull,
    );
    final architect =
        PlanStorefront.fromJson(fixture('architect')).tiers.singleWhere((tier) => tier.planId == 'architect');
    expect(architect.ctaLabel, r'Switch to yearly · save $398');
    const eur = StorefrontTier(
      tierId: 'plus:ladder_v1',
      planId: 'plus',
      name: 'Plus',
      hoursLine: 'About 100 hours of recording a month',
      bullets: ['Included'],
      recommended: false,
      isCurrent: true,
      prices: [
        StorefrontPrice(
          id: 'eur_month',
          interval: 'month',
          amountMinor: 1999,
          currency: 'eur',
          headline: '€19.99/month',
          renewalLine: 'Renews monthly until you cancel. Cancel anytime in settings.',
        ),
        StorefrontPrice(
          id: 'eur_year',
          interval: 'year',
          amountMinor: 19990,
          currency: 'eur',
          headline: '€16.66/month',
          renewalLine: 'Renews yearly until you cancel. Cancel anytime in settings.',
        ),
      ],
      action: 'checkout',
      ctaLabel: 'Get Plus',
    );
    expect(storefrontYearlySwitchLabel(eur), 'Switch to yearly · save €39.98');
    final cancelled = PlanStorefront.fromJson(fixture('cancel_scheduled'));
    final currentTier = cancelled.tiers.singleWhere((tier) => tier.isCurrent);
    final pro = cancelled.tiers.singleWhere((tier) => tier.planId == 'operator');
    expect(cancelled.tiers.first.planId, 'plus');
    expect(cancelled.tiers.where((tier) => tier.recommended), isEmpty);
    expect(pro.action, 'none');
    expect(cancelled.header, 'Your Plus plan ends Nov 1');
    expect(cancelled.current!.line, r"You're on Plus · $19.99/mo");
    expect(
      storefrontCheckoutDecision(cancelled.current, PlanType.plus, pro, pro.priceFor('month')!, cancelScheduled: true),
      StorefrontCheckoutDecision.refuse,
    );
    expect(
      storefrontCheckoutDecision(cancelled.current, PlanType.plus, currentTier, currentTier.priceFor('year')!,
          cancelScheduled: true),
      StorefrontCheckoutDecision.refuse,
    );
    expect(
      storefrontActionLabel(
        current: cancelled.current,
        tier: currentTier,
        price: currentTier.priceFor('month')!,
        decision: StorefrontCheckoutDecision.resubscribe,
      ),
      'Resubscribe',
    );
    expect(
      storefrontActionLabel(
        current: cancelled.current,
        tier: pro,
        price: pro.priceFor('month')!,
        decision: StorefrontCheckoutDecision.refuse,
      ),
      isNull,
    );
    expect(
      storefrontActionLabel(
        current: cancelled.current,
        tier: currentTier,
        price: currentTier.priceFor('year')!,
        decision: StorefrontCheckoutDecision.refuse,
      ),
      isNull,
    );
  });
}
