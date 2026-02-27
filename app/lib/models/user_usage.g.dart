// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'user_usage.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

UsageStats _$UsageStatsFromJson(Map<String, dynamic> json) => UsageStats(
      transcriptionSeconds: (json['transcription_seconds'] as num).toInt(),
      wordsTranscribed: (json['words_transcribed'] as num).toInt(),
      insightsGained: (json['insights_gained'] as num).toInt(),
      memoriesCreated: (json['memories_created'] as num).toInt(),
    );

Map<String, dynamic> _$UsageStatsToJson(UsageStats instance) =>
    <String, dynamic>{
      'transcription_seconds': instance.transcriptionSeconds,
      'words_transcribed': instance.wordsTranscribed,
      'insights_gained': instance.insightsGained,
      'memories_created': instance.memoriesCreated,
    };

UsageHistoryPoint _$UsageHistoryPointFromJson(Map<String, dynamic> json) =>
    UsageHistoryPoint(
      date: json['date'] as String,
      transcriptionSeconds: (json['transcription_seconds'] as num).toInt(),
      wordsTranscribed: (json['words_transcribed'] as num).toInt(),
      insightsGained: (json['insights_gained'] as num).toInt(),
      memoriesCreated: (json['memories_created'] as num).toInt(),
    );

Map<String, dynamic> _$UsageHistoryPointToJson(UsageHistoryPoint instance) =>
    <String, dynamic>{
      'date': instance.date,
      'transcription_seconds': instance.transcriptionSeconds,
      'words_transcribed': instance.wordsTranscribed,
      'insights_gained': instance.insightsGained,
      'memories_created': instance.memoriesCreated,
    };

UserUsageResponse _$UserUsageResponseFromJson(Map<String, dynamic> json) =>
    UserUsageResponse(
      today: json['today'] == null
          ? null
          : UsageStats.fromJson(json['today'] as Map<String, dynamic>),
      monthly: json['monthly'] == null
          ? null
          : UsageStats.fromJson(json['monthly'] as Map<String, dynamic>),
      yearly: json['yearly'] == null
          ? null
          : UsageStats.fromJson(json['yearly'] as Map<String, dynamic>),
      allTime: json['all_time'] == null
          ? null
          : UsageStats.fromJson(json['all_time'] as Map<String, dynamic>),
      history: (json['history'] as List<dynamic>?)
          ?.map((e) => UsageHistoryPoint.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$UserUsageResponseToJson(UserUsageResponse instance) =>
    <String, dynamic>{
      'today': instance.today,
      'monthly': instance.monthly,
      'yearly': instance.yearly,
      'all_time': instance.allTime,
      'history': instance.history,
    };
