import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/plan/plan_grouping.dart';
import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';

ActionItem _jira(
  String id, {
  String? status,
  String? statusType,
  String? projectKey,
  DateTime? dueAt,
  DateTime? createdAt,
}) => ActionItem(
  id: id,
  description: 'jira $id',
  completed: false,
  createdAt: createdAt ?? DateTime(2026, 4, 1),
  dueAt: dueAt,
  externalSource: ExternalSource(
    source: 'jira',
    externalId: id,
    url: 'https://x/$id',
    metadata: {
      if (status != null) 'status': status,
      if (statusType != null) 'status_type': statusType,
      if (projectKey != null) 'project_key': projectKey,
    },
  ),
);

ActionItem _transcript(String id, {DateTime? createdAt, DateTime? dueAt}) => ActionItem(
  id: id,
  description: 'transcript $id',
  completed: false,
  createdAt: createdAt ?? DateTime(2026, 4, 1),
  dueAt: dueAt,
);

void main() {
  group('PlanGrouping.byProject', () {
    test('groups Jira items by project_key, sorted alphabetically', () {
      final items = [
        _jira('A-1', projectKey: 'PROJ'),
        _jira('B-1', projectKey: 'ALPHA'),
        _jira('A-2', projectKey: 'PROJ'),
      ];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byProject);

      expect(groups.map((g) => g.title).toList(), ['ALPHA', 'PROJ']);
      expect(groups[0].items.map((i) => i.id), ['B-1']);
      expect(groups[1].items.map((i) => i.id).toSet(), {'A-1', 'A-2'});
    });

    test('Jira items missing project_key bucket under JIRA', () {
      final items = [_jira('PROJ-1', projectKey: 'PROJ'), _jira('Q-1', projectKey: null)];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byProject);

      expect(groups.map((g) => g.title).toList(), ['JIRA', 'PROJ']);
    });

    test('transcript items always tail under FROM CONVERSATIONS', () {
      final items = [_transcript('t1'), _jira('PROJ-1', projectKey: 'PROJ'), _transcript('t2')];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byProject);

      expect(groups.last.title, 'FROM CONVERSATIONS');
      expect(groups.last.items.map((i) => i.id).toSet(), {'t1', 't2'});
      expect(groups.first.title, 'PROJ');
    });

    test('inside a project, items sort by due_at then created_at', () {
      final items = [
        _jira('LATE', projectKey: 'P', dueAt: DateTime(2026, 6, 1)),
        _jira('EARLY', projectKey: 'P', dueAt: DateTime(2026, 5, 1)),
        _jira('NODUE', projectKey: 'P', dueAt: null, createdAt: DateTime(2026, 4, 1)),
      ];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byProject);

      expect(groups.single.items.map((i) => i.id).toList(), ['EARLY', 'LATE', 'NODUE']);
    });
  });

  group('PlanGrouping.byStatus', () {
    test('orders status groups by status_type (todo → indeterminate → done)', () {
      final items = [
        _jira('done-1', status: 'Done', statusType: 'done'),
        _jira('todo-1', status: 'To Do', statusType: 'todo'),
        _jira('rev-1', status: 'In Review', statusType: 'indeterminate'),
        _jira('prog-1', status: 'In Progress', statusType: 'indeterminate'),
      ];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byStatus);

      // todo first, then indeterminate (alphabetical: In Progress, In Review),
      // then done.
      expect(groups.map((g) => g.title).toList(), ['TO DO', 'IN PROGRESS', 'IN REVIEW', 'DONE']);
    });

    test('transcript items always tail under FROM CONVERSATIONS', () {
      final items = [_transcript('t1'), _jira('todo-1', status: 'To Do', statusType: 'todo')];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byStatus);

      expect(groups.last.title, 'FROM CONVERSATIONS');
      expect(groups.first.title, 'TO DO');
    });

    test('Jira items missing status bucket under "No Status"', () {
      final items = [_jira('a', status: null, statusType: null), _jira('b', status: 'Done', statusType: 'done')];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byStatus);

      expect(groups.map((g) => g.title).toSet(), {'DONE', 'NO STATUS'});
    });
  });

  group('PlanGrouping.byDate', () {
    test('keeps original buckets and labels', () {
      final now = DateTime.now();
      final items = [
        _jira('overdue', dueAt: now.subtract(const Duration(days: 2))),
        _jira('today', dueAt: now.add(const Duration(hours: 1))),
        _jira('week', dueAt: now.add(const Duration(days: 3))),
        _jira('later', dueAt: now.add(const Duration(days: 30))),
        _jira('anytime', dueAt: null),
      ];
      final groups = PlanGrouping.group(items, pivot: PlanPivot.byDate);
      final titles = groups.map((g) => g.title).toSet();

      expect(titles.contains('OVERDUE'), isTrue);
      expect(titles.contains('LATER'), isTrue);
      expect(titles.contains('ANYTIME'), isTrue);
    });
  });
}
