import 'dart:collection';

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

/// Provider-owned task membership. Rows are immutable generated DTOs, so every
/// change relevant to categorization passes through a list mutation. Tracking
/// those writes avoids scanning a 500-task snapshot just to validate a cache.
class TaskCategorizationList extends ListBase<ActionItemWithMetadata> {
  TaskCategorizationList([Iterable<ActionItemWithMetadata> items = const []]) : _items = List.of(items);

  final List<ActionItemWithMetadata> _items;
  int _version = 0;
  int _cachedVersion = -1;
  bool? _cachedCompleted;
  DateTime? _cachedAt;
  DateTime? _validUntil;
  Map<TaskCategory, List<ActionItemWithMetadata>>? _categories;

  @override
  int get length => _items.length;
  @override
  set length(int value) {
    if (value == _items.length) return;
    _items.length = value;
    _version++;
  }

  @override
  ActionItemWithMetadata operator [](int index) => _items[index];
  @override
  void operator []=(int index, ActionItemWithMetadata value) {
    if (identical(_items[index], value)) return;
    _items[index] = value;
    _version++;
  }

  @override
  void add(ActionItemWithMetadata element) {
    _items.add(element);
    _version++;
  }

  @override
  void addAll(Iterable<ActionItemWithMetadata> iterable) {
    if (identical(iterable, this)) {
      addAll(List<ActionItemWithMetadata>.of(this));
      return;
    }
    // Route each write through add so even a throwing iterable invalidates
    // the cache for any prefix already appended.
    for (final value in iterable) {
      add(value);
    }
  }

  @override
  void insert(int index, ActionItemWithMetadata element) {
    _items.insert(index, element);
    _version++;
  }

  @override
  void insertAll(int index, Iterable<ActionItemWithMetadata> iterable) {
    // Snapshot aliases/throwing iterables before changing membership.
    final inserted = iterable.toList();
    _items.insertAll(index, inserted);
    if (inserted.isNotEmpty) _version++;
  }

  Map<TaskCategory, List<ActionItemWithMetadata>>? _cached(bool completed, DateTime now) {
    if (_cachedVersion != _version ||
        _cachedCompleted != completed ||
        _cachedAt == null ||
        now.isBefore(_cachedAt!) ||
        !now.isBefore(_validUntil!)) {
      return null;
    }
    return _categories;
  }

  void _remember(
      bool completed, DateTime now, DateTime validUntil, Map<TaskCategory, List<ActionItemWithMetadata>> categories) {
    _cachedVersion = _version;
    _cachedCompleted = completed;
    _cachedAt = now;
    _validUntil = validUntil;
    _categories = categories;
  }
}

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
  if (items is TaskCategorizationList) {
    final cached = items._cached(showCompleted, current);
    if (cached != null) return cached;
  }
  var validUntil = DateTime(current.year, current.month, current.day + 1);

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
    if (!showCompleted && item.dueAt == null && item.createdAt != null) {
      // Aging is a strict comparison, so equality is still No deadline.
      final expiresAt = item.createdAt!.add(const Duration(days: 7, microseconds: 1));
      if (expiresAt.isAfter(current) && expiresAt.isBefore(validUntil)) validUntil = expiresAt;
    }
  }

  if (items is TaskCategorizationList) {
    final frozen = Map<TaskCategory, List<ActionItemWithMetadata>>.unmodifiable({
      for (final entry in categorized.entries) entry.key: UnmodifiableListView<ActionItemWithMetadata>(entry.value),
    });
    items._remember(showCompleted, current, validUntil, frozen);
    return frozen;
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
