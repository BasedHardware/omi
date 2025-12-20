import 'package:flutter/material.dart';
import '../models/task_data.dart';
import 'task_create_sheet.dart';

/// Full-screen task view with detailed steps and transcript references
class TaskScreen extends StatelessWidget {
  final TaskData data;

  const TaskScreen({
    super.key,
    required this.data,
  });

  void _showCreateTaskSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => TaskCreateSheet(task: data),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(context),
            Expanded(
              child: _TaskDetailView(
                task: data,
                onCreateTask: () => _showCreateTaskSheet(context),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 16, 16),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back, color: Colors.white),
          ),
          const SizedBox(width: 4),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: data.priority.color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              Icons.task_alt_rounded,
              color: data.priority.color,
              size: 18,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Task Details',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          // Priority badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: data.priority.backgroundColor,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  data.priority.icon,
                  size: 14,
                  color: data.priority.color,
                ),
                const SizedBox(width: 4),
                Text(
                  data.priority.displayName,
                  style: TextStyle(
                    color: data.priority.color,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TaskDetailView extends StatelessWidget {
  final TaskData task;
  final VoidCallback onCreateTask;

  const _TaskDetailView({
    required this.task,
    required this.onCreateTask,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Task title
              Text(
                task.title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w600,
                ),
              ),

              // Assignee and due date
              if (task.assignee != null || task.dueDate != null) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 8,
                  children: [
                    if (task.assignee != null)
                      _MetaChip(
                        icon: Icons.person_outline,
                        label: task.assignee!,
                      ),
                    if (task.dueDate != null)
                      _MetaChip(
                        icon: Icons.calendar_today_outlined,
                        label: task.dueDate!,
                      ),
                  ],
                ),
              ],

              // Summary
              if (task.summary != null && task.summary!.isNotEmpty) ...[
                const SizedBox(height: 20),
                Text(
                  task.summary!,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.8),
                    fontSize: 15,
                    height: 1.5,
                  ),
                ),
              ],

              // Steps section
              if (task.hasSteps) ...[
                const SizedBox(height: 24),
                _buildSectionHeader('Steps'),
                const SizedBox(height: 12),
                ...task.steps.asMap().entries.map((entry) {
                  final index = entry.key;
                  final step = entry.value;
                  final isLast = index == task.steps.length - 1;
                  return _StepItem(
                    key: ValueKey('task_step_$index'),
                    step: step,
                    index: index,
                    isLast: isLast,
                  );
                }),
              ],

              // Transcript references
              if (task.transcriptRefs.isNotEmpty) ...[
                const SizedBox(height: 24),
                _buildSectionHeader('Transcript References'),
                const SizedBox(height: 12),
                ...task.transcriptRefs.asMap().entries.map(
                  (entry) => _TranscriptRefItem(
                    key: ValueKey('task_ref_${entry.key}'),
                    ref: entry.value,
                  ),
                ),
              ],

              // Bottom spacing
              const SizedBox(height: 80),
            ],
          ),
        ),

        // Create task button
        _buildCreateButton(context),
      ],
    );
  }

  Widget _buildSectionHeader(String title) {
    return Row(
      children: [
        Text(
          title.toUpperCase(),
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Container(
            height: 1,
            color: Colors.white.withOpacity(0.1),
          ),
        ),
      ],
    );
  }

  Widget _buildCreateButton(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.black,
        border: Border(
          top: BorderSide(
            color: Colors.white.withOpacity(0.1),
          ),
        ),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: onCreateTask,
            icon: const Icon(Icons.add_task_rounded, size: 20),
            label: const Text('Create Task'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF8B5CF6),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _MetaChip({
    required this.icon,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: Colors.white.withOpacity(0.6)),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.8),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }
}

class _StepItem extends StatelessWidget {
  final TaskStepData step;
  final int index;
  final bool isLast;

  const _StepItem({
    super.key,
    required this.step,
    required this.index,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Step indicator
          SizedBox(
            width: 28,
            child: Column(
              children: [
                Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    color: step.status == TaskStatus.completed
                        ? const Color(0xFF22C55E)
                        : Colors.white.withOpacity(0.1),
                    shape: BoxShape.circle,
                    border: step.status != TaskStatus.completed
                        ? Border.all(
                            color: Colors.white.withOpacity(0.3),
                            width: 2,
                          )
                        : null,
                  ),
                  child: Center(
                    child: step.status == TaskStatus.completed
                        ? const Icon(Icons.check, size: 14, color: Colors.white)
                        : Text(
                            '${index + 1}',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.7),
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      color: Colors.white.withOpacity(0.15),
                    ),
                  ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          // Step content
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    step.title,
                    style: TextStyle(
                      color: Colors.white.withOpacity(
                        step.status == TaskStatus.completed ? 0.6 : 0.95,
                      ),
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                      decoration: step.status == TaskStatus.completed
                          ? TextDecoration.lineThrough
                          : null,
                    ),
                  ),
                  if (step.hasTranscriptRefs) ...[
                    const SizedBox(height: 8),
                    ...step.transcriptRefs.map(
                      (ref) => _TranscriptRefItem(ref: ref, compact: true),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Chat bubble style transcript reference - similar to live transcript
class _TranscriptRefItem extends StatelessWidget {
  final TranscriptReference ref;
  final bool compact;

  const _TranscriptRefItem({
    super.key,
    required this.ref,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: compact ? 8 : 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Speaker avatar
          Container(
            width: compact ? 28 : 32,
            height: compact ? 28 : 32,
            decoration: BoxDecoration(
              color: const Color(0xFF8B5CF6).withOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                ref.speaker.isNotEmpty ? ref.speaker[0].toUpperCase() : '?',
                style: TextStyle(
                  color: const Color(0xFF8B5CF6),
                  fontSize: compact ? 12 : 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          // Bubble content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Speaker name and time
                Row(
                  children: [
                    if (ref.speaker.isNotEmpty)
                      Text(
                        ref.speaker,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                          fontSize: compact ? 11 : 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    if (ref.time.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      Text(
                        ref.time,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.4),
                          fontSize: compact ? 10 : 11,
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                // Message bubble
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: compact ? 10 : 12,
                    vertical: compact ? 8 : 10,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.08),
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(4),
                      topRight: Radius.circular(16),
                      bottomLeft: Radius.circular(16),
                      bottomRight: Radius.circular(16),
                    ),
                  ),
                  child: Text(
                    ref.rawText,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.9),
                      fontSize: compact ? 13 : 14,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
