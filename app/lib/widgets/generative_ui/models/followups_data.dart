import 'package:flutter/material.dart';

/// Types for follow-up items
enum FollowupItemType {
  factCheck,
  verification,
  question,
  other;

  static FollowupItemType fromString(String? type) {
    if (type == null) return FollowupItemType.other;
    final normalized = type.toLowerCase().replaceAll(' ', '').replaceAll('-', '').replaceAll('_', '');
    switch (normalized) {
      case 'factcheck':
        return FollowupItemType.factCheck;
      case 'verification':
        return FollowupItemType.verification;
      case 'question':
        return FollowupItemType.question;
      default:
        return FollowupItemType.other;
    }
  }

  String get displayName {
    switch (this) {
      case FollowupItemType.factCheck:
        return 'Fact-check';
      case FollowupItemType.verification:
        return 'Verification';
      case FollowupItemType.question:
        return 'Question';
      case FollowupItemType.other:
        return 'To-do';
    }
  }

  Color get color {
    switch (this) {
      case FollowupItemType.factCheck:
        return const Color(0xFFF97316); // Orange
      case FollowupItemType.verification:
        return const Color(0xFF3B82F6); // Blue
      case FollowupItemType.question:
        return const Color(0xFF8B5CF6); // Purple
      case FollowupItemType.other:
        return const Color(0xFF6B7280); // Gray
    }
  }

  Color get backgroundColor {
    switch (this) {
      case FollowupItemType.factCheck:
        return const Color(0xFFF97316).withOpacity(0.15);
      case FollowupItemType.verification:
        return const Color(0xFF3B82F6).withOpacity(0.15);
      case FollowupItemType.question:
        return const Color(0xFF8B5CF6).withOpacity(0.15);
      case FollowupItemType.other:
        return const Color(0xFF6B7280).withOpacity(0.15);
    }
  }

  IconData get icon {
    switch (this) {
      case FollowupItemType.factCheck:
        return Icons.fact_check_outlined;
      case FollowupItemType.verification:
        return Icons.verified_outlined;
      case FollowupItemType.question:
        return Icons.help_outline;
      case FollowupItemType.other:
        return Icons.checklist;
    }
  }
}

/// Data model for a single follow-up item
class FollowupItemData {
  final FollowupItemType type;
  final String content;

  const FollowupItemData({
    required this.type,
    required this.content,
  });

  factory FollowupItemData.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
  }) {
    return FollowupItemData(
      type: FollowupItemType.fromString(attributes['type']),
      content: innerContent.trim(),
    );
  }
}

/// Data model for the entire followups component
class FollowupsDisplayData {
  final List<FollowupItemData> items;

  const FollowupsDisplayData({
    required this.items,
  });

  bool get isEmpty => items.isEmpty;
}
