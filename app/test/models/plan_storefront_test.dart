import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';

Map<String, dynamic> fixture() => jsonDecode(File('test/fixtures/plan_storefront.json').readAsStringSync());
void main() {
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
