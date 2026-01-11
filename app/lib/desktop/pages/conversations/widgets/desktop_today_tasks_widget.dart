import 'package:flutter/material.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

/// Desktop widget showing top 3 today's tasks with "Show all ->" button
class DesktopTodayTasksWidget extends StatelessWidget {
  const DesktopTodayTasksWidget({super.key});

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
          return item.dueAt!.isBefore(startOfTomorrow);
        }).toList();

        // Take top 3
        final displayTasks = todayTasks.take(3).toList();

        if (displayTasks.isEmpty && provider.actionItems.isEmpty) {
          return const SizedBox.shrink();
        }

        return Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
              width: 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header with "Today" and "Show all ->"
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Today',
                    style: TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  MouseRegion(
                    cursor: SystemMouseCursors.click,
                    child: GestureDetector(
                      onTap: () {
                        // Navigate to Actions tab (index 3)
                        context.read<HomeProvider>().setIndex(3);
                      },
                      child: Text(
                        'Show all →',
                        style: TextStyle(
                          color: ResponsiveHelper.textTertiary,
                          fontSize: 12,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              // Tasks list - use Expanded to fill available space
              Expanded(
                child: displayTasks.isEmpty
                    ? Center(
                        child: Text(
                          'No tasks for today.\nAsk Omi for more tasks or create manually.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: ResponsiveHelper.textTertiary,
                            fontSize: 13,
                          ),
                        ),
                      )
                    : ListView(
                        padding: EdgeInsets.zero,
                        children: displayTasks.map(
                          (task) => _TaskItem(task: task, provider: provider),
                        ).toList(),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _TaskItem extends StatefulWidget {
  final ActionItemWithMetadata task;
  final ActionItemsProvider provider;

  const _TaskItem({required this.task, required this.provider});

  @override
  State<_TaskItem> createState() => _TaskItemState();
}

class _TaskItemState extends State<_TaskItem> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () async {
          await widget.provider.updateActionItemState(widget.task, !widget.task.completed);
        },
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
          margin: const EdgeInsets.only(bottom: 8),
          decoration: BoxDecoration(
            color: _isHovered
                ? ResponsiveHelper.backgroundTertiary.withOpacity(0.5)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Checkbox
              Container(
                width: 20,
                height: 20,
                margin: const EdgeInsets.only(top: 2, right: 12),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: widget.task.completed
                        ? ResponsiveHelper.purplePrimary
                        : ResponsiveHelper.textTertiary,
                    width: 2,
                  ),
                  color: widget.task.completed
                      ? ResponsiveHelper.purplePrimary
                      : Colors.transparent,
                ),
                child: widget.task.completed
                    ? const Icon(Icons.check, size: 12, color: Colors.white)
                    : null,
              ),
              // Task text
              Expanded(
                child: Text(
                  widget.task.description,
                  style: TextStyle(
                    color: widget.task.completed
                        ? ResponsiveHelper.textTertiary
                        : ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    decoration: widget.task.completed ? TextDecoration.lineThrough : null,
                    height: 1.4,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
