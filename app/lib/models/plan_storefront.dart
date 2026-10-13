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

  /// Client safety boundary: presentation actions cannot migrate legacy prices
  /// or strip desktop entitlements, even when the server advertises checkout.
  bool canCheckout(StorefrontTier tier, StorefrontPrice price, {bool currentGrantsDesktop = false}) =>
      showSubscriptionUi &&
      current?.legacy != true &&
      tier.action == 'checkout' &&
      tier.prices.contains(price) &&
      price.id != current?.priceId &&
      (!(currentGrantsDesktop || PlanType.fromWire(current?.id ?? 'basic').grantsDesktop) ||
          PlanType.fromWire(tier.id).grantsDesktop);

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
