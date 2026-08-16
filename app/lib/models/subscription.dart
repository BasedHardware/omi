import 'package:omi/backend/schema/gen/subscription_usage_wire.g.dart' as wire;

enum PlanType { basic, unlimited, architect, operator, plus, unlimitedV2 }

enum SubscriptionStatus { active, inactive }

const Map<PlanType, String> _planTypeWireNames = {
  PlanType.basic: 'basic',
  PlanType.unlimited: 'unlimited',
  PlanType.architect: 'architect',
  PlanType.operator: 'operator',
  PlanType.plus: 'plus',
  PlanType.unlimitedV2: 'unlimited_v2',
};

extension PlanTypeX on PlanType {
  String get wireName => _planTypeWireNames[this]!;

  bool get isPaid => this != PlanType.basic;

  /// Plans with no monthly transcription cap. Plus is paid but metered
  /// (1500 min/month), so it is deliberately excluded.
  bool get hasUnlimitedTranscription =>
      this == PlanType.unlimited ||
      this == PlanType.operator ||
      this == PlanType.architect ||
      this == PlanType.unlimitedV2;

  /// Mirrors backend DESKTOP_ENTITLED_PLAN_TYPES.
  bool get grantsDesktop => this == PlanType.operator || this == PlanType.architect;
}

PlanType _planTypeFromWire(String? value) {
  for (final entry in _planTypeWireNames.entries) {
    if (entry.value == value) return entry.key;
  }
  return PlanType.basic;
}

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
