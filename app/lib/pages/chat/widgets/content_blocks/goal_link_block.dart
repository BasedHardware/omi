import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'chat_block_chrome.dart';

/// Renders a `goalLink` block.
///
/// Mobile has no goal detail route (goals live as a flat list behind
/// [GoalsProvider] and are rendered inline by the goals widget), so the block
/// opens a bottom sheet with the resolved goal's title and progress instead of
/// inventing a navigation destination. A goal that is not in the loaded list
/// renders the unavailable state rather than a dead button.
class GoalLinkBlock extends StatelessWidget {
  const GoalLinkBlock({super.key, required this.block});

  final GoalLinkContentBlock block;

  Goal? _resolve(GoalsProvider provider) {
    for (final goal in provider.goals) {
      if (goal.id == block.goalId) return goal;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<GoalsProvider>(
      builder: (context, provider, _) {
        final goal = _resolve(provider);
        if (goal == null && !provider.isLoading) {
          return ChatBlockUnavailable(
            key: Key('chat-block-goalLink-${block.id}-unavailable'),
            icon: Icons.flag_outlined,
            label: l10n.chatBlockGoal,
            message: l10n.chatBlockUnavailable,
          );
        }

        return ChatBlockLinkCard(
          key: Key('chat-block-goalLink-${block.id}'),
          icon: Icons.flag_outlined,
          label: l10n.chatBlockGoal,
          summary: block.summary,
          actionTitle: l10n.chatBlockOpenInGoals,
          actionKey: Key('chat-block-goalLink-${block.id}-open'),
          isOpening: goal == null,
          onAction: goal == null ? null : () => _showGoalSheet(context, goal),
        );
      },
    );
  }

  void _showGoalSheet(BuildContext context, Goal goal) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (sheetContext) {
        final colorScheme = Theme.of(sheetContext).colorScheme;
        final unit = goal.unit?.trim();
        final progress = '${_format(goal.currentValue)} / ${_format(goal.targetValue)}'
            '${unit == null || unit.isEmpty ? '' : ' $unit'}';
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ChatBlockEyebrow(icon: Icons.flag_outlined, label: sheetContext.l10n.chatBlockGoal),
                const SizedBox(height: 8),
                Text(goal.title, style: Theme.of(sheetContext).textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(
                  progress,
                  key: Key('chat-block-goalLink-${block.id}-progress'),
                  style: Theme.of(sheetContext).textTheme.bodyMedium?.copyWith(color: colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static String _format(double value) {
    return value == value.roundToDouble() ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
  }
}
