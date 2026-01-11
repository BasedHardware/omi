import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:provider/provider.dart';

/// Widget showing top 3 today's tasks with "Show all ->" button
class TodayTasksWidget extends StatelessWidget {
  const TodayTasksWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        // Get today's tasks - same logic as action_items_page.dart
        final now = DateTime.now();
        final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
        // Filter out old tasks (older than 7 days) - same as tasks page
        final sevenDaysAgo = now.subtract(const Duration(days: 7));

        // Get incomplete tasks due today (including recent overdue) - matches tasks page logic
        final todayTasks = provider.actionItems.where((item) {
          if (item.completed) return false;
          if (item.dueAt == null) return false;
          // Skip very old overdue tasks (older than 7 days)
          if (item.dueAt!.isBefore(sevenDaysAgo)) return false;
          // Same as tasks page: dueDate.isBefore(startOfTomorrow)
          return item.dueAt!.isBefore(startOfTomorrow);
        }).toList();

        // Take top 3
        final displayTasks = todayTasks.take(3).toList();

        if (displayTasks.isEmpty && provider.actionItems.isEmpty) {
          return const SizedBox.shrink();
        }

        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 16),
          padding: const EdgeInsets.only(bottom: 20),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: Colors.white.withOpacity(0.08),
                width: 1,
              ),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header with "Today" and "Show all ->"
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Today',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    GestureDetector(
                      onTap: () {
                        HapticFeedback.lightImpact();
                        // Navigate to tasks tab
                        context.read<HomeProvider>().setIndex(1);
                      },
                      child: Text(
                        'Show all →',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 13,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              // Tasks list
              if (displayTasks.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(
                    'No tasks for today. Ask Omi for more tasks or create manually.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 14,
                    ),
                  ),
                )
              else
                ...displayTasks.map(
                  (task) => _TaskItem(task: task, provider: provider),
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
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Checkbox
          GestureDetector(
            onTap: () async {
              HapticFeedback.lightImpact();
              await provider.updateActionItemState(task, !task.completed);
            },
            child: Container(
              width: 22,
              height: 22,
              margin: const EdgeInsets.only(top: 2, right: 12),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: task.completed ? Colors.amber : Colors.grey.shade600,
                  width: 2,
                ),
                color: task.completed ? Colors.amber : Colors.transparent,
              ),
              child: task.completed
                  ? const Icon(Icons.check, size: 14, color: Colors.black)
                  : null,
            ),
          ),
          // Task text
          Expanded(
            child: Text(
              task.description,
              style: TextStyle(
                color: task.completed ? Colors.grey.shade600 : Colors.white,
                fontSize: 15,
                decoration: task.completed ? TextDecoration.lineThrough : null,
                height: 1.4,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
