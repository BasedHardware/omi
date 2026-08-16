import 'package:omi/backend/schema/schema.dart';

/// Task list buckets for the action items page.
///
/// This is the app's `separate_overdue` model: past-due tasks get their own
/// Overdue bucket, and tasks with no due date created more than 7 days ago age
/// into Overdue too. macOS and Windows use the `fold_overdue` model instead
/// (past-due folds into Today, no aging rule). Both models are pinned per case
/// by the shared fixtures in `contracts/parity/task_due_buckets.json`; changing
/// the rule here means editing that fixture in the same PR.
enum TaskCategory { today, tomorrow, later, noDeadline, overdue }

/// Buckets [items] by due date relative to [now] (defaults to the wall clock;
/// injectable so the parity conformance test can run the fixture vectors).
///
/// Extracted from the action items page state so the rule is unit-testable.
/// The overdue branches only apply to the open-tasks view: in the completed
/// view a past-due task shows under Today and a stale dateless one under
/// No deadline.
Map<TaskCategory, List<ActionItemWithMetadata>> categorizeTasks(
  List<ActionItemWithMetadata> items,
  bool showCompleted, {
  DateTime? now,
}) {
  final current = now ?? DateTime.now();
  final startOfToday = DateTime(current.year, current.month, current.day);
  final startOfTomorrow = DateTime(current.year, current.month, current.day + 1);
  final startOfDayAfterTomorrow = DateTime(current.year, current.month, current.day + 2);
  final sevenDaysAgo = current.subtract(const Duration(days: 7));

  final Map<TaskCategory, List<ActionItemWithMetadata>> categorized = {
    TaskCategory.today: [],
    TaskCategory.tomorrow: [],
    TaskCategory.noDeadline: [],
    TaskCategory.later: [],
    TaskCategory.overdue: [],
  };

  for (var item in items) {
    // Skip completed items unless showing completed
    if (item.completed && !showCompleted) continue;
    if (!item.completed && showCompleted) continue;

    if (item.dueAt == null) {
      // No deadline tasks older than 7 days go to overdue
      if (!showCompleted && item.createdAt != null && item.createdAt!.isBefore(sevenDaysAgo)) {
        categorized[TaskCategory.overdue]!.add(item);
      } else {
        categorized[TaskCategory.noDeadline]!.add(item);
      }
    } else {
      final dueDate = item.dueAt!;
      if (!showCompleted && dueDate.isBefore(startOfToday)) {
        // Due date in the past → overdue
        categorized[TaskCategory.overdue]!.add(item);
      } else if (dueDate.isBefore(startOfTomorrow)) {
        categorized[TaskCategory.today]!.add(item);
      } else if (dueDate.isBefore(startOfDayAfterTomorrow)) {
        categorized[TaskCategory.tomorrow]!.add(item);
      } else {
        categorized[TaskCategory.later]!.add(item);
      }
    }
  }

  return categorized;
}
