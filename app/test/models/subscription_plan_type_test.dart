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
    test('decodes every catalog identity and the legacy pro alias', () {
      const expected = {
        'basic': PlanType.basic,
        'plus': PlanType.plus,
        'unlimited': PlanType.unlimited,
        'unlimited_v2': PlanType.unlimitedV2,
        'operator': PlanType.operator,
        'architect': PlanType.architect,
        'pro': PlanType.architect,
      };

      for (final entry in expected.entries) {
        final subscription = _subFromWirePlan(entry.key);
        expect(subscription.plan, entry.value, reason: '${entry.key} should decode to its catalog identity');
        final expectedWireName = entry.key == 'pro' ? 'architect' : entry.key;
        expect(
          subscription.toJson()['plan'],
          expectedWireName,
          reason: '${entry.key} should encode to its canonical catalog identity',
        );
      }

      final legacyPro = _subFromWirePlan('pro').plan;
      expect(legacyPro.isUnknown, isFalse);
      expect(legacyPro.wireName, 'architect');
    });

    test('preserves a future plan identity instead of falling back to basic', () {
      final subscription = _subFromWirePlan('future_plan_123');

      expect(subscription.plan, isNot(PlanType.basic));
      expect(subscription.plan.isUnknown, isTrue);
      expect(subscription.plan.name, 'future_plan_123');
      expect(subscription.plan.wireName, 'future_plan_123');
      expect(subscription.toJson()['plan'], 'future_plan_123');
    });

    test('serializes back to the backend plan id, not the Dart enum name', () {
      // PlanType.unlimitedV2.name is 'unlimitedV2'; the backend expects 'unlimited_v2'.
      expect(PlanType.unlimitedV2.wireName, 'unlimited_v2');
      expect(PlanType.plus.wireName, 'plus');
      for (final plan in PlanType.values) {
        expect(_subFromWirePlan(plan.wireName).plan, plan);
      }

      final future = _subFromWirePlan('future_plan_123');
      expect(future.toGenerated().plan, 'future_plan_123');
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

    test('unknown plans grant no paid capability by assumption', () {
      final unknown = PlanType.fromWire('future_plan_123');

      expect(unknown.isUnknown, isTrue);
      expect(unknown.isPaid, isFalse);
      expect(unknown.hasUnlimitedTranscription, isFalse);
      expect(unknown.grantsDesktop, isFalse);
    });
  });
}
