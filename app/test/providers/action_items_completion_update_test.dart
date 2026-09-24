import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/action_items.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/action_items_provider.dart';

Future<ActionItemsResponse?> _noItems({
  int limit = 50,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    const ActionItemsResponse(actionItems: [], hasMore: false);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('toggling completion does not write back the description and due date of the copy it was given', () async {
    final server = <String, Object?>{
      'description': 'Buy oat milk',
      'completed': true,
      'due_at': DateTime.utc(2026, 9, 26),
    };
    final provider = ActionItemsProvider(
      getActionItems: _noItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async {
        if (description != null) server['description'] = description;
        if (completed != null) server['completed'] = completed;
        if (dueAt != null) server['due_at'] = dueAt;
        return ActionItemWithMetadata(id: id, description: server['description'] as String, completed: false);
      },
    );
    addTearDown(provider.dispose);

    final staleCopy = ActionItemWithMetadata(
      id: 'task-1',
      description: 'Buy milk',
      completed: true,
      dueAt: DateTime.utc(2026, 9, 20),
    );
    await provider.updateActionItemState(staleCopy, false);

    expect(server, {'description': 'Buy oat milk', 'completed': false, 'due_at': DateTime.utc(2026, 9, 26)});
  });

  for (final throws in [false, true]) {
    test('completion serializes writes and restores Tasks and Home after ${throws ? 'an exception' : 'rejection'}',
        () async {
      final item = ActionItemWithMetadata(
        id: 'task-1',
        description: 'Buy milk',
        completed: false,
        dueAt: DateTime.now(),
      );
      final response = Completer<ActionItemWithMetadata?>();
      var writes = 0;
      final provider = ActionItemsProvider(
        getActionItems: _fetchItems([item]),
        updateActionItemRequest: (id, {description, completed, dueAt}) async {
          writes++;
          return response.future;
        },
      );
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      await provider.ensureHomeTodayTasksLoaded();
      expect(provider.todayPreviewTasks(), hasLength(1));

      final pending = provider.updateActionItemState(item, true);
      expect(provider.actionItems.single.completed, isTrue);
      expect(provider.todayPreviewTasks(), isEmpty);
      // A second control cannot race a conflicting PATCH against the first.
      final competing = provider.updateActionItemState(item, false);
      if (throws) {
        response.completeError(StateError('request failed'));
      } else {
        response.complete(null);
      }
      expect(await pending, isFalse);
      expect(await competing, isFalse);
      expect(writes, 1);
      expect(provider.actionItems.single.completed, isFalse);
      expect(provider.todayPreviewTasks(), hasLength(1));
      // The pending guard must be released on every failure path.
      expect(await provider.updateActionItemState(item, true), isFalse);
      expect(writes, 2);
    });
  }

  test('rejected same-state request restores the loaded value, not the inverse of the requested value', () async {
    const loaded = ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: true);
    final provider = ActionItemsProvider(
      getActionItems: _fetchItems([loaded]),
      updateActionItemRequest: (id, {description, completed, dueAt}) async => null,
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();

    expect(await provider.updateActionItemState(loaded.copyWith(completed: false), true), isFalse);
    expect(provider.actionItems.single.completed, isTrue);
  });

  test('a refresh during a completion request cannot undo the acknowledged completion', () async {
    const item = ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: false);
    final response = Completer<ActionItemWithMetadata?>();
    final provider = ActionItemsProvider(
      getActionItems: _fetchItems([item]),
      updateActionItemRequest: (id, {description, completed, dueAt}) => response.future,
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    final pending = provider.updateActionItemState(item, true);
    await provider.fetchActionItems();

    response.complete(item.copyWith(completed: true));
    expect(await pending, isTrue);
    expect(provider.actionItems.single.completed, isTrue);
  });

  test('a completion finishing after provider disposal does not notify a disposed owner', () async {
    const item = ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: false);
    final response = Completer<ActionItemWithMetadata?>();
    final provider = ActionItemsProvider(
      getActionItems: _fetchItems([item]),
      updateActionItemRequest: (id, {description, completed, dueAt}) => response.future,
    );
    await provider.ensureLoaded();
    provider.addListener(() {});
    final pending = provider.updateActionItemState(item, true);
    provider.dispose();

    response.complete(item.copyWith(completed: true));
    expect(await pending, isTrue);
  });

  for (final (typed, surface, target, readDuringWrite, saved) in [
    (false, 'refresh', true, false, true),
    (false, 'refresh', false, false, true),
    (false, 'home', true, false, true),
    (false, 'load more', true, false, true),
    (true, 'refresh', true, false, true),
    (true, 'home', true, false, true),
    (false, 'refresh', true, true, true),
    (false, 'refresh', true, true, false),
  ]) {
    test('$surface typed=$typed target=$target during=$readDuringWrite saved=$saved preserves overlapping writes',
        () async {
      final item = ActionItemWithMetadata(
        id: 'task-1',
        description: 'Buy milk',
        completed: !target,
        dueAt: DateTime.now(),
      );
      final staleRead = Completer<ActionItemsResponse>();
      final write = Completer<ActionItemWithMetadata?>();
      var reads = 0;
      Future<ActionItemsResponse> fetch() async {
        if (++reads == 1) return ActionItemsResponse(actionItems: [item], hasMore: true);
        if (reads == 2) return staleRead.future;
        return ActionItemsResponse(actionItems: [item.copyWith(description: 'Fresh server value')]);
      }

      final provider = ActionItemsProvider(
        actionItemsApi: typed
            ? ActionItemsApi(
                baseUrl: 'http://fixture.invalid/',
                send: (_) async {
                  return http.Response(jsonEncode((await fetch()).toJson()), 200);
                })
            : null,
        getActionItems: ({
          int limit = 50,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) =>
            fetch(),
        updateActionItemRequest: (id, {description, completed, dueAt}) => write.future,
      );
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      Future<bool>? pending;
      if (readDuringWrite) pending = provider.updateActionItemState(item, target);
      final refresh = switch (surface) {
        'home' => provider.ensureHomeTodayTasksLoaded(),
        'load more' => provider.loadMoreActionItems(),
        _ => provider.fetchActionItems(),
      };
      pending ??= provider.updateActionItemState(item, target);
      write.complete(saved ? item.copyWith(completed: target) : null);
      expect(await pending, saved);
      staleRead.complete(ActionItemsResponse(
        actionItems: [item.copyWith(description: 'Refreshed description', completed: saved ? !target : target)],
        hasMore: true,
        truncated: true,
      ));
      await refresh;

      final expectedState = saved ? target : !target;
      expect(provider.actionItems.every((row) => row.completed == expectedState), isTrue);
      if (surface == 'home') {
        expect(provider.todayPreviewTasks(), isEmpty);
      } else {
        expect(provider.actionItems.last.description, 'Refreshed description');
        expect(provider.hasMore, isTrue);
      }
      if (typed && surface == 'refresh') {
        expect(provider.apiViewState.data!.single.completed, expectedState);
      }
      // A later, non-overlapping read must still accept changes from the server.
      await provider.fetchActionItems();
      expect(provider.actionItems.single.completed, !target);
      expect(provider.actionItems.single.description, 'Fresh server value');
    });
  }
}

ActionItemsFetcher _fetchItems(List<ActionItemWithMetadata> items) => ({
      int limit = 50,
      int offset = 0,
      bool? completed,
      String? conversationId,
      DateTime? startDate,
      DateTime? endDate,
      DateTime? dueStartDate,
      DateTime? dueEndDate,
    }) async =>
        ActionItemsResponse(actionItems: items);
