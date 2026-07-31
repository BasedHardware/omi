import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _mem(String id, {String content = 'text'}) {
  return Memory(
    id: id,
    uid: 'user-1',
    content: content,
    category: MemoryCategory.manual,
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
    visibility: MemoryVisibility.public,
  );
}

ActionItemWithMetadata _item(String id, {String description = 'task'}) {
  return ActionItemWithMetadata(
    id: id,
    description: description,
    completed: false,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final List<MemoriesProvider> memoryProviders = [];
  final List<ActionItemsProvider> actionItemProviders = [];

  setUp(() {
    // SharedPreferences-backed getters (pendingMemories, uid, device-scope
    // prefs) are used in loadMemories(), so mock the backing store.
    SharedPreferences.setMockInitialValues({});
  });

  tearDown(() {
    // Cancel any pending deletion timers so they don't fire during
    // unrelated tests and attempt real HTTP calls / crash logs.
    for (final p in memoryProviders) {
      p.clearUserData();
      p.dispose();
    }
    for (final p in actionItemProviders) {
      p.clearUserData();
      p.dispose();
    }
    memoryProviders.clear();
    actionItemProviders.clear();
  });

  group('MemoriesProvider deletion eventual consistency', () {
    FetchMemoriesRequest emptyFetcher() {
      return ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true);
    }

    test('deleteMemory removes item optimistically and sets pending state', () {
      final provider = MemoriesProvider(
        fetchMemoriesRequest: emptyFetcher(),
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      provider.deleteMemory(_mem('mem-1'));

      expect(provider.memories, isEmpty, reason: 'Optimistic removal should hide the memory immediately');
      expect(provider.lastDeletedMemory, isNotNull);
      expect(provider.lastDeletedMemory!.id, 'mem-1');
    });

    test('restoreLastDeletedMemory brings the memory back and clears pending state', () async {
      final provider = MemoriesProvider(
        fetchMemoriesRequest: emptyFetcher(),
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      provider.deleteMemory(_mem('mem-2'));
      expect(provider.memories, isEmpty);

      final restored = await provider.restoreLastDeletedMemory();
      expect(restored, isTrue);
      expect(provider.memories.length, 1);
      expect(provider.memories.first.id, 'mem-2');
      expect(provider.lastDeletedMemory, isNull);
    });

    test('consecutive deletions replace pending state correctly', () {
      final provider = MemoriesProvider(
        fetchMemoriesRequest: emptyFetcher(),
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      provider.deleteMemory(_mem('mem-3'));
      expect(provider.lastDeletedMemory!.id, 'mem-3');

      provider.deleteMemory(_mem('mem-4'));
      expect(provider.lastDeletedMemory!.id, 'mem-4');
    });

    test('loadMemories filters out a pending-deletion memory returned by the server', () async {
      // Drives the production load path through loadMemories() with a
      // controllable fetcher that still returns the deleted ID, and asserts
      // the item stays hidden.
      final deleted = _mem('mem-5', content: 'should not reappear');

      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
          return GetMemoriesResult([deleted], true);
        },
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      provider.deleteMemory(deleted);
      expect(provider.memories, isEmpty);

      await provider.loadMemories();

      expect(provider.memories, isEmpty,
          reason: 'loadMemories must filter out the pending-deletion memory even '
              'when the server response still contains it');
    });

    test('undo window keeps pending state until explicit confirmation or restore', () async {
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
            GetMemoriesResult([_mem('mem-6', content: 'do not reappear')], true),
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      provider.deleteMemory(_mem('mem-6'));

      await provider.loadMemories();

      expect(provider.memories, isEmpty);
      expect(provider.lastDeletedMemory, isNotNull);
    });
  });

  group('ActionItemsProvider deletion eventual consistency', () {
    ActionItemsProvider newProvider({
      required ActionItemsFetcher fetcher,
      DeleteActionItemRequest? deleter,
    }) {
      final p = ActionItemsProvider(
        getActionItems: fetcher,
        deleteActionItemRequest: deleter ?? (_) async => true,
      );
      actionItemProviders.add(p);
      return p;
    }

    ActionItemsFetcher emptyFetcher() {
      return (
              {int limit = 100,
              int offset = 0,
              bool? completed,
              String? conversationId,
              DateTime? startDate,
              DateTime? endDate}) async =>
          const ActionItemsResponse(actionItems: []);
    }

    test('deleteActionItem removes item optimistically and tracks pending deletion', () async {
      final provider = newProvider(fetcher: emptyFetcher());

      final item = _item('task-1');
      provider.actionItems.insert(0, item);

      final success = await provider.deleteActionItem(item);
      expect(success, isTrue);
      expect(provider.actionItems.where((i) => i.id == 'task-1'), isEmpty);
    });

    test('fetchActionItems filters out a pending-deletion item returned by the server', () async {
      // Drives the production fetch path: the fetcher still returns the
      // deleted item, but the tombstone guard must prevent reinsertion.
      final deleted = _item('task-2', description: 'should not reappear');

      final provider = newProvider(
        fetcher: (
                {int limit = 100,
                int offset = 0,
                bool? completed,
                String? conversationId,
                DateTime? startDate,
                DateTime? endDate}) async =>
            ActionItemsResponse(actionItems: [deleted]),
      );

      // Let the constructor's _preload() settle so it doesn't race with
      // the test's fetch calls.
      await Future.delayed(Duration.zero);

      await provider.deleteActionItem(deleted);
      await provider.fetchActionItems();

      expect(provider.actionItems.where((i) => i.id == 'task-2'), isEmpty,
          reason: 'fetchActionItems must filter out the pending-deletion item even '
              'when the server response still contains it');
    });

    test('tombstone is lazily cleared once the server confirms deletion', () async {
      final deleted = _item('task-3');

      var fetchCall = 0;
      final provider = newProvider(
        fetcher: (
            {int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate}) async {
          fetchCall++;
          // First fetch returns the item (it's still live on the server);
          // second fetch (after server processed the delete) omits it.
          if (fetchCall == 1) {
            return ActionItemsResponse(actionItems: [deleted]);
          }
          return const ActionItemsResponse(actionItems: []);
        },
      );

      await provider.deleteActionItem(deleted);

      // First refresh — item still on server; tombstone prevents reinsertion.
      await provider.fetchActionItems();
      expect(provider.actionItems.where((i) => i.id == 'task-3'), isEmpty);

      // Second refresh — server confirms deletion; tombstone is retired.
      await provider.fetchActionItems();
      expect(provider.actionItems, isEmpty);
    });

    test('loadMoreActionItems filters pending-deletion items from paginated response', () async {
      final deleted = _item('task-4');

      final provider = newProvider(
        fetcher: (
            {int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate}) async {
          if (offset == 0) {
            return ActionItemsResponse(actionItems: [deleted], hasMore: true);
          }
          // Page 2 still returns the deleted item (stale read).
          return ActionItemsResponse(actionItems: [deleted]);
        },
      );

      // Initial load
      await provider.fetchActionItems();

      // Delete
      await provider.deleteActionItem(deleted);

      // loadMore — the stale page must not reinsert the deleted item.
      await provider.loadMoreActionItems();

      expect(provider.actionItems.where((i) => i.id == 'task-4'), isEmpty,
          reason: 'loadMoreActionItems must filter out pending-deletion items');
    });
  });
}
