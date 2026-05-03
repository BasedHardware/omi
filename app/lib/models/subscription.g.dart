// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'subscription.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PlanLimits _$PlanLimitsFromJson(Map<String, dynamic> json) => PlanLimits(
      transcriptionSeconds: (json['transcription_seconds'] as num?)?.toInt(),
      wordsTranscribed: (json['words_transcribed'] as num?)?.toInt(),
      insightsGained: (json['insights_gained'] as num?)?.toInt(),
      memoriesCreated: (json['memories_created'] as num?)?.toInt(),
      chatQuestionsPerMonth:
          (json['chat_questions_per_month'] as num?)?.toInt(),
      chatCostUsdPerMonth:
          (json['chat_cost_usd_per_month'] as num?)?.toDouble(),
    );

Map<String, dynamic> _$PlanLimitsToJson(PlanLimits instance) =>
    <String, dynamic>{
      'transcription_seconds': instance.transcriptionSeconds,
      'words_transcribed': instance.wordsTranscribed,
      'insights_gained': instance.insightsGained,
      'memories_created': instance.memoriesCreated,
      'chat_questions_per_month': instance.chatQuestionsPerMonth,
      'chat_cost_usd_per_month': instance.chatCostUsdPerMonth,
    };

Subscription _$SubscriptionFromJson(Map<String, dynamic> json) => Subscription(
      plan: $enumDecode(_$PlanTypeEnumMap, json['plan'],
          unknownValue: PlanType.basic),
      status: $enumDecode(_$SubscriptionStatusEnumMap, json['status'],
          unknownValue: SubscriptionStatus.inactive),
      currentPeriodEnd: (json['current_period_end'] as num?)?.toInt(),
      stripeSubscriptionId: json['stripe_subscription_id'] as String?,
      currentPriceId: json['current_price_id'] as String?,
      features: (json['features'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      cancelAtPeriodEnd: json['cancel_at_period_end'] as bool? ?? false,
      deprecated: json['deprecated'] as bool? ?? false,
      deprecationMessage: json['deprecation_message'] as String?,
      limits: json['limits'] == null
          ? null
          : PlanLimits.fromJson(json['limits'] as Map<String, dynamic>),
    );

Map<String, dynamic> _$SubscriptionToJson(Subscription instance) =>
    <String, dynamic>{
      'plan': _$PlanTypeEnumMap[instance.plan]!,
      'status': _$SubscriptionStatusEnumMap[instance.status]!,
      'current_period_end': instance.currentPeriodEnd,
      'stripe_subscription_id': instance.stripeSubscriptionId,
      'current_price_id': instance.currentPriceId,
      'features': instance.features,
      'cancel_at_period_end': instance.cancelAtPeriodEnd,
      'deprecated': instance.deprecated,
      'deprecation_message': instance.deprecationMessage,
      'limits': instance.limits,
    };

const _$PlanTypeEnumMap = {
  PlanType.basic: 'basic',
  PlanType.unlimited: 'unlimited',
  PlanType.architect: 'architect',
  PlanType.operator: 'operator',
};

const _$SubscriptionStatusEnumMap = {
  SubscriptionStatus.active: 'active',
  SubscriptionStatus.inactive: 'inactive',
};

PricingOption _$PricingOptionFromJson(Map<String, dynamic> json) =>
    PricingOption(
      id: json['id'] as String,
      title: json['title'] as String,
      description: json['description'] as String?,
      priceString: json['price_string'] as String,
    );

Map<String, dynamic> _$PricingOptionToJson(PricingOption instance) =>
    <String, dynamic>{
      'id': instance.id,
      'title': instance.title,
      'description': instance.description,
      'price_string': instance.priceString,
    };

SubscriptionPlan _$SubscriptionPlanFromJson(Map<String, dynamic> json) =>
    SubscriptionPlan(
      id: json['id'] as String,
      title: json['title'] as String,
      features: (json['features'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      prices: (json['prices'] as List<dynamic>?)
              ?.map((e) => PricingOption.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );

Map<String, dynamic> _$SubscriptionPlanToJson(SubscriptionPlan instance) =>
    <String, dynamic>{
      'id': instance.id,
      'title': instance.title,
      'features': instance.features,
      'prices': instance.prices,
    };

PhoneCallQuota _$PhoneCallQuotaFromJson(Map<String, dynamic> json) =>
    PhoneCallQuota(
      hasAccess: json['has_access'] as bool,
      isPaid: json['is_paid'] as bool,
      monthlyLimit: (json['monthly_limit'] as num?)?.toInt(),
      monthlyUsed: (json['monthly_used'] as num?)?.toInt() ?? 0,
      remaining: (json['remaining'] as num?)?.toInt(),
      maxDurationSeconds: (json['max_duration_seconds'] as num?)?.toInt(),
      allowedCountries: (json['allowed_countries'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      resetAt: (json['reset_at'] as num?)?.toInt(),
    );

Map<String, dynamic> _$PhoneCallQuotaToJson(PhoneCallQuota instance) =>
    <String, dynamic>{
      'has_access': instance.hasAccess,
      'is_paid': instance.isPaid,
      'monthly_limit': instance.monthlyLimit,
      'monthly_used': instance.monthlyUsed,
      'remaining': instance.remaining,
      'max_duration_seconds': instance.maxDurationSeconds,
      'allowed_countries': instance.allowedCountries,
      'reset_at': instance.resetAt,
    };

UserSubscriptionResponse _$UserSubscriptionResponseFromJson(
        Map<String, dynamic> json) =>
    UserSubscriptionResponse(
      subscription:
          Subscription.fromJson(json['subscription'] as Map<String, dynamic>),
      transcriptionSecondsUsed:
          (json['transcription_seconds_used'] as num).toInt(),
      transcriptionSecondsLimit:
          (json['transcription_seconds_limit'] as num).toInt(),
      wordsTranscribedUsed: (json['words_transcribed_used'] as num).toInt(),
      wordsTranscribedLimit: (json['words_transcribed_limit'] as num).toInt(),
      insightsGainedUsed: (json['insights_gained_used'] as num).toInt(),
      insightsGainedLimit: (json['insights_gained_limit'] as num).toInt(),
      memoriesCreatedUsed: (json['memories_created_used'] as num).toInt(),
      memoriesCreatedLimit: (json['memories_created_limit'] as num).toInt(),
      availablePlans: (json['available_plans'] as List<dynamic>?)
              ?.map((e) => SubscriptionPlan.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      showSubscriptionUi: json['show_subscription_ui'] as bool? ?? true,
      chatQuotaUsed: (json['chat_quota_used'] as num?)?.toDouble() ?? 0.0,
      chatQuotaUnit: json['chat_quota_unit'] as String?,
      chatQuotaPercent: (json['chat_quota_percent'] as num?)?.toDouble() ?? 0.0,
      chatQuotaAllowed: json['chat_quota_allowed'] as bool? ?? true,
      chatQuotaResetAt: (json['chat_quota_reset_at'] as num?)?.toInt(),
      phoneCallQuota: json['phone_call_quota'] == null
          ? null
          : PhoneCallQuota.fromJson(
              json['phone_call_quota'] as Map<String, dynamic>),
    );

Map<String, dynamic> _$UserSubscriptionResponseToJson(
        UserSubscriptionResponse instance) =>
    <String, dynamic>{
      'subscription': instance.subscription,
      'transcription_seconds_used': instance.transcriptionSecondsUsed,
      'transcription_seconds_limit': instance.transcriptionSecondsLimit,
      'words_transcribed_used': instance.wordsTranscribedUsed,
      'words_transcribed_limit': instance.wordsTranscribedLimit,
      'insights_gained_used': instance.insightsGainedUsed,
      'insights_gained_limit': instance.insightsGainedLimit,
      'memories_created_used': instance.memoriesCreatedUsed,
      'memories_created_limit': instance.memoriesCreatedLimit,
      'available_plans': instance.availablePlans,
      'show_subscription_ui': instance.showSubscriptionUi,
      'chat_quota_used': instance.chatQuotaUsed,
      'chat_quota_unit': instance.chatQuotaUnit,
      'chat_quota_percent': instance.chatQuotaPercent,
      'chat_quota_allowed': instance.chatQuotaAllowed,
      'chat_quota_reset_at': instance.chatQuotaResetAt,
      'phone_call_quota': instance.phoneCallQuota,
    };
