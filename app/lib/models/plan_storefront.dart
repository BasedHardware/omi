import 'package:omi/models/subscription.dart';

/// Presentation only. The backend owns tier rank, recommendation, copy, prices and entitlements.
/// Unknown schema versions and malformed purchasable prices fail closed.
class PlanStorefront {
  final List<StorefrontTier> tiers;
  final StorefrontCurrentPlan? current;
  final StorefrontUsageContext? usageContext;
  final bool showSubscriptionUi;

  const PlanStorefront({
    required this.tiers,
    this.current,
    this.usageContext,
    required this.showSubscriptionUi,
  });

  /// Current and usage snapshots must both permit a nonblocking budget nudge.
  bool get showBudgetNudge => showSubscriptionUi && current?.legacy == false && usageContext?.showBudgetNudge == true;

  bool shouldGate(String feature) =>
      showSubscriptionUi &&
      current != null &&
      current?.legacy == false &&
      usageContext?.legacy != true &&
      usageContext?.proGates.contains(feature) == true;

  factory PlanStorefront.fromJson(Map<String, dynamic> json) {
    if (json['schema_version'] != 1) throw const FormatException('Unsupported storefront schema');
    final tiers = (json['tiers'] as List).map((row) => StorefrontTier.fromJson(_object(row))).toList();
    if (tiers.map((tier) => tier.id).toSet().length != tiers.length) {
      throw const FormatException('Duplicate storefront tier');
    }
    return PlanStorefront(
      tiers: List.unmodifiable(tiers),
      current: json['current'] == null ? null : StorefrontCurrentPlan.fromJson(_object(json['current'])),
      usageContext:
          json['usage_context'] == null ? null : StorefrontUsageContext.fromJson(_object(json['usage_context'])),
      showSubscriptionUi: json['show_subscription_ui'] == true,
    );
  }
}

/// Checkout, resubscribe the current price, or refuse.
enum StorefrontCheckoutDecision { refuse, checkout, resubscribe }

/// basic < plus < operator < architect. Null when [id] is not on that ladder.
int? _storefrontLadderRank(String? id) {
  const ladder = ['basic', 'plus', 'operator', 'architect'];
  if (id == null) return null;
  final plan = PlanType.fromWire(id);
  if (plan.isUnknown) return null;
  final index = ladder.indexOf(plan.wireName);
  return index < 0 ? null : index;
}

bool _isNonLadderLegacyPlan(PlanType plan) => plan == PlanType.unlimited || plan == PlanType.unlimitedV2;

int? _higherRank(int? left, int? right) {
  if (left == null) return right;
  if (right == null) return left;
  return left > right ? left : right;
}

StorefrontPrice? _priceOnTier(StorefrontTier tier, String? id) {
  if (id == null || id.isEmpty) return null;
  for (final candidate in tier.prices) {
    if (candidate.id == id) return candidate;
  }
  return null;
}

/// Single checkout boundary for rendering and every tap or handoff.
///
/// Paid subscribers may move up the ladder, or from monthly to annual on the
/// same tier. Legacy prices, unlimited plans, and unrecognized ids never
/// check out. A scheduled cancellation resubscribes the current price only.
StorefrontCheckoutDecision storefrontCheckoutDecision(
  StorefrontCurrentPlan? current,
  PlanType? livePlan,
  StorefrontTier tier,
  StorefrontPrice price, {
  bool usageLegacy = false,
  bool cancelScheduled = false,
  bool showSubscriptionUi = true,
}) {
  if (!showSubscriptionUi || usageLegacy || current?.legacy == true) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (livePlan != null && (_isNonLadderLegacyPlan(livePlan) || livePlan.isUnknown)) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (current != null &&
      (_isNonLadderLegacyPlan(PlanType.fromWire(current.id)) || PlanType.fromWire(current.id).isUnknown)) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (tier.action != 'checkout' || !tier.prices.contains(price)) {
    return StorefrontCheckoutDecision.refuse;
  }
  final held = _priceOnTier(tier, current?.priceId);
  if (held != null && held.interval == 'year' && price.interval == 'month') {
    return StorefrontCheckoutDecision.refuse;
  }
  final targetRank = _storefrontLadderRank(tier.id);
  final effectiveRank = _higherRank(_storefrontLadderRank(current?.id), _storefrontLadderRank(livePlan?.wireName));
  if (effectiveRank != null && targetRank != null && targetRank < effectiveRank) {
    return StorefrontCheckoutDecision.refuse;
  }
  final effectiveGrantsDesktop =
      (livePlan?.grantsDesktop ?? false) || PlanType.fromWire(current?.id ?? 'basic').grantsDesktop;
  if (effectiveGrantsDesktop && !PlanType.fromWire(tier.id).grantsDesktop) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (price.id == current?.priceId) {
    return cancelScheduled ? StorefrontCheckoutDecision.resubscribe : StorefrontCheckoutDecision.refuse;
  }
  if (cancelScheduled) return StorefrontCheckoutDecision.refuse;
  return StorefrontCheckoutDecision.checkout;
}

class StorefrontTier {
  final String id;
  final String name;
  final String description;
  final List<String> outcomes;
  final String? recordingEquivalent;
  final bool recommended;
  final List<StorefrontPrice> prices;
  final String action;
  final String actionLabel;

  const StorefrontTier(
      {required this.id,
      required this.name,
      required this.description,
      required this.outcomes,
      this.recordingEquivalent,
      required this.recommended,
      required this.prices,
      required this.action,
      required this.actionLabel});

  factory StorefrontTier.fromJson(Map<String, dynamic> json) {
    final action = _text(json, 'action');
    if (!['none', 'checkout', 'manage'].contains(action)) {
      throw const FormatException('Unsupported storefront action');
    }
    final prices = (json['prices'] as List).map((row) => StorefrontPrice.fromJson(_object(row))).toList();
    if (prices.map((price) => price.interval).toSet().length != prices.length) {
      throw const FormatException('Duplicate storefront price interval');
    }
    return StorefrontTier(
      id: _text(json, 'id'),
      name: _text(json, 'name'),
      description: _text(json, 'description'),
      outcomes: List.unmodifiable((json['outcomes'] as List).map((value) {
        if (value is! String || value.trim().isEmpty) throw const FormatException('Invalid outcome');
        return value;
      })),
      recordingEquivalent: json['recording_equivalent'] as String?,
      recommended: json['recommended'] == true,
      prices: List.unmodifiable(prices),
      action: action,
      actionLabel: _text(json, 'action_label'),
    );
  }

  StorefrontPrice? priceFor(String interval) {
    for (final price in prices) {
      if (price.interval == interval) return price;
    }
    return null;
  }
}

class StorefrontPrice {
  /// Exact existing checkout price id. Never reconstructed from tier/interval.
  final String id;
  final String interval;
  final int amount;
  final String currency;
  final String formatted;
  final String monthlyEquivalent;
  final String renewalTerms;

  /// Computed by the server from live prices. No client arithmetic or fixed badge.
  final String? annualSavings;

  const StorefrontPrice(
      {required this.id,
      required this.interval,
      required this.amount,
      required this.currency,
      required this.formatted,
      required this.monthlyEquivalent,
      required this.renewalTerms,
      this.annualSavings});

  factory StorefrontPrice.fromJson(Map<String, dynamic> json) {
    final interval = _text(json, 'interval');
    final amount = json['amount'];
    if (!['month', 'year'].contains(interval) || amount is! int || amount < 0) {
      throw const FormatException('Invalid storefront price');
    }
    return StorefrontPrice(
        id: _text(json, 'id'),
        interval: interval,
        amount: amount,
        currency: _text(json, 'currency'),
        formatted: _text(json, 'formatted'),
        monthlyEquivalent: _text(json, 'monthly_equivalent'),
        renewalTerms: _text(json, 'renewal_terms'),
        annualSavings: json['annual_savings'] as String?);
  }
}

class StorefrontCurrentPlan {
  final String id;
  final String name;
  final String? priceId;
  final bool legacy;
  final String message;
  final String? formattedPrice;
  final String? renewalLabel;

  /// Backend-selected tier for display grouping of legacy plans; never an entitlement.
  final String? comparisonTierId;
  const StorefrontCurrentPlan(
      {required this.id,
      required this.name,
      this.priceId,
      required this.legacy,
      this.message = '',
      this.formattedPrice,
      this.renewalLabel,
      this.comparisonTierId});
  factory StorefrontCurrentPlan.fromJson(Map<String, dynamic> json) => StorefrontCurrentPlan(
      id: _text(json, 'id'),
      name: _text(json, 'name'),
      priceId: json['price_id'] as String?,
      legacy: _boolean(json, 'legacy'),
      message: json['message'] as String? ?? '',
      formattedPrice: json['formatted_price'] as String?,
      renewalLabel: json['renewal_label'] as String?,
      comparisonTierId: json['comparison_tier_id'] as String?);
}

class StorefrontUsageContext {
  /// Server-localized reason and outcome for the surface that opened the sheet.
  final String title;
  final String message;
  final String? meter;
  final String? resetLabel;
  final double? budgetPercent;
  final String? budgetNudgeLabel;
  final String? periodId;
  final bool legacy;

  /// Opening surface, such as `mcp_daily_cap`. Absent on older payloads.
  final String? source;

  /// Server entitlement decision; never inferred from the displayed tier.
  final Set<String> proGates;
  const StorefrontUsageContext(
      {required this.title,
      required this.message,
      this.meter,
      this.resetLabel,
      this.budgetPercent,
      this.budgetNudgeLabel,
      this.periodId,
      required this.legacy,
      this.source,
      this.proGates = const {}});
  factory StorefrontUsageContext.fromJson(Map<String, dynamic> json) {
    final percent = json['budget_percent'];
    if (percent != null && (percent is! num || !percent.isFinite || percent < 0)) {
      throw const FormatException('Invalid usage percentage');
    }
    final gates = json['pro_gates'] ?? const [];
    if (gates is! List || gates.any((value) => value is! String || value.trim().isEmpty)) {
      throw const FormatException('Invalid pro gates');
    }
    return StorefrontUsageContext(
        title: _text(json, 'title'),
        message: _text(json, 'message'),
        meter: json['meter'] as String?,
        resetLabel: json['reset_label'] as String?,
        budgetPercent: (percent as num?)?.toDouble(),
        budgetNudgeLabel: json['budget_nudge_label'] as String?,
        periodId: json['period_id'] as String?,
        legacy: _boolean(json, 'legacy'),
        source: json['source'] as String?,
        proGates: Set<String>.unmodifiable(gates.map((value) => value as String)));
  }

  /// At 100%, W4 owns the choice. Never create a competing budget dialog.
  bool get showBudgetNudge => !legacy && budgetPercent != null && budgetPercent! >= 80 && budgetPercent! < 100;
}

Map<String, dynamic> _object(Object? value) {
  if (value is! Map<String, dynamic>) throw const FormatException('Invalid storefront object');
  return value;
}

String _text(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) throw FormatException('Missing storefront $key');
  return value;
}

bool _boolean(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! bool) throw FormatException('Missing storefront $key');
  return value;
}
