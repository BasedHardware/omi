import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';

/// Copies of origin/lane/sub-w5-presentation-v2 backend/tests/fixtures/storefront_v2.
/// When that directory exists in this checkout, the bytes must match.
Map<String, dynamic> fixture([String name = 'plus_monthly_yearly_toggle']) =>
    jsonDecode(File('test/fixtures/storefront_v2/$name.json').readAsStringSync()) as Map<String, dynamic>;

void main() {
  test('schema version 2 parses deck fields and rejects every other version', () {
    final data = PlanStorefront.fromJson(fixture());
    expect(data.catalogRevision, 12);
    expect(data.header, 'Choose your plan');
    expect(data.current!.line, r"You're on Plus · $19.99/mo · renews Nov 1");
    expect(data.current!.legacyNote, isNull);
    expect(data.yearlyToggleLabel, 'Yearly · 2 months free');
    expect(data.tiers.map((tier) => tier.planId), ['operator', 'plus', 'architect']);
    final pro = data.tiers.singleWhere((tier) => tier.recommended);
    expect(pro.name, 'Pro');
    expect(pro.hoursLine, 'About 280 hours of recording a month, enough to wear it all day');
    expect(pro.ctaLabel, 'Upgrade to Pro');
    expect(pro.priceFor('month')!.subline, isNull);
    expect(pro.priceFor('year')!.id, 'price_operator_year');
    expect(pro.priceFor('year')!.subline, r'$499.90 billed yearly · 2 months free');
    expect(pro.priceFor('year')!.monthsFree, 2);
    expect(pro.priceFor('year')!.renewalLine, 'Renews yearly until you cancel. Cancel anytime in settings.');
    final plus = data.tiers.singleWhere((tier) => tier.isCurrent);
    expect(plus.planId, 'plus');
    expect(plus.action, 'checkout');
    expect(plus.ctaLabel, isNull);
    expect(plus.bullets, isEmpty);
    expect(plus.prices.map((price) => price.interval), ['year']);
    expect(plus.priceFor('year')!.headline, r'$19.99/month');
    expect(plus.priceFor('year')!.subline, r'$199.90 billed yearly · 2 months free');
    expect(plus.priceFor('year')!.ctaLabel, r'Switch to yearly · save $39.98');
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
    'free_settings': 'plus',
    'free_mcp_cap': 'plus',
    'free_pro_gate_proactive': 'operator',
    'plus_budget80': 'operator',
    'pro_budget_cap': 'architect',
  }.entries) {
    test('preserves server recommendation for ${entry.key}', () {
      final data = PlanStorefront.fromJson(fixture(entry.key));
      expect(data.tiers.singleWhere((tier) => tier.recommended).planId, entry.value);
      if (entry.key == 'free_mcp_cap') {
        expect(data.header, "You've used today's 100 MCP requests");
        expect(data.tiers.singleWhere((tier) => tier.isCurrent).bullets, isEmpty);
        expect(data.tiers.where((tier) => tier.bullets.isNotEmpty).every((tier) => tier.bullets.first.contains('MCP')),
            isTrue);
      }
      if (entry.key == 'free_pro_gate_proactive') {
        expect(data.tiers.singleWhere((tier) => tier.planId == 'operator').bullets.first,
            "Omi reminds you of things you said you'd do");
      }
    });
  }

  test('screen gate leads the Pro card with the screen bullet', () {
    final pro =
        PlanStorefront.fromJson(fixture('free_pro_gate_screen')).tiers.singleWhere((tier) => tier.planId == 'operator');
    expect(pro.bullets.first, "On your Mac, Omi can see what you're working on and help with it");
  });

  test('legacy note is required only for a legacy plan', () {
    for (final name in ['legacy_unlimited', 'legacy_neo']) {
      final legacy = PlanStorefront.fromJson(fixture(name));
      expect(legacy.current!.legacy, isTrue, reason: name);
      expect(legacy.current!.legacyNote, 'We don\'t sell this plan anymore, but yours stays exactly as it is.',
          reason: name);
      expect(legacy.shouldGate('proactive_agent'), isFalse, reason: name);
      expect(legacy.showBudgetNudge, isFalse, reason: name);
      final pro = legacy.tiers.singleWhere((tier) => tier.planId == 'operator');
      expect(
        storefrontCheckoutDecision(
            legacy.current, PlanType.fromWire(legacy.current!.planId), pro, pro.priceFor('month')!),
        StorefrontCheckoutDecision.refuse,
        reason: name,
      );
    }
    expect(PlanStorefront.fromJson(fixture('legacy_unlimited')).current!.line,
        r"You're on Unlimited · $29.99/mo · renews Nov 1");
    expect(PlanStorefront.fromJson(fixture('legacy_neo')).current!.line, r"You're on Neo · $19.99/mo · renews Nov 1");
    expect(PlanStorefront.fromJson(fixture('legacy_neo')).current!.planId, 'unlimited');
    final missing = fixture('legacy_unlimited');
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
    final architect = PlanStorefront.fromJson(fixture('architect_settings'));
    expect(architect.usage!.proGates, containsAll(['proactive_agent', 'screen_context']));
    expect(architect.current!.planId, 'architect');
    expect(architect.shouldGate('proactive_agent'), isFalse);
    expect(architect.shouldGate('screen_context'), isFalse);
    final plus = PlanStorefront.fromJson(fixture());
    expect(plus.shouldGate('proactive_agent'), isTrue);
    expect(plus.shouldGate('proactive_agent', livePlan: PlanType.operator), isFalse);
    expect(plus.shouldGate('screen_context', livePlan: PlanType.architect), isFalse);
  });

  test('Omi Pro, legacy Neo and unknown plans are not gated', () {
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
    expect(PlanStorefront.fromJson(fixture('plus_budget80')).showBudgetNudge, isTrue);
    expect(PlanStorefront.fromJson(fixture('plus_budget80')).usage!.nudgeLine, contains('80%'));
    final full = fixture('plus_budget80');
    full['usage']['percent'] = 100;
    expect(PlanStorefront.fromJson(full).showBudgetNudge, isFalse);
    for (final percent in [0, 79, 100, 120]) {
      final json = fixture('plus_budget80');
      json['usage']['percent'] = percent;
      expect(PlanStorefront.fromJson(json).usage!.showBudgetNudge, isFalse);
    }
    final cleared = fixture('plus_budget80');
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
    final plusMonthOther = priced('plus_month_other', 'month');
    final plusYear = priced('plus_year', 'year');
    final plus = tier('plus', [plusMonth, plusYear]);
    final plusYearOnly = tier('plus', [plusYear]);
    final plusTwoMonths = tier('plus', [plusMonth, plusMonthOther]);
    final operatorMonth = priced('operator_month', 'month');
    final operator = tier('operator', [operatorMonth, priced('operator_year', 'year')]);
    final architectMonth = priced('architect_month', 'month');
    final architect = tier('architect', [architectMonth, priced('architect_year', 'year')]);
    final basic = tier('basic', [priced('basic_month', 'month')]);
    final omiProMonth = priced('omi_pro_month', 'month');
    final omiProYear = priced('omi_pro_year', 'year');
    final omiPro = tier('unlimited_v2', [omiProMonth, omiProYear]);

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
      for (final plan in [PlanType.basic, PlanType.plus, PlanType.operator, PlanType.architect, PlanType.unlimited])
        (
          '${plan.wireName} may move to Omi Pro',
          StorefrontCheckoutDecision.checkout,
          current(plan.wireName, priceId: '${plan.wireName}_month'),
          plan,
          omiPro,
          omiProMonth,
          false,
          false
        ),
      (
        'Omi Pro monthly to annual',
        StorefrontCheckoutDecision.checkout,
        current('unlimited_v2', priceId: omiProMonth.id),
        PlanType.unlimitedV2,
        omiPro,
        omiProYear,
        false,
        false
      ),
      (
        'Omi Pro never moves down to a retired tier',
        StorefrontCheckoutDecision.refuse,
        current('unlimited_v2', priceId: omiProMonth.id),
        PlanType.unlimitedV2,
        architect,
        architectMonth,
        false,
        false
      ),
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
      (
        'monthly current checks out the only yearly price',
        StorefrontCheckoutDecision.checkout,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        plusYearOnly,
        plusYear,
        false,
        false
      ),
      (
        'same-tier other monthly price refuses',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        plusTwoMonths,
        plusMonthOther,
        false,
        false
      ),
      (
        'same-tier other yearly price refuses when already yearly',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: 'other_year', interval: 'year'),
        PlanType.plus,
        plusYearOnly,
        plusYear,
        false,
        false
      ),
    ];

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

  test('price cta_label is rendered verbatim and a refused decision draws no button', () {
    final settings = PlanStorefront.fromJson(fixture());
    final plus = settings.tiers.singleWhere((tier) => tier.planId == 'plus');
    expect(plus.ctaLabel, isNull);
    expect(plus.compact, isFalse);
    expect(plus.priceFor('year')!.ctaLabel, r'Switch to yearly · save $39.98');
    expect(
      storefrontCheckoutDecision(settings.current, PlanType.plus, plus, plus.priceFor('year')!),
      StorefrontCheckoutDecision.checkout,
    );
    expect(
      storefrontActionLabel(
        tier: plus,
        price: plus.priceFor('year')!,
        decision: StorefrontCheckoutDecision.checkout,
      ),
      r'Switch to yearly · save $39.98',
    );
    expect(plus.priceFor('month'), isNull);
    expect(
      storefrontActionLabel(
        tier: plus,
        price: plus.priceFor('year')!,
        decision: StorefrontCheckoutDecision.refuse,
      ),
      isNull,
    );
    final architect =
        PlanStorefront.fromJson(fixture('architect_settings')).tiers.singleWhere((tier) => tier.planId == 'architect');
    expect(architect.priceFor('year')!.headline, r'$199/month');
    expect(architect.priceFor('year')!.ctaLabel, r'Switch to yearly · save $398');
    expect(architect.ctaLabel, isNull);
    final free = PlanStorefront.fromJson(fixture('free_settings'));
    final basic = free.tiers.singleWhere((tier) => tier.planId == 'basic');
    expect(basic.compact, isTrue);
    expect(basic.priceFor('month')!.headline, r'$0');
    expect(basic.priceFor('month')!.id, isNull);
    expect(basic.priceFor('month')!.renewalLine, isNull);
    expect(
      storefrontCheckoutDecision(free.current, PlanType.basic, basic, basic.priceFor('month')!),
      StorefrontCheckoutDecision.refuse,
    );
    final unlimited =
        PlanStorefront.fromJson(fixture('legacy_unlimited')).tiers.singleWhere((tier) => tier.planId == 'unlimited_v2');
    expect(unlimited.hoursLine, isEmpty);
    expect(unlimited.compact, isTrue);
    expect(unlimited.bullets, isEmpty);
    final neo = PlanStorefront.fromJson(fixture('legacy_neo')).tiers.singleWhere((tier) => tier.planId == 'unlimited');
    expect(neo.hoursLine, isEmpty);
    expect(neo.compact, isTrue);
    expect(neo.bullets, isEmpty);
    final cleared = fixture();
    cleared['tiers'] = null;
    expect(PlanStorefront.fromJson(cleared).tiers, isEmpty);
    final cancelled = PlanStorefront.fromJson(fixture('cancel_scheduled_plus'));
    final currentTier = cancelled.tiers.singleWhere((tier) => tier.isCurrent);
    final pro = cancelled.tiers.singleWhere((tier) => tier.planId == 'operator');
    expect(cancelled.tiers.first.planId, 'plus');
    expect(cancelled.tiers.where((tier) => tier.recommended), isEmpty);
    expect(pro.action, 'none');
    expect(pro.blockedLine, 'Resubscribe first to change plans');
    expect(currentTier.blockedLine, isNull);
    expect(currentTier.compact, isFalse);
    expect(currentTier.bullets, isEmpty);
    expect(currentTier.prices, hasLength(1));
    expect(currentTier.priceFor('year'), isNull);
    expect(currentTier.priceFor('month')!.id, cancelled.current!.priceId);
    expect(cancelled.yearlyToggleLabel, isNull);
    expect(cancelled.header, 'Your Plus plan ends Nov 1');
    expect(cancelled.current!.line, r"You're on Plus · $19.99/mo");
    final cancelledFree = cancelled.tiers.singleWhere((tier) => tier.planId == 'basic');
    expect(cancelled.tiers.map((tier) => tier.planId), ['plus', 'basic', 'operator', 'architect']);
    expect(cancelledFree.action, 'none');
    expect(cancelledFree.compact, isTrue);
    expect(cancelledFree.bullets, isEmpty);
    expect(cancelledFree.ctaLabel, isNull);
    expect(cancelledFree.blockedLine, 'Resubscribe first to change plans');
    expect(cancelledFree.priceFor('month')!.headline, r'$0');
    final cancelledPro = PlanStorefront.fromJson(fixture('cancel_scheduled_pro'));
    expect(cancelledPro.tiers.map((tier) => tier.planId), ['operator', 'basic', 'plus', 'architect']);
    expect(cancelledPro.tiers.where((tier) => tier.recommended), isEmpty);
    expect(cancelledPro.tiers.singleWhere((tier) => tier.isCurrent).ctaLabel, 'Resubscribe');
    for (final planId in ['basic', 'plus', 'architect']) {
      final tier = cancelledPro.tiers.singleWhere((item) => item.planId == planId);
      expect(tier.action, 'none', reason: planId);
      expect(tier.blockedLine, 'Resubscribe first to change plans', reason: planId);
      expect(tier.ctaLabel, isNull, reason: planId);
    }
    final cap = PlanStorefront.fromJson(fixture('pro_budget_cap'));
    final capArchitect = cap.tiers.singleWhere((tier) => tier.recommended);
    expect(capArchitect.planId, 'architect');
    expect(capArchitect.action, 'checkout');
    expect(capArchitect.ctaLabel, 'Upgrade to Architect');
    expect(cap.tiers.map((tier) => tier.planId), ['architect', 'plus', 'operator']);
    expect(PlanStorefront.fromJson(fixture('pro_settings')).tiers.map((tier) => tier.planId), ['plus', 'operator']);
    expect(
      storefrontCheckoutDecision(cancelled.current, PlanType.plus, pro, pro.priceFor('month')!, cancelScheduled: true),
      StorefrontCheckoutDecision.refuse,
    );
    expect(
      storefrontCheckoutDecision(cancelled.current, PlanType.plus, pro, pro.priceFor('year')!, cancelScheduled: true),
      StorefrontCheckoutDecision.refuse,
    );
    expect(
      storefrontActionLabel(
        tier: currentTier,
        price: currentTier.priceFor('month')!,
        decision: StorefrontCheckoutDecision.resubscribe,
      ),
      'Resubscribe',
    );
    expect(
      storefrontActionLabel(
        tier: pro,
        price: pro.priceFor('month')!,
        decision: StorefrontCheckoutDecision.refuse,
      ),
      isNull,
    );
    expect(currentTier.priceFor('year'), isNull);
  });

  test('every current card publishes no bullets', () {
    final names = Directory('test/fixtures/storefront_v2')
        .listSync()
        .whereType<File>()
        .where((file) => file.path.endsWith('.json'))
        .map((file) => file.uri.pathSegments.last.replaceFirst('.json', ''));
    expect(names, hasLength(17));
    for (final name in names) {
      final data = PlanStorefront.fromJson(fixture(name));
      expect(data.tiers.where((tier) => tier.isCurrent), isNotEmpty, reason: name);
      expect(data.tiers.where((tier) => tier.isCurrent).every((tier) => tier.bullets.isEmpty), isTrue, reason: name);
    }
  });
}
