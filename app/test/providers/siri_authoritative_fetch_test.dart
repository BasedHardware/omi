import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
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
    await Future<void>.delayed(Duration.zero);
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
    await Future<void>.delayed(Duration.zero);
    expect(host.conversations.containsKey('remote-deleted-new'), isFalse);
    expect(host.conversations.containsKey('outside-page'), isTrue);
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
    await Future<void>.delayed(Duration.zero);
    expect(host.memories, isEmpty);
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
    host.tasks['remote-deleted'] = SiriTask(id: 'remote-deleted', title: 'private', completed: false, createdAtMs: now);
    host.tasks['completed-outside-filter'] =
        SiriTask(id: 'completed-outside-filter', title: 'done', completed: true, createdAtMs: now, completedAtMs: now);
    provider.toggleCompletedActionItems();
    expect(await provider.fetchActionItems(), isTrue);
    await Future<void>.delayed(Duration.zero);
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
    await Future<void>.delayed(Duration.zero);
    expect(host.tasks.containsKey('outside-page'), isTrue);
  });
}
