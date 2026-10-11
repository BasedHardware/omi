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

    categorized[categoryForItem(item, showCompleted, now: current)]!.add(item);
  }

  return categorized;
}

/// The bucket [item] belongs to, by the same rule [categorizeTasks] uses.
///
/// Callers that need one item's section (a drag and drop target, for instance)
/// must use this rather than their own copy: a second copy that ignores
/// [showCompleted] reads a past-due completed task as overdue while the list
/// shows it under Today, and a reorder inside that section then looks like a
/// move and rewrites the task's due date.
TaskCategory categoryForItem(
  ActionItemWithMetadata item,
  bool showCompleted, {
  DateTime? now,
}) {
  final current = now ?? DateTime.now();
  final startOfToday = DateTime(current.year, current.month, current.day);
  final startOfTomorrow = DateTime(current.year, current.month, current.day + 1);
  final startOfDayAfterTomorrow = DateTime(current.year, current.month, current.day + 2);
  final sevenDaysAgo = current.subtract(const Duration(days: 7));

  if (item.dueAt == null) {
    // No deadline tasks older than 7 days go to overdue
    if (!showCompleted && item.createdAt != null && item.createdAt!.isBefore(sevenDaysAgo)) {
      return TaskCategory.overdue;
    }
    return TaskCategory.noDeadline;
  }
  final dueDate = item.dueAt!;
  if (!showCompleted && dueDate.isBefore(startOfToday)) {
    // Due date in the past → overdue
    return TaskCategory.overdue;
  }
  if (dueDate.isBefore(startOfTomorrow)) {
    return TaskCategory.today;
  }
  if (dueDate.isBefore(startOfDayAfterTomorrow)) {
    return TaskCategory.tomorrow;
  }
  return TaskCategory.later;
}
