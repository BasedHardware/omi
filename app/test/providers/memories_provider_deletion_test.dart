import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memory-delete-test-user'});
    await SharedPreferencesUtil.init();
  });

  test('pending delete stays hidden across reload and restores when the server delete fails', () async {
    final memory = Memory(
      id: 'server-memory',
      uid: 'memory-delete-test-user',
      content: 'Memory that should not resurrect during undo',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      visibility: MemoryVisibility.private,
    );
    final deletedIDs = <String>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([memory], true);
      },
      deleteMemoryRequest: (id) async {
        deletedIDs.add(id);
        return false;
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    provider.deleteMemory(memory);
    await provider.loadMemories();
    expect(provider.memories, isEmpty, reason: 'a reload must not reinsert a memory pending undo');

    await provider.confirmPendingDeletion();

    expect(deletedIDs, [memory.id]);
    expect(provider.memories.map((memory) => memory.id), [memory.id]);
  });

  Memory memoryWithId(String id) => Memory(
        id: id,
        uid: 'memory-delete-test-user',
        content: 'Memory $id',
        category: MemoryCategory.manual,
        createdAt: DateTime(2026, 1, 1),
        updatedAt: DateTime(2026, 1, 1),
        visibility: MemoryVisibility.private,
      );

  test('deleting a second memory inside the undo window still deletes the first', () async {
    final first = memoryWithId('first');
    final second = memoryWithId('second');
    final serverMemories = [first, second];
    final deletedIDs = <String>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult(List.of(serverMemories), true);
      },
      deleteMemoryRequest: (id) async {
        deletedIDs.add(id);
        serverMemories.removeWhere((memory) => memory.id == id);
        return true;
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    provider.deleteMemory(first);
    provider.deleteMemory(second);
    await provider.confirmPendingDeletion();

    expect(deletedIDs, unorderedEquals([first.id, second.id]));

    await provider.loadMemories();
    expect(provider.memories, isEmpty);
  });

  test('a failed delete of the first memory restores it while the second is pending', () async {
    final first = memoryWithId('first');
    final second = memoryWithId('second');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([first, second], true);
      },
      deleteMemoryRequest: (id) async => id != first.id,
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    provider.deleteMemory(first);
    provider.deleteMemory(second);
    await pumpEventQueue();

    expect(provider.memories.map((memory) => memory.id), [first.id]);
    expect(provider.lastDeletedMemory?.id, second.id);
  });
}
