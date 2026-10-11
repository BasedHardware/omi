import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_management_sheet.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/siri_integration.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

final _memory = Memory(
  id: 'server-memory',
  uid: 'memory-delete-all-test-user',
  content: 'Still stored on the server',
  category: MemoryCategory.manual,
  createdAt: DateTime(2026, 1, 1),
  updatedAt: DateTime(2026, 1, 1),
  visibility: MemoryVisibility.private,
);

Memory _row(String id) => Memory(
      id: id,
      uid: 'memory-delete-all-test-user',
      content: 'Memory $id',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      visibility: MemoryVisibility.private,
    );

class _RecordingIndex extends SiriIndexApi {
  final calls = <String>[];
  final memories = <String, SiriMemory>{};

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> rows) async {
    calls.add('upsert');
    for (final row in rows) {
      memories[row.id] = row;
    }
  }

  @override
  Future<void> reconcileMemories(String uid, List<SiriMemory> rows) async {
    calls.add('reconcile');
    final keep = rows.map((row) => row.id).toSet();
    memories.removeWhere((id, _) => !keep.contains(id));
    for (final row in rows) {
      memories[row.id] = row;
    }
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {
    calls.add('delete');
    if (type == 'memory') {
      for (final id in ids) {
        memories.remove(id);
      }
    }
  }
}

MemoriesProvider _provider() => MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([_memory], true);
      },
    );

void main() {
  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memory-delete-all-test-user'});
    await SharedPreferencesUtil.init();
  });

  test('a clear-all the server did not accept keeps the memories', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final provider = _provider();
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final cleared = await provider.deleteAllMemories();

    expect(cleared, isFalse);
    expect(provider.memories.map((m) => m.id), [_memory.id]);
  });

  testWidgets('the sheet does not say memory was cleared when the server rejected it', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final provider = _provider();
    addTearDown(provider.dispose);
    await tester.runAsync(provider.loadMemories);

    await tester.pumpWidget(
      ChangeNotifierProvider<MemoriesProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showModalBottomSheet(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => MemoryManagementSheet(provider: provider),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete All Memories'));
    await tester.pumpAndSettle();

    await tester.runAsync(() async {
      await tester.tap(find.text('Clear Memory'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pumpAndSettle();

    expect(provider.memories.map((m) => m.id), [_memory.id]);
    expect(find.text("Omi's memory about you has been cleared"), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);

    await tester.pumpAndSettle(const Duration(seconds: 3));
  });

  test('a confirmed delete-all fences a pending continuation page', () async {
    final host = _RecordingIndex();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'memory-delete-all-test-user');
    addTearDown(() => SiriIntegration.testInstance = null);
    final gate = Completer<void>();
    var page = 0;
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: (
          {int limit = 100, int offset = 0, bool thisDeviceOnly = false, String? cursor, MemoryReadView? view}) {
        if (page++ == 0) {
          return Future.value(GetMemoriesResult([_memory], true, nextCursor: 'c2'));
        }
        return gate.future.then((_) => GetMemoriesResult([_memory, _row('m2')], true));
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: false),
      deleteAllMemoriesRequest: () async => true,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), [_memory.id]);

    expect(await provider.deleteAllMemories(), isTrue);
    expect(provider.memories, isEmpty);

    gate.complete();
    await load;
    await SiriIntegration.current.drainIndexForTest();

    expect(provider.memories, isEmpty);
    expect(SharedPreferencesUtil().cachedMemories, isEmpty);
    expect(host.memories, isEmpty);
    expect(host.calls.sublist(host.calls.lastIndexOf('reconcile') + 1), isNot(contains('upsert')),
        reason: 'the retired page must not index rows after the clear');
  });

  test('a history page pending when delete-all commits is dropped', () async {
    final historyGate = Completer<void>();
    var historyCalls = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([_memory], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) {
        if (historyCalls++ == 0) {
          return Future.value(GetLedgerHistoryResult([_row('h1')], supported: true, nextCursor: 'h2'));
        }
        return historyGate.future.then((_) => GetLedgerHistoryResult([_row('h2')], supported: true));
      },
      deleteAllMemoriesRequest: () async => true,
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.ledgerHistoryHasMore, isTrue);
    expect(provider.memories.map((m) => m.id), containsAll([_memory.id, 'h1']));

    final more = provider.loadMoreHistory();
    await pumpEventQueue();
    expect(await provider.deleteAllMemories(), isTrue);
    historyGate.complete();
    await more;

    expect(provider.memories, isEmpty);
    expect(provider.ledgerHistoryHasMore, isFalse);
  });

  test('a retired history request cannot release the flag of a newer one', () async {
    var historyCalls = 0;
    final historyGates = <Completer<void>>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([_memory], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) {
        historyCalls++;
        if (offset == 0) {
          return Future.value(GetLedgerHistoryResult([_row('h1')], supported: true, nextCursor: 'h2'));
        }
        final gate = Completer<void>();
        historyGates.add(gate);
        return gate.future.then((_) => GetLedgerHistoryResult([_row('late-${historyGates.length}')], supported: true));
      },
      deleteAllMemoriesRequest: () async => true,
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.ledgerHistoryHasMore, isTrue);

    final staleMore = provider.loadMoreHistory();
    await pumpEventQueue();
    expect(historyCalls, 2);
    expect(await provider.deleteAllMemories(), isTrue);

    await provider.loadMemories();
    expect(provider.ledgerHistoryHasMore, isTrue);
    final freshMore = provider.loadMoreHistory();
    await pumpEventQueue();
    expect(historyCalls, 4);

    historyGates[0].complete();
    await pumpEventQueue();
    final third = provider.loadMoreHistory();
    await pumpEventQueue();
    expect(historyCalls, 4, reason: 'the retired request must not release the newer request flag');
    await third;

    historyGates[1].complete();
    await freshMore;
    await staleMore;
    expect(provider.memories.map((m) => m.id), contains('late-2'));
    expect(provider.memories.map((m) => m.id), isNot(contains('late-1')));
  });

  test('a failed delete-all keeps the in-flight traversal and rows', () async {
    final gate = Completer<void>();
    var page = 0;
    final provider = MemoriesProvider(
      fetchMemoriesCursorRequest: (
          {int limit = 100, int offset = 0, bool thisDeviceOnly = false, String? cursor, MemoryReadView? view}) {
        if (page++ == 0) {
          return Future.value(GetMemoriesResult([_memory], true, nextCursor: 'c2'));
        }
        return gate.future.then((_) => GetMemoriesResult([_memory, _row('m2')], true));
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: false),
      deleteAllMemoriesRequest: () async => false,
    );
    addTearDown(provider.dispose);

    final load = provider.loadMemories(limit: 1);
    await pumpEventQueue();
    expect(provider.memories.map((m) => m.id), [_memory.id]);

    expect(await provider.deleteAllMemories(), isFalse);
    gate.complete();
    await load;
    expect(provider.memories.map((m) => m.id), containsAll([_memory.id, 'm2']));
  });
}
