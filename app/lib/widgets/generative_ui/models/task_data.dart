import 'package:flutter/material.dart';

/// Priority levels for tasks
enum TaskPriority {
  low,
  medium,
  high,
  urgent;

  static TaskPriority fromString(String? priority) {
    if (priority == null) return TaskPriority.medium;
    final normalized = priority.toLowerCase().trim();
    switch (normalized) {
      case 'low':
        return TaskPriority.low;
      case 'medium':
        return TaskPriority.medium;
      case 'high':
        return TaskPriority.high;
      case 'urgent':
      case 'critical':
        return TaskPriority.urgent;
      default:
        return TaskPriority.medium;
    }
  }

  String get displayName {
    switch (this) {
      case TaskPriority.low:
        return 'Low';
      case TaskPriority.medium:
        return 'Medium';
      case TaskPriority.high:
        return 'High';
      case TaskPriority.urgent:
        return 'Urgent';
    }
  }

  Color get color {
    switch (this) {
      case TaskPriority.low:
        return const Color(0xFF6B7280); // Gray
      case TaskPriority.medium:
        return const Color(0xFF3B82F6); // Blue
      case TaskPriority.high:
        return const Color(0xFFF59E0B); // Amber
      case TaskPriority.urgent:
        return const Color(0xFFEF4444); // Red
    }
  }

  Color get backgroundColor {
    return color.withOpacity(0.15);
  }

  IconData get icon {
    switch (this) {
      case TaskPriority.low:
        return Icons.arrow_downward_rounded;
      case TaskPriority.medium:
        return Icons.remove_rounded;
      case TaskPriority.high:
        return Icons.arrow_upward_rounded;
      case TaskPriority.urgent:
        return Icons.priority_high_rounded;
    }
  }
}

/// Task status for tracking completion
enum TaskStatus {
  pending,
  inProgress,
  completed,
  blocked;

  static TaskStatus fromString(String? status) {
    if (status == null) return TaskStatus.pending;
    final normalized = status.toLowerCase().replaceAll(' ', '').replaceAll('_', '');
    switch (normalized) {
      case 'pending':
      case 'todo':
        return TaskStatus.pending;
      case 'inprogress':
      case 'doing':
        return TaskStatus.inProgress;
      case 'completed':
      case 'done':
        return TaskStatus.completed;
      case 'blocked':
        return TaskStatus.blocked;
      default:
        return TaskStatus.pending;
    }
  }

  String get displayName {
    switch (this) {
      case TaskStatus.pending:
        return 'To Do';
      case TaskStatus.inProgress:
        return 'In Progress';
      case TaskStatus.completed:
        return 'Done';
      case TaskStatus.blocked:
        return 'Blocked';
    }
  }

  Color get color {
    switch (this) {
      case TaskStatus.pending:
        return const Color(0xFF6B7280); // Gray
      case TaskStatus.inProgress:
        return const Color(0xFF3B82F6); // Blue
      case TaskStatus.completed:
        return const Color(0xFF22C55E); // Green
      case TaskStatus.blocked:
        return const Color(0xFFEF4444); // Red
    }
  }

  IconData get icon {
    switch (this) {
      case TaskStatus.pending:
        return Icons.radio_button_unchecked;
      case TaskStatus.inProgress:
        return Icons.timelapse_rounded;
      case TaskStatus.completed:
        return Icons.check_circle;
      case TaskStatus.blocked:
        return Icons.block_rounded;
    }
  }
}

/// Integration platform types for task export
enum TaskIntegration {
  jira,
  github,
  clickup,
  asana,
  notion,
  linear,
  trello;

  String get displayName {
    switch (this) {
      case TaskIntegration.jira:
        return 'Jira';
      case TaskIntegration.github:
        return 'GitHub Issues';
      case TaskIntegration.clickup:
        return 'ClickUp';
      case TaskIntegration.asana:
        return 'Asana';
      case TaskIntegration.notion:
        return 'Notion';
      case TaskIntegration.linear:
        return 'Linear';
      case TaskIntegration.trello:
        return 'Trello';
    }
  }

  String get iconAsset {
    // These would be actual asset paths in your project
    switch (this) {
      case TaskIntegration.jira:
        return 'assets/icons/jira.png';
      case TaskIntegration.github:
        return 'assets/icons/github.png';
      case TaskIntegration.clickup:
        return 'assets/icons/clickup.png';
      case TaskIntegration.asana:
        return 'assets/icons/asana.png';
      case TaskIntegration.notion:
        return 'assets/icons/notion.png';
      case TaskIntegration.linear:
        return 'assets/icons/linear.png';
      case TaskIntegration.trello:
        return 'assets/icons/trello.png';
    }
  }

  Color get brandColor {
    switch (this) {
      case TaskIntegration.jira:
        return const Color(0xFF0052CC);
      case TaskIntegration.github:
        return const Color(0xFF24292E);
      case TaskIntegration.clickup:
        return const Color(0xFF7B68EE);
      case TaskIntegration.asana:
        return const Color(0xFFF06A6A);
      case TaskIntegration.notion:
        return const Color(0xFF000000);
      case TaskIntegration.linear:
        return const Color(0xFF5E6AD2);
      case TaskIntegration.trello:
        return const Color(0xFF0079BF);
    }
  }
}

/// A reference to a specific part of the transcript where the task was mentioned
class TranscriptReference {
  final String time;
  final String speaker;
  final String rawText;
  final String? context;

  const TranscriptReference({
    required this.time,
    required this.speaker,
    required this.rawText,
    this.context,
  });

  factory TranscriptReference.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
  }) {
    return TranscriptReference(
      time: attributes['t'] ?? attributes['time'] ?? '',
      speaker: attributes['by'] ?? attributes['speaker'] ?? '',
      rawText: innerContent.trim(),
      context: attributes['context'],
    );
  }
}

/// Data model for a single step within a task
class TaskStepData {
  final String title;
  final String? description;
  final TaskStatus status;
  final List<TranscriptReference> transcriptRefs;

  const TaskStepData({
    required this.title,
    this.description,
    this.status = TaskStatus.pending,
    this.transcriptRefs = const [],
  });

  factory TaskStepData.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
    required List<TranscriptReference> transcriptRefs,
  }) {
    return TaskStepData(
      title: attributes['title'] ?? innerContent.trim(),
      description: attributes['description'],
      status: TaskStatus.fromString(attributes['status']),
      transcriptRefs: transcriptRefs,
    );
  }

  bool get hasTranscriptRefs => transcriptRefs.isNotEmpty;
}

/// Data model for a complete task with steps and transcript references
class TaskData {
  final String title;
  final String? summary;
  final TaskPriority priority;
  final TaskStatus status;
  final String? assignee;
  final String? dueDate;
  final List<String> labels;
  final List<TaskStepData> steps;
  final List<TranscriptReference> transcriptRefs;

  const TaskData({
    required this.title,
    this.summary,
    this.priority = TaskPriority.medium,
    this.status = TaskStatus.pending,
    this.assignee,
    this.dueDate,
    this.labels = const [],
    this.steps = const [],
    this.transcriptRefs = const [],
  });

  bool get isEmpty => title.isEmpty && steps.isEmpty;
  bool get hasSteps => steps.isNotEmpty;
  bool get hasTranscriptRefs => transcriptRefs.isNotEmpty || steps.any((s) => s.hasTranscriptRefs);

  int get totalTranscriptRefs {
    int count = transcriptRefs.length;
    for (final step in steps) {
      count += step.transcriptRefs.length;
    }
    return count;
  }

  String get statusSummary {
    final total = steps.length;
    if (total == 0) return status.displayName;
    final completed = steps.where((s) => s.status == TaskStatus.completed).length;
    return '$completed/$total steps';
  }
}
