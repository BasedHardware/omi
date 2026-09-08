import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _ledgerFact({
  required String id,
  required String content,
  bool? userReview,
  String? supersededBy,
  String visibility = 'private',
}) {
  return Memory.fromJson({
    'id': id,
    'uid': 'ledger-correction-user',
    'content': content,
    'category': 'system',
    'created_at': '2026-08-23T12:00:00Z',
    'updated_at': '2026-08-23T12:00:00Z',
    'layer': 'long_term',
    'visibility': visibility,
    'ledger_schema_version': 'knowledge_ledger.v1',
    'kind': 'fact',
    'slot': 'home_city',
    'subject_scope': 'primary_user',
    'intent_backed': true,
    'curation_weight': 7,
    'write_reason': 'direct_user_statement',
    'user_review': userReview,
    'superseded_by': supersededBy,
    'evidence': const <Map<String, dynamic>>[],
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'ledger-correction-user'});
    await SharedPreferencesUtil.init();
  });

  test('rejected current fact swaps to authoritative correction', () async {
    final prior = _ledgerFact(id: 'prior', content: 'Lives in Boston', userReview: false);
    final replacement = _ledgerFact(id: 'replacement', content: 'Lives in Brooklyn', userReview: true);
    final requests = <(String, String)>[];
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([prior], true),
      editMemoryRequest: (memoryId, value) async {
        requests.add((memoryId, value));
        return EditMemoryResult(persisted: true, authoritativeMemory: replacement);
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    final persisted = await provider.editMemory(prior, 'Lives in Brooklyn');

    expect(persisted, isTrue);
    expect(requests, [('prior', 'Lives in Brooklyn')]);
    expect(provider.memories.single.id, 'replacement');
    expect(provider.memories.single.content, 'Lives in Brooklyn');
  });

  test('historical ledger fact never invokes correction request', () async {
    final historical = _ledgerFact(
      id: 'historical',
      content: 'Lives in Boston',
      supersededBy: 'replacement',
    );
    var requestCount = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([historical], true),
      editMemoryRequest: (memoryId, value) async {
        requestCount += 1;
        return const EditMemoryResult(persisted: true);
      },
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    final persisted = await provider.editMemory(historical, 'Different value');

    expect(persisted, isFalse);
    expect(requestCount, 0);
    expect(provider.memories.single.id, 'historical');
  });

  test('malformed authoritative replacement fails closed without swapping state', () async {
    final prior = _ledgerFact(id: 'prior', content: 'Lives in Boston');
    final wrongOwner = Memory.fromJson({
      ..._ledgerFact(id: 'replacement', content: 'Lives in Brooklyn').toJson(),
      'uid': 'foreign-user',
    });
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([prior], true),
      editMemoryRequest: (_, __) async => EditMemoryResult(persisted: true, authoritativeMemory: wrongOwner),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    final persisted = await provider.editMemory(prior, 'Lives in Brooklyn');

    expect(persisted, isFalse);
    expect(provider.memories.single.id, 'prior');
    expect(provider.memories.single.content, 'Lives in Boston');
  });

  test('shared visibility survives authoritative correction readback', () async {
    final prior = _ledgerFact(id: 'prior', content: 'Lives in Boston', visibility: 'shared');
    final replacement = _ledgerFact(id: 'replacement', content: 'Lives in Brooklyn', visibility: 'shared');
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([prior], true),
      editMemoryRequest: (_, __) async => EditMemoryResult(persisted: true, authoritativeMemory: replacement),
    );
    addTearDown(provider.dispose);

    await provider.loadMemories();
    final persisted = await provider.editMemory(prior, 'Lives in Brooklyn');

    expect(persisted, isTrue);
    expect(provider.memories.single.visibility, MemoryVisibility.shared);
    expect(provider.memories.single.toJson()['visibility'], 'shared');
  });
}
