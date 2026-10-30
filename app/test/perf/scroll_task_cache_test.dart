import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/task_categorization.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

ActionItemWithMetadata _task(String id, {bool completed = false, DateTime? dueAt, DateTime? createdAt}) =>
    ActionItemWithMetadata(id: id, description: id, completed: completed, dueAt: dueAt, createdAt: createdAt);

void main() {
  final now = DateTime(2026, 10, 24, 12);
  test('membership, replacement and reorder mutations invalidate cached buckets', () {
    final tasks = TaskCategorizationList([_task('a'), _task('b')]);
    Map<TaskCategory, List<ActionItemWithMetadata>> buckets() => categorizeTasks(tasks, false, now: now);
    var previous = buckets();
    expect(identical(buckets(), previous), isTrue);
    for (final mutate in <void Function()>[
      () => tasks.add(_task('c')),
      () => tasks.addAll([_task('d'), _task('e')]),
      () => tasks.insert(0, _task('f')),
      () => tasks.insertAll(1, [_task('g'), _task('h')]),
      () => tasks[0] = _task('i', completed: true),
      () => tasks.sort((a, b) => b.id.compareTo(a.id)),
      () => tasks.removeAt(0),
      () => tasks.removeWhere((t) => t.id == 'a'),
      () => tasks.removeRange(0, 1),
      () => tasks.retainWhere((t) => t.id == 'b'),
      tasks.clear,
    ]) {
      mutate();
      final current = buckets();
      expect(identical(current, previous), isFalse);
      expect(current, categorizeTasks(List.of(tasks), false, now: now));
      expect(identical(buckets(), current), isTrue);
      previous = current;
    }
  });

  test('empty insertion still checks its index and does not invalidate', () {
    final tasks = TaskCategorizationList([_task('a')]);
    final before = categorizeTasks(tasks, false, now: now);
    expect(() => tasks.insertAll(5, []), throwsRangeError);
    tasks.insertAll(0, []);
    expect(identical(categorizeTasks(tasks, false, now: now), before), isTrue);
  });

  test('no-op mutations do not invalidate', () {
    final tasks = TaskCategorizationList([_task('a')]);
    final first = categorizeTasks(tasks, false, now: now);
    tasks[0] = tasks[0];
    tasks.addAll([]);
    tasks.removeWhere((_) => false);
    tasks.length = tasks.length;
    expect(identical(categorizeTasks(tasks, false, now: now), first), isTrue);
  });

  test('cache is bounded by completed filter, midnight, aging and clock rollback', () {
    final tomorrow = DateTime(2026, 10, 25);
    final tasks = TaskCategorizationList([
      _task('due', dueAt: tomorrow),
      _task('aging', createdAt: now.subtract(const Duration(days: 7))),
      _task('done', completed: true),
    ]);
    final first = categorizeTasks(tasks, false, now: now);
    expect(first[TaskCategory.tomorrow]!.single.id, 'due');
    expect(first[TaskCategory.noDeadline]!.single.id, 'aging');
    final aged = categorizeTasks(tasks, false, now: now.add(const Duration(microseconds: 1)));
    expect(aged[TaskCategory.overdue]!.single.id, 'aging');
    final completed = categorizeTasks(tasks, true, now: now);
    expect(completed[TaskCategory.noDeadline]!.single.id, 'done');
    final midnight = categorizeTasks(tasks, false, now: tomorrow);
    expect(midnight[TaskCategory.today]!.single.id, 'due');
    final rolledBack = categorizeTasks(tasks, false, now: now);
    expect(rolledBack[TaskCategory.tomorrow]!.single.id, 'due');
    expect(rolledBack[TaskCategory.noDeadline]!.single.id, 'aging');
  });

  test('self append retains normal growable-list semantics', () {
    final tasks = TaskCategorizationList([_task('a'), _task('b')]);
    categorizeTasks(tasks, false, now: now);
    tasks.addAll(tasks);
    expect(tasks.map((t) => t.id), ['a', 'b', 'a', 'b']);
    expect(categorizeTasks(tasks, false, now: now)[TaskCategory.noDeadline], hasLength(4));
  });

  test('a throwing append invalidates any appended prefix', () {
    final tasks = TaskCategorizationList([_task('a')]);
    final before = categorizeTasks(tasks, false, now: now);
    Iterable<ActionItemWithMetadata> rows() sync* {
      yield _task('b');
      throw StateError('fixture');
    }

    expect(() => tasks.addAll(rows()), throwsStateError);
    final after = categorizeTasks(tasks, false, now: now);
    expect(identical(before, after), isFalse);
    expect(after[TaskCategory.noDeadline]!.map((t) => t.id), ['a', 'b']);
  });

  test('real provider projections invalidate on completion, saved task and logout', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final provider = ActionItemsProvider(
      actionItemsApi: ActionItemsApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async => http.Response(
          jsonEncode(request.url.endsWith('/b')
              ? _task('b').toJson()
              : {
                  'action_items': [_task('a').toJson()],
                  'has_more': false
                }),
          200,
        ),
      ),
      updateActionItemRequest: (id, {description, completed, dueAt}) async => _task(id, completed: completed ?? false),
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    final before = categorizeTasks(provider.actionItems, false, now: now);
    expect(identical(categorizeTasks(provider.actionItems, false, now: now), before), isTrue);
    await provider.updateActionItemState(provider.actionItems.single, true);
    expect(categorizeTasks(provider.actionItems, false, now: now).values.expand((v) => v), isEmpty);
    await provider.receiveSavedTask('b');
    expect(categorizeTasks(provider.actionItems, false, now: now)[TaskCategory.noDeadline]!.single.id, 'b');
    provider.clearUserData();
    expect(categorizeTasks(provider.actionItems, false, now: now).values.expand((v) => v), isEmpty);
  });
}
