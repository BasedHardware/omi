class ActionItemSummary {
  final String description;
  final String priority; // high, medium, low
  final String? sourceConversationId;
  final bool completed;

  ActionItemSummary({
    required this.description,
    this.priority = 'medium',
    this.sourceConversationId,
    this.completed = false,
  });

  factory ActionItemSummary.fromJson(Map<String, dynamic> json) {
    return ActionItemSummary(
      description: _toString(json['description']) ?? '',
      priority: _toString(json['priority']) ?? 'medium',
      sourceConversationId: _toString(json['source_conversation_id']),
      completed: json['completed'] == true,
    );
  }
}

class TopicHighlight {
  final String topic;
  final String emoji;
  final String summary;
  final List<String> conversationIds;

  TopicHighlight({
    required this.topic,
    required this.emoji,
    required this.summary,
    this.conversationIds = const [],
  });

  factory TopicHighlight.fromJson(Map<String, dynamic> json) {
    return TopicHighlight(
      topic: _toString(json['topic']) ?? '',
      emoji: _toString(json['emoji']) ?? '💡',
      summary: _toString(json['summary']) ?? '',
      conversationIds: (json['conversation_ids'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
    );
  }
}

class UnresolvedQuestion {
  final String question;
  final String? conversationId;

  UnresolvedQuestion({
    required this.question,
    this.conversationId,
  });

  factory UnresolvedQuestion.fromJson(Map<String, dynamic> json) {
    return UnresolvedQuestion(
      question: _toString(json['question']) ?? '',
      conversationId: _toString(json['conversation_id']),
    );
  }
}

class DecisionMade {
  final String decision;
  final String? conversationId;

  DecisionMade({
    required this.decision,
    this.conversationId,
  });

  factory DecisionMade.fromJson(Map<String, dynamic> json) {
    return DecisionMade(
      decision: _toString(json['decision']) ?? '',
      conversationId: _toString(json['conversation_id']),
    );
  }
}

class KnowledgeNugget {
  final String insight;
  final String? conversationId;

  KnowledgeNugget({
    required this.insight,
    this.conversationId,
  });

  factory KnowledgeNugget.fromJson(Map<String, dynamic> json) {
    return KnowledgeNugget(
      insight: _toString(json['insight']) ?? '',
      conversationId: _toString(json['conversation_id']),
    );
  }
}

class DayStats {
  final int totalConversations; // Excluding discarded
  final int totalDurationMinutes; // Excluding discarded
  final int actionItemsCount;

  DayStats({
    this.totalConversations = 0,
    this.totalDurationMinutes = 0,
    this.actionItemsCount = 0,
  });

  factory DayStats.fromJson(Map<String, dynamic> json) {
    return DayStats(
      totalConversations: _toInt(json['total_conversations']) ?? 0,
      totalDurationMinutes: _toInt(json['total_duration_minutes']) ?? 0,
      actionItemsCount: _toInt(json['action_items_count']) ?? 0,
    );
  }

  String get formattedDuration {
    if (totalDurationMinutes < 60) {
      return '${totalDurationMinutes}m';
    }
    final hours = totalDurationMinutes ~/ 60;
    final mins = totalDurationMinutes % 60;
    return mins > 0 ? '${hours}h ${mins}m' : '${hours}h';
  }
}

class LocationPin {
  final double latitude;
  final double longitude;
  final String? address;
  final String? conversationId;
  final String? time;

  LocationPin({
    required this.latitude,
    required this.longitude,
    this.address,
    this.conversationId,
    this.time,
  });

  factory LocationPin.fromJson(Map<String, dynamic> json) {
    return LocationPin(
      latitude: _toDouble(json['latitude']) ?? 0.0,
      longitude: _toDouble(json['longitude']) ?? 0.0,
      address: _toString(json['address']),
      conversationId: _toString(json['conversation_id']),
      time: _toString(json['time']),
    );
  }
}

class DailySummary {
  final String id;
  final String date; // YYYY-MM-DD
  final DateTime createdAt;

  // Headline & Overview
  final String headline;
  final String overview;
  final String dayEmoji;

  // Stats
  final DayStats stats;

  // Core content (all optional - skip if not enough quality data)
  final List<TopicHighlight> highlights;
  final List<ActionItemSummary> actionItems;
  final List<UnresolvedQuestion> unresolvedQuestions; // Max 3
  final List<DecisionMade> decisionsMade; // Max 3
  final List<KnowledgeNugget> knowledgeNuggets; // Max 3

  // Locations
  final List<LocationPin> locations;

  DailySummary({
    required this.id,
    required this.date,
    required this.createdAt,
    required this.headline,
    required this.overview,
    this.dayEmoji = '📅',
    required this.stats,
    this.highlights = const [],
    this.actionItems = const [],
    this.unresolvedQuestions = const [],
    this.decisionsMade = const [],
    this.knowledgeNuggets = const [],
    this.locations = const [],
  });

  factory DailySummary.fromJson(Map<String, dynamic> json) {
    DateTime createdAt;
    try {
      final createdAtValue = json['created_at'];
      if (createdAtValue is String) {
        createdAt = DateTime.parse(createdAtValue);
      } else {
        createdAt = DateTime.now();
      }
    } catch (e) {
      createdAt = DateTime.now();
    }

    return DailySummary(
      id: _toString(json['id']) ?? '',
      date: _toString(json['date']) ?? '',
      createdAt: createdAt,
      headline: _toString(json['headline']) ?? 'Your Day in Review',
      overview: _toString(json['overview']) ?? '',
      dayEmoji: _toString(json['day_emoji']) ?? '📅',
      stats: json['stats'] != null && json['stats'] is Map<String, dynamic>
          ? DayStats.fromJson(json['stats'])
          : DayStats(),
      highlights: _parseList<TopicHighlight>(
        json['highlights'],
        (e) => TopicHighlight.fromJson(e as Map<String, dynamic>),
      ),
      actionItems: _parseList<ActionItemSummary>(
        json['action_items'],
        (e) => ActionItemSummary.fromJson(e as Map<String, dynamic>),
      ),
      unresolvedQuestions: _parseList<UnresolvedQuestion>(
        json['unresolved_questions'],
        (e) => UnresolvedQuestion.fromJson(e as Map<String, dynamic>),
      ),
      decisionsMade: _parseList<DecisionMade>(
        json['decisions_made'],
        (e) => DecisionMade.fromJson(e as Map<String, dynamic>),
      ),
      knowledgeNuggets: _parseList<KnowledgeNugget>(
        json['knowledge_nuggets'],
        (e) => KnowledgeNugget.fromJson(e as Map<String, dynamic>),
      ),
      locations: _parseList<LocationPin>(
        json['locations'],
        (e) => LocationPin.fromJson(e as Map<String, dynamic>),
      ),
    );
  }

  String get formattedDate {
    final parts = date.split('-');
    if (parts.length == 3) {
      final month = int.tryParse(parts[1]) ?? 1;
      final day = int.tryParse(parts[2]) ?? 1;

      final months = [
        'January',
        'February',
        'March',
        'April',
        'May',
        'June',
        'July',
        'August',
        'September',
        'October',
        'November',
        'December'
      ];

      return '${months[month - 1]} $day, ${parts[0]}';
    }
    return date;
  }
}

// Helper functions for safe type conversion
String? _toString(dynamic value) {
  if (value == null) return null;
  return value.toString();
}

int? _toInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is double) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

double? _toDouble(dynamic value) {
  if (value == null) return null;
  if (value is double) return value;
  if (value is int) return value.toDouble();
  if (value is String) return double.tryParse(value);
  return null;
}

List<T> _parseList<T>(dynamic value, T Function(dynamic) parser) {
  if (value == null) return [];
  if (value is! List) return [];
  try {
    return value.map((e) => parser(e)).toList();
  } catch (e) {
    return [];
  }
}
