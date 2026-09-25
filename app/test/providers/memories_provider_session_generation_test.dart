import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _memory({required String id, required String uid}) => Memory(
      id: id,
      uid: uid,
      content: 'content-$id',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 9, 18),
      updatedAt: DateTime(2026, 9, 18),
      visibility: MemoryVisibility.private,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memories-session-user'});
    await SharedPreferencesUtil.init();
  });

  test('clearUserData mid-load refuses to publish the hung list', () async {
    final hang = Completer<GetMemoriesResult>();
    final stale = _memory(id: 'stale', uid: 'memories-session-user');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) => hang.future,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories();
    provider.clearUserData();
    hang.complete(GetMemoriesResult([stale], true));
    await load;

    expect(provider.memories, isEmpty, reason: 'must not publish a retired session fetch into the successor');
    expect(provider.hasLoaded, isFalse);
  });

  test('current-generation load after clear still publishes', () async {
    final live = _memory(id: 'live', uid: 'memories-session-user');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([live], true);
      },
    );
    addTearDown(provider.dispose);

    provider.clearUserData();
    await provider.loadMemories();

    expect(provider.memories.map((memory) => memory.id), [live.id]);
    expect(provider.hasLoaded, isTrue);
  });

  test('a load after clear does not join the retired in-flight fetch', () async {
    final first = Completer<GetMemoriesResult>();
    final second = Completer<GetMemoriesResult>();
    var fetches = 0;
    final stale = _memory(id: 'stale', uid: 'memories-session-user');
    final live = _memory(id: 'live', uid: 'memories-session-user');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) {
        fetches++;
        return fetches == 1 ? first.future : second.future;
      },
    );
    addTearDown(provider.dispose);

    final retired = provider.loadMemories();
    provider.clearUserData();
    final current = provider.loadMemories();
    first.complete(GetMemoriesResult([stale], true));
    await retired;
    expect(provider.memories, isEmpty);

    second.complete(GetMemoriesResult([live], true));
    await current;
    expect(provider.memories.map((memory) => memory.id), [live.id]);
    expect(fetches, 2);
  });
}
