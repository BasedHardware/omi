import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/library/conversation_model.dart';

Map<String, dynamic> _baseConversation({Map<String, dynamic>? structured}) {
  return {
    'id': 'c1',
    'created_at': '2026-04-30T10:00:00Z',
    'transcript_segments': const <Map<String, dynamic>>[],
    'apps_results': const <Map<String, dynamic>>[],
    'structured': structured ?? {'title': 'Sample', 'overview': '', 'action_items': const <Map<String, dynamic>>[]},
  };
}

void main() {
  group('ConversationItem.decisions getter', () {
    test('parses non-empty decisions array including null owner/due', () {
      final json = _baseConversation(
        structured: {
          'title': 'Sample',
          'overview': '',
          'action_items': const <Map<String, dynamic>>[],
          'decisions': [
            {
              'id': 'd1',
              'statement': 'Ship feature on Friday',
              'owner_name': 'Sarah',
              'due_at': '2026-06-13T00:00:00Z',
              'status': 'open',
              'open_questions': ['How will we test?', 'Who reviews?'],
              'related_action_item_ids': [0, 2],
            },
            {
              'id': 'd2',
              'statement': 'Defer redesign to Q3',
              'owner_name': null,
              'due_at': null,
              'status': 'blocked',
              'open_questions': const <String>[],
              'related_action_item_ids': const <int>[],
            },
          ],
        },
      );

      final item = ConversationItem.fromJson(json);
      final ds = item.decisions;
      expect(ds.length, 2);

      expect(ds[0].id, 'd1');
      expect(ds[0].statement, 'Ship feature on Friday');
      expect(ds[0].ownerName, 'Sarah');
      expect(ds[0].dueAt, isNotNull);
      expect(ds[0].status, 'open');
      expect(ds[0].openQuestions, ['How will we test?', 'Who reviews?']);
      expect(ds[0].relatedActionItemIds, [0, 2]);

      expect(ds[1].ownerName, isNull);
      expect(ds[1].dueAt, isNull);
      expect(ds[1].status, 'blocked');
      expect(ds[1].openQuestions, isEmpty);
      expect(ds[1].relatedActionItemIds, isEmpty);
    });

    test('returns empty list when structured lacks the decisions key (legacy backend)', () {
      // Legacy / non-allowlisted response: no `decisions` key at all.
      final json = _baseConversation(
        structured: {'title': 'Legacy', 'overview': '', 'action_items': const <Map<String, dynamic>>[]},
      );

      final item = ConversationItem.fromJson(json);
      expect(item.decisions, isEmpty);
      expect(item.hasDecisionsField, isFalse);
    });

    test('hasDecisionsField is true when key is present even with empty array', () {
      final json = _baseConversation(
        structured: {
          'title': 'Empty extraction',
          'overview': '',
          'action_items': const <Map<String, dynamic>>[],
          'decisions': const <Map<String, dynamic>>[],
        },
      );

      final item = ConversationItem.fromJson(json);
      expect(item.decisions, isEmpty);
      expect(item.hasDecisionsField, isTrue);
    });
  });

  group('DecisionItem.fromJson', () {
    test('handles missing/null fields with sensible defaults', () {
      final d = DecisionItem.fromJson(<String, dynamic>{});
      expect(d.id, '');
      expect(d.statement, '');
      expect(d.ownerName, isNull);
      expect(d.dueAt, isNull);
      expect(d.status, 'open');
      expect(d.openQuestions, isEmpty);
      expect(d.relatedActionItemIds, isEmpty);
    });

    test('coerces non-string entries out of open_questions and non-num entries out of related_action_item_ids', () {
      final d = DecisionItem.fromJson({
        'id': 'd1',
        'statement': 'x',
        'open_questions': ['ok', 42, null, 'fine'],
        'related_action_item_ids': [0, 'bad', 2.0, null, 3],
      });
      expect(d.openQuestions, ['ok', 'fine']);
      expect(d.relatedActionItemIds, [0, 2, 3]);
    });

    test('parses ISO date string into local DateTime', () {
      final d = DecisionItem.fromJson({'id': 'd1', 'statement': 'x', 'due_at': '2026-06-13T15:00:00Z'});
      expect(d.dueAt, isNotNull);
      // toLocal() converts; just assert the year/month so we don't trip on tz.
      expect(d.dueAt!.year, 2026);
      expect(d.dueAt!.month, 6);
    });
  });
}
