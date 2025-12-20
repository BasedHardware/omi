import 'package:flutter/material.dart';

/// Step types for flow visualization
enum FlowStepType {
  main,
  exception,
  alternative,
  optional;

  static FlowStepType fromString(String? type) {
    if (type == null) return FlowStepType.main;
    switch (type.toLowerCase().trim()) {
      case 'main':
      case 'primary':
        return FlowStepType.main;
      case 'exception':
      case 'error':
        return FlowStepType.exception;
      case 'alternative':
      case 'alt':
        return FlowStepType.alternative;
      case 'optional':
        return FlowStepType.optional;
      default:
        return FlowStepType.main;
    }
  }

  String get displayName {
    switch (this) {
      case FlowStepType.main:
        return 'Main';
      case FlowStepType.exception:
        return 'Exception';
      case FlowStepType.alternative:
        return 'Alternative';
      case FlowStepType.optional:
        return 'Optional';
    }
  }

  Color get color {
    switch (this) {
      case FlowStepType.main:
        return const Color(0xFF3B82F6); // Blue
      case FlowStepType.exception:
        return const Color(0xFFEF4444); // Red
      case FlowStepType.alternative:
        return const Color(0xFFF59E0B); // Amber
      case FlowStepType.optional:
        return const Color(0xFF6B7280); // Gray
    }
  }

  Color get backgroundColor {
    return color.withOpacity(0.12);
  }

  IconData get icon {
    switch (this) {
      case FlowStepType.main:
        return Icons.arrow_forward_rounded;
      case FlowStepType.exception:
        return Icons.warning_amber_rounded;
      case FlowStepType.alternative:
        return Icons.alt_route_rounded;
      case FlowStepType.optional:
        return Icons.more_horiz_rounded;
    }
  }
}

/// A single step in a flow
class FlowStepData {
  final String content;
  final FlowStepType type;

  const FlowStepData({
    required this.content,
    this.type = FlowStepType.main,
  });

  factory FlowStepData.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
  }) {
    return FlowStepData(
      content: innerContent.trim(),
      type: FlowStepType.fromString(attributes['type']),
    );
  }
}

/// Data model for a complete flow with steps
class FlowData {
  final String title;
  final List<FlowStepData> steps;

  const FlowData({
    required this.title,
    this.steps = const [],
  });

  bool get isEmpty => title.isEmpty && steps.isEmpty;
  bool get hasSteps => steps.isNotEmpty;

  int get mainStepCount => steps.where((s) => s.type == FlowStepType.main).length;
  int get exceptionCount => steps.where((s) => s.type == FlowStepType.exception).length;
}
