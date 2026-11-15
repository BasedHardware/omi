import 'package:flutter/widgets.dart';

import 'package:collection/collection.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Canonical product name for known IDs; backend title for a future tier.
String? planTitleForTier(String tierId, List<SubscriptionPlan> availablePlans) {
  const names = {
    'basic': 'Free',
    'plus': 'Plus',
    'operator': 'Operator',
    'architect': 'Architect',
    'pro': 'Architect',
    'unlimited': 'Neo',
    'unlimited_v2': 'Omi Pro'
  };
  final knownName = names[tierId];
  if (knownName != null) return knownName;
  final title = availablePlans.firstWhereOrNull((plan) => plan.id == tierId)?.title.trim();
  return (title == null || title.isEmpty) ? null : title;
}

/// Canonical product names for known IDs, even when a cached catalog has an old title.
/// Future plans may use their server title. Product names are not translated.
String planDisplayName(PlanType plan, List<SubscriptionPlan> availablePlans, AppLocalizations l10n) {
  if (plan == PlanType.basic) return l10n.free;
  final fromBackend = planTitleForTier(plan.wireName, availablePlans);
  if (fromBackend != null) return fromBackend;
  // A plan this client does not know yet: show its id readably rather than calling it Free.
  return plan.wireName
      .split(RegExp(r'[_\s-]+'))
      .where((word) => word.isNotEmpty)
      .map((word) => word[0].toUpperCase() + word.substring(1))
      .join(' ');
}

/// [planDisplayName] for the signed-in user's current subscription; "Free Plan" when there is
/// none yet.
String currentPlanDisplayName(BuildContext context, UserSubscriptionResponse? response) {
  if (response == null) return context.l10n.basicPlan;
  return planDisplayName(response.subscription.plan, response.availablePlans, context.l10n);
}
