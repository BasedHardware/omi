import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';

Map<String, dynamic> fixture() => jsonDecode(File('test/fixtures/plan_storefront.json').readAsStringSync());
void main() {
  test('unused current message is optional and malformed pro gates fail at parse time', () {
    final json = fixture();
    json['current'].remove('message');
    expect(PlanStorefront.fromJson(json).current!.message, isEmpty);
    for (final gates in [
      [1],
      ['proactive_agent', null],
      [''],
      'proactive_agent'
    ]) {
      json['usage_context']['pro_gates'] = gates;
      expect(() => PlanStorefront.fromJson(json), throwsFormatException);
    }
  });
  test('optional presentation fields preserve backend billing copy and period identity', () {
    final data = PlanStorefront.fromJson(fixture());
    expect(data.current!.formattedPrice, r'$19.99/mo');
    expect(data.current!.renewalLabel, 'Renews Nov 1');
    expect(data.usageContext!.periodId, '2026-10');
    expect(data.usageContext!.budgetNudgeLabel, contains('80%'));
    final json = fixture();
    json['current']['comparison_tier_id'] = 'plus';
    expect(PlanStorefront.fromJson(json).current!.comparisonTierId, 'plus');
    json['current'].remove('formatted_price');
    json['current'].remove('renewal_label');
    json['usage_context'].remove('period_id');
    expect(PlanStorefront.fromJson(json).current!.formattedPrice, isNull);
    expect(PlanStorefront.fromJson(json).usageContext!.periodId, isNull);
  });

  for (final entry in {
    'free_budget': 'plus',
    'free_mcp_cap': 'plus',
    'free_pro_gate': 'operator',
    'plus_budget': 'operator'
  }.entries) {
    test('preserves contextual server recommendation for ${entry.key}', () {
      final json = jsonDecode(File('test/fixtures/plan_storefront_${entry.key}.json').readAsStringSync())
          as Map<String, dynamic>;
      final data = PlanStorefront.fromJson(json);
      expect(data.tiers.singleWhere((tier) => tier.recommended).id, entry.value);
      if (entry.key == 'free_mcp_cap') expect(data.usageContext!.source, 'mcp_daily_cap');
    });
  }
  test('rejects unknown actions, ambiguous intervals and nonboolean legacy flags', () {
    final action = fixture();
    action['tiers'][1]['action'] = 'redirect';
    expect(() => PlanStorefront.fromJson(action), throwsFormatException);
    final duplicate = fixture();
    duplicate['tiers'][1]['prices'].add(duplicate['tiers'][1]['prices'][0]);
    expect(() => PlanStorefront.fromJson(duplicate), throwsFormatException);
    for (final section in ['current', 'usage_context']) {
      for (final flag in ['true', 1, null]) {
        final json = fixture();
        json[section]['legacy'] = flag;
        expect(() => PlanStorefront.fromJson(json), throwsFormatException);
      }
    }
  });
  test('preserves server order, recommendation, exact prices and computed savings', () {
    final data = PlanStorefront.fromJson(fixture());
    expect(data.tiers.map((t) => t.id), ['basic', 'plus', 'operator', 'architect']);
    final pro = data.tiers.singleWhere((t) => t.recommended);
    expect(pro.name, 'Pro');
    expect(pro.priceFor('year')!.id, 'fixture_operator_year');
    expect(pro.priceFor('year')!.annualSavings, 'Save 16.7% compared with monthly');
    expect(data.current!.priceId, 'fixture_plus_month');
    expect(data.usageContext!.showBudgetNudge, isTrue);
  });
  test('unknown tiers retain identity without inferring entitlement', () {
    final json = fixture();
    json['tiers'][0]['id'] = 'future_plan';
    expect(PlanStorefront.fromJson(json).tiers.first.id, 'future_plan');
  });
  test('fails closed for unsupported schemas, malformed prices and duplicates', () {
    final version = fixture()..['schema_version'] = 2;
    expect(() => PlanStorefront.fromJson(version), throwsFormatException);
    final price = fixture();
    price['tiers'][1]['prices'][0]['interval'] = 'week';
    expect(() => PlanStorefront.fromJson(price), throwsFormatException);
    final duplicate = fixture();
    duplicate['tiers'][1]['id'] = 'basic';
    expect(() => PlanStorefront.fromJson(duplicate), throwsFormatException);
    final hidden = fixture()..remove('show_subscription_ui');
    expect(PlanStorefront.fromJson(hidden).showSubscriptionUi, isFalse);
    final missingLegacy = fixture();
    missingLegacy['current'].remove('legacy');
    expect(() => PlanStorefront.fromJson(missingLegacy), throwsFormatException);
  });
  test('Pro gates follow server decisions and never override legacy access', () {
    final json = fixture();
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isTrue);
    expect(PlanStorefront.fromJson(json).shouldGate('future_feature'), isFalse);
    json['current']['legacy'] = true;
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isFalse);
    json['current'] = null;
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isFalse);
    json['show_subscription_ui'] = false;
    expect(PlanStorefront.fromJson(json).shouldGate('proactive_agent'), isFalse);
  });
  test('current legacy alone suppresses the budget nudge', () {
    final json = fixture();
    json['current']['legacy'] = true;
    expect(PlanStorefront.fromJson(json).showBudgetNudge, isFalse);
    json['current'] = null;
    expect(PlanStorefront.fromJson(json).showBudgetNudge, isFalse);
  });
  test('legacy budgets never nudge and 100% belongs to W4', () {
    for (final percent in [0, 79, 100, 120]) {
      final json = fixture();
      json['usage_context']['budget_percent'] = percent;
      expect(PlanStorefront.fromJson(json).usageContext!.showBudgetNudge, isFalse);
    }
    final json = fixture();
    json['usage_context']['legacy'] = true;
    json['current']['legacy'] = true;
    expect(PlanStorefront.fromJson(json).usageContext!.showBudgetNudge, isFalse);
    expect(PlanStorefront.fromJson(json).current!.legacy, isTrue);
  });

  test('storefrontCheckoutDecision allows only upward moves or same-tier annual', () {
    StorefrontPrice priced(String id, String interval) => StorefrontPrice(
        id: id,
        interval: interval,
        amount: 100,
        currency: 'usd',
        formatted: r'$1',
        monthlyEquivalent: r'$1/mo',
        renewalTerms: 'Renews');
    StorefrontTier tier(String id, List<StorefrontPrice> prices) => StorefrontTier(
        id: id,
        name: id,
        description: 'd',
        outcomes: const ['o'],
        recommended: id == 'operator',
        prices: prices,
        action: 'checkout',
        actionLabel: 'Continue');
    StorefrontCurrentPlan current(String id, {String? priceId, bool legacy = false}) =>
        StorefrontCurrentPlan(id: id, name: id, priceId: priceId, legacy: legacy);

    final plusMonth = priced('plus_month', 'month');
    final plusYear = priced('plus_year', 'year');
    final plus = tier('plus', [plusMonth, plusYear]);
    final operatorMonth = priced('operator_month', 'month');
    final operatorYear = priced('operator_year', 'year');
    final operator = tier('operator', [operatorMonth, operatorYear]);
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
        'cancelled different price refuses',
        StorefrontCheckoutDecision.refuse,
        current('plus', priceId: plusMonth.id),
        PlanType.plus,
        operator,
        operatorMonth,
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
}
