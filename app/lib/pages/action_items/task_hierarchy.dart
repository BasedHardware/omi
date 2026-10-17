import 'package:omi/backend/schema/schema.dart';

import 'task_categorization.dart';

/// Task hierarchy and ordering rules shared by the Tasks page's Flutter list and its native
/// projection. The data model is flat (no parent id): a row's children are the contiguous rows below
/// it with a deeper indent level, so every rule here works on one category's display order.

/// The deepest indent level a task may have.
const maxTaskIndent = 3;

/// [items] in display order: rows with a sort order first (ascending), then by due date and creation
/// time.
List<ActionItemWithMetadata> orderedTaskItems(List<ActionItemWithMetadata> items) {
  final sorted = List<ActionItemWithMetadata>.from(items);
  sorted.sort((a, b) {
    // Items with sortOrder > 0 come first, sorted ascending
    if (a.sortOrder > 0 && b.sortOrder > 0) {
      return a.sortOrder.compareTo(b.sortOrder);
    }
    if (a.sortOrder > 0) return -1;
    if (b.sortOrder > 0) return 1;
    // Fallback: sort by dueAt then createdAt
    final aDue = a.dueAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final bDue = b.dueAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final dueCmp = aDue.compareTo(bDue);
    if (dueCmp != 0) return dueCmp;
    final aCreated = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final bCreated = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    return aCreated.compareTo(bCreated);
  });
  return sorted;
}

/// Sequential sort orders for ids in display [order]: 1000, 2000, ...
Map<String, int> taskSortOrders(List<String> order) => {
      for (var index = 0; index < order.length; index++) order[index]: (index + 1) * 1000,
    };

/// Walks the displayed [categoryItems] forward from [parent] and returns every contiguous
/// descendant — rows with strictly greater indent_level, stopping at the first sibling/ancestor.
List<String> visibleDescendantIds(ActionItemWithMetadata parent, List<ActionItemWithMetadata> categoryItems) {
  final idx = categoryItems.indexWhere((i) => i.id == parent.id);
  if (idx < 0) return const [];
  final ids = <String>[];
  for (int i = idx + 1; i < categoryItems.length; i++) {
    if (categoryItems[i].indentLevel <= parent.indentLevel) break;
    ids.add(categoryItems[i].id);
  }
  return ids;
}

/// Caps the drop indent at one level deeper than the row immediately preceding the drop slot
/// (skipping the dragged row itself). Without this, a user could indent past a parent that doesn't
/// exist yet.
int maxIndentForDrop({
  required ActionItemWithMetadata draggedItem,
  required int targetIdx,
  required bool isAbove,
  required List<ActionItemWithMetadata> categoryItems,
}) {
  if (targetIdx < 0) return maxTaskIndent;
  int idx = isAbove ? targetIdx - 1 : targetIdx;
  while (idx >= 0 && categoryItems[idx].id == draggedItem.id) {
    idx--;
  }
  if (idx < 0) return 0;
  return (categoryItems[idx].indentLevel + 1).clamp(0, maxTaskIndent);
}

/// The row menu's indent bound: one level deeper than the previous displayed row, and 0 for the
/// first row. Indent is offered only while [item]'s level is below it.
int maxIndentFor(ActionItemWithMetadata item, List<ActionItemWithMetadata> ordered) {
  final index = ordered.indexWhere((i) => i.id == item.id);
  return index <= 0 ? 0 : (ordered[index - 1].indentLevel + 1).clamp(0, maxTaskIndent);
}

/// The ids a reorder from [before] to [after] (the same ids) moved. A single move is the id whose
/// removal leaves both orders equal; an adjacent swap has two such ids and both count. Anything else
/// counts every id whose position changed.
List<String> movedTaskIds(List<String> before, List<String> after) {
  final changed = [
    for (var index = 0; index < after.length; index++)
      if (index >= before.length || before[index] != after[index]) after[index],
  ];
  bool singleMove(String id) {
    final a = before.where((other) => other != id).toList();
    final b = after.where((other) => other != id).toList();
    if (a.length != b.length) return false;
    for (var index = 0; index < a.length; index++) {
      if (a[index] != b[index]) return false;
    }
    return true;
  }

  final single = changed.where(singleMove).toList();
  return single.isNotEmpty ? single : changed;
}

/// The due date a task gets when it moves to [category] (drag and drop, or Set Due Date): 23:59 on
/// today, tomorrow or the day after; none for No deadline; yesterday for Overdue so it stays there.
DateTime? defaultDueDateForCategory(TaskCategory category, DateTime now) {
  switch (category) {
    case TaskCategory.today:
      return DateTime(now.year, now.month, now.day, 23, 59);
    case TaskCategory.tomorrow:
      return DateTime(now.year, now.month, now.day + 1, 23, 59);
    case TaskCategory.noDeadline:
      return null;
    case TaskCategory.later:
      // Day after tomorrow
      return DateTime(now.year, now.month, now.day + 2, 23, 59);
    case TaskCategory.overdue:
      // Yesterday, so the task stays in overdue after rebuild
      return DateTime(now.year, now.month, now.day - 1, 23, 59);
  }
}
