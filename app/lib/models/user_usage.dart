import 'package:json_annotation/json_annotation.dart';

part 'user_usage.g.dart';

@JsonSerializable(fieldRename: FieldRename.snake)
class UsageStats {
  final int transcriptionSeconds;
  final int wordsTranscribed;
  final int insightsGained;
  final int memoriesCreated;

  UsageStats({
    required this.transcriptionSeconds,
    required this.wordsTranscribed,
    required this.insightsGained,
    required this.memoriesCreated,
  });

  factory UsageStats.fromJson(Map<String, dynamic> json) => _$UsageStatsFromJson(json);
  Map<String, dynamic> toJson() => _$UsageStatsToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class UsageHistoryPoint {
  final String date;
  final int transcriptionSeconds;
  final int wordsTranscribed;
  final int insightsGained;
  final int memoriesCreated;

  UsageHistoryPoint({
    required this.date,
    required this.transcriptionSeconds,
    required this.wordsTranscribed,
    required this.insightsGained,
    required this.memoriesCreated,
  });

  factory UsageHistoryPoint.fromJson(Map<String, dynamic> json) => _$UsageHistoryPointFromJson(json);
  Map<String, dynamic> toJson() => _$UsageHistoryPointToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class UserUsageResponse {
  final UsageStats? today;
  final UsageStats? monthly;
  final UsageStats? yearly;
  final UsageStats? allTime;
  final List<UsageHistoryPoint>? history;

  UserUsageResponse({
    this.today,
    this.monthly,
    this.yearly,
    this.allTime,
    this.history,
  });

  factory UserUsageResponse.fromJson(Map<String, dynamic> json) => _$UserUsageResponseFromJson(json);
  Map<String, dynamic> toJson() => _$UserUsageResponseToJson(this);
}
