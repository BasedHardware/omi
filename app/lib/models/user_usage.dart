import 'package:omi/backend/schema/gen/subscription_usage_wire.g.dart' as wire;

class UsageStats {
  final int transcriptionSeconds;
  final int speechSeconds;
  final int wordsTranscribed;
  final int insightsGained;
  final int memoriesCreated;

  UsageStats({
    required this.transcriptionSeconds,
    required this.speechSeconds,
    required this.wordsTranscribed,
    required this.insightsGained,
    required this.memoriesCreated,
  });

  factory UsageStats.fromJson(Map<String, dynamic> json) {
    return UsageStats.fromGenerated(wire.GeneratedUsageStats.fromJson(json));
  }

  factory UsageStats.fromGenerated(wire.GeneratedUsageStats generated) {
    return UsageStats(
      transcriptionSeconds: generated.transcriptionSeconds,
      speechSeconds: generated.speechSeconds,
      wordsTranscribed: generated.wordsTranscribed,
      insightsGained: generated.insightsGained,
      memoriesCreated: generated.memoriesCreated,
    );
  }

  wire.GeneratedUsageStats toGenerated() {
    return wire.GeneratedUsageStats(
      transcriptionSeconds: transcriptionSeconds,
      speechSeconds: speechSeconds,
      wordsTranscribed: wordsTranscribed,
      insightsGained: insightsGained,
      memoriesCreated: memoriesCreated,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class UsageHistoryPoint {
  final String date;
  final int transcriptionSeconds;
  final int speechSeconds;
  final int wordsTranscribed;
  final int insightsGained;
  final int memoriesCreated;

  UsageHistoryPoint({
    required this.date,
    required this.transcriptionSeconds,
    required this.speechSeconds,
    required this.wordsTranscribed,
    required this.insightsGained,
    required this.memoriesCreated,
  });

  factory UsageHistoryPoint.fromJson(Map<String, dynamic> json) {
    return UsageHistoryPoint.fromGenerated(wire.GeneratedUsageHistoryPoint.fromJson(json));
  }

  factory UsageHistoryPoint.fromGenerated(wire.GeneratedUsageHistoryPoint generated) {
    return UsageHistoryPoint(
      date: generated.date,
      transcriptionSeconds: generated.transcriptionSeconds,
      speechSeconds: generated.speechSeconds,
      wordsTranscribed: generated.wordsTranscribed,
      insightsGained: generated.insightsGained,
      memoriesCreated: generated.memoriesCreated,
    );
  }

  wire.GeneratedUsageHistoryPoint toGenerated() {
    return wire.GeneratedUsageHistoryPoint(
      date: date,
      transcriptionSeconds: transcriptionSeconds,
      speechSeconds: speechSeconds,
      wordsTranscribed: wordsTranscribed,
      insightsGained: insightsGained,
      memoriesCreated: memoriesCreated,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class UserUsageResponse {
  final UsageStats? today;
  final UsageStats? monthly;
  final UsageStats? yearly;
  final UsageStats? allTime;
  final List<UsageHistoryPoint>? history;

  UserUsageResponse({this.today, this.monthly, this.yearly, this.allTime, this.history});

  factory UserUsageResponse.fromJson(Map<String, dynamic> json) {
    return UserUsageResponse.fromGenerated(wire.GeneratedUserUsageResponse.fromJson(json));
  }

  factory UserUsageResponse.fromGenerated(wire.GeneratedUserUsageResponse generated) {
    return UserUsageResponse(
      today: generated.today == null ? null : UsageStats.fromGenerated(generated.today!),
      monthly: generated.monthly == null ? null : UsageStats.fromGenerated(generated.monthly!),
      yearly: generated.yearly == null ? null : UsageStats.fromGenerated(generated.yearly!),
      allTime: generated.allTime == null ? null : UsageStats.fromGenerated(generated.allTime!),
      history: generated.history?.map(UsageHistoryPoint.fromGenerated).toList(),
    );
  }

  wire.GeneratedUserUsageResponse toGenerated() {
    return wire.GeneratedUserUsageResponse(
      today: today?.toGenerated(),
      monthly: monthly?.toGenerated(),
      yearly: yearly?.toGenerated(),
      allTime: allTime?.toGenerated(),
      history: history?.map((point) => point.toGenerated()).toList(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}
