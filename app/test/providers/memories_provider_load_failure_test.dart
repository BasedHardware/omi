import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

GetMemoriesResult _failedFetch() =>
    const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError);

Memory _memory() => Memory(
      id: 'mem-1',
      uid: 'memories-load-failure-user',
      content: 'A real memory',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 8, 17),
      updatedAt: DateTime(2026, 8, 17),
      visibility: MemoryVisibility.private,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memories-load-failure-user'});
    await SharedPreferencesUtil.init();
  });

  test('a failed fetch is a load error, not an empty memories list', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async => _failedFetch(),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();

    expect(provider.loadFailed, isTrue);
    expect(provider.showLoadError, isTrue);
    expect(provider.memories, isEmpty);
    expect(provider.loading, isFalse);
  });

  test('a failed refresh keeps previously loaded memories instead of wiping them', () async {
    var fail = false;
    final memory = _memory();
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        if (fail) return _failedFetch();
        return GetMemoriesResult([memory], true);
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.memories.map((item) => item.id), [memory.id]);

    fail = true;
    await provider.loadMemories();

    expect(provider.loadFailed, isTrue);
    expect(provider.showLoadError, isFalse, reason: 'stale memories must still be shown');
    expect(provider.memories.map((item) => item.id), [memory.id]);
  });

  test('a later successful fetch clears the load-error state', () async {
    var fail = true;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        if (fail) return _failedFetch();
        return const GetMemoriesResult([], true);
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.showLoadError, isTrue);

    fail = false;
    await provider.loadMemories();

    expect(provider.loadFailed, isFalse);
    expect(provider.showLoadError, isFalse);
    expect(provider.memories, isEmpty);
  });
}
