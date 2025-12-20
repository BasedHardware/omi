import 'package:flutter/material.dart';
import '../models/task_data.dart';

/// Service class for managing task integrations with external platforms
/// like Jira, GitHub, ClickUp, etc.
class TaskIntegrationService {
  static final TaskIntegrationService _instance = TaskIntegrationService._internal();
  factory TaskIntegrationService() => _instance;
  TaskIntegrationService._internal();

  /// List of available integrations (would be fetched from backend in real implementation)
  final List<TaskIntegrationConfig> _availableIntegrations = [
    TaskIntegrationConfig(
      integration: TaskIntegration.jira,
      isConnected: false,
    ),
    TaskIntegrationConfig(
      integration: TaskIntegration.github,
      isConnected: false,
    ),
    TaskIntegrationConfig(
      integration: TaskIntegration.clickup,
      isConnected: false,
    ),
    TaskIntegrationConfig(
      integration: TaskIntegration.asana,
      isConnected: false,
    ),
    TaskIntegrationConfig(
      integration: TaskIntegration.notion,
      isConnected: false,
    ),
    TaskIntegrationConfig(
      integration: TaskIntegration.linear,
      isConnected: false,
    ),
    TaskIntegrationConfig(
      integration: TaskIntegration.trello,
      isConnected: false,
    ),
  ];

  List<TaskIntegrationConfig> get availableIntegrations => _availableIntegrations;

  List<TaskIntegrationConfig> get connectedIntegrations =>
      _availableIntegrations.where((i) => i.isConnected).toList();

  /// Check if any integrations are connected
  bool get hasConnectedIntegrations =>
      _availableIntegrations.any((i) => i.isConnected);

  /// Connect to an integration (placeholder for OAuth flow)
  Future<bool> connect(TaskIntegration integration) async {
    // In a real implementation, this would:
    // 1. Open OAuth flow for the integration
    // 2. Store tokens securely
    // 3. Fetch user's projects/boards/repos
    debugPrint('Connecting to ${integration.displayName}...');

    // Simulate connection delay
    await Future.delayed(const Duration(seconds: 1));

    // Update the integration status
    final index = _availableIntegrations
        .indexWhere((i) => i.integration == integration);
    if (index != -1) {
      _availableIntegrations[index] = TaskIntegrationConfig(
        integration: integration,
        isConnected: true,
        projects: [
          // Mock projects for demonstration
          IntegrationProject(id: '1', name: 'Main Project'),
          IntegrationProject(id: '2', name: 'Side Project'),
        ],
      );
    }

    return true;
  }

  /// Disconnect from an integration
  Future<void> disconnect(TaskIntegration integration) async {
    final index = _availableIntegrations
        .indexWhere((i) => i.integration == integration);
    if (index != -1) {
      _availableIntegrations[index] = TaskIntegrationConfig(
        integration: integration,
        isConnected: false,
      );
    }
  }

  /// Create a task in the specified integration
  Future<TaskCreationResult> createTask({
    required TaskIntegration integration,
    required TaskData task,
    required String projectId,
    String? additionalNotes,
  }) async {
    // In a real implementation, this would:
    // 1. Format the task according to the integration's API requirements
    // 2. Include transcript references in the description
    // 3. Map priority/status to integration-specific values
    // 4. Create the task via API
    // 5. Return the created task URL/ID

    debugPrint('Creating task in ${integration.displayName}...');
    debugPrint('Task: ${task.title}');
    debugPrint('Project ID: $projectId');

    // Simulate API call
    await Future.delayed(const Duration(milliseconds: 1500));

    // Generate mock response based on integration
    final taskUrl = _generateMockTaskUrl(integration, task.title);

    return TaskCreationResult(
      success: true,
      taskUrl: taskUrl,
      taskId: 'TASK-${DateTime.now().millisecondsSinceEpoch}',
      integration: integration,
    );
  }

  String _generateMockTaskUrl(TaskIntegration integration, String title) {
    final slug = title.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '-');
    switch (integration) {
      case TaskIntegration.jira:
        return 'https://your-org.atlassian.net/browse/PROJ-123';
      case TaskIntegration.github:
        return 'https://github.com/your-org/repo/issues/123';
      case TaskIntegration.clickup:
        return 'https://app.clickup.com/t/abc123';
      case TaskIntegration.asana:
        return 'https://app.asana.com/0/123/456';
      case TaskIntegration.notion:
        return 'https://notion.so/$slug';
      case TaskIntegration.linear:
        return 'https://linear.app/your-team/issue/TEAM-123';
      case TaskIntegration.trello:
        return 'https://trello.com/c/abc123/$slug';
    }
  }

  /// Format task description for external integration including transcript refs
  String formatTaskDescription(TaskData task) {
    final buffer = StringBuffer();

    // Add summary if present
    if (task.summary != null && task.summary!.isNotEmpty) {
      buffer.writeln(task.summary);
      buffer.writeln();
    }

    // Add steps as checklist
    if (task.hasSteps) {
      buffer.writeln('## Steps');
      for (final step in task.steps) {
        final checkbox = step.status == TaskStatus.completed ? '[x]' : '[ ]';
        buffer.writeln('- $checkbox ${step.title}');

        // Add step-level transcript refs
        if (step.hasTranscriptRefs) {
          for (final ref in step.transcriptRefs) {
            buffer.writeln('  > _"${ref.rawText}"_ - ${ref.speaker} (${ref.time})');
          }
        }
      }
      buffer.writeln();
    }

    // Add task-level transcript references
    if (task.transcriptRefs.isNotEmpty) {
      buffer.writeln('## Context from Conversation');
      for (final ref in task.transcriptRefs) {
        buffer.writeln('> _"${ref.rawText}"_');
        buffer.writeln('> — ${ref.speaker} (${ref.time})');
        buffer.writeln();
      }
    }

    // Add labels
    if (task.labels.isNotEmpty) {
      buffer.writeln('---');
      buffer.writeln('Labels: ${task.labels.join(', ')}');
    }

    return buffer.toString();
  }
}

/// Configuration for a task integration
class TaskIntegrationConfig {
  final TaskIntegration integration;
  final bool isConnected;
  final List<IntegrationProject> projects;
  final String? error;

  const TaskIntegrationConfig({
    required this.integration,
    required this.isConnected,
    this.projects = const [],
    this.error,
  });
}

/// A project/board/repo in an integration
class IntegrationProject {
  final String id;
  final String name;
  final String? description;
  final String? iconUrl;

  const IntegrationProject({
    required this.id,
    required this.name,
    this.description,
    this.iconUrl,
  });
}

/// Result of creating a task in an integration
class TaskCreationResult {
  final bool success;
  final String? taskUrl;
  final String? taskId;
  final TaskIntegration integration;
  final String? error;

  const TaskCreationResult({
    required this.success,
    this.taskUrl,
    this.taskId,
    required this.integration,
    this.error,
  });
}
