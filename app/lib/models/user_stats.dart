class UserStats {
  final int totalWords;
  final double totalHours;
  final int currentStreak;
  final int longestStreak;
  final List<String> activeDays;

  UserStats({
    required this.totalWords,
    required this.totalHours,
    required this.currentStreak,
    required this.longestStreak,
    required this.activeDays,
  });

  factory UserStats.fromJson(Map<String, dynamic> json) {
    return UserStats(
      totalWords: json['total_words'] as int? ?? 0,
      totalHours: (json['total_hours'] as num?)?.toDouble() ?? 0.0,
      currentStreak: json['current_streak'] as int? ?? 0,
      longestStreak: json['longest_streak'] as int? ?? 0,
      activeDays: (json['active_days'] as List<dynamic>?)?.map((e) => e as String).toList() ?? [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'total_words': totalWords,
      'total_hours': totalHours,
      'current_streak': currentStreak,
      'longest_streak': longestStreak,
      'active_days': activeDays,
    };
  }
}
