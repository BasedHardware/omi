import 'package:omi/models/subscription.dart';
import 'package:omi/backend/schema/gen/storefront_wire.g.dart';

/// Presentation only. The backend owns tier rank, recommendation, copy, prices and entitlements.
/// Schema version 2 is the only accepted payload. Unknown versions and malformed purchasable prices fail closed.
class PlanStorefront {
  final int catalogRevision;
  final List<StorefrontTier> tiers;
  final StorefrontCurrentPlan? current;
  final StorefrontUsage? usage;
  final String header;
  final String? yearlyToggleLabel;
  final bool showSubscriptionUi;
  final GeneratedStorefrontCapChoice? atCap;
  final ChatAtCap? chatAtCap;

  const PlanStorefront({
    required this.catalogRevision,
    required this.tiers,
    this.current,
    this.usage,
    required this.header,
    this.yearlyToggleLabel,
    required this.showSubscriptionUi,
    this.atCap,
    this.chatAtCap,
  });

  /// Current and usage snapshots must both permit a nonblocking budget nudge.
  bool get showBudgetNudge => showSubscriptionUi && current?.legacy == false && usage?.showBudgetNudge == true;

  /// Pro gates apply below Pro on the ladder. A live or payload Operator,
  /// Architect or Omi Pro plan already includes them. Legacy Neo (`unlimited`)
  /// and unknown ids are not gated: opening the paywall would skip the save.
  bool shouldGate(String feature, {PlanType? livePlan}) {
    if (!showSubscriptionUi || current == null || current!.legacy) return false;
    if (usage?.proGates.contains(feature) != true) return false;
    if (_isOffLadderOrUnknown(current!.planId) || _isOffLadderOrUnknown(livePlan?.wireName)) return false;
    final rank = _higherRank(_storefrontLadderRank(current!.planId), _storefrontLadderRank(livePlan?.wireName));
    final proRank = _storefrontLadderRank('operator');
    if (rank != null && proRank != null && rank >= proRank) return false;
    return true;
  }

  factory PlanStorefront.fromJson(Map<String, dynamic> json) {
    if (json['schema_version'] != 2) throw const FormatException('Unsupported storefront schema');
    final revision = json['catalog_revision'];
    if (revision is! int || revision < 0) throw const FormatException('Invalid storefront catalog revision');
    final rawTiers = json['tiers'];
    if (rawTiers != null && rawTiers is! List) throw const FormatException('Invalid storefront tiers');
    final tiers = ((rawTiers as List?) ?? const []).map((row) => StorefrontTier.fromJson(_object(row))).toList();
    if (tiers.map((tier) => tier.tierId).toSet().length != tiers.length) {
      throw const FormatException('Duplicate storefront tier');
    }
    if (tiers.map((tier) => tier.planId).toSet().length != tiers.length) {
      throw const FormatException('Duplicate storefront plan');
    }
    final yearly = json['yearly_toggle_label'];
    if (yearly != null && (yearly is! String || yearly.trim().isEmpty)) {
      throw const FormatException('Invalid yearly toggle label');
    }
    return PlanStorefront(
      chatAtCap: json['chat_at_cap'] == null ? null : ChatAtCap.fromJson(_object(json['chat_at_cap'])),
      atCap: json['at_cap'] == null ? null : GeneratedStorefrontCapChoice.fromJson(_object(json['at_cap'])),
      catalogRevision: revision,
      tiers: List.unmodifiable(tiers),
      current: json['current'] == null ? null : StorefrontCurrentPlan.fromJson(_object(json['current'])),
      usage: json['usage'] == null ? null : StorefrontUsage.fromJson(_object(json['usage'])),
      header: _text(json, 'header'),
      yearlyToggleLabel: yearly as String?,
      showSubscriptionUi: json['show_subscription_ui'] == true,
    );
  }
}

/// Checkout, resubscribe the current price, or refuse.
enum StorefrontCheckoutDecision { refuse, checkout, resubscribe }

/// basic < plus < operator < architect < unlimited_v2 (Omi Pro, the only plan
/// sold). Null when [id] is not on that ladder.
int? _storefrontLadderRank(String? id) {
  const ladder = ['basic', 'plus', 'operator', 'architect', 'unlimited_v2'];
  if (id == null) return null;
  final plan = PlanType.fromWire(id);
  if (plan.isUnknown) return null;
  final index = ladder.indexOf(plan.wireName);
  return index < 0 ? null : index;
}

bool _isNonLadderLegacyPlan(PlanType plan) => plan == PlanType.unlimited;

bool _isOffLadderOrUnknown(String? id) {
  if (id == null) return false;
  final plan = PlanType.fromWire(id);
  return plan.isUnknown || _isNonLadderLegacyPlan(plan);
}

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
/// Paid subscribers may move up the ladder. The only same-tier purchase is
/// monthly to annual, and only from a monthly current price — including when
/// that card publishes just the yearly price. Annual to monthly and every
/// other same-tier price are refused. Legacy prices and unrecognized ids never
/// check out; a legacy Neo subscriber may only move to Omi Pro. While a cancellation is scheduled the
/// payment API rejects every other price, so the only purchase is resubscribe
/// on the current price.
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
  final toOmiPro = PlanType.fromWire(tier.planId) == PlanType.unlimitedV2;
  if (livePlan != null && ((_isNonLadderLegacyPlan(livePlan) && !toOmiPro) || livePlan.isUnknown)) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (current != null &&
      ((_isNonLadderLegacyPlan(PlanType.fromWire(current.planId)) && !toOmiPro) ||
          PlanType.fromWire(current.planId).isUnknown)) {
    return StorefrontCheckoutDecision.refuse;
  }
  // `none` is not purchasable. `current` proceeds only when that price has a
  // cta_label. `checkout` may omit the tier label when the price label is the
  // words (same-tier yearly switch). Rank, interval, legacy, and cancellation
  // checks below still apply.
  if (tier.action == 'none' || !tier.prices.contains(price)) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (tier.action == 'current' && price.ctaLabel == null) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (tier.action != 'checkout' && tier.action != 'current') {
    return StorefrontCheckoutDecision.refuse;
  }
  if (price.id == null) return StorefrontCheckoutDecision.refuse;
  final held = _priceOnTier(tier, current?.priceId);
  final sameTierAnnualToMonthly = price.interval == 'month' &&
      current != null &&
      current.interval == 'year' &&
      PlanType.fromWire(current.planId) == PlanType.fromWire(tier.planId);
  if ((held != null && held.interval == 'year' && price.interval == 'month') || sameTierAnnualToMonthly) {
    return StorefrontCheckoutDecision.refuse;
  }
  final targetRank = _storefrontLadderRank(tier.planId);
  final effectiveRank = _higherRank(_storefrontLadderRank(current?.planId), _storefrontLadderRank(livePlan?.wireName));
  if (effectiveRank != null && targetRank != null && targetRank < effectiveRank) {
    return StorefrontCheckoutDecision.refuse;
  }
  final effectiveGrantsDesktop =
      (livePlan?.grantsDesktop ?? false) || PlanType.fromWire(current?.planId ?? 'basic').grantsDesktop;
  if (effectiveGrantsDesktop && !PlanType.fromWire(tier.planId).grantsDesktop) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (price.id == current?.priceId) {
    return cancelScheduled ? StorefrontCheckoutDecision.resubscribe : StorefrontCheckoutDecision.refuse;
  }
  if (cancelScheduled) return StorefrontCheckoutDecision.refuse;
  final sameTier = current != null && PlanType.fromWire(current.planId) == PlanType.fromWire(tier.planId);
  if (sameTier && !(current.interval == 'month' && price.interval == 'year')) {
    return StorefrontCheckoutDecision.refuse;
  }
  return StorefrontCheckoutDecision.checkout;
}

/// Button text for one selected price. The backend owns the words: a per-price
/// [StorefrontPrice.ctaLabel] replaces the tier label. A refused decision draws nothing.
String? storefrontActionLabel({
  required StorefrontTier tier,
  required StorefrontPrice price,
  required StorefrontCheckoutDecision decision,
}) {
  if (decision == StorefrontCheckoutDecision.refuse) return null;
  return price.ctaLabel ?? tier.ctaLabel;
}

class StorefrontTier {
  final String tierId;
  final String planId;
  final String name;
  final String hoursLine;
  final List<String> bullets;
  final bool recommended;
  final bool isCurrent;
  final List<StorefrontPrice> prices;
  final String action;
  final String? ctaLabel;
  final String? blockedLine;
  final bool compact;

  const StorefrontTier({
    required this.tierId,
    required this.planId,
    required this.name,
    required this.hoursLine,
    required this.bullets,
    required this.recommended,
    required this.isCurrent,
    required this.prices,
    required this.action,
    this.ctaLabel,
    this.blockedLine,
    this.compact = false,
  });

  factory StorefrontTier.fromJson(Map<String, dynamic> json) {
    final action = _text(json, 'action');
    if (!['none', 'checkout', 'current'].contains(action)) {
      throw const FormatException('Unsupported storefront action');
    }
    final cta = _optionalText(json, 'cta_label');
    // A checkout tier may leave cta_label null when the price carries the label.
    final prices = (json['prices'] as List).map((row) => StorefrontPrice.fromJson(_object(row))).toList();
    if (prices.map((price) => price.interval).toSet().length != prices.length) {
      throw const FormatException('Duplicate storefront price interval');
    }
    final hours = json['hours_line'];
    if (hours is! String) throw const FormatException('Missing storefront hours_line');
    return StorefrontTier(
      tierId: _text(json, 'tier_id'),
      planId: _text(json, 'plan_id'),
      name: _text(json, 'name'),
      hoursLine: hours,
      bullets: List.unmodifiable((json['bullets'] as List).map((value) {
        if (value is! String || value.trim().isEmpty) throw const FormatException('Invalid bullet');
        return value;
      })),
      recommended: _boolean(json, 'recommended'),
      isCurrent: _boolean(json, 'is_current'),
      prices: List.unmodifiable(prices),
      action: action,
      ctaLabel: cta,
      blockedLine: _optionalText(json, 'blocked_line'),
      compact: json.containsKey('compact') ? _boolean(json, 'compact') : false,
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
  /// Exact existing checkout price id. Never reconstructed from tier or interval.
  /// Null when the backend has no purchasable price for this row (for example Free).
  final String? id;
  final String interval;
  final int amountMinor;
  final String currency;
  final String headline;
  final String? subline;
  final String? renewalLine;
  final int? monthsFree;
  final String? ctaLabel;
  final List<String> confirmLines;

  const StorefrontPrice({
    required this.id,
    required this.interval,
    required this.amountMinor,
    required this.currency,
    required this.headline,
    this.subline,
    this.renewalLine,
    this.monthsFree,
    this.ctaLabel,
    this.confirmLines = const [],
  });

  factory StorefrontPrice.fromJson(Map<String, dynamic> json) {
    final interval = _text(json, 'interval');
    final amount = json['amount_minor'];
    if (!['month', 'year'].contains(interval) || amount is! int || amount < 0) {
      throw const FormatException('Invalid storefront price');
    }
    final months = json['months_free'];
    if (months != null && (months is! int || months < 0)) {
      throw const FormatException('Invalid storefront months free');
    }
    return StorefrontPrice(
      id: _optionalText(json, 'price_id'),
      interval: interval,
      amountMinor: amount,
      currency: _text(json, 'currency'),
      headline: _text(json, 'headline'),
      subline: _optionalText(json, 'subline'),
      renewalLine: _optionalText(json, 'renewal_line'),
      monthsFree: months as int?,
      ctaLabel: _optionalText(json, 'cta_label'),
      confirmLines: List<String>.unmodifiable(
          (json['confirm_lines'] as List? ?? const []).whereType<String>().where((line) => line.trim().isNotEmpty)),
    );
  }
}

class StorefrontCurrentPlan {
  final String planId;
  final String name;
  final String? priceId;
  final String? interval;
  final bool legacy;
  final bool cancelAtPeriodEnd;
  final String line;
  final String? legacyNote;

  const StorefrontCurrentPlan({
    required this.planId,
    required this.name,
    this.priceId,
    this.interval,
    required this.legacy,
    required this.cancelAtPeriodEnd,
    required this.line,
    this.legacyNote,
  });

  factory StorefrontCurrentPlan.fromJson(Map<String, dynamic> json) {
    final legacy = _boolean(json, 'legacy');
    final note = json['legacy_note'];
    if (legacy) {
      if (note is! String || note.trim().isEmpty) throw const FormatException('Missing storefront legacy note');
    } else if (note != null) {
      throw const FormatException('Unexpected storefront legacy note');
    }
    final interval = json['interval'];
    if (interval != null && interval != 'month' && interval != 'year') {
      throw const FormatException('Invalid storefront interval');
    }
    final priceId = json['price_id'];
    if (priceId != null && (priceId is! String || priceId.trim().isEmpty)) {
      throw const FormatException('Invalid storefront price id');
    }
    return StorefrontCurrentPlan(
      planId: _text(json, 'plan_id'),
      name: _text(json, 'name'),
      priceId: priceId as String?,
      interval: interval as String?,
      legacy: legacy,
      cancelAtPeriodEnd: _boolean(json, 'cancel_at_period_end'),
      line: _text(json, 'line'),
      legacyNote: note as String?,
    );
  }
}

class StorefrontUsage {
  final String kind;
  final double? percent;
  final String? periodId;
  final String? resetLabel;
  final String? meterLine;
  final int? hoursLeft;
  final String? nudgeLine;
  final String? moreLabel;
  final Set<String> proGates;
  final bool mcpCapReached;

  const StorefrontUsage({
    required this.kind,
    this.percent,
    this.periodId,
    this.resetLabel,
    this.meterLine,
    this.hoursLeft,
    this.nudgeLine,
    this.moreLabel,
    this.mcpCapReached = false,
    this.proGates = const {},
  });

  factory StorefrontUsage.fromJson(Map<String, dynamic> json) {
    final kind = _text(json, 'kind');
    if (!['usage_budget', 'transcription', 'unavailable'].contains(kind)) {
      throw const FormatException('Unsupported usage kind');
    }
    final percent = json['percent'];
    if (percent != null && (percent is! num || !percent.isFinite || percent < 0)) {
      throw const FormatException('Invalid usage percentage');
    }
    final gates = json['pro_gates'] ?? const [];
    if (gates is! List || gates.any((value) => value is! String || value.trim().isEmpty)) {
      throw const FormatException('Invalid pro gates');
    }
    return StorefrontUsage(
      kind: kind,
      percent: (percent as num?)?.toDouble(),
      periodId: _optionalText(json, 'period_id'),
      resetLabel: _optionalText(json, 'reset_label'),
      meterLine: _optionalText(json, 'meter_line'),
      hoursLeft: _optionalCount(json, 'hours_left'),
      nudgeLine: _optionalText(json, 'nudge_line'),
      moreLabel: _optionalText(json, 'more_label'),
      mcpCapReached: json['mcp_cap_reached'] == true,
      proGates: Set<String>.unmodifiable(gates.map((value) => value as String)),
    );
  }

  StorefrontUsage withMeterLine(String? meterLine) => StorefrontUsage(
        kind: kind,
        percent: percent,
        periodId: periodId,
        resetLabel: resetLabel,
        meterLine: meterLine,
        hoursLeft: hoursLeft,
        nudgeLine: nudgeLine,
        moreLabel: moreLabel,
        mcpCapReached: mcpCapReached,
        proGates: proGates,
      );

  /// At 100%, W4 owns the choice. Never create a competing budget dialog.
  bool get showBudgetNudge =>
      kind == 'usage_budget' &&
      percent != null &&
      percent! >= 80 &&
      percent! < 100 &&
      nudgeLine != null &&
      nudgeLine!.isNotEmpty;
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

int? _optionalCount(Map<String, dynamic> json, String key) {
  if (!json.containsKey(key) || json[key] == null) return null;
  final value = json[key];
  if (value is! int || value < 0) throw FormatException('Invalid storefront $key');
  return value;
}

String? _optionalText(Map<String, dynamic> json, String key) {
  if (!json.containsKey(key) || json[key] == null) return null;
  return _text(json, key);
}

bool _boolean(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! bool) throw FormatException('Missing storefront $key');
  return value;
}

/// Backend-owned composer state. Never inferred from a local tier or message count.
class ChatAtCap {
  final String title, body, resetLine;
  final int resetAt;
  final String? upgradeLabel;
  const ChatAtCap(
      {required this.title, required this.body, required this.resetLine, required this.resetAt, this.upgradeLabel});
  factory ChatAtCap.fromJson(Map<String, dynamic> json) {
    if (json['state'] != 'paused' || json['trigger'] != 'usage_budget' || json['reset_at'] is! int) {
      throw const FormatException('Invalid chat pause state');
    }
    return ChatAtCap(
        title: _text(json, 'title'),
        body: _text(json, 'body'),
        resetLine: _text(json, 'reset_line'),
        resetAt: json['reset_at'] as int,
        upgradeLabel: json['upgrade_label'] as String?);
  }
  bool get active => DateTime.now().millisecondsSinceEpoch < resetAt * 1000;
}
