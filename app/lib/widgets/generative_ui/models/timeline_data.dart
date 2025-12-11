import 'package:flutter/material.dart';

/// Event types for timeline with associated colors
enum TimelineEventLabel {
  context,
  conflict,
  claim,
  decision,
  reaction,
  humanImpact,
  nextSteps,
  other;

  static TimelineEventLabel fromString(String? label) {
    if (label == null) return TimelineEventLabel.other;
    final normalized = label.toLowerCase().replaceAll(' ', '').replaceAll('_', '');
    switch (normalized) {
      case 'context':
        return TimelineEventLabel.context;
      case 'conflict':
        return TimelineEventLabel.conflict;
      case 'claim':
        return TimelineEventLabel.claim;
      case 'decision':
        return TimelineEventLabel.decision;
      case 'reaction':
        return TimelineEventLabel.reaction;
      case 'humanimpact':
        return TimelineEventLabel.humanImpact;
      case 'nextsteps':
        return TimelineEventLabel.nextSteps;
      default:
        return TimelineEventLabel.other;
    }
  }

  String get displayName {
    switch (this) {
      case TimelineEventLabel.context:
        return 'Context';
      case TimelineEventLabel.conflict:
        return 'Conflict';
      case TimelineEventLabel.claim:
        return 'Claim';
      case TimelineEventLabel.decision:
        return 'Decision';
      case TimelineEventLabel.reaction:
        return 'Reaction';
      case TimelineEventLabel.humanImpact:
        return 'Human impact';
      case TimelineEventLabel.nextSteps:
        return 'Next steps';
      case TimelineEventLabel.other:
        return 'Event';
    }
  }

  Color get color {
    switch (this) {
      case TimelineEventLabel.context:
        return const Color(0xFF3B82F6); // Blue
      case TimelineEventLabel.conflict:
        return const Color(0xFFEF4444); // Red
      case TimelineEventLabel.claim:
        return const Color(0xFFF59E0B); // Amber
      case TimelineEventLabel.decision:
        return const Color(0xFF22C55E); // Green
      case TimelineEventLabel.reaction:
        return const Color(0xFF8B5CF6); // Purple
      case TimelineEventLabel.humanImpact:
        return const Color(0xFFEC4899); // Pink
      case TimelineEventLabel.nextSteps:
        return const Color(0xFF06B6D4); // Cyan
      case TimelineEventLabel.other:
        return const Color(0xFF6B7280); // Gray
    }
  }
}

/// Data model for a single timeline event
class TimelineEventData {
  final String time;
  final String label;
  final TimelineEventLabel labelType;
  final String description;

  const TimelineEventData({
    required this.time,
    required this.label,
    required this.labelType,
    required this.description,
  });

  factory TimelineEventData.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
  }) {
    final label = attributes['label'] ?? 'Event';
    return TimelineEventData(
      time: attributes['time'] ?? '',
      label: label,
      labelType: TimelineEventLabel.fromString(label),
      description: innerContent.trim(),
    );
  }
}

/// Data model for the entire timeline component
class TimelineDisplayData {
  final String? title;
  final List<TimelineEventData> events;

  const TimelineDisplayData({
    this.title,
    required this.events,
  });

  bool get isEmpty => events.isEmpty;
}
