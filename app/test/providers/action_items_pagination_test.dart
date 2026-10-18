import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';

class _TaskServer {
  final rows = List.generate(
    151,
    (i) => ActionItemWithMetadata(id: 'task-$i', description: 'Task $i', completed: false),
  );
  final offsets = <int>[];
  bool failNext = false;
  Future<ActionItemsResponse?> Function(ActionItemsResponse)? interceptNext;

  Future<ActionItemsResponse?> fetch({
    int limit = 100,
    int offset = 0,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
  }) async {
    offsets.add(offset);
    if (failNext) {
      failNext = false;
      return null;
    }
    final response = ActionItemsResponse(
      actionItems: rows.skip(offset).take(limit).toList(),
      hasMore: offset + limit < rows.length,
    );
    final intercept = interceptNext;
    interceptNext = null;
    return intercept == null ? response : await intercept(response);
  }

  void remove(Iterable<String> ids) {
    final removed = ids.toSet();
    rows.removeWhere((item) => removed.contains(item.id));
  }
}

void _expectRows(ActionItemsProvider provider, Iterable<ActionItemWithMetadata> expected) {
  final actualIds = provider.actionItems.map((item) => item.id).toList();
  expect(actualIds.toSet(), expected.map((item) => item.id).toSet());
  expect(actualIds.length, actualIds.toSet().length, reason: 'Every server ID must occur at most once');
}

Future<void> _drain(ActionItemsProvider provider) async {
  for (var attempt = 0; attempt < 10 && provider.hasMore; attempt++) {
    await provider.loadMoreActionItems();
  }
  expect(provider.hasMore, isFalse, reason: 'Finite server data must finish within the bounded page budget');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<ActionItemsProvider> createProvider(
    _TaskServer server, {
    DeleteActionItemRequest? delete,
    BulkDeleteActionItemsRequest? bulkDelete,
    CreateActionItemRequest? create,
  }) async {
    final provider = ActionItemsProvider(
      getActionItems: server.fetch,
      deleteActionItemRequest: delete ?? (_) async => false,
      bulkDeleteActionItemsRequest: bulkDelete ?? (_) async => null,
      createActionItemRequest: create,
    );
    addTearDown(() {
      provider.clearUserData();
      provider.dispose();
    });
    await provider.ensureLoaded();
    return provider;
  }

  for (final deleteLastHalf in [false, true]) {
    test('pending bulk delete progresses past ${deleteLastHalf ? 'tombstone' : 'duplicate'}-only overlap', () async {
      final server = _TaskServer();
      final deletion = Completer<List<String>?>();
      final provider = await createProvider(server, bulkDelete: (_) => deletion.future);
      final victims = provider.actionItems.skip(deleteLastHalf ? 50 : 0).take(50).toList();
      final victimIds = victims.map((item) => item.id).toSet();
      for (final item in victims) {
        provider.selectItem(item.id);
      }
      final deleting = provider.deleteSelectedItems();
      expect(provider.actionItems, hasLength(50));
      try {
        await _drain(provider);
        _expectRows(provider, server.rows.where((item) => !victimIds.contains(item.id)));
        expect(server.offsets, [0, 100, 150]);
      } finally {
        deletion.complete(null);
        await deleting;
      }
    });
  }

  test('refresh with staged rows retains the unfiltered server position', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    final victims = provider.actionItems.take(50).toList();
    final victimIds = victims.map((item) => item.id).toSet();
    for (final item in victims) {
      provider.stageDeleteActionItem(item);
    }
    await provider.fetchActionItems();

    await _drain(provider);

    _expectRows(provider, server.rows.where((item) => !victimIds.contains(item.id)));
    expect(server.offsets, [0, 0, 100, 150]);
  });

  test('undo after paging restores one staged row without duplicates', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    provider.stageDeleteActionItem(provider.actionItems.first);
    await _drain(provider);

    expect(await provider.undoStagedDelete('task-0'), isTrue);

    _expectRows(provider, server.rows);
  });

  test('failed bulk delete after paging restores all rows and selection', () async {
    final server = _TaskServer();
    final deletion = Completer<List<String>?>();
    final provider = await createProvider(server, bulkDelete: (_) => deletion.future);
    provider.startSelection();
    final victims = provider.actionItems.take(50).toList();
    for (final item in victims) {
      provider.selectItem(item.id);
    }
    final deleting = provider.deleteSelectedItems();
    try {
      await _drain(provider);
    } finally {
      deletion.complete(null);
      await deleting;
    }

    _expectRows(provider, server.rows);
    expect(provider.isSelectionMode, isTrue);
    expect(provider.selectedItems, victims.map((item) => item.id).toSet());
  });

  for (final successCount in [25, 50]) {
    test('$successCount successful bulk deletions after paging do not skip the final server row', () async {
      final server = _TaskServer();
      final deletion = Completer<List<String>?>();
      final provider = await createProvider(server, bulkDelete: (_) => deletion.future);
      final victims = provider.actionItems.take(50).toList();
      for (final item in victims) {
        provider.selectItem(item.id);
      }
      final deleting = provider.deleteSelectedItems();
      await provider.loadMoreActionItems();
      final deletedIds = victims.take(successCount).map((item) => item.id).toList();
      server.remove(deletedIds);
      deletion.complete(deletedIds);
      expect(await deleting, successCount == victims.length);

      await _drain(provider);

      _expectRows(provider, server.rows);
      expect(provider.actionItems.any((item) => item.id == 'task-150'), isTrue);
    });
  }

  test('successful staged deletion before load-more does not skip shifted rows', () async {
    final server = _TaskServer();
    final provider = await createProvider(server, delete: (id) async {
      server.remove([id]);
      return true;
    });
    provider.stageDeleteActionItem(provider.actionItems.first);
    expect(await provider.commitStagedDelete('task-0'), isTrue);

    await _drain(provider);

    _expectRows(provider, server.rows);
  });

  test('a page begun before successful deletion cannot overwrite the restarted pagination', () async {
    final server = _TaskServer();
    final deletion = Completer<bool>();
    final provider = await createProvider(server, delete: (_) => deletion.future);
    provider.stageDeleteActionItem(provider.actionItems.first);
    final deleting = provider.commitStagedDelete('task-0');
    final captured = Completer<ActionItemsResponse>();
    final release = Completer<ActionItemsResponse?>();
    server.interceptNext = (response) {
      captured.complete(response);
      return release.future;
    };
    final loading = provider.loadMoreActionItems();
    final oldPage = await captured.future;
    server.remove(['task-0']);
    deletion.complete(true);
    expect(await deleting, isTrue);
    release.complete(oldPage);
    await loading;

    await _drain(provider);

    _expectRows(provider, server.rows);
  });

  test('a page begun before refresh cannot advance the refreshed pagination', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    final captured = Completer<ActionItemsResponse>();
    final release = Completer<ActionItemsResponse?>();
    server.interceptNext = (response) {
      captured.complete(response);
      return release.future;
    };
    final loading = provider.loadMoreActionItems();
    final oldPage = await captured.future;
    final removedIds = server.rows.take(50).map((item) => item.id).toList();
    server.remove(removedIds);
    await provider.fetchActionItems();
    release.complete(oldPage);
    await loading;

    await _drain(provider);

    _expectRows(provider, server.rows);
  });

  test('a failed page retries the same server offset', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    server.failNext = true;
    await provider.loadMoreActionItems();
    expect(provider.actionItems, hasLength(100));
    await _drain(provider);

    _expectRows(provider, server.rows);
    expect(server.offsets, [0, 100, 100, 150]);
  });

  test('typed rejected rows and duplicate-only pages advance by consumed server rows', () async {
    final offsets = <int>[];
    Map<String, Object> row(String id) => {'id': id, 'description': id, 'completed': false};
    final provider = ActionItemsProvider(
      actionItemsApi: api.ActionItemsApi(
        baseUrl: 'http://127.0.0.1:9/',
        send: (request) async {
          final offset = int.parse(Uri.parse(request.url).queryParameters['offset']!);
          offsets.add(offset);
          final rows = switch (offset) {
            0 => [row('a'), 'malformed', row('b')],
            3 => [row('b'), row('b'), 'malformed'],
            6 => [row('c')],
            _ => <Object>[],
          };
          return http.Response(jsonEncode({'action_items': rows, 'has_more': offset < 6}), 200);
        },
      ),
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();

    await _drain(provider);

    expect(provider.actionItems.map((item) => item.id), ['a', 'b', 'c']);
    expect(offsets, [0, 3, 6]);
  });

  test('pending creation keeps server offset and success survives a refresh that removes the temporary row', () async {
    final server = _TaskServer();
    final creation = Completer<ActionItemWithMetadata?>();
    final provider = await createProvider(server,
        create: ({required description, dueAt, conversationId, completed = false}) => creation.future);
    final creating = provider.createActionItem(description: 'Created task');
    expect(provider.actionItems, hasLength(101));
    await provider.loadMoreActionItems();
    expect(server.offsets, [0, 100]);
    await provider.fetchActionItems();
    const created = ActionItemWithMetadata(id: 'created', description: 'Created task', completed: false);
    server.rows.insert(0, created);
    creation.complete(created);
    expect(await creating, same(created));

    await _drain(provider);

    _expectRows(provider, server.rows);
  });

  test('a page begun before successful creation cannot skip a shifted server row', () async {
    final server = _TaskServer();
    final creation = Completer<ActionItemWithMetadata?>();
    final provider = await createProvider(server,
        create: ({required description, dueAt, conversationId, completed = false}) => creation.future);
    final creating = provider.createActionItem(description: 'Created task');
    final captured = Completer<ActionItemsResponse>();
    final release = Completer<ActionItemsResponse?>();
    server.interceptNext = (response) {
      captured.complete(response);
      return release.future;
    };
    final loading = provider.loadMoreActionItems();
    final oldPage = await captured.future;
    const created = ActionItemWithMetadata(id: 'created', description: 'Created task', completed: false);
    server.rows.insert(0, created);
    creation.complete(created);
    await creating;
    release.complete(oldPage);
    await loading;

    await _drain(provider);

    _expectRows(provider, server.rows);
  });

  test('a superseded page cannot clear the loading flag of a newer refresh', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    final oldCaptured = Completer<ActionItemsResponse>();
    final oldRelease = Completer<ActionItemsResponse?>();
    server.interceptNext = (response) {
      oldCaptured.complete(response);
      return oldRelease.future;
    };
    final loading = provider.loadMoreActionItems();
    final oldPage = await oldCaptured.future;
    final newCaptured = Completer<ActionItemsResponse>();
    final newRelease = Completer<ActionItemsResponse?>();
    server.interceptNext = (response) {
      newCaptured.complete(response);
      return newRelease.future;
    };
    final refreshing = provider.fetchActionItems();
    final newPage = await newCaptured.future;
    oldRelease.complete(oldPage);
    await loading;
    final wasStillFetching = provider.isFetching;
    newRelease.complete(newPage);
    await refreshing;

    expect(wasStillFetching, isTrue);
    expect(provider.isFetching, isFalse);
    _expectRows(provider, server.rows.take(100));
  });

  test('a superseded constructor preload cannot clear successful refresh hydration', () async {
    final server = _TaskServer();
    final captured = Completer<ActionItemsResponse>();
    final release = Completer<ActionItemsResponse?>();
    server.interceptNext = (response) {
      captured.complete(response);
      return release.future;
    };
    final provider = ActionItemsProvider(getActionItems: server.fetch);
    addTearDown(provider.dispose);
    final initialLoading = provider.ensureLoaded();
    final oldPage = await captured.future;
    server.remove(server.rows.take(50).map((item) => item.id).toList());
    await provider.fetchActionItems();
    release.complete(oldPage);
    await initialLoading;

    expect(provider.hasLoaded, isTrue);
    _expectRows(provider, server.rows.take(100));
  });

  test('an empty page with hasMore exits without retrying forever', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    server.interceptNext = (_) async => const ActionItemsResponse(actionItems: [], hasMore: true);

    await provider.loadMoreActionItems();

    expect(server.offsets, [0, 100]);
    expect(provider.isFetching, isFalse);
    expect(provider.hasMore, isTrue);
    _expectRows(provider, server.rows.take(100));
  });

  test('duplicate-only pages have a bounded request budget and retry from the advanced offset', () async {
    final server = _TaskServer();
    final provider = await createProvider(server);
    var duplicateCalls = 0;
    late Future<ActionItemsResponse?> Function(ActionItemsResponse) duplicates;
    duplicates = (_) async {
      duplicateCalls++;
      // End a broken unbounded implementation deterministically, instead of hanging the suite.
      if (duplicateCalls > 8) return null;
      server.interceptNext = duplicates;
      return ActionItemsResponse(actionItems: [server.rows.first], hasMore: true);
    };
    server.interceptNext = duplicates;

    await provider.loadMoreActionItems();
    final firstCallCount = duplicateCalls;
    await provider.loadMoreActionItems();

    expect(firstCallCount, inInclusiveRange(1, 3));
    expect(duplicateCalls - firstCallCount, inInclusiveRange(1, 3));
    expect(server.offsets.skip(1), List.generate(duplicateCalls, (i) => 100 + i));
    expect(provider.hasMore, isTrue);
    expect(provider.isFetching, isFalse);
    _expectRows(provider, server.rows.take(100));
  });
}
