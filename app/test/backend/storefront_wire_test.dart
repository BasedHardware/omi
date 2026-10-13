import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/storefront_wire.g.dart';

void main() {
  test('storefront v2 golden decodes through the generated client', () {
    final raw = File('../backend/tests/fixtures/storefront_v2/free_settings.json').readAsStringSync();
    final decoded = GeneratedStorefrontResponse.fromJson(jsonDecode(raw) as Map<String, dynamic>);

    expect(decoded.schemaVersion, 2);
    expect(decoded.header, 'Choose your plan');
    expect(decoded.tiers.map((tier) => tier.name), ['Plus', 'Free', 'Pro', 'Architect']);
    expect(decoded.tiers.first.recommended, isTrue);
    expect(decoded.yearlyToggleLabel, 'Yearly · 2 months free');
    final free = decoded.tiers.firstWhere((tier) => tier.name == 'Free');
    expect(free.compact, isTrue);
    expect(free.blockedLine, isNull);
    expect(free.ctaLabel, isNull);

    final roundTrip = GeneratedStorefrontResponse.fromJson(decoded.toJson());
    expect(roundTrip.toJson(), decoded.toJson());
  });
}
