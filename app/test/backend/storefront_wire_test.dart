import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';

/// The request path is [PlanStorefront.fromJson] (schema 2). Schema 1 is not decoded here.
void main() {
  Map<String, dynamic> fixture(String name) =>
      jsonDecode(File('test/fixtures/storefront_v2/$name.json').readAsStringSync()) as Map<String, dynamic>;

  test('request path decodes schema 2 and keeps additive fields from changing the plan', () {
    final json = fixture('settings');
    json['future_field'] = true;
    final first = (json['tiers'] as List).first as Map<String, dynamic>;
    first['plan_id'] = 'future_backend_plan';
    first['tier_id'] = 'future_backend_plan:ladder_v1';
    first['future_field'] = true;
    final sheet = PlanStorefront.fromJson(json);
    expect(sheet.header, 'Choose your plan');
    expect(sheet.tiers.first.planId, 'future_backend_plan');
    expect(sheet.tiers.first.ctaLabel, 'Upgrade to Pro');
  });

  test('schema 1 is rejected by the request path', () {
    final json = fixture('free');
    json['schema_version'] = 1;
    expect(() => PlanStorefront.fromJson(json), throwsFormatException);
  });
}
