import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));
  final catalog = [
    SubscriptionPlan(id: 'unlimited', title: 'Neo'),
    SubscriptionPlan(id: 'operator', title: 'Operator'),
    SubscriptionPlan(id: 'architect', title: 'Architect'),
  ];

  group('planDisplayName', () {
    test('the free plan is always the localized Free Plan', () {
      expect(planDisplayName(PlanType.basic, catalog, l10n), l10n.basicPlan);
    });

    test('uses the backend title for the tier', () {
      expect(planDisplayName(PlanType.unlimited, catalog, l10n), 'Neo');
      expect(planDisplayName(PlanType.operator, catalog, l10n), 'Operator');
      // The legacy `pro` id is canonicalized to Architect.
      expect(planDisplayName(PlanType.fromWire('pro'), catalog, l10n), 'Architect');
    });

    test('falls back to the known product name when the backend does not list the tier', () {
      expect(planDisplayName(PlanType.plus, const [], l10n), 'Plus');
      expect(planDisplayName(PlanType.operator, const [], l10n), 'Operator');
      expect(planDisplayName(PlanType.unlimitedV2, const [], l10n), l10n.unlimitedPlan);
    });

    test('an unknown future plan shows its id readably, never "Free Plan"', () {
      expect(planDisplayName(PlanType.fromWire('team_max'), const [], l10n), 'Team Max');
      expect(planDisplayName(PlanType.fromWire('team_max'), [SubscriptionPlan(id: 'team_max', title: 'Team')], l10n),
          'Team');
    });

    test('a blank backend title is ignored', () {
      expect(planTitleForTier('plus', [SubscriptionPlan(id: 'plus', title: '  ')]), isNull);
      expect(planDisplayName(PlanType.plus, [SubscriptionPlan(id: 'plus', title: '')], l10n), 'Plus');
    });
  });
}
