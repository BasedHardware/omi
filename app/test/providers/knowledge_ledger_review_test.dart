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
}) {
  return Memory(
    id: id,
    uid: 'ledger-review-user',
    content: id,
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 8, 23),
    updatedAt: DateTime.utc(2026, 8, 23),
    visibility: MemoryVisibility.private,
    userReview: review,
    ledgerSchemaVersion: 'knowledge_ledger.v1',
    ledgerKind: kind,
    ledgerSlot: kind == KnowledgeLedgerKind.fact ? (slot ?? id) : null,
    invalidAt: invalidAt,
    validAt: validAt,
    intentBacked: true,
    curationWeight: weight,
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
}
