// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'announcement.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

Targeting _$TargetingFromJson(Map<String, dynamic> json) => Targeting(
      appVersionMin: json['app_version_min'] as String?,
      appVersionMax: json['app_version_max'] as String?,
      firmwareVersionMin: json['firmware_version_min'] as String?,
      firmwareVersionMax: json['firmware_version_max'] as String?,
      deviceModels: (json['device_models'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList(),
      platforms: (json['platforms'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList(),
      trigger: $enumDecodeNullable(_$TriggerTypeEnumMap, json['trigger']) ??
          TriggerType.versionUpgrade,
      testUids: (json['test_uids'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList(),
    );

Map<String, dynamic> _$TargetingToJson(Targeting instance) => <String, dynamic>{
      'app_version_min': instance.appVersionMin,
      'app_version_max': instance.appVersionMax,
      'firmware_version_min': instance.firmwareVersionMin,
      'firmware_version_max': instance.firmwareVersionMax,
      'device_models': instance.deviceModels,
      'platforms': instance.platforms,
      'trigger': _$TriggerTypeEnumMap[instance.trigger]!,
      'test_uids': instance.testUids,
    };

const _$TriggerTypeEnumMap = {
  TriggerType.immediate: 'immediate',
  TriggerType.versionUpgrade: 'version_upgrade',
  TriggerType.firmwareUpgrade: 'firmware_upgrade',
};

Display _$DisplayFromJson(Map<String, dynamic> json) => Display(
      priority: (json['priority'] as num?)?.toInt() ?? 0,
      startAt: json['start_at'] == null
          ? null
          : DateTime.parse(json['start_at'] as String),
      expiresAt: json['expires_at'] == null
          ? null
          : DateTime.parse(json['expires_at'] as String),
      dismissible: json['dismissible'] as bool? ?? true,
      showOnce: json['show_once'] as bool? ?? true,
    );

Map<String, dynamic> _$DisplayToJson(Display instance) => <String, dynamic>{
      'priority': instance.priority,
      'start_at': instance.startAt?.toIso8601String(),
      'expires_at': instance.expiresAt?.toIso8601String(),
      'dismissible': instance.dismissible,
      'show_once': instance.showOnce,
    };

ChangelogItem _$ChangelogItemFromJson(Map<String, dynamic> json) =>
    ChangelogItem(
      title: json['title'] as String,
      description: json['description'] as String,
      icon: json['icon'] as String?,
    );

Map<String, dynamic> _$ChangelogItemToJson(ChangelogItem instance) =>
    <String, dynamic>{
      'title': instance.title,
      'description': instance.description,
      'icon': instance.icon,
    };

ChangelogContent _$ChangelogContentFromJson(Map<String, dynamic> json) =>
    ChangelogContent(
      title: json['title'] as String,
      changes: (json['changes'] as List<dynamic>)
          .map((e) => ChangelogItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$ChangelogContentToJson(ChangelogContent instance) =>
    <String, dynamic>{
      'title': instance.title,
      'changes': instance.changes.map((e) => e.toJson()).toList(),
    };

FeatureStep _$FeatureStepFromJson(Map<String, dynamic> json) => FeatureStep(
      title: json['title'] as String,
      description: json['description'] as String,
      imageUrl: json['image_url'] as String?,
      videoUrl: json['video_url'] as String?,
      highlightText: json['highlight_text'] as String?,
    );

Map<String, dynamic> _$FeatureStepToJson(FeatureStep instance) =>
    <String, dynamic>{
      'title': instance.title,
      'description': instance.description,
      'image_url': instance.imageUrl,
      'video_url': instance.videoUrl,
      'highlight_text': instance.highlightText,
    };

FeatureContent _$FeatureContentFromJson(Map<String, dynamic> json) =>
    FeatureContent(
      title: json['title'] as String,
      steps: (json['steps'] as List<dynamic>)
          .map((e) => FeatureStep.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$FeatureContentToJson(FeatureContent instance) =>
    <String, dynamic>{
      'title': instance.title,
      'steps': instance.steps.map((e) => e.toJson()).toList(),
    };

AnnouncementCTA _$AnnouncementCTAFromJson(Map<String, dynamic> json) =>
    AnnouncementCTA(
      text: json['text'] as String,
      action: json['action'] as String,
    );

Map<String, dynamic> _$AnnouncementCTAToJson(AnnouncementCTA instance) =>
    <String, dynamic>{
      'text': instance.text,
      'action': instance.action,
    };

AnnouncementContent _$AnnouncementContentFromJson(Map<String, dynamic> json) =>
    AnnouncementContent(
      title: json['title'] as String,
      body: json['body'] as String,
      imageUrl: json['image_url'] as String?,
      cta: json['cta'] == null
          ? null
          : AnnouncementCTA.fromJson(json['cta'] as Map<String, dynamic>),
    );

Map<String, dynamic> _$AnnouncementContentToJson(
        AnnouncementContent instance) =>
    <String, dynamic>{
      'title': instance.title,
      'body': instance.body,
      'image_url': instance.imageUrl,
      'cta': instance.cta?.toJson(),
    };

Announcement _$AnnouncementFromJson(Map<String, dynamic> json) => Announcement(
      id: json['id'] as String,
      type: $enumDecode(_$AnnouncementTypeEnumMap, json['type']),
      createdAt: DateTime.parse(json['created_at'] as String),
      active: json['active'] as bool? ?? true,
      appVersion: json['app_version'] as String?,
      firmwareVersion: json['firmware_version'] as String?,
      deviceModels: (json['device_models'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      expiresAt: json['expires_at'] == null
          ? null
          : DateTime.parse(json['expires_at'] as String),
      targeting: json['targeting'] == null
          ? null
          : Targeting.fromJson(json['targeting'] as Map<String, dynamic>),
      display: json['display'] == null
          ? null
          : Display.fromJson(json['display'] as Map<String, dynamic>),
      content: json['content'] as Map<String, dynamic>,
    );

Map<String, dynamic> _$AnnouncementToJson(Announcement instance) =>
    <String, dynamic>{
      'id': instance.id,
      'type': _$AnnouncementTypeEnumMap[instance.type]!,
      'created_at': instance.createdAt.toIso8601String(),
      'active': instance.active,
      'app_version': instance.appVersion,
      'firmware_version': instance.firmwareVersion,
      'device_models': instance.deviceModels,
      'expires_at': instance.expiresAt?.toIso8601String(),
      'targeting': instance.targeting?.toJson(),
      'display': instance.display?.toJson(),
      'content': instance.content,
    };

const _$AnnouncementTypeEnumMap = {
  AnnouncementType.changelog: 'changelog',
  AnnouncementType.feature: 'feature',
  AnnouncementType.announcement: 'announcement',
};
