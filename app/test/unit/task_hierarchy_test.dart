import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/task_categorization.dart';
import 'package:omi/pages/action_items/task_hierarchy.dart';

ActionItemWithMetadata _task(String id, {int sortOrder = 0, int indent = 0, DateTime? dueAt, DateTime? createdAt}) =>
    ActionItemWithMetadata(
        id: id,
        description: id,
        completed: false,
        sortOrder: sortOrder,
        indentLevel: indent,
        dueAt: dueAt,
        createdAt: createdAt);

List<String> _ids(List<ActionItemWithMetadata> items) => items.map((item) => item.id).toList();

void main() {
  test('orderedTaskItems puts sorted rows first, then by due date and creation time', () {
    final items = [
      _task('late_due', dueAt: DateTime(2026, 5, 3)),
      _task('second', sortOrder: 2000),
      _task('early_due_new', dueAt: DateTime(2026, 5, 1), createdAt: DateTime(2026, 4, 2)),
      _task('first', sortOrder: 1000),
      _task('early_due_old', dueAt: DateTime(2026, 5, 1), createdAt: DateTime(2026, 4, 1)),
      _task('no_due'),
    ];
    expect(_ids(orderedTaskItems(items)), ['first', 'second', 'no_due', 'early_due_old', 'early_due_new', 'late_due']);
    expect(_ids(items).first, 'late_due', reason: 'the input list is not reordered in place');
  });

  test('taskSortOrders numbers the display order in steps of 1000', () {
    expect(taskSortOrders(['b', 'a', 'c']), {'b': 1000, 'a': 2000, 'c': 3000});
  });

  test('visibleDescendantIds walks deeper contiguous rows and stops at a sibling', () {
    final rows = [
      _task('a'),
      _task('a1', indent: 1),
      _task('a1x', indent: 2),
      _task('a2', indent: 1),
      _task('b'),
      _task('b1', indent: 1),
    ];
    expect(visibleDescendantIds(rows[0], rows), ['a1', 'a1x', 'a2']);
    expect(visibleDescendantIds(rows[1], rows), ['a1x']);
    expect(visibleDescendantIds(rows[2], rows), isEmpty);
    expect(visibleDescendantIds(rows[4], rows), ['b1']);
    expect(visibleDescendantIds(_task('missing'), rows), isEmpty);
  });

  test('maxIndentForDrop is one deeper than the row before the slot, skipping the dragged row', () {
    final rows = [_task('a'), _task('b', indent: 2), _task('c', indent: 3), _task('d')];
    expect(maxIndentForDrop(draggedItem: rows[3], targetIdx: -1, isAbove: true, categoryItems: rows), 3);
    expect(maxIndentForDrop(draggedItem: rows[3], targetIdx: 0, isAbove: true, categoryItems: rows), 0);
    expect(maxIndentForDrop(draggedItem: rows[3], targetIdx: 0, isAbove: false, categoryItems: rows), 1);
    expect(maxIndentForDrop(draggedItem: rows[3], targetIdx: 2, isAbove: true, categoryItems: rows), 3);
    expect(maxIndentForDrop(draggedItem: rows[3], targetIdx: 2, isAbove: false, categoryItems: rows), 3,
        reason: 'never deeper than 3');
    expect(maxIndentForDrop(draggedItem: rows[1], targetIdx: 2, isAbove: true, categoryItems: rows), 1,
        reason: 'the dragged row itself is skipped');
    expect(maxIndentForDrop(draggedItem: rows[0], targetIdx: 1, isAbove: true, categoryItems: rows), 0);
  });

  test('maxIndentFor bounds the menu indent by the previous row, from 0 to 3', () {
    final rows = [_task('a', indent: 1), _task('b'), _task('c', indent: 3), _task('d', indent: 3)];
    expect(maxIndentFor(rows[0], rows), 0, reason: 'the first row never indents');
    expect(maxIndentFor(rows[1], rows), 2);
    expect(maxIndentFor(rows[2], rows), 1);
    expect(maxIndentFor(rows[3], rows), 3, reason: 'one deeper than 3 is still 3');
    expect(maxIndentFor(_task('missing'), rows), 0);
  });

  test('movedTaskIds names the single moved row, both rows of a swap, or every changed row', () {
    expect(movedTaskIds(['a', 'b', 'c', 'd'], ['b', 'c', 'a', 'd']), ['a']);
    expect(movedTaskIds(['a', 'b', 'c', 'd'], ['a', 'd', 'b', 'c']), ['d']);
    expect(movedTaskIds(['a', 'b', 'c'], ['b', 'a', 'c']), ['b', 'a']);
    expect(movedTaskIds(['a', 'b', 'c', 'd'], ['b', 'a', 'd', 'c']), ['b', 'a', 'd', 'c']);
    expect(movedTaskIds(['a', 'b'], ['a', 'b']), isEmpty);
  });

  test('defaultDueDateForCategory keeps the drag and drop dates for every category', () {
    final now = DateTime(2026, 12, 31, 15, 20);
    expect(defaultDueDateForCategory(TaskCategory.today, now), DateTime(2026, 12, 31, 23, 59));
    expect(defaultDueDateForCategory(TaskCategory.tomorrow, now), DateTime(2027, 1, 1, 23, 59));
    expect(defaultDueDateForCategory(TaskCategory.later, now), DateTime(2027, 1, 2, 23, 59));
    expect(defaultDueDateForCategory(TaskCategory.noDeadline, now), isNull);
    expect(defaultDueDateForCategory(TaskCategory.overdue, now), DateTime(2026, 12, 30, 23, 59));
    for (final category in TaskCategory.values) {
      final due = defaultDueDateForCategory(category, now);
      if (due != null) {
        expect(categoryForItem(_task('t', dueAt: due), false, now: now), category,
            reason: 'a moved task lands in the category it was moved to');
      }
    }
  });
}
