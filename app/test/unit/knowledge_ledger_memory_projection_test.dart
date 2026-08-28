import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/memory.dart';

Map<String, dynamic> _ledgerJson({
  String id = 'ledger-1',
  String kind = 'fact',
  String? body,
  String? slot = 'home_city',
  bool? userReview,
  String? supersededBy,
  String? invalidAt,
}) {
  return {
    'id': id,
    'uid': 'user-1',
    'content': 'Lives in Toronto',
    'category': 'system',
    'created_at': '2026-08-23T12:00:00Z',
    'updated_at': '2026-08-23T12:00:00Z',
    'layer': 'long_term',
    'visibility': 'private',
    'ledger_schema_version': 'knowledge_ledger.v1',
    'kind': kind,
    'body': body,
    'slot': slot,
    'subject_scope': 'primary_user',
    'intent_backed': true,
    'curation_weight': 7,
    'valid_at': '2026-08-23T12:00:00Z',
    'write_reason': 'direct_user_statement',
    'trigger_condition': kind == 'trigger'
        ? {
            'keywords': ['Toronto']
          }
        : <String, dynamic>{},
    'user_review': userReview,
    'superseded_by': supersededBy,
    'invalid_at': invalidAt,
    'evidence': [
      {
        'evidence_id': 'ev-1',
        'independence_group': 'user-assertion',
        'source_type': 'chat_turn',
      },
    ],
  };
}

void main() {
  test('mobile adapter preserves the complete ledger projection', () {
    final memory = Memory.fromJson(_ledgerJson());

    expect(memory.isKnowledgeLedger, isTrue);
    expect(memory.isCurrentKnowledgeLedgerRow, isTrue);
    expect(memory.isHistoricalKnowledgeLedgerRow, isFalse);
    expect(memory.ledgerKind, KnowledgeLedgerKind.fact);
    expect(memory.ledgerSlot, 'home_city');
    expect(memory.subjectScope, 'primary_user');
    expect(memory.intentBacked, isTrue);
    expect(memory.curationWeight, 7);
    expect(memory.writeReason, 'direct_user_statement');
    expect(memory.evidence.single['evidence_id'], 'ev-1');

    final roundTrip = Memory.fromJson(memory.toJson());
    expect(roundTrip.ledgerKind, KnowledgeLedgerKind.fact);
    expect(roundTrip.ledgerSlot, 'home_city');
    expect(roundTrip.isCurrentKnowledgeLedgerRow, isTrue);
    expect(roundTrip.evidence.single['source_type'], 'chat_turn');
  });

  test('playbook bodies and trigger conditions remain progressively available', () {
    final playbook = Memory.fromJson(
      _ledgerJson(kind: 'document', body: 'Run the release checklist in order.', slot: null),
    );
    final trigger = Memory.fromJson(_ledgerJson(kind: 'trigger', slot: null));

    expect(playbook.isLedgerPlaybook, isTrue);
    expect(playbook.ledgerBody, 'Run the release checklist in order.');
    expect(trigger.isLedgerTrigger, isTrue);
    expect(trigger.triggerCondition, {
      'keywords': ['Toronto']
    });
  });

  test('rejected, invalidated, and superseded rows are historical', () {
    for (final memory in [
      Memory.fromJson(_ledgerJson(userReview: false)),
      Memory.fromJson(_ledgerJson(invalidAt: '2026-08-24T00:00:00Z')),
      Memory.fromJson(_ledgerJson(supersededBy: 'ledger-2')),
    ]) {
      expect(memory.isCurrentKnowledgeLedgerRow, isFalse);
      expect(memory.isHistoricalKnowledgeLedgerRow, isTrue);
    }
  });

  test('legacy rows never gain ledger authority from compatibility tier fields', () {
    final memory = Memory.fromJson({
      'id': 'legacy-1',
      'uid': 'user-1',
      'content': 'Legacy memory',
      'created_at': '2026-08-23T12:00:00Z',
      'updated_at': '2026-08-23T12:00:00Z',
      'memory_tier': 'long_term',
    });

    expect(memory.isKnowledgeLedger, isFalse);
    expect(memory.isCurrentKnowledgeLedgerRow, isFalse);
    expect(memory.isHistoricalKnowledgeLedgerRow, isFalse);
  });
}
