import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/task_data.dart';
import '../services/task_integration_service.dart';

/// Bottom sheet for creating tasks in external integrations
class TaskCreateSheet extends StatefulWidget {
  final TaskData task;

  const TaskCreateSheet({
    super.key,
    required this.task,
  });

  @override
  State<TaskCreateSheet> createState() => _TaskCreateSheetState();
}

class _TaskCreateSheetState extends State<TaskCreateSheet> {
  final _service = TaskIntegrationService();
  TaskIntegration? _selectedIntegration;
  IntegrationProject? _selectedProject;
  bool _isCreating = false;
  TaskCreationResult? _result;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1A1A1A),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Handle
            Center(
              child: Container(
                margin: const EdgeInsets.only(top: 12),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),

            // Content
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: _result != null
                    ? _buildResultView()
                    : _selectedIntegration != null
                        ? _buildProjectSelector()
                        : _buildIntegrationSelector(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildIntegrationSelector() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Header
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFF8B5CF6).withOpacity(0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.add_task_rounded,
                color: Color(0xFF8B5CF6),
                size: 22,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Create Task',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  Text(
                    'Choose where to create this task',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),

        const SizedBox(height: 20),

        // Task preview
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white.withOpacity(0.1)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.task.title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
              if (widget.task.summary != null) ...[
                const SizedBox(height: 6),
                Text(
                  widget.task.summary!,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 13,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              const SizedBox(height: 10),
              Row(
                children: [
                  _TaskMetaChip(
                    icon: widget.task.priority.icon,
                    label: widget.task.priority.displayName,
                    color: widget.task.priority.color,
                  ),
                  const SizedBox(width: 8),
                  if (widget.task.hasSteps)
                    _TaskMetaChip(
                      icon: Icons.checklist_rounded,
                      label: '${widget.task.steps.length} steps',
                      color: Colors.white.withOpacity(0.6),
                    ),
                  if (widget.task.hasTranscriptRefs) ...[
                    const SizedBox(width: 8),
                    _TaskMetaChip(
                      icon: Icons.format_quote_rounded,
                      label: '${widget.task.totalTranscriptRefs} refs',
                      color: Colors.white.withOpacity(0.6),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),

        // Integrations list
        Text(
          'INTEGRATIONS',
          style: TextStyle(
            color: Colors.white.withOpacity(0.4),
            fontSize: 11,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),

        const SizedBox(height: 12),

        ...TaskIntegration.values.map((integration) {
          final config = _service.availableIntegrations
              .firstWhere((c) => c.integration == integration);
          return _IntegrationTile(
            integration: integration,
            isConnected: config.isConnected,
            onTap: () => _handleIntegrationSelect(integration, config),
          );
        }),
      ],
    );
  }

  Widget _buildProjectSelector() {
    final config = _service.availableIntegrations
        .firstWhere((c) => c.integration == _selectedIntegration);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Back button and header
        Row(
          children: [
            IconButton(
              onPressed: () => setState(() {
                _selectedIntegration = null;
                _selectedProject = null;
              }),
              icon: const Icon(Icons.arrow_back, color: Colors.white),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
            const SizedBox(width: 12),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: _selectedIntegration!.brandColor.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                _getIntegrationIcon(_selectedIntegration!),
                color: _selectedIntegration!.brandColor,
                size: 18,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'Select Project',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: 20),

        // Project list or empty state
        if (config.projects.isEmpty)
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 40),
              child: Column(
                children: [
                  Icon(
                    Icons.folder_outlined,
                    size: 48,
                    color: Colors.white.withOpacity(0.3),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'No projects found',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          ...config.projects.map((project) {
            final isSelected = _selectedProject?.id == project.id;
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: InkWell(
                onTap: () => setState(() => _selectedProject = project),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? _selectedIntegration!.brandColor.withOpacity(0.15)
                        : Colors.white.withOpacity(0.05),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isSelected
                          ? _selectedIntegration!.brandColor.withOpacity(0.5)
                          : Colors.white.withOpacity(0.1),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Icon(
                          Icons.folder_rounded,
                          size: 18,
                          color: isSelected
                              ? _selectedIntegration!.brandColor
                              : Colors.white.withOpacity(0.6),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          project.name,
                          style: TextStyle(
                            color: Colors.white.withOpacity(isSelected ? 1 : 0.8),
                            fontSize: 14,
                            fontWeight:
                                isSelected ? FontWeight.w600 : FontWeight.w400,
                          ),
                        ),
                      ),
                      if (isSelected)
                        Icon(
                          Icons.check_circle,
                          size: 20,
                          color: _selectedIntegration!.brandColor,
                        ),
                    ],
                  ),
                ),
              ),
            );
          }),

        const SizedBox(height: 20),

        // Create button
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: _selectedProject != null && !_isCreating
                ? _createTask
                : null,
            style: ElevatedButton.styleFrom(
              backgroundColor: _selectedIntegration!.brandColor,
              foregroundColor: Colors.white,
              disabledBackgroundColor:
                  _selectedIntegration!.brandColor.withOpacity(0.3),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: _isCreating
                ? SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        Colors.white.withOpacity(0.7),
                      ),
                    ),
                  )
                : Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.add_task_rounded, size: 20),
                      const SizedBox(width: 8),
                      Text('Create in ${_selectedIntegration!.displayName}'),
                    ],
                  ),
          ),
        ),
      ],
    );
  }

  Widget _buildResultView() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const SizedBox(height: 20),

        // Success/Error icon
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: _result!.success
                ? const Color(0xFF22C55E).withOpacity(0.15)
                : const Color(0xFFEF4444).withOpacity(0.15),
            shape: BoxShape.circle,
          ),
          child: Icon(
            _result!.success ? Icons.check_rounded : Icons.error_outline,
            size: 40,
            color: _result!.success
                ? const Color(0xFF22C55E)
                : const Color(0xFFEF4444),
          ),
        ),

        const SizedBox(height: 20),

        Text(
          _result!.success ? 'Task Created!' : 'Failed to Create Task',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),

        const SizedBox(height: 8),

        Text(
          _result!.success
              ? 'Your task has been created in ${_result!.integration.displayName}'
              : _result!.error ?? 'An unexpected error occurred',
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 14,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 24),

        // Action buttons
        if (_result!.success && _result!.taskUrl != null)
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: () => _openTaskUrl(_result!.taskUrl!),
              icon: const Icon(Icons.open_in_new, size: 18),
              label: const Text('Open Task'),
              style: ElevatedButton.styleFrom(
                backgroundColor: _result!.integration.brandColor,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),

        const SizedBox(height: 12),

        SizedBox(
          width: double.infinity,
          child: TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(
              _result!.success ? 'Done' : 'Close',
              style: TextStyle(
                color: Colors.white.withOpacity(0.7),
              ),
            ),
          ),
        ),

        const SizedBox(height: 10),
      ],
    );
  }

  void _handleIntegrationSelect(
    TaskIntegration integration,
    TaskIntegrationConfig config,
  ) async {
    if (!config.isConnected) {
      // Show connecting state and attempt to connect
      setState(() => _selectedIntegration = integration);

      final success = await _service.connect(integration);
      if (success && mounted) {
        setState(() {
          // Refresh the integration config after connection
        });
      }
    } else {
      setState(() {
        _selectedIntegration = integration;
      });
    }
  }

  Future<void> _createTask() async {
    if (_selectedIntegration == null || _selectedProject == null) return;

    setState(() => _isCreating = true);

    try {
      final result = await _service.createTask(
        integration: _selectedIntegration!,
        task: widget.task,
        projectId: _selectedProject!.id,
      );

      if (mounted) {
        setState(() {
          _result = result;
          _isCreating = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _result = TaskCreationResult(
            success: false,
            integration: _selectedIntegration!,
            error: e.toString(),
          );
          _isCreating = false;
        });
      }
    }
  }

  Future<void> _openTaskUrl(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  IconData _getIntegrationIcon(TaskIntegration integration) {
    switch (integration) {
      case TaskIntegration.jira:
        return Icons.bug_report_outlined;
      case TaskIntegration.github:
        return Icons.code_rounded;
      case TaskIntegration.clickup:
        return Icons.bolt_rounded;
      case TaskIntegration.asana:
        return Icons.assignment_outlined;
      case TaskIntegration.notion:
        return Icons.article_outlined;
      case TaskIntegration.linear:
        return Icons.linear_scale_rounded;
      case TaskIntegration.trello:
        return Icons.dashboard_outlined;
    }
  }
}

class _IntegrationTile extends StatelessWidget {
  final TaskIntegration integration;
  final bool isConnected;
  final VoidCallback onTap;

  const _IntegrationTile({
    required this.integration,
    required this.isConnected,
    required this.onTap,
  });

  IconData _getIcon() {
    switch (integration) {
      case TaskIntegration.jira:
        return Icons.bug_report_outlined;
      case TaskIntegration.github:
        return Icons.code_rounded;
      case TaskIntegration.clickup:
        return Icons.bolt_rounded;
      case TaskIntegration.asana:
        return Icons.assignment_outlined;
      case TaskIntegration.notion:
        return Icons.article_outlined;
      case TaskIntegration.linear:
        return Icons.linear_scale_rounded;
      case TaskIntegration.trello:
        return Icons.dashboard_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: Colors.white.withOpacity(0.1),
            ),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: integration.brandColor.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  _getIcon(),
                  color: integration.brandColor,
                  size: 20,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      integration.displayName,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    Text(
                      isConnected ? 'Connected' : 'Tap to connect',
                      style: TextStyle(
                        color: isConnected
                            ? const Color(0xFF22C55E)
                            : Colors.white.withOpacity(0.4),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                isConnected
                    ? Icons.check_circle
                    : Icons.arrow_forward_ios_rounded,
                size: isConnected ? 22 : 16,
                color: isConnected
                    ? const Color(0xFF22C55E)
                    : Colors.white.withOpacity(0.3),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TaskMetaChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _TaskMetaChip({
    required this.icon,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
