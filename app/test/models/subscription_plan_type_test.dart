import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/subscription.dart';

Subscription _subFromWirePlan(String plan) {
  return Subscription.fromJson({
    'plan': plan,
    'status': 'active',
    'features': <String>[],
    'cancel_at_period_end': false,
    'deprecated': false,
    'limits': <String, dynamic>{},
  });
}

void main() {
  group('PlanType wire mapping', () {
    test('decodes the mobile consumer tiers instead of falling back to basic', () {
      // Regression: before the enum carried plus/unlimited_v2, an unknown plan
      // fell back to PlanType.basic — a paying subscriber was shown as free.
      expect(_subFromWirePlan('plus').plan, PlanType.plus);
      expect(_subFromWirePlan('unlimited_v2').plan, PlanType.unlimitedV2);
    });

    test('decodes the existing tiers', () {
      expect(_subFromWirePlan('basic').plan, PlanType.basic);
      expect(_subFromWirePlan('unlimited').plan, PlanType.unlimited);
      expect(_subFromWirePlan('operator').plan, PlanType.operator);
      expect(_subFromWirePlan('architect').plan, PlanType.architect);
    });

    test('still falls back to basic for a genuinely unknown plan', () {
      expect(_subFromWirePlan('some_future_tier').plan, PlanType.basic);
    });

    test('serializes back to the backend plan id, not the Dart enum name', () {
      // PlanType.unlimitedV2.name is 'unlimitedV2'; the backend expects 'unlimited_v2'.
      expect(PlanType.unlimitedV2.wireName, 'unlimited_v2');
      expect(PlanType.plus.wireName, 'plus');
      for (final plan in PlanType.values) {
        expect(_subFromWirePlan(plan.wireName).plan, plan);
      }
    });
  });

  group('PlanType semantics', () {
    test('every non-basic tier is paid', () {
      expect(PlanType.basic.isPaid, isFalse);
      for (final plan in PlanType.values.where((p) => p != PlanType.basic)) {
        expect(plan.isPaid, isTrue, reason: '${plan.name} should be paid');
      }
    });

    test('plus is paid but metered, so it is not unlimited transcription', () {
      expect(PlanType.plus.isPaid, isTrue);
      expect(PlanType.plus.hasUnlimitedTranscription, isFalse);
    });

    test('unlimited tiers have no transcription cap', () {
      expect(PlanType.unlimitedV2.hasUnlimitedTranscription, isTrue);
      expect(PlanType.unlimited.hasUnlimitedTranscription, isTrue);
      expect(PlanType.operator.hasUnlimitedTranscription, isTrue);
      expect(PlanType.architect.hasUnlimitedTranscription, isTrue);
      expect(PlanType.basic.hasUnlimitedTranscription, isFalse);
    });

    test('only operator and architect grant desktop (mirrors backend)', () {
      expect(PlanType.operator.grantsDesktop, isTrue);
      expect(PlanType.architect.grantsDesktop, isTrue);
      for (final plan in [PlanType.basic, PlanType.unlimited, PlanType.plus, PlanType.unlimitedV2]) {
        expect(plan.grantsDesktop, isFalse, reason: '${plan.name} must not grant desktop');
      }
    });
  });
}
