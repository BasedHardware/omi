import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/siri_integration.dart';

class _SlowIndex extends SiriIndexApi {
  _SlowIndex(this.block);
  final String block;
  final started = Completer<void>();
  final release = Completer<void>();

  Future<void> _call(String operation) async {
    if (operation != block) return;
    if (!started.isCompleted) started.complete();
    await release.future;
  }

  @override
  Future<void> reconcileMemories(String uid, List<SiriMemory> rows) => _call('reconcile');

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> rows) => _call('upsert');

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) => _call('delete');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const uid = 'siri-nonblocking-owner';

  Memory row(String id) => Memory(
        id: id,
        uid: uid,
        content: 'Memory $id',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private,
      );

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': uid});
    await SharedPreferencesUtil.init();
  });
  tearDown(() => SiriIntegration.testInstance = null);

  test('Memories finishes loading while native reconcile never returns', () async {
    final host = _SlowIndex('reconcile');
    SiriIntegration.testInstance = SiriIntegration.forTest(host, uid);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row('visible')], true),
    );
    addTearDown(provider.dispose);
    addTearDown(() => host.release.complete());

    await provider.loadMemories().timeout(const Duration(seconds: 1));
    await host.started.future.timeout(const Duration(seconds: 1));
    expect(provider.loading, isFalse);
    expect(provider.memories.map((memory) => memory.id), ['visible']);
  });

  test('confirmed create returns while native upsert never returns', () async {
    final host = _SlowIndex('upsert');
    SiriIntegration.testInstance = SiriIntegration.forTest(host, uid);
    final provider = MemoriesProvider(createMemoryRequest: (_, __, ___) async => row('created'));
    addTearDown(provider.dispose);
    addTearDown(() => host.release.complete());

    expect(await provider.createMemory('New fact').timeout(const Duration(seconds: 1)), isTrue);
    await host.started.future.timeout(const Duration(seconds: 1));
    expect(provider.memories.map((memory) => memory.id), ['created']);
  });

  test('delete and undo return while native deletion never returns', () async {
    final host = _SlowIndex('delete');
    SiriIntegration.testInstance = SiriIntegration.forTest(host, uid);
    final memory = row('undo');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([memory], true),
    );
    addTearDown(provider.dispose);
    addTearDown(() => host.release.complete());
    await provider.loadMemories();

    await provider.deleteMemory(memory).timeout(const Duration(seconds: 1));
    await host.started.future.timeout(const Duration(seconds: 1));
    expect(provider.memories, isEmpty);
    expect(await provider.restoreLastDeletedMemory().timeout(const Duration(seconds: 1)), isTrue);
    expect(provider.memories.map((row) => row.id), ['undo']);
  });
}
