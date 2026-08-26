import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/plan_pricing.dart';

List<Map<String, dynamic>> _tier({num? monthly, num? yearly}) {
  return [
    if (monthly != null) {'interval': 'month', 'unit_amount': monthly},
    if (yearly != null) {'interval': 'year', 'unit_amount': yearly},
  ];
}

void main() {
  // Returns a count rather than a label: the English 'N Months Free' string it
  // used to build could not be translated. The rendered badge is covered in
  // test/unit/plans_sheet_l10n_test.dart.
  group('annualMonthsFree', () {
    test('Plus and Unlimited save 3 months, not the hardcoded 2', () {
      // Regression: the badge was hardcoded to '2 Months Free', which was only
      // ever right for legacy Neo. Plus ($17.99/mo, $161.91/yr) and Unlimited
      // ($29.99/mo, $269.91/yr) both bill 9 months for a year.
      expect(annualMonthsFree(_tier(monthly: 1799, yearly: 16191)), 3);
      expect(annualMonthsFree(_tier(monthly: 2999, yearly: 26991)), 3);
    });

    test('legacy Neo still shows 2 months', () {
      expect(annualMonthsFree(_tier(monthly: 1999, yearly: 19999)), 2);
    });

    test('a single free month is still reported', () {
      expect(annualMonthsFree(_tier(monthly: 1000, yearly: 11000)), 1);
    });

    test('returns null when the annual plan is not cheaper', () {
      expect(annualMonthsFree(_tier(monthly: 1000, yearly: 12000)), isNull);
      expect(annualMonthsFree(_tier(monthly: 1000, yearly: 13000)), isNull);
    });

    test('returns null when a price is missing or unusable', () {
      expect(annualMonthsFree(_tier(monthly: 1799)), isNull);
      expect(annualMonthsFree(_tier(yearly: 16191)), isNull);
      expect(annualMonthsFree(const []), isNull);
      expect(annualMonthsFree(_tier(monthly: 0, yearly: 16191)), isNull);
    });
  });

  group('annualDiscountPercent', () {
    test('Plus and Unlimited discount 25%, not the hardcoded 17%', () {
      // Regression: the yearly-toggle badge was a hardcoded "Save ~17%" string
      // in all 49 locales. 17% is the legacy Neo discount; 3 months free is 25%.
      expect(annualDiscountPercent(_tier(monthly: 1799, yearly: 16191)), 25);
      expect(annualDiscountPercent(_tier(monthly: 2999, yearly: 26991)), 25);
    });

    test('legacy Neo still discounts ~17%', () {
      expect(annualDiscountPercent(_tier(monthly: 1999, yearly: 19999)), 17);
    });

    test('returns null when annual is not cheaper or prices are unusable', () {
      expect(annualDiscountPercent(_tier(monthly: 1000, yearly: 12000)), isNull);
      expect(annualDiscountPercent(_tier(monthly: 1000, yearly: 13000)), isNull);
      expect(annualDiscountPercent(_tier(monthly: 1799)), isNull);
      expect(annualDiscountPercent(const []), isNull);
    });
  });

  group('bestAnnualDiscountPercent', () {
    test('advertises the best discount across the shown tiers', () {
      final neo = _tier(monthly: 1999, yearly: 19999); // 17%
      final plus = _tier(monthly: 1799, yearly: 16191); // 25%
      expect(bestAnnualDiscountPercent([neo, plus]), 25);
      expect(bestAnnualDiscountPercent([neo]), 17);
    });

    test('ignores tiers with unusable prices', () {
      final broken = _tier(monthly: 1799);
      final plus = _tier(monthly: 1799, yearly: 16191);
      expect(bestAnnualDiscountPercent([broken, plus]), 25);
    });

    test('returns null when no tier has a usable discount', () {
      expect(bestAnnualDiscountPercent([_tier(monthly: 1799), const []]), isNull);
      expect(bestAnnualDiscountPercent(const []), isNull);
    });
  });

  group('shouldShowPlanContinueButton', () {
    test('hides when plans are loading, cancelled, or a change is already scheduled', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: false,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: false,
        ),
        isFalse,
      );
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: false,
          hasScheduledUpgrade: false,
          isCancelled: true,
          plansLoaded: true,
        ),
        isFalse,
      );
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: false,
          hasScheduledUpgrade: true,
          isCancelled: false,
          plansLoaded: true,
        ),
        isFalse,
      );
    });

    test('shows for monthly users, including same-tier monthly→annual', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: false,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
          selectedTierId: 'plus',
          currentTierId: 'plus',
        ),
        isTrue,
      );
    });

    test('hides for annual users already on the selected tier', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: true,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
          selectedTierId: 'plus',
          currentTierId: 'plus',
        ),
        isFalse,
      );
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: true,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
        ),
        isFalse,
      );
    });

    test('shows for annual Plus selecting Unlimited — do not restore !isOnAnnualPlan', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: true,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
          selectedTierId: 'unlimited_v2',
          currentTierId: 'plus',
        ),
        isTrue,
      );
    });

    test('hides desktop-plan Continue onto a mobile tier (manage-only)', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: false,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
          selectedTierId: 'plus',
          currentTierId: 'architect',
          currentGrantsDesktop: true,
        ),
        isFalse,
      );
    });

    test('still shows monthly→annual Continue on a desktop plan', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: false,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
          selectedTierId: 'architect',
          currentTierId: 'architect',
          currentGrantsDesktop: true,
        ),
        isTrue,
      );
    });

    test('hides same-tier annual Continue on a desktop plan', () {
      expect(
        shouldShowPlanContinueButton(
          isOnAnnualPlan: true,
          hasScheduledUpgrade: false,
          isCancelled: false,
          plansLoaded: true,
          selectedTierId: 'architect',
          currentTierId: 'architect',
          currentGrantsDesktop: true,
        ),
        isFalse,
      );
    });
  });
}
