import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _memory({
  required String id,
  String? band = 'current',
  DateTime? computedAt,
  bool historical = false,
}) {
  computedAt ??= DateTime.utc(2026, 9, 13);
  return Memory(
    id: id,
    uid: 'temporal-user',
    content: id,
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 9, 13),
    updatedAt: DateTime.utc(2026, 9, 13),
    visibility: MemoryVisibility.private,
    currencyBand: band,
    currency: band == null ? null : 0.8,
    beliefComputedAt: computedAt,
    asOf: computedAt,
    ledgerSchemaVersion: historical ? 'knowledge_ledger.v1' : null,
    ledgerKind: historical ? KnowledgeLedgerKind.fact : null,
    intentBacked: historical,
    invalidAt: historical ? DateTime.utc(2026, 9, 12) : null,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'temporal-user'});
    await SharedPreferencesUtil.init();
  });

  test(
    'server views keep useful-now, history, and all datasets disjoint',
    () async {
      final current = _memory(id: 'current');
      final old = _memory(id: 'old', historical: true);
      final requestedViews = <MemoryReadView?>[];
      final provider = MemoriesProvider(
        fetchMemoriesCursorRequest: ({
          int limit = 100,
          int offset = 0,
          bool thisDeviceOnly = false,
          String? cursor,
          MemoryReadView? view,
        }) async =>
            (() {
          requestedViews.add(view);
          final rows = switch (view) {
            MemoryReadView.history => [old],
            MemoryReadView.all => [current, old],
            _ => [current],
          };
          return GetMemoriesResult(rows, true, beliefEnabled: true);
        })(),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: false, beliefEnabled: true),
      );
      addTearDown(provider.dispose);

      await provider.loadMemories();
      expect(provider.memoryBeliefEnabled, isTrue);
      expect(provider.filteredMemories.map((memory) => memory.id), ['current']);
      expect(requestedViews, [null, MemoryReadView.usefulNow]);

      provider.setCollectionView(MemoryCollectionView.history);
      await Future<void>.delayed(Duration.zero);
      await provider.loadMemories();
      expect(provider.filteredMemories.map((memory) => memory.id), ['old']);
      expect(requestedViews.last, MemoryReadView.history);

      provider.setCollectionView(MemoryCollectionView.all);
      await Future<void>.delayed(Duration.zero);
      await provider.loadMemories();
      expect(provider.filteredMemories.map((memory) => memory.id), ['current', 'old']);
      expect(requestedViews.last, MemoryReadView.all);
    },
  );

  test(
    'history continuation keeps partial state until the server finishes',
    () async {
      final first = _memory(id: 'old-1', historical: true);
      final second = _memory(id: 'old-2', historical: true);
      var historyCalls = 0;
      final historyOffsets = <int>[];
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({
          int limit = 100,
          int offset = 0,
          bool thisDeviceOnly = false,
        }) async =>
            const GetMemoriesResult([], true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async {
          historyCalls++;
          historyOffsets.add(offset);
          if (historyCalls == 1) {
            return GetLedgerHistoryResult(
              [first],
              supported: true,
              truncated: true,
            );
          }
          return GetLedgerHistoryResult([second], supported: true);
        },
      );
      addTearDown(provider.dispose);

      await provider.loadMemories();
      expect(provider.ledgerHistoryHasMore, isTrue);
      expect(provider.ledgerHistoryTruncated, isTrue);

      await provider.loadMoreHistory();
      expect(historyOffsets, [0, 1]);
      expect(
        provider.memories.map((memory) => memory.id),
        containsAll(<String>['old-1', 'old-2']),
      );
      expect(provider.ledgerHistoryHasMore, isFalse);
      expect(provider.ledgerHistoryTruncated, isFalse);
    },
  );

  test('concurrent load-more history calls are single-flight', () async {
    final offsets = <int>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({
        int limit = 100,
        int offset = 0,
        bool thisDeviceOnly = false,
      }) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async {
        offsets.add(offset);
        return GetLedgerHistoryResult(
          [_memory(id: 'old-$offset', historical: true)],
          supported: true,
          truncated: true,
        );
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.ledgerHistoryHasMore, isTrue);
    expect(offsets, [0]);

    final first = provider.loadMoreHistory();
    final second = provider.loadMoreHistory();
    await Future.wait([first, second]);
    // The second call must not refetch the in-flight offset: each page is
    // requested exactly once and the continuation stays sequential.
    expect(offsets, [0, 1]);

    await provider.loadMoreHistory();
    expect(offsets, [0, 1, 2]);
    expect(
      provider.memories.map((memory) => memory.id),
      containsAllInOrder(<String>['old-0', 'old-1', 'old-2']),
    );
  });

  test('history follows a short server cursor page instead of claiming completion', () async {
    final calls = <({int offset, String? cursor})>[];
    final old = _memory(id: 'history-cursor-old', historical: true);
    var page = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true, beliefEnabled: true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: false),
      fetchLedgerHistoryCursorRequest: ({int limit = 500, int offset = 0, String? cursor}) async {
        calls.add((offset: offset, cursor: cursor));
        page++;
        if (page == 1) {
          return const GetLedgerHistoryResult(
            [],
            supported: true,
            nextCursor: 'history-2',
            beliefEnabled: true,
          );
        }
        return GetLedgerHistoryResult([old], supported: true, beliefEnabled: true);
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(calls, [(offset: 0, cursor: null), (offset: 0, cursor: 'history-2')]);
    expect(provider.memories.map((memory) => memory.id), ['history-cursor-old']);
    expect(provider.ledgerHistoryHasMore, isFalse);
    expect(provider.ledgerHistoryTruncated, isFalse);
  });

  test('suppressed rows stay available in explicit history only', () async {
    final suppressed = _memory(id: 'suppressed')
      ..arguments = {
        'memory_use': {'suppressed': true, 'state': 'suppressed'},
      };
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({
        int limit = 100,
        int offset = 0,
        bool thisDeviceOnly = false,
      }) async =>
          GetMemoriesResult(
        [suppressed],
        true,
        beliefEnabled: true,
      ),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async => GetLedgerHistoryResult(
        [suppressed],
        supported: true,
        beliefEnabled: true,
      ),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.filteredMemories, isEmpty);
    provider.setCollectionView(MemoryCollectionView.history);
    await Future<void>.delayed(Duration.zero);
    expect(provider.filteredMemories.map((memory) => memory.id), ['suppressed']);
  });

  test(
    'a missing capability header resets temporal filtering and preserves rows',
    () async {
      final current = _memory(id: 'current');
      final old = _memory(id: 'old', historical: true);
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({
          int limit = 100,
          int offset = 0,
          bool thisDeviceOnly = false,
        }) async =>
            GetMemoriesResult([current], true, beliefEnabled: true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            GetLedgerHistoryResult([old], supported: true),
      );
      addTearDown(provider.dispose);

      await provider.loadMemories();
      expect(provider.memoryBeliefEnabled, isFalse);
      expect(
        provider.filteredMemories.map((memory) => memory.id),
        contains('old'),
      );
    },
  );

  test('a false capability preserves legacy rows without temporal filtering', () async {
    final current = _memory(id: 'current-false');
    final old = _memory(id: 'old-false', historical: true);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({
        int limit = 100,
        int offset = 0,
        bool thisDeviceOnly = false,
      }) async =>
          GetMemoriesResult([current], true, beliefEnabled: true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async => GetLedgerHistoryResult(
        [old],
        supported: true,
        beliefEnabled: false,
      ),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(provider.memoryBeliefEnabled, isFalse);
    expect(
      provider.filteredMemories.map((memory) => memory.id),
      containsAll(<String>['current-false', 'old-false']),
    );
  });

  test(
    'memory-use retries reuse one feedback id and refresh the confirmed row',
    () async {
      final memory = _memory(id: 'use-1');
      final feedbackIds = <String>[];
      var useCalls = 0;
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({
          int limit = 100,
          int offset = 0,
          bool thisDeviceOnly = false,
        }) async =>
            GetMemoriesResult([memory], true, beliefEnabled: true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: false, beliefEnabled: true),
        memoryUseRequest: ({
          required String memoryId,
          required MemoryUseAction action,
          required String feedbackId,
        }) async {
          feedbackIds.add(feedbackId);
          useCalls++;
          if (useCalls == 1) return const MemoryUseResult(persisted: false);
          return MemoryUseResult(
            persisted: true,
            memoryId: memoryId,
            action: action,
            feedbackId: feedbackId,
            suppressed: true,
          );
        },
      );
      addTearDown(provider.dispose);

      await provider.loadMemories();
      expect(
        await provider.setMemoryUse(memory, MemoryUseAction.suppress),
        isFalse,
      );
      expect(
        await provider.setMemoryUse(memory, MemoryUseAction.suppress),
        isTrue,
      );
      expect(feedbackIds, hasLength(2));
      expect(feedbackIds[0], feedbackIds[1]);
      expect(memory.memoryUseSuppressed, isTrue);
      // The acknowledged action is complete; a later distinct click gets a
      // fresh id rather than replaying the old receipt.
      expect(
        await provider.setMemoryUse(memory, MemoryUseAction.suppress),
        isTrue,
      );
      expect(feedbackIds, hasLength(3));
      expect(feedbackIds[2], isNot(feedbackIds[1]));
    },
  );

  test('memory-use confirmation bypasses a pre-mutation in-flight load', () async {
    final memory = _memory(id: 'use-race');
    final firstPage = Completer<GetMemoriesResult>();
    var fetchCalls = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({
        int limit = 100,
        int offset = 0,
        bool thisDeviceOnly = false,
      }) async {
        fetchCalls++;
        if (fetchCalls == 3) return firstPage.future;
        return GetMemoriesResult([memory], true, beliefEnabled: true);
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: false, beliefEnabled: true),
      memoryUseRequest: ({
        required String memoryId,
        required MemoryUseAction action,
        required String feedbackId,
      }) async =>
          MemoryUseResult(
        persisted: true,
        memoryId: memoryId,
        action: action,
        feedbackId: feedbackId,
        suppressed: true,
      ),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    expect(fetchCalls, 2);

    final initialLoad = provider.loadMemories();
    await Future<void>.delayed(Duration.zero);
    expect(fetchCalls, 3);

    expect(
      await provider.setMemoryUse(memory, MemoryUseAction.suppress),
      isTrue,
    );
    expect(fetchCalls, 4);
    expect(memory.memoryUseSuppressed, isTrue);

    firstPage.complete(GetMemoriesResult([memory], true, beliefEnabled: true));
    await initialLoad;
  });

  test(
    'current list follows a server cursor after an empty page without mixing offset',
    () async {
      final calls = <({int offset, String? cursor, MemoryReadView? view})>[];
      final provider = MemoriesProvider(
        fetchMemoriesCursorRequest: ({
          int limit = 100,
          int offset = 0,
          bool thisDeviceOnly = false,
          String? cursor,
          MemoryReadView? view,
        }) async {
          calls.add((offset: offset, cursor: cursor, view: view));
          if (cursor == null) {
            return const GetMemoriesResult(
              [],
              true,
              nextCursor: 'memory-2',
              beliefEnabled: true,
            );
          }
          return GetMemoriesResult([
            _memory(id: 'memory-2'),
          ], true, beliefEnabled: true);
        },
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: false),
      );
      addTearDown(provider.dispose);

      await provider.loadMemories();
      expect(calls, [
        (offset: 0, cursor: null, view: null),
        (offset: 0, cursor: null, view: MemoryReadView.usefulNow),
        (offset: 0, cursor: 'memory-2', view: MemoryReadView.usefulNow),
      ]);
      expect(
        provider.memories.map((memory) => memory.id),
        contains('memory-2'),
      );
    },
  );
  test(
    'memory-use suppress allow suppress creates three distinct acknowledged actions',
    () async {
      final memory = _memory(id: 'roundtrip');
      final actions = <MemoryUseAction>[];
      final feedbackIds = <String>[];
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({
          int limit = 100,
          int offset = 0,
          bool thisDeviceOnly = false,
        }) async =>
            GetMemoriesResult([memory], true, beliefEnabled: true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: false, beliefEnabled: true),
        memoryUseRequest: ({
          required String memoryId,
          required MemoryUseAction action,
          required String feedbackId,
        }) async {
          actions.add(action);
          feedbackIds.add(feedbackId);
          return MemoryUseResult(
            persisted: true,
            memoryId: memoryId,
            action: action,
            feedbackId: feedbackId,
            suppressed: action == MemoryUseAction.suppress,
          );
        },
      );
      addTearDown(provider.dispose);

      await provider.loadMemories();
      expect(
        await provider.setMemoryUse(memory, MemoryUseAction.suppress),
        isTrue,
      );
      expect(
        await provider.setMemoryUse(memory, MemoryUseAction.allow),
        isTrue,
      );
      expect(
        await provider.setMemoryUse(memory, MemoryUseAction.suppress),
        isTrue,
      );
      expect(actions, [
        MemoryUseAction.suppress,
        MemoryUseAction.allow,
        MemoryUseAction.suppress,
      ]);
      expect(feedbackIds.toSet(), hasLength(3));
    },
  );
}
