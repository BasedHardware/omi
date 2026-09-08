import 'dart:async';

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

    test('consecutive deletions finalize the second memory before a refresh', () async {
      // When two memories are deleted within the undo window, the second
      // deleteMemory() cancels the first timer and replaces _pendingDeletionId.
      // The second memory is finalized; the first is a known limitation of
      // the single-pending-ID design (tracked separately). This test verifies
      // the current pending memory is finalized and suppressed through refresh.
      final deletedIds = <String>[];
      final mem4 = _mem('mem-4a', content: 'second');

      var deletionFinalized = false;
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
          // Before finalization, the server still has the memory (stale read).
          // After finalization (server delete completed), it's gone.
          if (!deletionFinalized) {
            return GetMemoriesResult([mem4], true);
          }
          return const GetMemoriesResult([], true);
        },
        deleteMemoryRequest: (id) async {
          deletedIds.add(id);
          return true;
        },
      );
      memoryProviders.add(provider);

      provider.deleteMemory(_mem('mem-3a', content: 'first'));
      provider.deleteMemory(mem4);

      // Confirm pending deletion — this finalizes the second memory.
      await provider.confirmPendingDeletion();
      deletionFinalized = true;

      expect(deletedIds, contains('mem-4a'),
          reason: 'confirmPendingDeletion must finalize the current pending deletion');

      // The finalized second memory must not reappear after refresh.
      await provider.loadMemories();
      expect(provider.memories.where((m) => m.id == 'mem-4a'), isEmpty,
          reason: 'The finalized deletion must remain suppressed after refresh');
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

    test('deletion during in-flight loadMemories is suppressed by apply-time re-check', () async {
      // If the user deletes a memory after loadMemories() has already started
      // (tombstoneId was null at snapshot), the stale response still contains
      // the deleted ID. The apply-time re-check of _pendingDeletionId must
      // filter it out.
      final victim = _mem('mem-7', content: 'deleted mid-load');

      final fetchCompleter = Completer<GetMemoriesResult>();
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
          return fetchCompleter.future;
        },
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      // Start the load — it hangs on the uncompleted fetcher.
      final loadFuture = provider.loadMemories();

      // Delete the memory while the load is in flight. This sets
      // _pendingDeletionId after loadMemories() already snapshotted null.
      provider.deleteMemory(victim);
      expect(provider.memories, isEmpty, reason: 'Optimistic removal should hide the memory immediately');

      // Complete the fetch with a stale response that still contains the victim.
      fetchCompleter.complete(GetMemoriesResult([victim], true));
      await loadFuture;

      expect(provider.memories.where((m) => m.id == 'mem-7'), isEmpty,
          reason: 'loadMemories must re-check _pendingDeletionId at apply time '
              'and suppress items deleted after the snapshot was taken');
    });

    test('loadMemories stops paging when the server signals truncation', () async {
      var calls = 0;
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
          calls++;
          // First page is full but truncated; provider must not continue.
          return GetMemoriesResult(
            [
              Memory(
                  id: 'm-$calls',
                  uid: 'u1',
                  content: 'c',
                  category: MemoryCategory.manual,
                  createdAt: DateTime.now(),
                  updatedAt: DateTime.now(),
                  visibility: MemoryVisibility.public)
            ],
            true,
            truncated: true,
          );
        },
        deleteMemoryRequest: (_) async => true,
      );
      memoryProviders.add(provider);

      await provider.loadMemories(limit: 1);

      expect(calls, 1, reason: 'A truncated page must stop further fetch attempts');
      expect(provider.memories.length, 1);
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

      var staleMode = false;
      final provider = newProvider(
        fetcher: (
            {int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate}) async {
          // In stale mode the server still returns the deleted item; once
          // cleared, the server response omits it.
          if (staleMode) {
            return ActionItemsResponse(actionItems: [deleted]);
          }
          return const ActionItemsResponse(actionItems: []);
        },
      );

      // Let the constructor's _preload() settle so it doesn't consume our
      // fetchCall sequence.
      await Future.delayed(Duration.zero);

      await provider.deleteActionItem(deleted);

      // First refresh — stale server response still contains the item;
      // tombstone prevents reinsertion.
      staleMode = true;
      await provider.fetchActionItems();
      expect(provider.actionItems.where((i) => i.id == 'task-3'), isEmpty);

      // Second refresh — server confirms deletion; tombstone is retired.
      staleMode = false;
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
