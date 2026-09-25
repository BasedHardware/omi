import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Widget showing top 3 today's tasks with "Show all ->" button
class TodayTasksWidget extends StatefulWidget {
  const TodayTasksWidget({super.key});

  @override
  State<TodayTasksWidget> createState() => _TodayTasksWidgetState();
}

class _TodayTasksWidgetState extends State<TodayTasksWidget> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(context.read<ActionItemsProvider>().ensureHomeTodayTasksLoaded());
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        final displayTasks = provider.todayPreviewTasks();

        // Hide if no today tasks
        if (displayTasks.isEmpty) {
          return const SizedBox.shrink();
        }

        return Container(
          margin: const EdgeInsets.only(left: 24, right: 8),
          padding: const EdgeInsets.only(bottom: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header with "Today" and "View All"
              Padding(
                padding: const EdgeInsets.only(top: 4, right: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Semantics(header: true, child: Text(context.l10n.today, style: OmiType.title3)),
                    OmiButton.tertiary(
                      label: context.l10n.viewAll,
                      size: OmiButtonSize.compact,
                      onPressed: () {
                        OmiHaptics.selection();
                        // Navigate to Tasks tab (index 2). Index 1 is Conversations.
                        context.read<HomeProvider>().setIndex(2);
                      },
                    ),
                  ],
                ),
              ),
              Transform.translate(
                offset: const Offset(-8, 0),
                child: Container(
                  margin: const EdgeInsets.only(top: 8),
                  decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  child: Column(
                    children: displayTasks.map((task) => _TaskItem(task: task, provider: provider)).toList(),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _TaskItem extends StatelessWidget {
  final ActionItemWithMetadata task;
  final ActionItemsProvider provider;

  const _TaskItem({required this.task, required this.provider});

  @override
  Widget build(BuildContext context) {
    // Same row behaviour as the Tasks page: the mark completes instantly, the row opens the task.
    return InkWell(
      borderRadius: OmiRadius.mdAll,
      onTap: () => showActionItemFormSheet(context, actionItem: task),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Semantics(
            button: true,
            checked: task.completed,
            label: task.completed ? context.l10n.markIncomplete : context.l10n.markComplete,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () async {
                OmiHaptics.light();
                await provider.updateActionItemState(task, !task.completed);
              },
              child: SizedBox(
                width: kOmiMinTapTarget,
                height: kOmiMinTapTarget,
                child: Center(child: TaskCompletionMark(completed: task.completed)),
              ),
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Text(
                task.description,
                style: OmiType.subhead.copyWith(
                  color: task.completed ? OmiColors.textTertiary : OmiColors.textPrimary,
                  decoration: task.completed ? TextDecoration.lineThrough : null,
                  height: 1.4,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
