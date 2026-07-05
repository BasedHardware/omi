import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
// Phase 4.1 — none of these classes typedef to their GeneratedDailySummary* types.
// The generated fields are all nullable (String?/bool?/int?/double?) while these
// classes coerce them to non-null with defaults (?? '', ?? 'medium', ?? false,
// ?? 0, ?? 0.0). DayStats.formattedDuration and DailySummary.formattedDate are
// computed getters, and DailySummary.fromJson carries a degraded try/catch fallback.
// All are kept as deliberate adapters.

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
    return ActionItemSummary.fromGenerated(wire.GeneratedDailySummaryActionItem.fromJson(json));
  }

  factory ActionItemSummary.fromGenerated(wire.GeneratedDailySummaryActionItem generated) {
    return ActionItemSummary(
      description: generated.description ?? '',
      priority: generated.priority ?? 'medium',
      sourceConversationId: generated.sourceConversationId,
      completed: generated.completed ?? false,
    );
  }
}

class TopicHighlight {
  final String topic;
  final String emoji;
  final String summary;
  final List<String> conversationIds;

  TopicHighlight({required this.topic, required this.emoji, required this.summary, this.conversationIds = const []});

  factory TopicHighlight.fromJson(Map<String, dynamic> json) {
    return TopicHighlight.fromGenerated(wire.GeneratedDailySummaryTopicHighlight.fromJson(json));
  }

  factory TopicHighlight.fromGenerated(wire.GeneratedDailySummaryTopicHighlight generated) {
    return TopicHighlight(
      topic: generated.topic ?? '',
      emoji: generated.emoji ?? '💡',
      summary: generated.summary ?? '',
      conversationIds: generated.conversationIds ?? [],
    );
  }
}

class UnresolvedQuestion {
  final String question;
  final String? conversationId;

  UnresolvedQuestion({required this.question, this.conversationId});

  factory UnresolvedQuestion.fromJson(Map<String, dynamic> json) {
    return UnresolvedQuestion.fromGenerated(wire.GeneratedDailySummaryUnresolvedQuestion.fromJson(json));
  }

  factory UnresolvedQuestion.fromGenerated(wire.GeneratedDailySummaryUnresolvedQuestion generated) {
    return UnresolvedQuestion(question: generated.question ?? '', conversationId: generated.conversationId);
  }
}

class DecisionMade {
  final String decision;
  final String? conversationId;

  DecisionMade({required this.decision, this.conversationId});

  factory DecisionMade.fromJson(Map<String, dynamic> json) {
    return DecisionMade.fromGenerated(wire.GeneratedDailySummaryDecisionMade.fromJson(json));
  }

  factory DecisionMade.fromGenerated(wire.GeneratedDailySummaryDecisionMade generated) {
    return DecisionMade(decision: generated.decision ?? '', conversationId: generated.conversationId);
  }
}

class KnowledgeNugget {
  final String insight;
  final String? conversationId;

  KnowledgeNugget({required this.insight, this.conversationId});

  factory KnowledgeNugget.fromJson(Map<String, dynamic> json) {
    return KnowledgeNugget.fromGenerated(wire.GeneratedDailySummaryKnowledgeNugget.fromJson(json));
  }

  factory KnowledgeNugget.fromGenerated(wire.GeneratedDailySummaryKnowledgeNugget generated) {
    return KnowledgeNugget(insight: generated.insight ?? '', conversationId: generated.conversationId);
  }
}

class DayStats {
  final int totalConversations; // Excluding discarded
  final int totalDurationMinutes; // Excluding discarded
  final int actionItemsCount;

  DayStats({this.totalConversations = 0, this.totalDurationMinutes = 0, this.actionItemsCount = 0});

  factory DayStats.fromJson(Map<String, dynamic> json) {
    return DayStats.fromGenerated(wire.GeneratedDailySummaryDayStats.fromJson(json));
  }

  factory DayStats.fromGenerated(wire.GeneratedDailySummaryDayStats generated) {
    return DayStats(
      totalConversations: generated.totalConversations ?? 0,
      totalDurationMinutes: generated.totalDurationMinutes ?? 0,
      actionItemsCount: generated.actionItemsCount ?? 0,
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

  LocationPin({required this.latitude, required this.longitude, this.address, this.conversationId, this.time});

  factory LocationPin.fromJson(Map<String, dynamic> json) {
    return LocationPin.fromGenerated(wire.GeneratedDailySummaryLocationPin.fromJson(json));
  }

  factory LocationPin.fromGenerated(wire.GeneratedDailySummaryLocationPin generated) {
    return LocationPin(
      latitude: generated.latitude ?? 0.0,
      longitude: generated.longitude ?? 0.0,
      address: generated.address,
      conversationId: generated.conversationId,
      time: generated.time,
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
    try {
      return DailySummary.fromGenerated(wire.GeneratedDailySummaryResponse.fromJson(json));
    } catch (_) {
      // Degraded fallback: generated parser failed on malformed data.
      // Return a minimal summary with defaults rather than hand-parsing partial JSON.
      return DailySummary(
        id: '',
        date: '',
        createdAt: DateTime.now(),
        headline: 'Your Day in Review',
        overview: '',
        dayEmoji: '📅',
        stats: DayStats(),
      );
    }
  }

  factory DailySummary.fromGenerated(wire.GeneratedDailySummaryResponse generated, {DateTime? createdAt}) {
    return DailySummary(
      id: generated.id ?? '',
      date: generated.date ?? '',
      createdAt: createdAt ?? generated.createdAt ?? DateTime.now(),
      headline: generated.headline ?? 'Your Day in Review',
      overview: generated.overview ?? '',
      dayEmoji: generated.dayEmoji ?? '📅',
      stats: generated.stats == null ? DayStats() : DayStats.fromGenerated(generated.stats!),
      highlights: generated.highlights?.map(TopicHighlight.fromGenerated).toList() ?? [],
      actionItems: generated.actionItems?.map(ActionItemSummary.fromGenerated).toList() ?? [],
      unresolvedQuestions: generated.unresolvedQuestions?.map(UnresolvedQuestion.fromGenerated).toList() ?? [],
      decisionsMade: generated.decisionsMade?.map(DecisionMade.fromGenerated).toList() ?? [],
      knowledgeNuggets: generated.knowledgeNuggets?.map(KnowledgeNugget.fromGenerated).toList() ?? [],
      locations: generated.locations?.map(LocationPin.fromGenerated).toList() ?? [],
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
        'December',
      ];

      return '${months[month - 1]} $day, ${parts[0]}';
    }
    return date;
  }
}
