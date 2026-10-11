import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/memory.dart';

Map<String, dynamic> _memoryJson({
  String id = 'memory-1',
  String? beliefComputedAt = '2026-09-13T12:00:00Z',
  String? currencyBand = 'current',
  double? currency = 0.9,
  String? asOf = '2026-09-13T11:00:00Z',
}) {
  return {
    'id': id,
    'uid': 'user-1',
    'content': 'Prefers voice transcription memories',
    'category': 'system',
    'created_at': '2026-09-01T12:00:00Z',
    'updated_at': '2026-09-13T12:00:00Z',
    'layer': 'long_term',
    'visibility': 'private',
    'belief_class': 'preference',
    'belief_computed_at': beliefComputedAt,
    'currency': currency,
    'currency_band': currencyBand,
    'half_life_days': 180,
    'as_of': asOf,
    'arguments': {
      'memory_use': {
        'state': 'useful',
        'suppressed': false,
        'last_action': 'useful',
        'feedback_id': 'feedback-1',
      },
    },
  };
}

void main() {
  test('temporal fields survive decode and cache round trip', () {
    final memory = Memory.fromJson(_memoryJson());

    expect(memory.beliefClass, 'preference');
    expect(memory.currency, 0.9);
    expect(memory.currencyBand, 'current');
    expect(memory.halfLifeDays, 180);
    expect(memory.asOf?.toUtc(), DateTime.parse('2026-09-13T11:00:00Z'));
    expect(
      memory.beliefComputedAt?.toUtc(),
      DateTime.parse('2026-09-13T12:00:00Z'),
    );
    expect(memory.isCurrentForUse, isTrue);
    expect(memory.memoryUseSuppressed, isFalse);
    expect(memory.memoryUseAction, 'useful');

    final roundTrip = Memory.fromJson(memory.toJson());
    expect(roundTrip.currencyBand, 'current');
    expect(roundTrip.beliefComputedAt?.toUtc(), memory.beliefComputedAt?.toUtc());
    expect(roundTrip.asOf?.toUtc(), memory.asOf?.toUtc());
    expect(roundTrip.memoryUseSuppressed, isFalse);
    expect(roundTrip.memoryUseAction, 'useful');
  });

  test(
    'unknown assessment is usable but never fabricated as a currency value',
    () {
      final memory = Memory.fromJson(
        _memoryJson(currency: null, currencyBand: null),
      );

      expect(memory.hasUnknownCurrency, isTrue);
      expect(memory.currency, isNull);
      expect(memory.currencyBand, isNull);
      expect(memory.isCurrentForUse, isTrue);
      expect(memory.isUsefulNow, isTrue);
    },
  );

  test('an old response without an assessment is not current', () {
    final memory = Memory.fromJson(
      _memoryJson(beliefComputedAt: null, currency: null, currencyBand: null),
    );

    expect(memory.hasCurrencyAssessment, isFalse);
    expect(memory.isCurrentForUse, isFalse);
    expect(memory.isUsefulNow, isTrue);
  });

  test('a deleted row without an assessment is never useful now', () {
    final memory = Memory.fromJson({
      ..._memoryJson(beliefComputedAt: null, currency: null, currencyBand: null),
      'deleted': true,
    });

    expect(memory.deleted, isTrue);
    expect(memory.hasCurrencyAssessment, isFalse);
    expect(memory.isCurrentForUse, isFalse);
    expect(memory.isUsefulNow, isFalse);
  });

  test(
    'historical ledger rows stay out of current use even with a current band',
    () {
      final memory = Memory.fromJson({
        ..._memoryJson(),
        'ledger_schema_version': 'knowledge_ledger.v1',
        'kind': 'fact',
        'intent_backed': true,
        'invalid_at': '2026-09-12T12:00:00Z',
      });

      expect(memory.isHistoricalKnowledgeLedgerRow, isTrue);
      expect(memory.isCurrentForUse, isFalse);
      expect(memory.isUsefulNow, isFalse);
    },
  );
}
