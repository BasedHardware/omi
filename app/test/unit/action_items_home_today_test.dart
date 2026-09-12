import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/providers/action_items_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

ActionItemWithMetadata _item({
  required String id,
  required bool completed,
  DateTime? dueAt,
}) {
  return wire.GeneratedActionItemResponse(
    id: id,
    description: id,
    completed: completed,
    dueAt: dueAt,
  );
}

void main() {
  final now = DateTime(2026, 9, 12, 15, 0);

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('filterTodayTasks keeps due-today and recent overdue, drops completed and old', () {
    final today = DateTime(2026, 9, 12, 10);
    final yesterday = DateTime(2026, 9, 11, 10);
    final eightDaysAgo = DateTime(2026, 9, 4, 10);
    final tomorrow = DateTime(2026, 9, 13, 10);
    final items = [
      _item(id: 'today', completed: false, dueAt: today),
      _item(id: 'overdue', completed: false, dueAt: yesterday),
      _item(id: 'old', completed: false, dueAt: eightDaysAgo),
      _item(id: 'done', completed: true, dueAt: today),
      _item(id: 'later', completed: false, dueAt: tomorrow),
      _item(id: 'nodue', completed: false),
    ];

    final filtered = ActionItemsProvider.filterTodayTasks(items, now: now).map((i) => i.id).toList();
    expect(filtered, ['today', 'overdue']);
  });

  test('home preview uses a due-window fetch, not the first global page', () async {
    final hiddenDue = _item(id: 'hidden-due', completed: false, dueAt: now);
    final filler = List.generate(
      100,
      (i) => _item(id: 'filler-$i', completed: false, dueAt: now.add(const Duration(days: 30))),
    );

    final dueCalls = <Map<String, Object?>>[];
    final provider = ActionItemsProvider(
      getActionItems: ({
        limit = 50,
        offset = 0,
        completed,
        conversationId,
        startDate,
        endDate,
        dueStartDate,
        dueEndDate,
      }) async {
        if (dueStartDate != null || dueEndDate != null) {
          dueCalls.add({
            'limit': limit,
            'completed': completed,
            'dueStartDate': dueStartDate,
            'dueEndDate': dueEndDate,
          });
          return ActionItemsResponse(actionItems: [hiddenDue], hasMore: false);
        }
        return ActionItemsResponse(actionItems: filler, hasMore: true);
      },
    );

    await provider.ensureLoaded();
    expect(provider.todayPreviewTasks(now: now), isEmpty);

    await provider.ensureHomeTodayTasksLoaded(now: now);
    final preview = provider.todayPreviewTasks(now: now);
    expect(preview.map((i) => i.id), ['hidden-due']);
    expect(provider.actionItems.map((i) => i.id).toList(), filler.map((i) => i.id).toList());
    expect(provider.actionItems.any((i) => i.id == 'hidden-due'), isFalse);
    expect(dueCalls, isNotEmpty);
    expect(dueCalls.first['completed'], false);
    expect(dueCalls.first['limit'], 100);
    expect((dueCalls.first['dueStartDate'] as DateTime).isBefore(now), isTrue);
    expect((dueCalls.first['dueEndDate'] as DateTime).isBefore(DateTime(2026, 9, 13)), isTrue);

    provider.dispose();
  });

  test('empty due-window result does not hide a first-page today task', () async {
    final firstPageDue = _item(id: 'first-page-due', completed: false, dueAt: now);
    final provider = ActionItemsProvider(
      getActionItems: ({
        limit = 50,
        offset = 0,
        completed,
        conversationId,
        startDate,
        endDate,
        dueStartDate,
        dueEndDate,
      }) async {
        if (dueStartDate != null || dueEndDate != null) {
          return const ActionItemsResponse(actionItems: [], hasMore: false);
        }
        return ActionItemsResponse(actionItems: [firstPageDue], hasMore: false);
      },
    );

    await provider.ensureLoaded();
    await provider.ensureHomeTodayTasksLoaded(now: now);
    expect(provider.todayPreviewTasks(now: now).map((i) => i.id), ['first-page-due']);
    provider.dispose();
  });
}
