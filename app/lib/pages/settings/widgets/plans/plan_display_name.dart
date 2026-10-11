import 'package:flutter/widgets.dart';

import 'package:collection/collection.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The backend's display title for a plan tier ([tierId] is the wire `plan_id`, e.g. `operator`),
/// or null when the subscription response does not list that tier.
String? planTitleForTier(String tierId, List<SubscriptionPlan> availablePlans) {
  final title = availablePlans.firstWhereOrNull((plan) => plan.id == tierId)?.title.trim();
  return (title == null || title.isEmpty) ? null : title;
}

/// The name to show for [plan]: the backend's title for that tier when the subscription response
/// lists it, otherwise the product name this client knows ("Plus", "Operator", …). The free plan
/// is always the localized "Free Plan"; product names are not translated.
String planDisplayName(PlanType plan, List<SubscriptionPlan> availablePlans, AppLocalizations l10n) {
  if (plan == PlanType.basic) return l10n.basicPlan;
  final fromBackend = planTitleForTier(plan.wireName, availablePlans);
  if (fromBackend != null) return fromBackend;
  if (plan == PlanType.plus) return 'Plus';
  if (plan == PlanType.operator) return 'Operator';
  if (plan == PlanType.architect) return 'Architect';
  if (plan == PlanType.unlimited || plan == PlanType.unlimitedV2) return l10n.unlimitedPlan;
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
