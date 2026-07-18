import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/plan_pricing.dart';

List<Map<String, dynamic>> _tier({num? monthly, num? yearly}) {
  return [
    if (monthly != null) {'interval': 'month', 'unit_amount': monthly},
    if (yearly != null) {'interval': 'year', 'unit_amount': yearly},
  ];
}

void main() {
  group('annualSaveTag', () {
    test('Plus and Unlimited save 3 months, not the hardcoded 2', () {
      // Regression: the badge was hardcoded to '2 Months Free', which was only
      // ever right for legacy Neo. Plus ($17.99/mo, $161.91/yr) and Unlimited
      // ($29.99/mo, $269.91/yr) both bill 9 months for a year.
      expect(annualSaveTag(_tier(monthly: 1799, yearly: 16191)), '3 Months Free');
      expect(annualSaveTag(_tier(monthly: 2999, yearly: 26991)), '3 Months Free');
    });

    test('legacy Neo still shows 2 months', () {
      expect(annualSaveTag(_tier(monthly: 1999, yearly: 19999)), '2 Months Free');
    });

    test('singular month is not pluralized', () {
      expect(annualSaveTag(_tier(monthly: 1000, yearly: 11000)), '1 Month Free');
    });

    test('returns null when the annual plan is not cheaper', () {
      expect(annualSaveTag(_tier(monthly: 1000, yearly: 12000)), isNull);
      expect(annualSaveTag(_tier(monthly: 1000, yearly: 13000)), isNull);
    });

    test('returns null when a price is missing or unusable', () {
      expect(annualSaveTag(_tier(monthly: 1799)), isNull);
      expect(annualSaveTag(_tier(yearly: 16191)), isNull);
      expect(annualSaveTag(const []), isNull);
      expect(annualSaveTag(_tier(monthly: 0, yearly: 16191)), isNull);
    });
  });
}
