import 'package:omi/models/subscription.dart';

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

  const PlanStorefront({
    required this.catalogRevision,
    required this.tiers,
    this.current,
    this.usage,
    required this.header,
    this.yearlyToggleLabel,
    required this.showSubscriptionUi,
  });

  /// Current and usage snapshots must both permit a nonblocking budget nudge.
  bool get showBudgetNudge => showSubscriptionUi && current?.legacy == false && usage?.showBudgetNudge == true;

  /// Pro gates apply below Pro on the ladder. A live or payload Pro/Architect
  /// plan already includes them. Non-ladder plans (`unlimited`, `unlimited_v2`)
  /// and unknown ids are not gated: checkout refuses that payload, and opening
  /// the paywall would skip the save.
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
    final tiers = (json['tiers'] as List).map((row) => StorefrontTier.fromJson(_object(row))).toList();
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
/// Paid subscribers may move up the ladder, or from monthly to annual on the
/// same tier. Same-tier annual to monthly is refused from the held yearly
/// price or from [StorefrontCurrentPlan.interval], including when the payload
/// omits that yearly price. Legacy prices, unlimited plans, and unrecognized
/// ids never check out. While a cancellation is scheduled the payment API
/// rejects every other price, so the only purchase is resubscribe on the
/// current price.
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
      (_isNonLadderLegacyPlan(PlanType.fromWire(current.planId)) || PlanType.fromWire(current.planId).isUnknown)) {
    return StorefrontCheckoutDecision.refuse;
  }
  if (tier.action != 'checkout' || !tier.prices.contains(price)) {
    return StorefrontCheckoutDecision.refuse;
  }
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
  return StorefrontCheckoutDecision.checkout;
}

/// Copy-deck label for the current tier's yearly price.
/// Saving is 12× the monthly amount minus the annual amount, from [tier]'s prices.
/// The currency symbol and separators come from the monthly headline so a non-USD
/// price still produces a label and the switch button stays visible.
String? storefrontYearlySwitchLabel(StorefrontTier tier) {
  final month = tier.priceFor('month');
  final year = tier.priceFor('year');
  if (month == null || year == null || month.currency != year.currency) return null;
  final saving = month.amountMinor * 12 - year.amountMinor;
  if (saving <= 0) return null;
  return 'Switch to yearly · save ${_formatMinor(saving, month.currency, month.headline)}';
}

/// Button text for one selected price. The current tier never says "Get {Plan}".
String? storefrontActionLabel({
  required StorefrontCurrentPlan? current,
  required StorefrontTier tier,
  required StorefrontPrice price,
  required StorefrontCheckoutDecision decision,
}) {
  if (decision == StorefrontCheckoutDecision.refuse) return null;
  if (decision == StorefrontCheckoutDecision.resubscribe) return tier.ctaLabel;
  final ownTier = current != null && (tier.isCurrent || current.planId == tier.planId);
  if (!ownTier) return tier.ctaLabel;
  if (current.interval == 'month' && price.interval == 'year') return storefrontYearlySwitchLabel(tier);
  return null;
}

/// Stripe zero-decimal currencies: the minor unit is already the major unit.
const _zeroDecimalCurrencies = {
  'bif',
  'clp',
  'djf',
  'gnf',
  'jpy',
  'kmf',
  'krw',
  'mga',
  'pyg',
  'rwf',
  'ugx',
  'vnd',
  'vuv',
  'xaf',
  'xof',
  'xpf',
};

String _formatMinor(int minor, String currency, String headline) {
  final zeroDecimal = _zeroDecimalCurrencies.contains(currency.toLowerCase());
  final affix = _currencyAffix(headline);
  final whole = zeroDecimal ? minor : minor ~/ 100;
  final fraction = zeroDecimal ? 0 : minor.abs() % 100;
  final thousandsSep = affix.decimalSep == ',' ? '.' : ',';
  final digits = whole.abs().toString();
  final grouped = StringBuffer();
  if (whole < 0) grouped.write('-');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) grouped.write(thousandsSep);
    grouped.write(digits[i]);
  }
  final amount = !zeroDecimal && fraction != 0
      ? '$grouped${affix.decimalSep}${fraction.toString().padLeft(2, '0')}'
      : grouped.toString();
  if (affix.prefix.isEmpty && affix.suffix.trim().isEmpty) return '${currency.toUpperCase()} $amount';
  return '${affix.prefix}$amount${affix.suffix}';
}

({String prefix, String suffix, String decimalSep}) _currencyAffix(String headline) {
  final price = headline.split('/').first.trim();
  final match = RegExp(r'^(\D*)(\d[\d.,]*\d|\d)(\D*)$').firstMatch(price);
  if (match == null) return (prefix: '', suffix: '', decimalSep: '.');
  final number = match.group(2)!;
  final comma = number.lastIndexOf(',');
  final dot = number.lastIndexOf('.');
  var decimalSep = '.';
  if (comma > dot && number.length - comma - 1 == 2) decimalSep = ',';
  return (prefix: match.group(1) ?? '', suffix: match.group(3) ?? '', decimalSep: decimalSep);
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
  });

  factory StorefrontTier.fromJson(Map<String, dynamic> json) {
    final action = _text(json, 'action');
    if (!['none', 'checkout', 'current'].contains(action)) {
      throw const FormatException('Unsupported storefront action');
    }
    final cta = json['cta_label'];
    if (action == 'checkout') {
      if (cta is! String || cta.trim().isEmpty) throw const FormatException('Missing storefront cta_label');
    } else if (cta != null && (cta is! String || cta.trim().isEmpty)) {
      throw const FormatException('Invalid storefront cta_label');
    }
    final prices = (json['prices'] as List).map((row) => StorefrontPrice.fromJson(_object(row))).toList();
    if (prices.map((price) => price.interval).toSet().length != prices.length) {
      throw const FormatException('Duplicate storefront price interval');
    }
    return StorefrontTier(
      tierId: _text(json, 'tier_id'),
      planId: _text(json, 'plan_id'),
      name: _text(json, 'name'),
      hoursLine: _text(json, 'hours_line'),
      bullets: List.unmodifiable((json['bullets'] as List).map((value) {
        if (value is! String || value.trim().isEmpty) throw const FormatException('Invalid bullet');
        return value;
      })),
      recommended: _boolean(json, 'recommended'),
      isCurrent: _boolean(json, 'is_current'),
      prices: List.unmodifiable(prices),
      action: action,
      ctaLabel: cta as String?,
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
  final String id;
  final String interval;
  final int amountMinor;
  final String currency;
  final String headline;
  final String? subline;
  final String renewalLine;
  final int? monthsFree;

  const StorefrontPrice({
    required this.id,
    required this.interval,
    required this.amountMinor,
    required this.currency,
    required this.headline,
    this.subline,
    required this.renewalLine,
    this.monthsFree,
  });

  factory StorefrontPrice.fromJson(Map<String, dynamic> json) {
    final interval = _text(json, 'interval');
    final amount = json['amount_minor'];
    if (!['month', 'year'].contains(interval) || amount is! int || amount < 0) {
      throw const FormatException('Invalid storefront price');
    }
    final subline = json['subline'];
    if (subline != null && (subline is! String || subline.trim().isEmpty)) {
      throw const FormatException('Invalid storefront subline');
    }
    final months = json['months_free'];
    if (months != null && (months is! int || months < 0)) {
      throw const FormatException('Invalid storefront months free');
    }
    return StorefrontPrice(
      id: _text(json, 'price_id'),
      interval: interval,
      amountMinor: amount,
      currency: _text(json, 'currency'),
      headline: _text(json, 'headline'),
      subline: subline as String?,
      renewalLine: _text(json, 'renewal_line'),
      monthsFree: months as int?,
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
  final String? nudgeLine;
  final Set<String> proGates;

  const StorefrontUsage({
    required this.kind,
    this.percent,
    this.periodId,
    this.resetLabel,
    this.meterLine,
    this.nudgeLine,
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
      nudgeLine: _optionalText(json, 'nudge_line'),
      proGates: Set<String>.unmodifiable(gates.map((value) => value as String)),
    );
  }

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

String? _optionalText(Map<String, dynamic> json, String key) {
  if (!json.containsKey(key) || json[key] == null) return null;
  return _text(json, key);
}

bool _boolean(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! bool) throw FormatException('Missing storefront $key');
  return value;
}
