import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

Memory memory(String id, {String owner = 'owner-a'}) => Memory(
      id: id,
      uid: owner,
      content: 'Memory $id',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      visibility: MemoryVisibility.private,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-a'});
    await SharedPreferencesUtil.init();
  });

  for (final nextOwner in ['owner-a', 'owner-b']) {
    test('failed delete cannot restore a retired session into $nextOwner', () async {
      final oldMemory = memory('old');
      final response = Completer<bool>();
      final provider = MemoriesProvider(deleteMemoryRequest: (_) => response.future);
      addTearDown(provider.dispose);
      await provider.deleteMemory(oldMemory);
      final deletion = provider.confirmPendingDeletion(id: oldMemory.id);
      provider.clearUserData();
      SharedPreferencesUtil().uid = nextOwner;

      response.complete(false);
      await deletion;

      expect(provider.memories, isEmpty, reason: 'a retired request must never restore or index its private row');
      expect(provider.lastDeletedMemory, isNull);
    });
  }

  test('all staged and in-flight deletes stay hidden during refresh', () async {
    final first = memory('first');
    final second = memory('second');
    final response = Completer<bool>();
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([first, second], true),
      deleteMemoryRequest: (_) => response.future,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await provider.deleteMemory(first);
    await provider.deleteMemory(second);
    await provider.loadMemories();

    expect(provider.memories, isEmpty, reason: 'replacing the Undo toast must not expose the earlier request');

    response.complete(true);
    await provider.confirmPendingDeletion(id: second.id);
    await provider.loadMemories();
    expect(provider.memories, isEmpty, reason: 'a stale server projection must not revive confirmed deletes');
  });

  test('repeated commits join one request and Undo cannot reverse a submitted delete', () async {
    final row = memory('single-flight');
    final response = Completer<bool>();
    var requests = 0;
    final provider = MemoriesProvider(deleteMemoryRequest: (_) {
      requests++;
      return response.future;
    });
    addTearDown(provider.dispose);
    await provider.deleteMemory(row);
    final first = provider.confirmPendingDeletion(id: row.id);
    final second = provider.confirmPendingDeletion(id: row.id);
    final restored = await provider.restoreLastDeletedMemory(id: row.id);

    expect(requests, 1);
    expect(restored, isFalse, reason: 'Undo is no longer offered once the irreversible request has started');
    expect(provider.lastDeletedMemory, isNull);
    response.complete(true);
    await Future.wait([first, second]);
    expect(provider.memories, isEmpty);
  });

  for (final action in ['create', 'sync']) {
    test('deletion during $action removes the returned server ID, not just the draft', () async {
      final creation = Completer<Memory?>();
      final deleted = <String>[];
      final provider = MemoriesProvider(
        createMemoryRequest: (_, __, ___) => creation.future,
        deleteMemoryRequest: (id) async {
          deleted.add(id);
          return true;
        },
      );
      addTearDown(provider.dispose);
      late Future<dynamic> saving;
      late Memory draft;
      if (action == 'create') {
        saving = provider.createMemory('Pending memory');
        draft = provider.memories.single;
      } else {
        draft = memory('offline');
        SharedPreferencesUtil().addPendingMemory(draft);
        saving = provider.syncPendingMemories();
      }
      SharedPreferencesUtil().cachedMemories = [draft];
      await provider.deleteMemory(draft);
      final deleting = provider.confirmPendingDeletion(id: draft.id);
      creation.complete(memory('server-id'));
      await saving;
      await deleting;

      expect(deleted, ['server-id']);
      expect(provider.memories, isEmpty);
      expect(SharedPreferencesUtil().pendingMemories, isEmpty);
      expect(SharedPreferencesUtil().cachedMemories, isEmpty);
    });
  }

  test('Undo after a draft upload restores its canonical ID without duplicate rows', () async {
    final creation = Completer<Memory?>();
    final provider = MemoriesProvider(createMemoryRequest: (_, __, ___) => creation.future);
    addTearDown(provider.dispose);
    final saving = provider.createMemory('Pending memory');
    final draft = provider.memories.single;
    await provider.deleteMemory(draft);
    creation.complete(memory('canonical'));
    await saving;
    expect(await provider.restoreLastDeletedMemory(id: draft.id), isTrue);
    expect(provider.memories.map((row) => row.id), ['canonical']);
  });

  test('one refusal restores only its own row and reports the failure once', () async {
    var failures = 0;
    final response = Completer<bool>();
    final row = memory('retry');
    final provider = MemoriesProvider(deleteMemoryRequest: (_) => response.future);
    addTearDown(provider.dispose);
    await provider.deleteMemory(row, onFailure: () => failures++);
    final first = provider.confirmPendingDeletion(id: row.id);
    final joined = provider.confirmPendingDeletion(id: row.id);
    response.complete(false);
    await Future.wait([first, joined]);
    expect(failures, 1);
    expect(provider.memories.map((row) => row.id), ['retry']);
  });

  test('wrong-owner and signed-out rows never authorize deletion', () async {
    var requests = 0;
    final provider = MemoriesProvider(deleteMemoryRequest: (_) async {
      requests++;
      return true;
    });
    addTearDown(provider.dispose);
    await provider.deleteMemory(memory('foreign', owner: 'owner-b'));
    await provider.confirmPendingDeletion(id: 'foreign');
    SharedPreferencesUtil().uid = '';
    await provider.deleteMemory(memory('signed-out'));
    await provider.confirmPendingDeletion(id: 'signed-out');
    expect(requests, 0);
  });

  test('failed delete after provider disposal does not publish', () async {
    final response = Completer<bool>();
    final provider = MemoriesProvider(deleteMemoryRequest: (_) => response.future);
    await provider.deleteMemory(memory('disposed'));
    final deletion = provider.confirmPendingDeletion();
    provider.dispose();
    response.complete(false);
    await expectLater(deletion, completes);
    expect(provider.memories, isEmpty);
  });

  test('confirmed delete after disposal still retires the same owner cache', () async {
    final response = Completer<bool>();
    final row = memory('disposed-success');
    SharedPreferencesUtil().cachedMemories = [row];
    final provider = MemoriesProvider(deleteMemoryRequest: (_) => response.future);
    await provider.deleteMemory(row);
    final deletion = provider.confirmPendingDeletion(id: row.id);
    provider.dispose();
    response.complete(true);
    await deletion;
    expect(SharedPreferencesUtil().cachedMemories, isEmpty);
    expect(SharedPreferencesUtil().confirmedMemoryDeletionIds, contains(row.id));
  });
}
