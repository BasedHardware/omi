import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memory-delete-test-user'});
    FlutterSecureStorage.setMockInitialValues({});
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
}
