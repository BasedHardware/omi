import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';

Map<String, dynamic> fixture() => jsonDecode(File('test/fixtures/plan_storefront.json').readAsStringSync());
void main() {
  test('optional presentation fields preserve backend billing copy and period identity', () {
    final data = PlanStorefront.fromJson(fixture());
    expect(data.current!.formattedPrice, r'$19.99/mo');
    expect(data.current!.renewalLabel, 'Renews Nov 1');
    expect(data.usageContext!.periodId, '2026-10');
    expect(data.usageContext!.budgetNudgeLabel, contains('80%'));
    final json = fixture();
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
      expect(PlanStorefront.fromJson(json).tiers.singleWhere((tier) => tier.recommended).id, entry.value);
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
}
