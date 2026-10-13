import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/storefront_wire.g.dart';

void main() {
  Map<String, dynamic> fixture() =>
      jsonDecode(File('../backend/tests/unit/fixtures/storefront/ladder_v1_free.json').readAsStringSync())
          as Map<String, dynamic>;

  test('generated DTO decodes the backend fixture without client plan rules', () {
    final json = fixture();
    final sheet = GeneratedStorefrontResponse.fromJson(json);
    final tiers = sheet.tiers!;
    expect(sheet.schemaVersion, 1);
    expect(sheet.nextOfferTierId, 'plus:ladder_v1');
    expect(tiers.map((tier) => tier.displayName), ['Free', 'Plus', 'Pro', 'Architect']);
    expect(tiers[1].prices[1].annualSavings!.amountMinor, 3998);
    expect(tiers[1].prices[1].monthlyEquivalent, r'$16.66/mo');
    expect(GeneratedStorefrontResponse.fromJson(sheet.toJson()).toJson(), sheet.toJson());
  });

  test('wire tier identity tolerates a future backend plan and additive fields', () {
    final json = fixture();
    final tiers = json['tiers'] as List<dynamic>;
    final first = tiers.first as Map<String, dynamic>;
    first['plan_id'] = 'future_backend_plan';
    first['future_field'] = true;
    final sheet = GeneratedStorefrontResponse.fromJson(json);
    expect(sheet.tiers!.first.planId, 'future_backend_plan');
  });
}
