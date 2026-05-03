import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/task_data.dart';

/// Detail view of a single generative task tag, including all steps and any
/// transcript references.
///
/// Simplified from the legacy `/app` version (which embedded a TaskCreateSheet
/// + integration push to Jira / GitHub / ClickUp / Linear / etc.). app-v2's
/// integration story is owned by `AppsProvider`, so this screen just renders
/// the read-only task data; "send to Jira" is a follow-up that should
/// route through the existing apps + reprocess pipeline.
class TaskScreen extends StatelessWidget {
  final TaskData data;

  const TaskScreen({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: AppColors.backgroundPrimary,
        elevation: 0,
        title: const Text(
          'Task',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(AppStyles.spacingL, 0, AppStyles.spacingL, AppStyles.spacingXL),
        children: [
          Text(
            data.title,
            style: const TextStyle(color: AppColors.textPrimary, fontSize: 22, fontWeight: FontWeight.w600),
          ),
          if (data.summary != null && data.summary!.isNotEmpty) ...[
            const SizedBox(height: AppStyles.spacingM),
            Text(data.summary!, style: const TextStyle(color: AppColors.textSecondary, fontSize: 15, height: 1.5)),
          ],
          const SizedBox(height: AppStyles.spacingL),
          _MetaRow(label: 'Priority', value: data.priority.displayName, color: data.priority.color),
          _MetaRow(label: 'Status', value: data.status.displayName, color: data.status.color),
          if (data.assignee != null) _MetaRow(label: 'Assignee', value: data.assignee!),
          if (data.dueDate != null) _MetaRow(label: 'Due', value: data.dueDate!),
          if (data.steps.isNotEmpty) ...[
            const SizedBox(height: AppStyles.spacingXL),
            const Text(
              'STEPS',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary,
                letterSpacing: 0.8,
              ),
            ),
            const SizedBox(height: AppStyles.spacingS),
            for (final step in data.steps) _StepRow(step: step),
          ],
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.label, required this.value, this.color});
  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingS),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(label, style: const TextStyle(color: AppColors.textTertiary, fontSize: 13)),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(color: color ?? AppColors.textPrimary, fontSize: 14, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({required this.step});
  final TaskStepData step;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(step.status.icon, size: 18, color: step.status.color),
          ),
          const SizedBox(width: AppStyles.spacingS),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(step.title, style: const TextStyle(color: AppColors.textPrimary, fontSize: 14, height: 1.4)),
                if (step.description != null && step.description!.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      step.description!,
                      style: const TextStyle(color: AppColors.textTertiary, fontSize: 13, height: 1.4),
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
