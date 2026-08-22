import 'package:omi/backend/schema/gen/subscription_usage_wire.g.dart' as wire;

enum SubscriptionStatus { active, inactive }

/// A subscription plan identity received from the backend.
///
/// This is intentionally a class rather than an enum. The backend can deploy
/// a new plan before this app is updated, and decoding that value must not
/// silently turn a paying subscriber into [PlanType.basic]. Known plan values
/// retain the enum-shaped API used by the app (`PlanType.values`, `.name`, and
/// the static plan constants), while unknown values retain their raw wire ID.
class PlanType {
  static const PlanType basic = PlanType._('basic', 'basic', 'basic');
  static const PlanType unlimited = PlanType._('unlimited', 'unlimited', 'unlimited');
  static const PlanType architect = PlanType._('architect', 'architect', 'architect');
  static const PlanType operator = PlanType._('operator', 'operator', 'operator');
  static const PlanType plus = PlanType._('plus', 'plus', 'plus');
  static const PlanType unlimitedV2 = PlanType._('unlimitedV2', 'unlimited_v2', 'unlimited_v2');

  /// The canonical catalog identities known by this client.
  ///
  /// Legacy aliases and future identities are deliberately not included.
  static const List<PlanType> values = <PlanType>[basic, unlimited, architect, operator, plus, unlimitedV2];

  /// Dart-style identifier used by existing analytics and UI call sites.
  final String name;

  /// The exact plan ID to use at the backend wire boundary.
  ///
  /// For an unknown plan this is the raw value received from the backend.
  final String wireName;

  /// Canonical catalog identity, or null for an unrecognized future value.
  final String? _canonicalWireName;

  const PlanType._(this.name, this.wireName, this._canonicalWireName);

  /// Creates a lossless representation for a plan ID unknown to this client.
  factory PlanType.unknown(String rawWireName) {
    return PlanType._(rawWireName, rawWireName, null);
  }

  /// Decodes a backend plan ID without collapsing unknown values to Basic.
  ///
  /// `pro` is the catalog's legacy alias for Architect and is canonicalized to
  /// Architect's identity at the domain boundary.
  factory PlanType.fromWire(String? value) {
    switch (value) {
      case 'basic':
        return PlanType.basic;
      case 'unlimited':
        return PlanType.unlimited;
      case 'architect':
        return PlanType.architect;
      case 'operator':
        return PlanType.operator;
      case 'plus':
        return PlanType.plus;
      case 'unlimited_v2':
        return PlanType.unlimitedV2;
      case 'pro':
        return PlanType.architect;
      case null:
        // GeneratedSubscription supplies the legacy default for an omitted
        // plan field. Keep this defensive path aligned with that contract.
        return PlanType.basic;
      default:
        return PlanType.unknown(value);
    }
  }

  bool get isUnknown => _canonicalWireName == null;

  /// Unknown plans never infer paid access from an unfamiliar ID.
  bool get isPaid => !isUnknown && _canonicalWireName != PlanType.basic.wireName;

  /// Plans with no monthly transcription cap. Plus is paid but metered
  /// (1500 min/month), so it is deliberately excluded. Unknown plans are
  /// conservative and do not infer unlimited access.
  bool get hasUnlimitedTranscription =>
      _canonicalWireName == PlanType.unlimited.wireName ||
      _canonicalWireName == PlanType.operator.wireName ||
      _canonicalWireName == PlanType.architect.wireName ||
      _canonicalWireName == PlanType.unlimitedV2.wireName;

  /// Mirrors backend DESKTOP_ENTITLED_PLAN_TYPES.
  bool get grantsDesktop =>
      _canonicalWireName == PlanType.operator.wireName || _canonicalWireName == PlanType.architect.wireName;

  @override
  bool operator ==(Object other) {
    if (other is! PlanType) return false;
    if (isUnknown || other.isUnknown) {
      return isUnknown && other.isUnknown && wireName == other.wireName;
    }
    return _canonicalWireName == other._canonicalWireName;
  }

  @override
  int get hashCode => isUnknown ? wireName.hashCode : _canonicalWireName.hashCode;

  @override
  String toString() => isUnknown ? 'PlanType.unknown($wireName)' : 'PlanType.$name';
}

PlanType _planTypeFromWire(String? value) => PlanType.fromWire(value);

SubscriptionStatus _subscriptionStatusFromWire(String? value) {
  return SubscriptionStatus.values.asNameMap()[value] ?? SubscriptionStatus.inactive;
}

class PlanLimits {
  final int? transcriptionSeconds;
  final int? wordsTranscribed;
  final int? insightsGained;
  final int? chatQuestionsPerMonth;
  final double? chatCostUsdPerMonth;

  PlanLimits({
    this.transcriptionSeconds,
    this.wordsTranscribed,
    this.insightsGained,
    this.chatQuestionsPerMonth,
    this.chatCostUsdPerMonth,
  });

  factory PlanLimits.fromJson(Map<String, dynamic> json) {
    return PlanLimits.fromGenerated(wire.GeneratedPlanLimits.fromJson(json));
  }

  factory PlanLimits.fromGenerated(wire.GeneratedPlanLimits generated) {
    return PlanLimits(
      transcriptionSeconds: generated.transcriptionSeconds,
      wordsTranscribed: generated.wordsTranscribed,
      insightsGained: generated.insightsGained,
      chatQuestionsPerMonth: generated.chatQuestionsPerMonth,
      chatCostUsdPerMonth: generated.chatCostUsdPerMonth,
    );
  }

  wire.GeneratedPlanLimits toGenerated() {
    return wire.GeneratedPlanLimits(
      transcriptionSeconds: transcriptionSeconds,
      wordsTranscribed: wordsTranscribed,
      insightsGained: insightsGained,
      chatQuestionsPerMonth: chatQuestionsPerMonth,
      chatCostUsdPerMonth: chatCostUsdPerMonth,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class Subscription {
  final PlanType plan;
  final SubscriptionStatus status;
  final int? currentPeriodEnd;
  final String? stripeSubscriptionId;
  final String? currentPriceId;
  final List<String> features;
  final bool cancelAtPeriodEnd;
  final bool deprecated;
  final String? deprecationMessage;
  final PlanLimits limits;

  Subscription({
    required this.plan,
    required this.status,
    this.currentPeriodEnd,
    this.stripeSubscriptionId,
    this.currentPriceId,
    this.features = const [],
    this.cancelAtPeriodEnd = false,
    this.deprecated = false,
    this.deprecationMessage,
    PlanLimits? limits,
  }) : limits = limits ?? PlanLimits();

  factory Subscription.fromJson(Map<String, dynamic> json) {
    return Subscription.fromGenerated(wire.GeneratedSubscription.fromJson(json));
  }

  factory Subscription.fromGenerated(wire.GeneratedSubscription generated) {
    return Subscription(
      plan: _planTypeFromWire(generated.plan),
      status: _subscriptionStatusFromWire(generated.status),
      currentPeriodEnd: generated.currentPeriodEnd,
      stripeSubscriptionId: generated.stripeSubscriptionId,
      currentPriceId: generated.currentPriceId,
      features: generated.features,
      cancelAtPeriodEnd: generated.cancelAtPeriodEnd,
      deprecated: generated.deprecated,
      deprecationMessage: generated.deprecationMessage,
      limits: PlanLimits.fromGenerated(generated.limits),
    );
  }

  wire.GeneratedSubscription toGenerated() {
    return wire.GeneratedSubscription(
      plan: plan.wireName,
      status: status.name,
      currentPeriodEnd: currentPeriodEnd,
      stripeSubscriptionId: stripeSubscriptionId,
      currentPriceId: currentPriceId,
      features: features,
      cancelAtPeriodEnd: cancelAtPeriodEnd,
      deprecated: deprecated,
      deprecationMessage: deprecationMessage,
      limits: limits.toGenerated(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class PricingOption {
  final String id;
  final String title;
  final String? description;
  final String priceString;

  PricingOption({required this.id, required this.title, this.description, required this.priceString});

  factory PricingOption.fromJson(Map<String, dynamic> json) {
    return PricingOption.fromGenerated(wire.GeneratedPricingOption.fromJson(json));
  }

  factory PricingOption.fromGenerated(wire.GeneratedPricingOption generated) {
    return PricingOption(
      id: generated.id,
      title: generated.title,
      description: generated.description,
      priceString: generated.priceString,
    );
  }

  wire.GeneratedPricingOption toGenerated() {
    return wire.GeneratedPricingOption(id: id, title: title, description: description, priceString: priceString);
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class SubscriptionPlan {
  final String id;
  final String title;
  final List<String> features;
  final List<PricingOption> prices;

  SubscriptionPlan({required this.id, required this.title, this.features = const [], this.prices = const []});

  factory SubscriptionPlan.fromJson(Map<String, dynamic> json) {
    return SubscriptionPlan.fromGenerated(wire.GeneratedSubscriptionPlan.fromJson(json));
  }

  factory SubscriptionPlan.fromGenerated(wire.GeneratedSubscriptionPlan generated) {
    return SubscriptionPlan(
      id: generated.id,
      title: generated.title,
      features: generated.features,
      prices: generated.prices.map(PricingOption.fromGenerated).toList(),
    );
  }

  wire.GeneratedSubscriptionPlan toGenerated() {
    return wire.GeneratedSubscriptionPlan(
      id: id,
      title: title,
      features: features,
      prices: prices.map((price) => price.toGenerated()).toList(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class PhoneCallQuota {
  final bool hasAccess;
  final bool isPaid;
  final int? monthlyLimit;
  final int monthlyUsed;
  final int? remaining;
  final int? maxDurationSeconds;
  final List<String> allowedCountries;
  final int? resetAt;

  PhoneCallQuota({
    required this.hasAccess,
    required this.isPaid,
    this.monthlyLimit,
    this.monthlyUsed = 0,
    this.remaining,
    this.maxDurationSeconds,
    this.allowedCountries = const [],
    this.resetAt,
  });

  factory PhoneCallQuota.fromJson(Map<String, dynamic> json) {
    return PhoneCallQuota.fromGenerated(wire.GeneratedPhoneCallQuota.fromJson(json));
  }

  factory PhoneCallQuota.fromGenerated(wire.GeneratedPhoneCallQuota generated) {
    return PhoneCallQuota(
      hasAccess: generated.hasAccess,
      isPaid: generated.isPaid,
      monthlyLimit: generated.monthlyLimit,
      monthlyUsed: generated.monthlyUsed,
      remaining: generated.remaining,
      maxDurationSeconds: generated.maxDurationSeconds,
      allowedCountries: generated.allowedCountries,
      resetAt: generated.resetAt,
    );
  }

  wire.GeneratedPhoneCallQuota toGenerated() {
    return wire.GeneratedPhoneCallQuota(
      hasAccess: hasAccess,
      isPaid: isPaid,
      monthlyLimit: monthlyLimit,
      monthlyUsed: monthlyUsed,
      remaining: remaining,
      maxDurationSeconds: maxDurationSeconds,
      allowedCountries: allowedCountries,
      resetAt: resetAt,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class UserSubscriptionResponse {
  final Subscription subscription;
  final int transcriptionSecondsUsed;
  final int transcriptionSecondsLimit;
  final int wordsTranscribedUsed;
  final int wordsTranscribedLimit;
  final int insightsGainedUsed;
  final int insightsGainedLimit;
  final List<SubscriptionPlan> availablePlans;
  final bool showSubscriptionUi;
  // Chat quota fields — populated from subscription endpoint
  final double chatQuotaUsed;
  final String? chatQuotaUnit;
  final double chatQuotaPercent;
  final bool chatQuotaAllowed;
  final int? chatQuotaResetAt;
  final PhoneCallQuota? phoneCallQuota;

  UserSubscriptionResponse({
    required this.subscription,
    required this.transcriptionSecondsUsed,
    required this.transcriptionSecondsLimit,
    required this.wordsTranscribedUsed,
    required this.wordsTranscribedLimit,
    required this.insightsGainedUsed,
    required this.insightsGainedLimit,
    this.availablePlans = const [],
    this.showSubscriptionUi = true,
    this.chatQuotaUsed = 0.0,
    this.chatQuotaUnit,
    this.chatQuotaPercent = 0.0,
    this.chatQuotaAllowed = true,
    this.chatQuotaResetAt,
    this.phoneCallQuota,
  });

  factory UserSubscriptionResponse.fromJson(Map<String, dynamic> json) {
    return UserSubscriptionResponse.fromGenerated(wire.GeneratedUserSubscriptionResponse.fromJson(json));
  }

  factory UserSubscriptionResponse.fromGenerated(wire.GeneratedUserSubscriptionResponse generated) {
    return UserSubscriptionResponse(
      subscription: Subscription.fromGenerated(generated.subscription),
      transcriptionSecondsUsed: generated.transcriptionSecondsUsed,
      transcriptionSecondsLimit: generated.transcriptionSecondsLimit,
      wordsTranscribedUsed: generated.wordsTranscribedUsed,
      wordsTranscribedLimit: generated.wordsTranscribedLimit,
      insightsGainedUsed: generated.insightsGainedUsed,
      insightsGainedLimit: generated.insightsGainedLimit,
      availablePlans: generated.availablePlans.map(SubscriptionPlan.fromGenerated).toList(),
      showSubscriptionUi: generated.showSubscriptionUi,
      chatQuotaUsed: generated.chatQuotaUsed,
      chatQuotaUnit: generated.chatQuotaUnit,
      chatQuotaPercent: generated.chatQuotaPercent,
      chatQuotaAllowed: generated.chatQuotaAllowed,
      chatQuotaResetAt: generated.chatQuotaResetAt,
      phoneCallQuota: generated.phoneCallQuota == null ? null : PhoneCallQuota.fromGenerated(generated.phoneCallQuota!),
    );
  }

  wire.GeneratedUserSubscriptionResponse toGenerated() {
    return wire.GeneratedUserSubscriptionResponse(
      subscription: subscription.toGenerated(),
      transcriptionSecondsUsed: transcriptionSecondsUsed,
      transcriptionSecondsLimit: transcriptionSecondsLimit,
      wordsTranscribedUsed: wordsTranscribedUsed,
      wordsTranscribedLimit: wordsTranscribedLimit,
      insightsGainedUsed: insightsGainedUsed,
      insightsGainedLimit: insightsGainedLimit,
      availablePlans: availablePlans.map((plan) => plan.toGenerated()).toList(),
      showSubscriptionUi: showSubscriptionUi,
      chatQuotaUsed: chatQuotaUsed,
      chatQuotaUnit: chatQuotaUnit,
      chatQuotaPercent: chatQuotaPercent,
      chatQuotaAllowed: chatQuotaAllowed,
      chatQuotaResetAt: chatQuotaResetAt,
      phoneCallQuota: phoneCallQuota?.toGenerated(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}
