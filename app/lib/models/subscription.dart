import 'package:json_annotation/json_annotation.dart';

part 'subscription.g.dart';

enum PlanType { basic, unlimited, architect, operator }

enum SubscriptionStatus { active, inactive }

@JsonSerializable(fieldRename: FieldRename.snake)
class PlanLimits {
  final int? transcriptionSeconds;
  final int? wordsTranscribed;
  final int? insightsGained;
  final int? memoriesCreated;
  final int? chatQuestionsPerMonth;
  final double? chatCostUsdPerMonth;

  PlanLimits({
    this.transcriptionSeconds,
    this.wordsTranscribed,
    this.insightsGained,
    this.memoriesCreated,
    this.chatQuestionsPerMonth,
    this.chatCostUsdPerMonth,
  });

  factory PlanLimits.fromJson(Map<String, dynamic> json) => _$PlanLimitsFromJson(json);
  Map<String, dynamic> toJson() => _$PlanLimitsToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class Subscription {
  @JsonKey(unknownEnumValue: PlanType.basic)
  final PlanType plan;
  @JsonKey(unknownEnumValue: SubscriptionStatus.inactive)
  final SubscriptionStatus status;
  final int? currentPeriodEnd;
  final String? stripeSubscriptionId;
  final String? currentPriceId;
  @JsonKey(defaultValue: [])
  final List<String> features;
  @JsonKey(defaultValue: false)
  final bool cancelAtPeriodEnd;
  @JsonKey(defaultValue: false)
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

  factory Subscription.fromJson(Map<String, dynamic> json) => _$SubscriptionFromJson(json);
  Map<String, dynamic> toJson() => _$SubscriptionToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class PricingOption {
  final String id;
  final String title;
  final String? description;
  final String priceString;

  PricingOption({required this.id, required this.title, this.description, required this.priceString});

  factory PricingOption.fromJson(Map<String, dynamic> json) => _$PricingOptionFromJson(json);
  Map<String, dynamic> toJson() => _$PricingOptionToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class SubscriptionPlan {
  final String id;
  final String title;
  @JsonKey(defaultValue: [])
  final List<String> features;
  @JsonKey(defaultValue: [])
  final List<PricingOption> prices;

  SubscriptionPlan({required this.id, required this.title, this.features = const [], this.prices = const []});

  factory SubscriptionPlan.fromJson(Map<String, dynamic> json) => _$SubscriptionPlanFromJson(json);
  Map<String, dynamic> toJson() => _$SubscriptionPlanToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class PhoneCallQuota {
  final bool hasAccess;
  final bool isPaid;
  final int? monthlyLimit;
  @JsonKey(defaultValue: 0)
  final int monthlyUsed;
  final int? remaining;
  final int? maxDurationSeconds;
  @JsonKey(defaultValue: [])
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

  factory PhoneCallQuota.fromJson(Map<String, dynamic> json) => _$PhoneCallQuotaFromJson(json);
  Map<String, dynamic> toJson() => _$PhoneCallQuotaToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class UserSubscriptionResponse {
  final Subscription subscription;
  final int transcriptionSecondsUsed;
  final int transcriptionSecondsLimit;
  final int wordsTranscribedUsed;
  final int wordsTranscribedLimit;
  final int insightsGainedUsed;
  final int insightsGainedLimit;
  final int memoriesCreatedUsed;
  final int memoriesCreatedLimit;
  @JsonKey(defaultValue: [])
  final List<SubscriptionPlan> availablePlans;
  @JsonKey(defaultValue: true)
  final bool showSubscriptionUi;
  // Chat quota fields — populated from subscription endpoint
  @JsonKey(defaultValue: 0.0)
  final double chatQuotaUsed;
  final String? chatQuotaUnit;
  @JsonKey(defaultValue: 0.0)
  final double chatQuotaPercent;
  @JsonKey(defaultValue: true)
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
    required this.memoriesCreatedUsed,
    required this.memoriesCreatedLimit,
    this.availablePlans = const [],
    this.showSubscriptionUi = true,
    this.chatQuotaUsed = 0.0,
    this.chatQuotaUnit,
    this.chatQuotaPercent = 0.0,
    this.chatQuotaAllowed = true,
    this.chatQuotaResetAt,
    this.phoneCallQuota,
  });

  factory UserSubscriptionResponse.fromJson(Map<String, dynamic> json) => _$UserSubscriptionResponseFromJson(json);
  Map<String, dynamic> toJson() => _$UserSubscriptionResponseToJson(this);
}
