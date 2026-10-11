import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/task_categorization.dart';

final _now = DateTime(2026, 9, 21, 10);

ActionItemWithMetadata _task({required bool completed, DateTime? dueAt, DateTime? createdAt}) => ActionItemWithMetadata(
      id: 'task-1',
      description: 'Send the budget',
      completed: completed,
      dueAt: dueAt,
      createdAt: createdAt,
    );

void main() {
  group('categoryForItem', () {
    test('past due open task is overdue, past due completed task is today', () {
      final overdueDue = DateTime(2026, 9, 18, 9);

      expect(categoryForItem(_task(completed: false, dueAt: overdueDue), false, now: _now), TaskCategory.overdue);
      expect(categoryForItem(_task(completed: true, dueAt: overdueDue), true, now: _now), TaskCategory.today);
    });

    test('stale dateless open task ages into overdue, completed one stays under no deadline', () {
      final oldCreatedAt = DateTime(2026, 8, 1);

      expect(categoryForItem(_task(completed: false, createdAt: oldCreatedAt), false, now: _now), TaskCategory.overdue);
      expect(
        categoryForItem(_task(completed: true, createdAt: oldCreatedAt), true, now: _now),
        TaskCategory.noDeadline,
      );
    });

    test('buckets by due date', () {
      final cases = {
        DateTime(2026, 9, 21, 23, 59): TaskCategory.today,
        DateTime(2026, 9, 22, 8): TaskCategory.tomorrow,
        DateTime(2026, 9, 30, 8): TaskCategory.later,
      };

      cases.forEach((dueAt, expected) {
        expect(categoryForItem(_task(completed: false, dueAt: dueAt), false, now: _now), expected);
        expect(categoryForItem(_task(completed: true, dueAt: dueAt), true, now: _now), expected);
      });
    });

    test('matches the section the list puts the task in', () {
      final items = [
        _task(completed: true, dueAt: DateTime(2026, 9, 18, 9)),
        _task(completed: true, createdAt: DateTime(2026, 8, 1)),
        _task(completed: false, dueAt: DateTime(2026, 9, 18, 9)),
        _task(completed: false, dueAt: DateTime(2026, 9, 22, 8)),
        _task(completed: false, createdAt: DateTime(2026, 8, 1)),
      ];

      for (final showCompleted in [true, false]) {
        categorizeTasks(items, showCompleted, now: _now).forEach((category, tasks) {
          for (final task in tasks) {
            expect(categoryForItem(task, showCompleted, now: _now), category);
          }
        });
      }
    });
  });
}
