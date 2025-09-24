// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'subscription.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

Subscription _$SubscriptionFromJson(Map<String, dynamic> json) => Subscription(
      plan: $enumDecode(_$PlanTypeEnumMap, json['plan']),
      status: $enumDecode(_$SubscriptionStatusEnumMap, json['status']),
      currentPeriodEnd: (json['current_period_end'] as num?)?.toInt(),
      stripeSubscriptionId: json['stripe_subscription_id'] as String?,
      features: (json['features'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      cancelAtPeriodEnd: json['cancel_at_period_end'] as bool? ?? false,
    );

Map<String, dynamic> _$SubscriptionToJson(Subscription instance) =>
    <String, dynamic>{
      'plan': _$PlanTypeEnumMap[instance.plan]!,
      'status': _$SubscriptionStatusEnumMap[instance.status]!,
      'current_period_end': instance.currentPeriodEnd,
      'stripe_subscription_id': instance.stripeSubscriptionId,
      'features': instance.features,
      'cancel_at_period_end': instance.cancelAtPeriodEnd,
    };

const _$PlanTypeEnumMap = {
  PlanType.basic: 'basic',
  PlanType.unlimited: 'unlimited',
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
      showSubscriptionUi: json['show_subscription_ui'] as bool? ?? false,
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
    };
