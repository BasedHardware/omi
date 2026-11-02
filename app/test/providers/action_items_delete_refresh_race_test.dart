import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';

ActionItemWithMetadata _item(String id, {String? description}) =>
    ActionItemWithMetadata(id: id, description: description ?? id, completed: false);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<ActionItemsProvider> provider({
    required ActionItemsFetcher fetcher,
    DeleteActionItemRequest? deleter,
    BulkDeleteActionItemsRequest? bulkDeleter,
  }) async {
    final p = ActionItemsProvider(
      getActionItems: fetcher,
      deleteActionItemRequest: deleter,
      bulkDeleteActionItemsRequest: bulkDeleter,
    );
    await p.ensureLoaded();
    addTearDown(p.dispose);
    return p;
  }

  ActionItemsFetcher fetchRows(List<ActionItemWithMetadata> Function() rows) => ({
        int limit = 100,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async =>
          ActionItemsResponse(actionItems: rows());

  for (final deletedIds in <List<String>?>[
    null,
    ['a'],
    ['a', 'b']
  ]) {
    test('refresh during bulk delete cannot duplicate or resurrect rows after receipt $deletedIds', () async {
      final a = _item('a', description: 'Same text, separate task');
      final b = _item('b', description: 'Same text, separate task');
      final c = _item('c');
      var rows = [a, b, c];
      final receipt = Completer<List<String>?>();
      final p = await provider(fetcher: fetchRows(() => rows), bulkDeleter: (_) => receipt.future);

      p.startSelectionWithItem('a');
      p.selectItem('b');
      final deletion = p.deleteSelectedItems();
      expect(p.actionItems.map((item) => item.id), ['c']);

      // A transient empty/older list is not acknowledgement of a pending mutation.
      rows = [c];
      await p.fetchActionItems();
      rows = [a, b, c];
      await p.fetchActionItems();

      receipt.complete(deletedIds);
      expect(await deletion, deletedIds?.length == 2);
      expect(
        p.actionItems.map((item) => item.id),
        unorderedEquals([
          if (!(deletedIds?.contains('a') ?? false)) 'a',
          if (!(deletedIds?.contains('b') ?? false)) 'b',
          'c',
        ]),
      );
    });
  }

  for (final staged in [false, true]) {
    test('missing refresh while ${staged ? 'staged' : 'direct'} delete is in flight cannot retire its tombstone',
        () async {
      final victim = _item('deleted');
      final retained = _item('retained');
      var rows = [victim, retained];
      final receipt = Completer<bool>();
      final p = await provider(fetcher: fetchRows(() => rows), deleter: (_) => receipt.future);

      late Future<bool> deletion;
      if (staged) {
        p.stageDeleteActionItem(victim);
        deletion = p.commitStagedDelete(victim.id);
      } else {
        deletion = p.deleteActionItem(victim);
      }

      rows = [retained];
      await p.fetchActionItems();
      rows = [victim, retained];
      await p.fetchActionItems();
      receipt.complete(true);
      expect(await deletion, isTrue);
      expect(p.actionItems.map((item) => item.id), ['retained']);
    });
  }

  test('a refresh started before delete acknowledgement cannot retire its tombstone after acknowledgement', () async {
    final victim = _item('deleted');
    final retained = _item('retained');
    final receipt = Completer<bool>();
    final oldRead = Completer<ActionItemsResponse?>();
    var calls = 0;
    final p = await provider(
      fetcher: ({
        int limit = 100,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async {
        calls++;
        if (calls == 2) return oldRead.future;
        return ActionItemsResponse(actionItems: [victim, retained]);
      },
      deleter: (_) => receipt.future,
    );

    final deletion = p.deleteActionItem(victim);
    final refresh = p.fetchActionItems();
    receipt.complete(true);
    expect(await deletion, isTrue);
    oldRead.complete(ActionItemsResponse(actionItems: [retained]));
    await refresh;
    await p.fetchActionItems();

    expect(p.actionItems.map((item) => item.id), ['retained']);
  });

  for (final lane in ['tasks', 'pagination', 'home']) {
    test('a newer absence read cannot release suppression ahead of an older $lane read', () async {
      final now = DateTime.now();
      final victim = _item('deleted').copyWith(dueAt: now);
      final retained = _item('retained').copyWith(dueAt: now);
      final oldRead = Completer<ActionItemsResponse?>();
      var calls = 0;
      final p = await provider(
        fetcher: ({
          int limit = 100,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async {
          calls++;
          if (calls == 1) return ActionItemsResponse(actionItems: [victim, retained], hasMore: true);
          if (calls == 2) return oldRead.future;
          return ActionItemsResponse(actionItems: [retained]);
        },
        deleter: (_) async => true,
      );

      final older = switch (lane) {
        'tasks' => p.fetchActionItems(),
        'pagination' => p.loadMoreActionItems(),
        _ => p.ensureHomeTodayTasksLoaded(now: now),
      };
      expect(await p.deleteActionItem(victim), isTrue);
      await p.fetchActionItems();
      oldRead.complete(ActionItemsResponse(actionItems: [victim, retained]));
      await older;

      expect(p.actionItems.map((item) => item.id), ['retained']);
      expect(p.todayPreviewTasks(now: now).map((item) => item.id), ['retained']);
      // Once the older read settles, a later full read can finish reconciliation.
      await p.fetchActionItems();
      expect(p.actionItems.map((item) => item.id), ['retained']);
    });
  }

  for (final filter in ['completed', 'date']) {
    test('a late $filter-filtered response cannot confirm deletion after the filter changes', () async {
      final victim = _item('deleted');
      final retained = _item('retained');
      final filteredRead = Completer<ActionItemsResponse?>();
      var rows = [victim, retained];
      final p = await provider(
        fetcher: ({
          int limit = 100,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async {
          if (completed == false || startDate != null) return filteredRead.future;
          return ActionItemsResponse(actionItems: rows);
        },
        deleter: (_) async => true,
      );
      expect(await p.deleteActionItem(victim), isTrue);
      rows = [retained];

      if (filter == 'completed') {
        p.toggleCompletedActionItems();
        p.toggleCompletedActionItems();
      } else {
        p.setDateRangeFilter(DateTime(2026, 10, 1), DateTime(2026, 10, 2));
        p.clearDateRangeFilter();
      }
      await Future<void>.delayed(Duration.zero);
      filteredRead.complete(ActionItemsResponse(actionItems: [retained]));
      await Future<void>.delayed(Duration.zero);
      rows = [victim, retained];
      await p.fetchActionItems();

      expect(p.actionItems.map((item) => item.id), ['retained']);
    });
  }

  for (final deletedIds in <List<String>?>[
    null,
    ['a']
  ]) {
    test('bulk rollback keeps an already restored task once after receipt $deletedIds', () async {
      final a = _item('a');
      final b = _item('b');
      final c = _item('c');
      final receipt = Completer<List<String>?>();
      final p = await provider(fetcher: fetchRows(() => [a, b, c]), bulkDeleter: (_) => receipt.future);
      p.startSelectionWithItem('a');
      p.selectItem('b');
      final deletion = p.deleteSelectedItems();

      // A single-task Undo may have restored the ID before the bulk receipt.
      final restored = b.copyWith(description: 'Current row from Undo');
      p.stageDeleteActionItem(restored);
      expect(await p.undoStagedDelete('b'), isTrue);
      receipt.complete(deletedIds);
      expect(await deletion, isFalse);

      expect(p.actionItems.where((item) => item.id == 'b').single.description, 'Current row from Undo');
      expect(p.actionItems.map((item) => item.id), unorderedEquals([if (deletedIds == null) 'a', 'b', 'c']));
    });
  }

  test('a thrown bulk delete restores distinct IDs even when their descriptions match', () async {
    final a = _item('a', description: 'Same text');
    final b = _item('b', description: 'Same text');
    final p = await provider(
      fetcher: fetchRows(() => [a, b]),
      bulkDeleter: (_) async => throw StateError('transport failed'),
    );
    p.startSelectionWithItem('a');
    p.selectItem('b');

    expect(await p.deleteSelectedItems(), isFalse);
    expect(p.actionItems.map((item) => item.id), ['a', 'b']);
  });

  test('clearing an account drops its delete suppression and rejects its late receipt', () async {
    final victim = _item('deleted');
    final receipt = Completer<bool>();
    final p = await provider(fetcher: fetchRows(() => [victim]), deleter: (_) => receipt.future);
    final deletion = p.deleteActionItem(victim);

    p.clearUserData();
    await p.fetchActionItems();
    receipt.complete(true);
    expect(await deletion, isFalse);
    expect(p.actionItems.map((item) => item.id), ['deleted']);
  });

  for (final failedRead in [false, true]) {
    test('suppression can retire after an older ${failedRead ? 'throwing' : 'null'} read settles', () async {
      final victim = _item('deleted');
      final retained = _item('retained');
      final oldRead = Completer<ActionItemsResponse?>();
      var rows = [victim, retained];
      var calls = 0;
      final p = await provider(
        fetcher: ({
          int limit = 100,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async {
          calls++;
          if (calls == 2) return oldRead.future;
          return ActionItemsResponse(actionItems: rows);
        },
        deleter: (_) async => true,
      );

      final older = p.fetchActionItems();
      expect(await p.deleteActionItem(victim), isTrue);
      rows = [retained];
      await p.fetchActionItems();
      if (failedRead) {
        oldRead.completeError(StateError('read failed'));
      } else {
        oldRead.complete(null);
      }
      expect(await older, isFalse);
      // This complete post-acknowledgement read may finally retire suppression.
      await p.fetchActionItems();
      rows = [victim.copyWith(description: 'Later server record'), retained];
      await p.fetchActionItems();
      expect(p.actionItems.map((item) => item.id), ['deleted', 'retained']);
    });
  }
}
