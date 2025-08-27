import 'package:json_annotation/json_annotation.dart';

part 'subscription.g.dart';

enum PlanType {
  basic,
  unlimited,
}

enum SubscriptionStatus {
  active,
  inactive,
}

@JsonSerializable(fieldRename: FieldRename.snake)
class Subscription {
  final PlanType plan;
  final SubscriptionStatus status;
  final int? currentPeriodEnd;
  final String? stripeSubscriptionId;
  @JsonKey(defaultValue: [])
  final List<String> features;
  @JsonKey(defaultValue: false)
  final bool cancelAtPeriodEnd;

  Subscription({
    required this.plan,
    required this.status,
    this.currentPeriodEnd,
    this.stripeSubscriptionId,
    this.features = const [],
    this.cancelAtPeriodEnd = false,
  });

  factory Subscription.fromJson(Map<String, dynamic> json) => _$SubscriptionFromJson(json);
  Map<String, dynamic> toJson() => _$SubscriptionToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class PricingOption {
  final String id;
  final String title;
  final String? description;
  final String priceString;

  PricingOption({
    required this.id,
    required this.title,
    this.description,
    required this.priceString,
  });

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

  SubscriptionPlan({
    required this.id,
    required this.title,
    this.features = const [],
    this.prices = const [],
  });

  factory SubscriptionPlan.fromJson(Map<String, dynamic> json) => _$SubscriptionPlanFromJson(json);
  Map<String, dynamic> toJson() => _$SubscriptionPlanToJson(this);
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
  @JsonKey(defaultValue: false)
  final bool showSubscriptionUi;

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
  });

  factory UserSubscriptionResponse.fromJson(Map<String, dynamic> json) => _$UserSubscriptionResponseFromJson(json);
  Map<String, dynamic> toJson() => _$UserSubscriptionResponseToJson(this);
}
