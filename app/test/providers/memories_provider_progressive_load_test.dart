import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/siri_integration.dart';

const _uid = 'progressive-load-user';

Memory _row(String id) => Memory(
      id: id,
      uid: _uid,
      content: 'Memory $id',
      category: MemoryCategory.manual,
      createdAt: DateTime.utc(2026, 8, 17),
      updatedAt: DateTime.utc(2026, 8, 17),
      visibility: MemoryVisibility.private,
    );

Memory _supersededFact() => Memory(
      id: 'superseded',
      uid: _uid,
      content: 'Lives in Brooklyn',
      category: MemoryCategory.system,
      createdAt: DateTime.utc(2026, 8, 23),
      updatedAt: DateTime.utc(2026, 8, 23),
      visibility: MemoryVisibility.private,
      ledgerSchemaVersion: 'knowledge_ledger.v1',
      ledgerKind: KnowledgeLedgerKind.fact,
      ledgerSlot: 'home_city',
      supersededBy: 'newer-fact',
      invalidAt: DateTime.utc(2026, 8, 24),
      intentBacked: true,
    );

Memory _currentFact() => Memory(
      id: 'current-fact',
      uid: _uid,
      content: 'Lives in Brooklyn',
      category: MemoryCategory.system,
      createdAt: DateTime.utc(2026, 8, 23),
      updatedAt: DateTime.utc(2026, 8, 23),
      visibility: MemoryVisibility.private,
      ledgerSchemaVersion: 'knowledge_ledger.v1',
      ledgerKind: KnowledgeLedgerKind.fact,
      ledgerSlot: 'home_city',
      intentBacked: true,
    );

Memory _revertReplacement(Memory source) => Memory(
      id: 'restored-fact',
      uid: source.uid,
      content: source.content,
      category: source.category,
      createdAt: DateTime.utc(2026, 8, 24),
      updatedAt: DateTime.utc(2026, 8, 24),
      visibility: source.visibility,
      ledgerSchemaVersion: 'knowledge_ledger.v1',
      ledgerKind: KnowledgeLedgerKind.fact,
      ledgerSlot: source.ledgerSlot,
      validAt: DateTime.utc(2026, 8, 24),
      intentBacked: true,
      writeReason: 'direct_user_statement',
      evidence: [
        {'source_type': 'explicit_user_revert', 'source_id': source.id},
      ],
    );

class _RecordingIndex extends SiriIndexApi {
  final calls = <String>[];
  final reconcileStarted = Completer<void>();

  @override
  Future<void> reconcileMemories(String uid, List<SiriMemory> rows) async {
    calls.add('reconcile');
    if (!reconcileStarted.isCompleted) reconcileStarted.complete();
  }

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> rows) async => calls.add('upsert');

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async => calls.add('delete');
}

FetchMemoriesCursorRequest _gatedPages(
  List<GetMemoriesResult> pages, {
  Completer<void>? gate,
  void Function(int pageIndex)? onPage,
}) {
  var index = 0;
  return ({int limit = 100, int offset = 0, bool thisDeviceOnly = false, String? cursor, MemoryReadView? view}) {
    final pageIndex = index < pages.length ? index++ : pages.length - 1;
    onPage?.call(pageIndex);
    if (pageIndex == 1 && gate != null) {
      return gate.future.then((_) => pages[pageIndex]);
    }
    return Future.value(pages[pageIndex]);
  };
}

FetchLedgerHistoryRequest _noHistory() =>
    ({int limit = 500, int offset = 0}) async => const GetLedgerHistoryResult([], supported: false);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': _uid});
    await SharedPreferencesUtil.init();
  });
  tearDown(() => SiriIntegration.testInstance = null);

  test('first current page is visible while the next page is still pending', () async {
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.loading, isFalse);
    expect(provider.hasLoaded, isTrue);
    expect(provider.loadFailed, isFalse);
    expect(provider.memories.map((m) => m.id), ['m1']);

    gate.complete();
    await load;
    expect(provider.memories.map((m) => m.id), ['m1', 'm2']);
  });

  test('continuation failure retains first-page rows and marks the load failed', () async {
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);

    gate.complete();
    await load;
    expect(provider.loadFailed, isTrue);
    expect(provider.showLoadError, isFalse);
    expect(provider.memories.map((m) => m.id), ['m1']);
  });

  test('a thrown continuation retains first-page rows and releases the loader', () async {
    final gate = Completer<void>();
    var index = 0;
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: (
          {int limit = 100, int offset = 0, bool thisDeviceOnly = false, String? cursor, MemoryReadView? view}) {
        if (index++ == 0) {
          return Future.value(GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'));
        }
        return gate.future.then((_) => throw StateError('offline'));
      },
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);

    gate.complete();
    await load;
    expect(provider.loading, isFalse);
    expect(provider.loadFailed, isTrue);
    expect(provider.memories.map((m) => m.id), ['m1']);
  });

  test('an initial synchronous fetch throw settles into the failure state', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) =>
          throw StateError('offline'),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.loading, isFalse);
    expect(provider.hasLoaded, isTrue);
    expect(provider.loadFailed, isTrue);
    expect(provider.memories, isEmpty);
  });

  test('disposing while a page fetch is pending never notifies listeners', () async {
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) =>
          gate.future.then((_) => GetMemoriesResult([_row('m1')], true)),
      fetchLedgerHistoryRequest: _noHistory(),
    );

    final load = provider.loadMemories();
    provider.dispose();
    gate.complete();
    await load;
  });

  test('clearUserData while a continuation is pending blocks late publication', () async {
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);

    provider.clearUserData();
    gate.complete();
    await load;
    expect(provider.memories, isEmpty);
  });

  test('a superseding view prevents a late page from the retired traversal publishing', () async {
    final gate = Completer<void>();
    final arrived = Completer<void>();
    var index = 0;
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: (
          {int limit = 100, int offset = 0, bool thisDeviceOnly = false, String? cursor, MemoryReadView? view}) {
        final call = index++;
        if (call == 0) {
          return Future.value(GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'));
        }
        if (call == 1) {
          return gate.future.then((_) => GetMemoriesResult([_row('m2')], true));
        }
        if (!arrived.isCompleted) arrived.complete();
        return Future.value(GetMemoriesResult(call == 2 ? [_row('m3')] : <Memory>[], true));
      },
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);

    provider.setCollectionView(MemoryCollectionView.all);
    await arrived.future;
    gate.complete();
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m3']);
    expect(provider.memories.map((m) => m.id).contains('m2'), isFalse);
    await load;
  });

  test('a ledger projection change while pending blocks late publication', () async {
    final fact = _supersededFact();
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([fact], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      revertMemoryRequest: (id, operationId) async =>
          RevertMemoryResult(persisted: true, authoritativeMemory: _revertReplacement(fact)),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['superseded']);

    expect(await provider.revertSupersededFact(fact), isTrue);
    gate.complete();
    await load;
    expect(provider.memories.map((m) => m.id).contains('m2'), isFalse);
    expect(provider.memories.map((m) => m.id), containsAllInOrder(['superseded', 'restored-fact']));
  });

  test('a deleted row stays out of provisional and final output', () async {
    final deleted = _row('m1');
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([deleted], true, nextCursor: 'c2'),
        GetMemoriesResult([deleted, _row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      deleteMemoryRequest: (id) async => true,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);

    await provider.deleteMemory(deleted);
    expect(provider.memories, isEmpty);

    gate.complete();
    await load;
    expect(provider.memories.map((m) => m.id), ['m2']);
  });

  test('a delete-all while a continuation is pending never republishes pre-deletion rows', () async {
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      deleteAllMemoriesRequest: () async => true,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);

    expect(await provider.deleteAllMemories(), isTrue);
    gate.complete();
    await load;
    await pumpEventQueue();

    expect(provider.memories, isEmpty, reason: 'a successful delete-all must fence the in-flight traversal');
    expect(provider.loadFailed, isFalse);
    expect(provider.loading, isFalse);
  });

  test('Siri reconciles only after the traversal completes', () async {
    final host = _RecordingIndex();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, _uid);
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);
    expect(host.calls, isNot(contains('reconcile')));

    gate.complete();
    await load;
    await host.reconcileStarted.future.timeout(const Duration(seconds: 2));
    expect(host.calls, contains('reconcile'));
  });

  test('Siri does not reconcile on a partial failure', () async {
    final host = _RecordingIndex();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, _uid);
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    gate.complete();
    await load;
    await SiriIntegration.current.drainIndexForTest();

    expect(provider.loadFailed, isTrue);
    expect(provider.memories.map((m) => m.id), ['m1']);
    expect(host.calls, contains('upsert'), reason: 'the visible first page is still indexed provisionally');
    expect(host.calls, isNot(contains('reconcile')));
  });

  test('a partial failure upserts the retained rows so Siri matches what is shown', () async {
    final host = _RecordingIndex();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, _uid);
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    gate.complete();
    await load;
    await pumpEventQueue();

    expect(provider.loadFailed, isTrue);
    expect(provider.memories.map((m) => m.id), ['m1']);
    expect(host.calls, contains('upsert'), reason: 'retained partial rows must reach Siri/search indexing');
    expect(host.calls, isNot(contains('reconcile')), reason: 'a partial traversal is never authoritative');
  });

  test('provisional pages upsert to Siri while the traversal is still pending', () async {
    final host = _RecordingIndex();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, _uid);
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    await SiriIntegration.current.drainIndexForTest();
    expect(provider.memories.map((m) => m.id), ['m1']);
    expect(host.calls, contains('upsert'));
    expect(host.calls, isNot(contains('reconcile')));

    gate.complete();
    await load;
    await SiriIntegration.current.drainIndexForTest();
    expect(host.calls.last, 'reconcile');
  });

  test('a confirmed create while a continuation is pending survives the late page', () async {
    final gate = Completer<void>();
    final serverRow = _row('server-created');
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m1'), _row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      createMemoryRequest: (content, visibility, category) async => serverRow,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);
    expect(await provider.createMemory('remembered'), isTrue);
    expect(provider.memories.map((m) => m.id), contains('server-created'));

    gate.complete();
    await load;
    expect(provider.memories.map((m) => m.id), contains('server-created'));
  });

  test('a confirmed delete while a continuation is pending keeps the row out', () async {
    final gate = Completer<void>();
    final deleted = _row('m1');
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([deleted], true, nextCursor: 'c2'),
        GetMemoriesResult([deleted, _row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      deleteMemoryRequest: (id) async => true,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['m1']);
    await provider.deleteMemory(deleted);
    await provider.confirmPendingDeletion();
    expect(provider.memories, isEmpty);

    gate.complete();
    await load;
    expect(provider.memories.map((m) => m.id), isNot(contains('m1')));
  });

  test('a confirmed delete removes only its own id from the owner cache', () async {
    SharedPreferencesUtil().cachedMemories = [_row('cached-deleted'), _row('unseen')];
    final gate = Completer<void>();
    final deleted = _row('cached-deleted');
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([deleted], true, nextCursor: 'c2'),
        GetMemoriesResult([deleted, _row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      deleteMemoryRequest: (id) async => true,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    await provider.deleteMemory(deleted);
    await provider.confirmPendingDeletion();
    expect(SharedPreferencesUtil().cachedMemories.map((m) => m.id), ['unseen']);

    gate.complete();
    await load;
    expect(SharedPreferencesUtil().cachedMemories.map((m) => m.id), ['unseen']);
  });

  test('a confirmed create upserts into the owner cache while a page is pending', () async {
    SharedPreferencesUtil().cachedMemories = [_row('unseen')];
    final gate = Completer<void>();
    final serverRow = _row('server-created');
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'),
        GetMemoriesResult([_row('m1'), _row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      createMemoryRequest: (content, visibility, category) async => serverRow,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(await provider.createMemory('remembered'), isTrue);
    gate.complete();
    await load;
    expect(SharedPreferencesUtil().cachedMemories.map((m) => m.id), containsAll(['unseen', 'server-created']));
  });

  test('a confirmed create evicts the optimistic uuid from the owner cache', () async {
    String? optimisticId;
    final serverRow = _row('server-created');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([_row('m1')], true),
      fetchLedgerHistoryRequest: _noHistory(),
      createMemoryRequest: (content, visibility, category) async {
        optimisticId = SharedPreferencesUtil().pendingMemories.last.id;
        SharedPreferencesUtil().cachedMemories = [...SharedPreferencesUtil().cachedMemories, _row(optimisticId!)];
        return serverRow;
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    SharedPreferencesUtil().cachedMemories = [_row('unseen')];
    expect(await provider.createMemory('remembered'), isTrue);
    final cachedIds = SharedPreferencesUtil().cachedMemories.map((m) => m.id).toList();
    expect(cachedIds, unorderedEquals(['unseen', 'server-created']));
    expect(cachedIds, isNot(contains(optimisticId)));
  });
  test('a thrown continuation upserts the retained rows so Siri matches what is shown', () async {
    final host = _RecordingIndex();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, _uid);
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: (
          {int limit = 100, int offset = 0, bool thisDeviceOnly = false, String? cursor, MemoryReadView? view}) {
        if (cursor == null) return Future.value(GetMemoriesResult([_row('m1')], true, nextCursor: 'c2'));
        return gate.future.then((_) => throw StateError('offline'));
      },
      fetchLedgerHistoryRequest: _noHistory(),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    gate.complete();
    await load;
    await pumpEventQueue();

    expect(provider.loadFailed, isTrue);
    expect(provider.memories.map((m) => m.id), ['m1']);
    expect(host.calls, contains('upsert'), reason: 'rows retained after a thrown continuation must still be indexed');
    expect(host.calls, isNot(contains('reconcile')));
  });

  test('an authoritative ledger edit fences a still-running traversal', () async {
    final fact = _currentFact();
    final gate = Completer<void>();
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: _gatedPages([
        GetMemoriesResult([fact], true, nextCursor: 'c2'),
        GetMemoriesResult([fact, _row('m2')], true),
      ], gate: gate),
      fetchLedgerHistoryRequest: _noHistory(),
      editMemoryRequest: (id, value) async =>
          EditMemoryResult(persisted: true, authoritativeMemory: _revertReplacement(fact)),
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), ['current-fact']);

    expect(await provider.editMemory(fact, fact.content), isTrue);
    gate.complete();
    await load;
    await pumpEventQueue();

    expect(provider.memories.map((m) => m.id), contains('restored-fact'));
    expect(provider.memories.map((m) => m.id), isNot(contains('superseded')),
        reason: 'a replaced fact must not resurrect from the stale traversal snapshot');
  });

  test('a delete-all during a pending-memory sync releases the sync latch', () async {
    final gate = Completer<void>();
    final drafts = <Memory>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(List<Memory>.of(drafts), true),
      fetchLedgerHistoryRequest: _noHistory(),
      deleteAllMemoriesRequest: () async => true,
      createMemoryRequest: (content, visibility, category) => gate.future.then((_) => null),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    SharedPreferencesUtil().pendingMemories = [
      _row('draft-1'),
    ];
    final sync = provider.syncPendingMemories();
    await pumpEventQueue();
    expect(await provider.deleteAllMemories(), isTrue);

    gate.complete();
    await sync;
    await pumpEventQueue();

    // The latch must be free again: a later sync attempt may proceed.
    expect(provider.isSyncing, isFalse, reason: 'delete-all must not strand the pending-sync latch');
  });
}
