import 'package:flutter_test/flutter_test.dart';
import 'dart:async';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/siri_integration.dart';

class _SnapshotHost extends SiriIndexApi {
  final conversations = <String, SiriConversation>{};
  final memories = <String, SiriMemory>{};
  final tasks = <String, SiriTask>{};
  Completer<void>? pendingMemoryDelete;
  Completer<void>? pendingConversationDelete;

  @override
  Future<void> upsertConversations(String uid, List<SiriConversation> rows) async {
    for (final row in rows) {
      conversations[row.id] = row;
    }
  }

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> rows) async {
    for (final row in rows) {
      memories[row.id] = row;
    }
  }

  @override
  Future<void> upsertTasks(String uid, List<SiriTask> rows) async {
    for (final row in rows) {
      tasks[row.id] = row;
    }
  }

  @override
  Future<void> reconcileConversations(String uid, List<SiriConversation> rows, int? coveredAfterMs) async {
    final keep = rows.map((row) => row.id).toSet();
    conversations
        .removeWhere((id, row) => (coveredAfterMs == null || row.startedAtMs > coveredAfterMs) && !keep.contains(id));
    await upsertConversations(uid, rows);
  }

  @override
  Future<void> reconcileMemories(String uid, List<SiriMemory> rows) async {
    final keep = rows.map((row) => row.id).toSet();
    memories.removeWhere((id, _) => !keep.contains(id));
    await upsertMemories(uid, rows);
  }

  @override
  Future<void> reconcileTasks(String uid, List<SiriTask> rows, bool includeCompleted) async {
    final keep = rows.map((row) => row.id).toSet();
    tasks.removeWhere((id, row) => (includeCompleted || !row.completed) && !keep.contains(id));
    await upsertTasks(uid, rows);
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {
    if (type == 'memory') await pendingMemoryDelete?.future;
    if (type == 'conversation') await pendingConversationDelete?.future;
    final rows = switch (type) {
      'conversation' => conversations,
      'memory' => memories,
      'task' => tasks,
      _ => throw ArgumentError.value(type),
    };
    for (final id in ids) {
      rows.remove(id);
    }
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'siri-fetch-owner'});
    await SharedPreferencesUtil.init();
  });

  _SnapshotHost hostForTest() {
    final host = _SnapshotHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'siri-fetch-owner');
    addTearDown(() => SiriIntegration.testInstance = null);
    return host;
  }

  test('complete conversation fetch removes remotely deleted ids from the index', () async {
    final host = hostForTest();
    host.conversations['remote-deleted'] = SiriConversation(
        id: 'remote-deleted',
        title: 'private',
        summary: 'summary',
        startedAtMs: DateTime.now().millisecondsSinceEpoch,
        updatedAtMs: DateTime.now().millisecondsSinceEpoch);
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    expect(await provider.fetchConversations(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.conversations, isEmpty);
  });

  test('first conversation page reconciles only newer-than-window ids', () async {
    final host = hostForTest();
    final now = DateTime.now();
    host.conversations['remote-deleted-new'] = SiriConversation(
        id: 'remote-deleted-new',
        title: 'private',
        summary: 'summary',
        startedAtMs: now.millisecondsSinceEpoch,
        updatedAtMs: now.millisecondsSinceEpoch);
    host.conversations['outside-page'] = SiriConversation(
        id: 'outside-page',
        title: 'older',
        summary: 'summary',
        startedAtMs: now.subtract(const Duration(days: 100)).millisecondsSinceEpoch,
        updatedAtMs: now.millisecondsSinceEpoch);
    final rows = List.generate(
      50,
      (index) => ServerConversation(
        id: 'page-$index',
        createdAt: now.subtract(Duration(hours: index + 1)),
        structured: Structured('Page $index', 'summary'),
        status: ConversationStatus.completed,
      ),
    );
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: rows, ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    expect(await provider.fetchConversations(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.conversations.containsKey('remote-deleted-new'), isFalse);
    expect(host.conversations.containsKey('outside-page'), isTrue);
  });

  test('merge notification deletes source conversations and upserts merged row', () async {
    final host = hostForTest();
    final now = DateTime.now();
    ServerConversation row(String id) => ServerConversation(
          id: id,
          createdAt: now,
          structured: Structured(id, 'summary'),
          status: ConversationStatus.completed,
        );
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async => (item: row('merged'), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    await provider.addConversation(row('source'));
    await SiriIntegration.current.drainIndexForTest();
    expect(host.conversations.containsKey('source'), isTrue);
    await provider.onMergeCompleted('merged', ['source']);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.conversations.containsKey('source'), isFalse);
    expect(host.conversations.containsKey('merged'), isTrue);
  });

  test('merge notification restores state and fetches merged row with an empty visible list', () async {
    final host = hostForTest();
    final row = ServerConversation(
      id: 'merged-outside-page',
      createdAt: DateTime.now(),
      structured: Structured('Merged', 'summary'),
      status: ConversationStatus.completed,
    );
    var fetches = 0;
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async {
        fetches++;
        return (item: row, ok: true);
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.mergingConversationIds.add('source-outside-page');

    await provider.onMergeCompleted(row.id, ['source-outside-page']);
    await SiriIntegration.current.drainIndexForTest();

    expect(provider.mergingConversationIds, isNot(contains('source-outside-page')));
    expect(fetches, 1);
    expect(provider.conversations.map((item) => item.id), contains(row.id));
    expect(host.conversations, contains(row.id));
  });

  test('merge fetch proceeds while an unrelated Spotlight delete is pending', () async {
    final host = hostForTest()..pendingConversationDelete = Completer<void>();
    var fetches = 0;
    final row =
        ServerConversation(id: 'merged', createdAt: DateTime.now(), structured: Structured('Merged', 'summary'));
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async {
        fetches++;
        return (item: row, ok: true);
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final merge = provider.onMergeCompleted(row.id, ['source']);
    await Future<void>.delayed(Duration.zero);
    expect(fetches, 1, reason: 'the normal merge fetch cannot wait on Spotlight');
    expect(provider.conversations.map((item) => item.id), contains(row.id));
    host.pendingConversationDelete!.complete();
    await merge;
    await SiriIntegration.current.drainIndexForTest();
    expect(host.conversations, contains(row.id));
  });

  test('complete unfiltered memory fetch removes remotely deleted ids', () async {
    final host = hostForTest();
    host.memories['remote-deleted'] =
        SiriMemory(id: 'remote-deleted', content: 'private', createdAtMs: DateTime.now().millisecondsSinceEpoch);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories, isEmpty);
  });

  test('failed ledger history cannot make a useful-now memory fetch authoritative', () async {
    final host = _SnapshotHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'siri-fetch-owner',
        memoryPageFetcher: ({required limit, required offset, cursor}) async =>
            const GetMemoriesResult([], true, truncated: true));
    addTearDown(() => SiriIntegration.testInstance = null);
    final now = DateTime.now();
    Memory row(String id) => Memory(
        id: id,
        uid: 'siri-fetch-owner',
        content: id,
        category: MemoryCategory.manual,
        createdAt: now,
        updatedAt: now,
        visibility: MemoryVisibility.private);
    await SiriIntegration.current.upsertMemories([row('outside-useful-now')]);
    final requestedViews = <MemoryReadView?>[];
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: ({limit = 100, offset = 0, thisDeviceOnly = false, cursor, view}) async {
        requestedViews.add(view);
        return GetMemoriesResult([row('useful-now')], true, beliefEnabled: true);
      },
      fetchLedgerHistoryRequest: ({limit = 500, offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: false),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    expect(requestedViews, contains(MemoryReadView.usefulNow));
    expect(host.memories.keys, contains('outside-useful-now'));
  });

  test('confirmed memory review removes a rejected row from the index', () async {
    final host = hostForTest();
    final row = Memory(
        id: 'reviewed',
        uid: 'siri-fetch-owner',
        content: 'private fact',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      reviewMemoryRequest: (_, __) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories.containsKey(row.id), isTrue);
    expect(await provider.reviewMemory(row, false), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories.containsKey(row.id), isFalse);
  });

  test('confirmed memory edit updates indexed content', () async {
    final host = hostForTest();
    final row = Memory(
        id: 'edited',
        uid: 'siri-fetch-owner',
        content: 'old',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      editMemoryRequest: (_, __) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    expect(await provider.editMemory(row, 'new'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories[row.id]?.content, 'new');
  });

  test('confirmed edit of an unloaded memory cannot leave stale indexed text', () async {
    final host = hostForTest();
    final row = Memory(
        id: 'unloaded-edit',
        uid: 'siri-fetch-owner',
        content: 'old',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    await SiriIntegration.current.upsertMemories([row]);
    final provider = MemoriesProvider(
      editMemoryRequest: (_, __) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(provider.dispose);
    expect(await provider.editMemory(row, 'new'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories[row.id]?.content, 'new');
  });

  test('confirmed delete all memories clears memory index but retains other types', () async {
    final host = hostForTest();
    final row = Memory(
        id: 'delete-all',
        uid: 'siri-fetch-owner',
        content: 'private',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      deleteAllMemoriesRequest: () async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    host.tasks['retained-task'] = SiriTask(
        id: 'retained-task', title: 'task', completed: false, createdAtMs: DateTime.now().millisecondsSinceEpoch);
    expect(await provider.deleteAllMemories(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories, isEmpty);
    expect(host.tasks.containsKey('retained-task'), isTrue);
  });

  test('failed delete all memories keeps existing index entries', () async {
    final host = hostForTest();
    final row = Memory(
        id: 'still-owned',
        uid: 'siri-fetch-owner',
        content: 'private',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      deleteAllMemoriesRequest: () async => false,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    expect(await provider.deleteAllMemories(), isFalse);
    expect(host.memories.containsKey(row.id), isTrue);
  });

  test('memory undo completes while native delete is pending, then restores in order', () async {
    final host = hostForTest();
    final row = Memory(
      id: 'undo-race',
      uid: 'siri-fetch-owner',
      content: 'restore me',
      category: MemoryCategory.manual,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      visibility: MemoryVisibility.private,
    );
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories, contains(row.id));

    host.pendingMemoryDelete = Completer<void>();
    provider.deleteMemory(row);
    final restored = provider.restoreLastDeletedMemory(id: row.id);
    var completed = false;
    restored.then((_) => completed = true);
    await Future<void>.delayed(Duration.zero);
    expect(completed, isTrue);
    host.pendingMemoryDelete!.complete();
    expect(await restored, isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories, contains(row.id));
  });

  test('confirmed memory create and visibility mutation update the snapshot', () async {
    final host = hostForTest();
    final confirmed = Memory(
        id: 'created-server-id',
        uid: 'siri-fetch-owner',
        content: 'remembered',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(
      createMemoryRequest: (_, __, ___) async => confirmed,
      updateMemoryVisibilityRequest: (_, __) async => true,
    );
    addTearDown(provider.dispose);
    expect(await provider.createMemory('remembered'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories['created-server-id']?.content, 'remembered');
    expect(await provider.updateMemoryVisibility(provider.memories.single, MemoryVisibility.public), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories['created-server-id'], isNotNull);
  });

  test('confirmed visibility update refreshes the indexed projection', () async {
    final host = hostForTest();
    final row = Memory(
        id: 'visible',
        uid: 'siri-fetch-owner',
        content: 'fact',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      updateMemoryVisibilityRequest: (_, __) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    host.memories.remove(row.id);
    expect(await provider.updateMemoryVisibility(row, MemoryVisibility.public), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories.containsKey(row.id), isTrue);
  });

  test('bulk visibility writes reproject every confirmed memory', () async {
    final host = hostForTest();
    final rows = ['bulk-a', 'bulk-b']
        .map((id) => Memory(
            id: id,
            uid: 'siri-fetch-owner',
            content: id,
            category: MemoryCategory.manual,
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
            visibility: MemoryVisibility.public))
        .toList();
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(rows, true),
      updateMemoryVisibilityRequest: (_, __) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await SiriIntegration.current.drainIndexForTest();
    host.memories.clear();
    expect(await provider.updateAllMemoriesVisibility(true), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories.keys.toSet(), {'bulk-a', 'bulk-b'});
  });

  test('offline memory upload indexes its confirmed server row', () async {
    final host = hostForTest();
    var attempt = 0;
    final confirmed = Memory(
        id: 'uploaded',
        uid: 'siri-fetch-owner',
        content: 'offline fact',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final provider = MemoriesProvider(createMemoryRequest: (_, __, ___) async {
      attempt++;
      return attempt == 1 ? null : confirmed;
    });
    addTearDown(provider.dispose);
    expect(await provider.createMemory('offline fact'), isTrue);
    expect(host.memories, isEmpty);
    await provider.syncPendingMemories();
    await SiriIntegration.current.drainIndexForTest();
    expect(host.memories.containsKey('uploaded'), isTrue);
  });

  test('default filtered memory view refreshes the owner-wide all view', () async {
    final host = _SnapshotHost();
    host.memories['remote-deleted'] =
        SiriMemory(id: 'remote-deleted', content: 'private', createdAtMs: DateTime.now().millisecondsSinceEpoch);
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        memoryPageFetcher: ({required limit, required offset, cursor}) async => const GetMemoriesResult([], true));

    await siri.refreshAuthoritativeMemories();
    expect(host.memories, isEmpty);
  });

  test('truncated owner-wide memory traversal never prunes unseen ids', () async {
    final host = _SnapshotHost();
    host.memories['outside-page'] =
        SiriMemory(id: 'outside-page', content: 'private', createdAtMs: DateTime.now().millisecondsSinceEpoch);
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        memoryPageFetcher: ({required limit, required offset, cursor}) async =>
            const GetMemoriesResult([], true, truncated: true));

    await siri.refreshAuthoritativeMemories();
    expect(host.memories.containsKey('outside-page'), isTrue);
  });

  test('stale owner-wide refresh cannot reindex a deleted memory before undo', () async {
    final host = _SnapshotHost();
    final row = Memory(
      id: 'pending-delete',
      uid: 'siri-fetch-owner',
      content: 'private fact',
      category: MemoryCategory.manual,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      visibility: MemoryVisibility.private,
    );
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        memoryPageFetcher: ({required limit, required offset, cursor}) async => GetMemoriesResult([row], true));
    SiriIntegration.testInstance = siri;
    addTearDown(() => SiriIntegration.testInstance = null);

    await siri.upsertMemories([row]);
    siri.queueDelete('memory', row.id);
    await siri.drainIndexForTest();
    expect(host.memories.containsKey(row.id), isFalse);

    await siri.refreshAuthoritativeMemories();
    expect(host.memories.containsKey(row.id), isFalse);

    siri.queueUpsertMemories([row], restoreDeleted: true);
    await siri.drainIndexForTest();
    expect(host.memories.containsKey(row.id), isTrue);
  });

  test('complete active task fetch removes absent active ids but preserves completed ids', () async {
    final host = hostForTest();
    final now = DateTime.now().millisecondsSinceEpoch;
    final provider = ActionItemsProvider(
      getActionItems: ({
        limit = 100,
        offset = 0,
        completed,
        conversationId,
        startDate,
        endDate,
        dueStartDate,
        dueEndDate,
      }) async =>
          const ActionItemsResponse(actionItems: [], hasMore: false),
    );
    addTearDown(provider.dispose);

    await provider.ensureLoaded();
    await SiriIntegration.current.drainIndexForTest();
    host.tasks['remote-deleted'] = SiriTask(id: 'remote-deleted', title: 'private', completed: false, createdAtMs: now);
    host.tasks['completed-outside-filter'] =
        SiriTask(id: 'completed-outside-filter', title: 'done', completed: true, createdAtMs: now, completedAtMs: now);
    provider.toggleCompletedActionItems();
    expect(await provider.fetchActionItems(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.tasks.containsKey('remote-deleted'), isFalse);
    expect(host.tasks.containsKey('completed-outside-filter'), isTrue);
  });

  test('partial active task fetch preserves ids outside the loaded page', () async {
    final host = hostForTest();
    final now = DateTime.now().millisecondsSinceEpoch;
    host.tasks['outside-page'] = SiriTask(id: 'outside-page', title: 'private', completed: false, createdAtMs: now);
    final provider = ActionItemsProvider(
      getActionItems: ({
        limit = 100,
        offset = 0,
        completed,
        conversationId,
        startDate,
        endDate,
        dueStartDate,
        dueEndDate,
      }) async =>
          const ActionItemsResponse(actionItems: [], hasMore: true),
    );
    addTearDown(provider.dispose);

    expect(await provider.fetchActionItems(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.tasks.containsKey('outside-page'), isTrue);
  });

  test('owner-wide refresh indexes tasks, conversations and memories beyond UI pages', () async {
    final now = DateTime.now();
    final host = _SnapshotHost();
    final taskOffsets = <String>[];
    final conversationOffsets = <int>[];
    final memoryCursors = <String?>[];
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        taskPageFetcher: ({required limit, required offset, required completed}) async {
      taskOffsets.add('$completed:$offset');
      if (completed) {
        return ApiSuccess(ActionItemsResponse(actionItems: [
          ActionItemWithMetadata(
              id: 'recent-completed', description: 'Recent', completed: true, completedAt: now, status: 'completed'),
        ], hasMore: false));
      }
      return ApiSuccess(ActionItemsResponse(
          actionItems: offset == 0
              ? List.generate(
                  100,
                  (i) =>
                      ActionItemWithMetadata(id: 'open-$i', description: 'Open $i', completed: false, status: 'active'))
              : [
                  const ActionItemWithMetadata(
                      id: 'open-beyond-page', description: 'Later', completed: false, status: 'active')
                ],
          hasMore: offset == 0));
    }, conversationPageFetcher: ({required limit, required offset, required startDate}) async {
      conversationOffsets.add(offset);
      final rows = offset == 0
          ? List.generate(
              100,
              (i) => ServerConversation(
                  id: 'conversation-$i',
                  createdAt: now,
                  structured: Structured('Title $i', 'Summary'),
                  status: ConversationStatus.completed))
          : [
              ServerConversation(
                  id: 'conversation-beyond-page',
                  createdAt: now,
                  structured: Structured('Later', 'Summary'),
                  status: ConversationStatus.completed)
            ];
      return ApiSuccess<List<ServerConversation>>(rows);
    }, memoryPageFetcher: ({required limit, required offset, cursor}) async {
      memoryCursors.add(cursor);
      Memory row(String id) => Memory(
          id: id,
          uid: 'siri-fetch-owner',
          content: id,
          category: MemoryCategory.manual,
          createdAt: now,
          updatedAt: now,
          visibility: MemoryVisibility.private,
          layer: MemoryLayer.longTerm,
          layerIsExplicit: true);
      return cursor == null
          ? GetMemoriesResult([row('memory-first')], true, nextCursor: 'second')
          : GetMemoriesResult([row('memory-beyond-page')], true);
    });

    await siri.refreshOwnerWideIndex();
    expect(host.tasks.keys, containsAll(['open-beyond-page', 'recent-completed']));
    expect(host.conversations.keys, contains('conversation-beyond-page'));
    expect(host.memories.keys, contains('memory-beyond-page'));
    expect(taskOffsets, ['false:0', 'false:100', 'true:0']);
    expect(conversationOffsets, [0, 100]);
    expect(memoryCursors, [null, 'second']);
  });

  test('owner-wide conversation refresh backs off on 429 and never prunes an incomplete window', () async {
    final host = _SnapshotHost();
    final now = DateTime.now().millisecondsSinceEpoch;
    host.conversations['unseen'] =
        SiriConversation(id: 'unseen', title: 'Keep', summary: 'Private', startedAtMs: now, updatedAtMs: now);
    var calls = 0;
    final delays = <Duration>[];
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        conversationPageFetcher: ({required limit, required offset, required startDate}) async {
          calls++;
          return calls == 1
              ? const ApiFailure<List<ServerConversation>>(
                  ApiProblem(ApiProblemKind.rateLimited, statusCode: 429, retryAfter: Duration(seconds: 3)))
              : const ApiFailure<List<ServerConversation>>(ApiProblem(ApiProblemKind.server, statusCode: 503));
        },
        taskPageFetcher: ({required limit, required offset, required completed}) async =>
            const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false)),
        memoryPageFetcher: ({required limit, required offset, cursor}) async => const GetMemoriesResult([], true),
        delay: (duration) async => delays.add(duration));
    await siri.refreshOwnerWideIndex();
    expect(calls, 2);
    expect(delays, contains(const Duration(seconds: 3)));
    expect(host.conversations.keys, contains('unseen'));
  });

  test('typed list APIs preserve server truncation headers for safe reconciliation', () async {
    const headers = {'x-omi-list-truncated': 'true'};
    final conversations = await ConversationApi(
        baseUrl: 'http://localhost/', send: (_) async => http.Response('[]', 200, headers: headers)).list();
    final tasks = await ActionItemsApi(
        baseUrl: 'http://localhost/',
        send: (_) async => http.Response('{"action_items":[],"has_more":false}', 200, headers: headers)).list();
    expect((conversations as ApiSuccess<List<ServerConversation>>).truncated, isTrue);
    expect((tasks as ApiSuccess<ActionItemsResponse>).truncated, isTrue);
  });

  test('incomplete owner-wide task traversal keeps unseen indexed tasks', () async {
    final host = _SnapshotHost();
    final now = DateTime.now().millisecondsSinceEpoch;
    host.tasks['unseen'] = SiriTask(id: 'unseen', title: 'Keep', completed: false, createdAtMs: now);
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        taskPageFetcher: ({required limit, required offset, required completed}) async => completed
            ? const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false))
            : const ApiFailure(ApiProblem(ApiProblemKind.rateLimited, statusCode: 429)),
        conversationPageFetcher: ({required limit, required offset, required startDate}) async =>
            const ApiSuccess<List<ServerConversation>>([]),
        memoryPageFetcher: ({required limit, required offset, cursor}) async => const GetMemoriesResult([], true));

    await siri.refreshOwnerWideIndex();
    expect(host.tasks.keys, contains('unseen'));
  });

  test('delete reaches Spotlight while an owner-wide fetch is pending', () async {
    final host = _SnapshotHost();
    final fetchStarted = Completer<void>();
    final releaseFetch = Completer<ApiResult<ActionItemsResponse>>();
    final now = DateTime.now();
    host.memories['deleted-during-fetch'] =
        SiriMemory(id: 'deleted-during-fetch', content: 'Private', createdAtMs: now.millisecondsSinceEpoch);
    final staleRow = Memory(
        id: 'deleted-during-fetch',
        uid: 'siri-fetch-owner',
        content: 'Private',
        category: MemoryCategory.manual,
        createdAt: now,
        updatedAt: now,
        visibility: MemoryVisibility.private);
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        taskPageFetcher: ({required limit, required offset, required completed}) {
          if (!completed) {
            fetchStarted.complete();
            return releaseFetch.future;
          }
          return Future.value(const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false)));
        },
        conversationPageFetcher: ({required limit, required offset, required startDate}) async =>
            const ApiSuccess<List<ServerConversation>>([]),
        memoryPageFetcher: ({required limit, required offset, cursor}) async => GetMemoriesResult([staleRow], true));

    final refresh = siri.refreshOwnerWideIndex();
    await fetchStarted.future;
    siri.queueDelete('memory', 'deleted-during-fetch');
    await siri.drainIndexForTest().timeout(const Duration(seconds: 1));
    expect(host.memories.containsKey('deleted-during-fetch'), isFalse);
    releaseFetch.complete(const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false)));
    await refresh;
    expect(host.memories.containsKey('deleted-during-fetch'), isFalse,
        reason: 'stale owner-wide projection must respect the queued delete fence');
  });

  test('capped conversation traversal adds fetched rows without pruning unseen ids', () async {
    final host = _SnapshotHost();
    final now = DateTime.now();
    host.conversations['unseen'] = SiriConversation(
        id: 'unseen',
        title: 'Keep',
        summary: 'Private',
        startedAtMs: now.millisecondsSinceEpoch,
        updatedAtMs: now.millisecondsSinceEpoch);
    var pages = 0;
    final siri = SiriIntegration.forTest(host, 'siri-fetch-owner',
        taskPageFetcher: ({required limit, required offset, required completed}) async =>
            const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false)),
        conversationPageFetcher: ({required limit, required offset, required startDate}) async {
          pages++;
          return ApiSuccess<List<ServerConversation>>(List.generate(
              limit,
              (i) => ServerConversation(
                  id: 'row-${offset + i}',
                  createdAt: now,
                  structured: Structured('Title', 'Summary'),
                  status: ConversationStatus.completed)));
        },
        memoryPageFetcher: ({required limit, required offset, cursor}) async => const GetMemoriesResult([], true));

    await siri.refreshOwnerWideIndex();
    expect(pages, 20);
    expect(host.conversations.length, 2001);
    expect(host.conversations.keys, contains('unseen'));
  });
}
