import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _ledgerMemory({
  required String id,
  required KnowledgeLedgerKind kind,
  int weight = 0,
  bool? review,
  DateTime? invalidAt,
  DateTime? validAt,
  String? slot,
  String? supersededBy,
  String content = '',
  String uid = 'ledger-review-user',
  String schemaVersion = 'knowledge_ledger.v1',
  bool intentBacked = true,
  bool isLocked = false,
}) {
  return Memory(
    id: id,
    uid: uid,
    content: content.isEmpty ? id : content,
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 8, 23),
    updatedAt: DateTime.utc(2026, 8, 23),
    visibility: MemoryVisibility.private,
    userReview: review,
    ledgerSchemaVersion: schemaVersion,
    ledgerKind: kind,
    ledgerSlot: kind == KnowledgeLedgerKind.fact ? (slot ?? id) : null,
    invalidAt: invalidAt,
    validAt: validAt,
    supersededBy: supersededBy,
    intentBacked: intentBacked,
    curationWeight: weight,
    isLocked: isLocked,
  );
}

Memory _revertReplacement(
  Memory source, {
  String id = 'restored-fact',
  String? uid,
  String? content,
  MemoryVisibility? visibility,
}) {
  return Memory(
    id: id,
    uid: uid ?? source.uid,
    content: content ?? source.content,
    category: source.category,
    createdAt: DateTime.utc(2026, 8, 24),
    updatedAt: DateTime.utc(2026, 8, 24),
    visibility: visibility ?? source.visibility,
    ledgerSchemaVersion: 'knowledge_ledger.v1',
    ledgerKind: KnowledgeLedgerKind.fact,
    ledgerSlot: source.ledgerSlot,
    subjectScope: source.subjectScope,
    subjectEntityId: source.subjectEntityId,
    validAt: DateTime.utc(2026, 8, 24),
    intentBacked: true,
    curationWeight: source.curationWeight,
    writeReason: 'direct_user_statement',
    evidence: [
      {'source_type': 'explicit_user_revert', 'source_id': source.id},
    ],
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'ledger-review-user'});
    await SharedPreferencesUtil.init();
  });

  test('provider exposes deterministic current and historical ledger views', () async {
    final rows = [
      _ledgerMemory(id: 'fact-low', kind: KnowledgeLedgerKind.fact, weight: 1),
      _ledgerMemory(id: 'fact-high', kind: KnowledgeLedgerKind.fact, weight: 9),
      _ledgerMemory(id: 'playbook', kind: KnowledgeLedgerKind.document),
      _ledgerMemory(id: 'trigger', kind: KnowledgeLedgerKind.trigger),
      _ledgerMemory(
        id: 'closed',
        kind: KnowledgeLedgerKind.fact,
        invalidAt: DateTime.utc(2026, 8, 24),
      ),
    ];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(rows, true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();

    expect(provider.currentLedgerFacts.map((row) => row.id), ['fact-high', 'fact-low']);
    expect(provider.currentLedgerPlaybooks.map((row) => row.id), ['playbook']);
    expect(provider.currentLedgerTriggers.map((row) => row.id), ['trigger']);
    expect(provider.historicalLedgerRows.map((row) => row.id), ['closed']);
  });

  test('current fact ordering matches canonical validity tie breaker', () async {
    final newer = _ledgerMemory(
      id: 'newer',
      kind: KnowledgeLedgerKind.fact,
      slot: 'home_city',
      validAt: DateTime.utc(2026, 8, 23),
    );
    final older = _ledgerMemory(
      id: 'older',
      kind: KnowledgeLedgerKind.fact,
      slot: 'home_city',
      validAt: DateTime.utc(2026, 8, 22),
    );
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([newer, older], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();

    expect(provider.currentLedgerFacts.map((row) => row.id), ['older', 'newer']);
  });

  test('review is optimistic but rolls back when canonical persistence fails', () async {
    final row = _ledgerMemory(id: 'fact', kind: KnowledgeLedgerKind.fact);
    final requested = <bool>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async {
        requested.add(value);
        return false;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(await provider.reviewMemory(row, false), isFalse);
    expect(requested, [false]);
    expect(row.userReview, isNull);
    expect(row.reviewed, isFalse);
  });

  test('persisted rejection moves a row into the historical projection', () async {
    final row = _ledgerMemory(id: 'fact', kind: KnowledgeLedgerKind.fact);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(await provider.reviewMemory(row, false), isTrue);
    expect(provider.currentLedgerFacts, isEmpty);
    expect(provider.historicalLedgerRows.map((item) => item.id), ['fact']);
  });

  test('accepting a rejected row restores it to the current projection', () async {
    final row = _ledgerMemory(id: 'rejected', kind: KnowledgeLedgerKind.fact, review: false);
    final requested = <bool>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([row], supported: true),
      reviewMemoryRequest: (id, value) async {
        requested.add(value);
        return true;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(provider.historicalLedgerRows.map((item) => item.id), ['rejected']);
    expect(await provider.reviewMemory(row, true), isTrue);
    expect(requested, [true]);
    expect(provider.currentLedgerFacts.map((item) => item.id), ['rejected']);
    expect(provider.historicalLedgerRows, isEmpty);
  });

  test('transport exceptions roll back the optimistic review', () async {
    final row = _ledgerMemory(id: 'fact', kind: KnowledgeLedgerKind.fact, review: true);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([row], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => throw StateError('offline'),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(await provider.reviewMemory(row, false), isFalse);
    expect(row.userReview, isTrue);
    expect(row.reviewed, isFalse);
  });

  test('reload merges canonical history without duplicating current rows', () async {
    final current = _ledgerMemory(id: 'current', kind: KnowledgeLedgerKind.fact);
    final rejected = _ledgerMemory(id: 'rejected', kind: KnowledgeLedgerKind.fact, review: false);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([current], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([current, rejected], supported: true),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();

    expect(provider.memories.map((row) => row.id), ['current', 'rejected']);
    expect(provider.currentLedgerFacts.map((row) => row.id), ['current']);
    expect(provider.historicalLedgerRows.map((row) => row.id), ['rejected']);
    expect(provider.ledgerHistorySupported, isTrue);
    expect(provider.ledgerHistoryTruncated, isFalse);
  });

  test('truncated history remains visible and is labeled partial', () async {
    final rejected = _ledgerMemory(id: 'rejected', kind: KnowledgeLedgerKind.fact, review: false);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([rejected], supported: true, truncated: true),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();

    expect(provider.historicalLedgerRows.map((row) => row.id), ['rejected']);
    expect(provider.ledgerHistorySupported, isTrue);
    expect(provider.ledgerHistoryTruncated, isTrue);
  });

  test('superseded fact revert is non-optimistic, debounced, and appends the authoritative replacement', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      slot: 'home_city',
      supersededBy: 'newer-fact',
      invalidAt: DateTime.utc(2026, 8, 24),
      weight: 4,
    );
    final response = Completer<RevertMemoryResult>();
    final operationIds = <String>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([source], supported: true),
      revertMemoryRequest: (id, operationId) {
        operationIds.add(operationId);
        return response.future;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final firstTap = provider.revertSupersededFact(source);
    expect(provider.isRevertingMemory(source.id), isTrue);
    expect(provider.memories.map((memory) => memory.id), ['superseded']);
    expect(await provider.revertSupersededFact(source), isFalse);
    expect(operationIds, hasLength(1));
    expect(operationIds.single, matches(RegExp(r'^[0-9a-f-]{36}$')));

    response.complete(
      RevertMemoryResult(persisted: true, authoritativeMemory: _revertReplacement(source)),
    );
    expect(await firstTap, isTrue);
    expect(provider.isRevertingMemory(source.id), isFalse);
    expect(provider.historicalLedgerRows.map((memory) => memory.id), ['superseded']);
    expect(provider.currentLedgerFacts.map((memory) => memory.id), ['restored-fact']);
    expect(provider.canRevertSupersededFact(source), isFalse);
  });

  test('revert reuses its operation id after an ambiguous lost response', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      supersededBy: 'newer-fact',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final operationIds = <String>[];
    var requestCount = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([source], supported: true),
      revertMemoryRequest: (id, operationId) async {
        operationIds.add(operationId);
        requestCount++;
        return requestCount == 1
            ? const RevertMemoryResult(persisted: false)
            : RevertMemoryResult(persisted: true, authoritativeMemory: _revertReplacement(source));
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(await provider.revertSupersededFact(source), isFalse);
    expect(await provider.revertSupersededFact(source), isTrue);
    expect(operationIds, hasLength(2));
    expect(operationIds.toSet(), hasLength(1));
    expect(provider.currentLedgerFacts.map((memory) => memory.id), ['restored-fact']);
  });

  test('revert rejects malformed authoritative replacements without local mutation', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      supersededBy: 'newer-fact',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final invalidReplacements = [
      _revertReplacement(source, id: source.id),
      _revertReplacement(source, uid: 'different-user'),
      _revertReplacement(source, content: 'Lives in Queens'),
    ];

    for (final replacement in invalidReplacements) {
      final provider = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
            const GetMemoriesResult([], true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            GetLedgerHistoryResult([source], supported: true),
        revertMemoryRequest: (id, operationId) async =>
            RevertMemoryResult(persisted: true, authoritativeMemory: replacement),
      );
      await provider.loadMemories();

      expect(await provider.revertSupersededFact(source), isFalse);
      expect(provider.memories.map((memory) => memory.id), ['superseded']);
      provider.dispose();
    }
  });

  test('revert validates replacement visibility against the current chain tail', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      slot: 'home_city',
      supersededBy: 'current-tail',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final tail = _ledgerMemory(
      id: 'current-tail',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Queens',
      slot: 'home_city',
    )..visibility = MemoryVisibility.public;
    final closedTail = _ledgerMemory(
      id: 'current-tail',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Queens',
      slot: 'home_city',
      supersededBy: 'matching-visibility',
      invalidAt: DateTime.utc(2026, 8, 24),
    )..visibility = MemoryVisibility.public;
    final responses = [
      RevertMemoryResult(
        persisted: true,
        authoritativeMemory: _revertReplacement(source, id: 'wrong-visibility'),
      ),
      RevertMemoryResult(
        persisted: true,
        authoritativeMemory: _revertReplacement(
          source,
          id: 'matching-visibility',
          visibility: MemoryVisibility.public,
        ),
      ),
    ];
    var historyRequests = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([tail], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async {
        historyRequests++;
        return GetLedgerHistoryResult(
          historyRequests < 2 ? [source] : [source, closedTail],
          supported: true,
        );
      },
      revertMemoryRequest: (id, operationId) async => responses.removeAt(0),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(await provider.revertSupersededFact(source), isFalse);
    expect(provider.memories.any((memory) => memory.id == 'wrong-visibility'), isFalse);
    expect(await provider.revertSupersededFact(source), isTrue);
    expect(provider.currentLedgerFacts.map((memory) => memory.id), ['matching-visibility']);
    expect(provider.historicalLedgerRows.map((memory) => memory.id), containsAll(['superseded', 'current-tail']));
  });

  test('revert preserves a replacement loaded by a refresh while the mutation response is in flight', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      slot: 'home_city',
      supersededBy: 'current-tail',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final tail = _ledgerMemory(
      id: 'current-tail',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Queens',
      slot: 'home_city',
    );
    final replacement = _revertReplacement(source);
    final closedTail = _ledgerMemory(
      id: 'current-tail',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Queens',
      slot: 'home_city',
      supersededBy: replacement.id,
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final response = Completer<RevertMemoryResult>();
    var serverReverted = false;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(serverReverted ? [replacement] : [tail], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult(serverReverted ? [source, closedTail] : [source], supported: true),
      revertMemoryRequest: (id, operationId) => response.future,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final pendingRevert = provider.revertSupersededFact(source);
    serverReverted = true;
    await provider.loadMemories();
    expect(provider.currentLedgerFacts.map((memory) => memory.id), [replacement.id]);

    response.complete(RevertMemoryResult(persisted: true, authoritativeMemory: replacement));
    expect(await pendingRevert, isTrue);
    expect(provider.currentLedgerFacts.map((memory) => memory.id), [replacement.id]);
  });

  test('refresh started before a revert cannot overwrite its authoritative replacement', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      slot: 'home_city',
      supersededBy: 'current-tail',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final tail = _ledgerMemory(
      id: 'current-tail',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Queens',
      slot: 'home_city',
    );
    final replacement = _revertReplacement(source);
    final response = Completer<RevertMemoryResult>();
    final staleCurrentResponse = Completer<GetMemoriesResult>();
    var currentRequests = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) {
        currentRequests++;
        if (currentRequests == 1) return Future.value(GetMemoriesResult([tail], true));
        return staleCurrentResponse.future;
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([source], supported: true),
      revertMemoryRequest: (id, operationId) => response.future,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final pendingRevert = provider.revertSupersededFact(source);
    final staleRefresh = provider.loadMemories();
    response.complete(RevertMemoryResult(persisted: true, authoritativeMemory: replacement));
    expect(await pendingRevert, isTrue);
    expect(provider.currentLedgerFacts.map((memory) => memory.id), [replacement.id]);

    staleCurrentResponse.complete(GetMemoriesResult([tail], true));
    await staleRefresh;
    expect(provider.currentLedgerFacts.map((memory) => memory.id), [replacement.id]);
    expect(provider.loading, isFalse);
  });

  test('revert never removes an unrelated current fact when the local chain has a missing link', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      slot: 'home_city',
      supersededBy: 'missing-intermediate',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final unrelatedCurrent = _ledgerMemory(
      id: 'unrelated-current',
      kind: KnowledgeLedgerKind.fact,
      content: 'Lives in Brooklyn',
      slot: 'home_city',
    );
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([unrelatedCurrent], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([source], supported: true),
      revertMemoryRequest: (id, operationId) async =>
          RevertMemoryResult(persisted: true, authoritativeMemory: _revertReplacement(source)),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    expect(provider.canRevertSupersededFact(source), isTrue);
    expect(await provider.revertSupersededFact(source), isTrue);
    expect(
      provider.currentLedgerFacts.map((memory) => memory.id),
      containsAll(['unrelated-current', 'restored-fact']),
    );
    expect(provider.memories.any((memory) => memory.id == 'unrelated-current'), isTrue);
  });

  test('session generation change discards a late authoritative revert response', () async {
    final source = _ledgerMemory(
      id: 'superseded',
      kind: KnowledgeLedgerKind.fact,
      supersededBy: 'newer-fact',
      invalidAt: DateTime.utc(2026, 8, 24),
    );
    final response = Completer<RevertMemoryResult>();
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult([source], supported: true),
      revertMemoryRequest: (id, operationId) => response.future,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final pending = provider.revertSupersededFact(source);
    provider.clearUserData();
    response.complete(
      RevertMemoryResult(persisted: true, authoritativeMemory: _revertReplacement(source)),
    );

    expect(await pending, isFalse);
    expect(provider.memories, isEmpty);
  });

  test('revert excludes standalone closed, rejected-current, non-fact, future, and legacy rows', () async {
    final rows = [
      _ledgerMemory(
        id: 'closed',
        kind: KnowledgeLedgerKind.fact,
        invalidAt: DateTime.utc(2026, 8, 24),
      ),
      _ledgerMemory(id: 'rejected', kind: KnowledgeLedgerKind.fact, review: false),
      _ledgerMemory(id: 'playbook', kind: KnowledgeLedgerKind.document, supersededBy: 'replacement'),
      _ledgerMemory(
        id: 'future',
        kind: KnowledgeLedgerKind.fact,
        supersededBy: 'replacement',
        schemaVersion: 'knowledge_ledger.v2',
      ),
      _ledgerMemory(
        id: 'legacy',
        kind: KnowledgeLedgerKind.fact,
        supersededBy: 'replacement',
        schemaVersion: '',
      ),
    ];
    var requests = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          GetLedgerHistoryResult(rows, supported: true),
      revertMemoryRequest: (id, operationId) async {
        requests++;
        return const RevertMemoryResult(persisted: false);
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    for (final row in rows) {
      expect(provider.canRevertSupersededFact(row), isFalse, reason: row.id);
      expect(await provider.revertSupersededFact(row), isFalse, reason: row.id);
    }
    expect(requests, 0);
  });

  test('a locked memory absent from the loaded list is not reviewed', () async {
    final reviews = <String>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async {
        reviews.add(id);
        return true;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final locked = _ledgerMemory(id: 'locked-absent', kind: KnowledgeLedgerKind.fact, isLocked: true);
    expect(await provider.reviewMemory(locked, false), isFalse);
    expect(reviews, isEmpty, reason: 'locked rows are immutable even when the id is not in the loaded list');
  });

  test('clearUserData resets the review-card hydration budget', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    // Spend the whole budget for an id the settled list does not resolve.
    expect(provider.consumeHydrationAsk('mem-a'), isTrue);
    expect(provider.consumeHydrationAsk('mem-a'), isFalse);
    provider.clearUserData();

    // A new account session restores eligibility.
    expect(provider.consumeHydrationAsk('mem-a'), isTrue);
  });

  test('clearUserData clears settled verdicts recorded for unresolved ids', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final absent = _ledgerMemory(id: 'mem-absent', kind: KnowledgeLedgerKind.fact);
    expect(await provider.reviewMemory(absent, true), isTrue);
    expect(provider.settledReviewFor('mem-absent'), isTrue);

    provider.clearUserData();
    expect(provider.settledReviewFor('mem-absent'), isNull);
  });

  test('a settled verdict for an unresolved id is recorded and overwritable', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final absent = _ledgerMemory(id: 'mem-absent', kind: KnowledgeLedgerKind.fact);
    expect(await provider.reviewMemory(absent, false), isTrue);
    expect(provider.settledReviewFor('mem-absent'), isFalse);

    // The same user can change their mind; the last persisted verdict stands.
    expect(await provider.reviewMemory(absent, true), isTrue);
    expect(provider.settledReviewFor('mem-absent'), isTrue);
  });

  test('concurrent same-parameter loads are coalesced instead of racing', () async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        fetches++;
        await Future<void>.delayed(const Duration(milliseconds: 10));
        return GetMemoriesResult([_ledgerMemory(id: 'fact', kind: KnowledgeLedgerKind.fact)], true);
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
    );
    addTearDown(provider.dispose);

    // Several review cards mount while the first fetch is still in flight
    // (`hasLoaded` still false). They must join the one load, not start
    // races the sequence guard would discard.
    await Future.wait([provider.loadMemories(), provider.loadMemories(), provider.loadMemories()]);

    expect(fetches, 1);
    expect(provider.memories.map((item) => item.id), ['fact']);
  });
}
