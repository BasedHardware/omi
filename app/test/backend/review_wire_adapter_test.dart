import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/review_wire.g.dart' as wire;
import 'package:omi/backend/schema/review.dart';

void main() {
  test('generated change page retains pagination and reversible UI state', () {
    final page = ReviewChangesPage.fromGenerated(wire.GeneratedReviewChangesResponse.fromJson({
      'changes': [
        {
          'change_id': 'synthetic-change',
          'kind': 'rename',
          'title': 'Synthetic correction',
          'created_at': '2026-10-08T12:00:00Z',
          'undone': true,
          'refs': [
            {'type': 'conversation', 'id': 'synthetic-conversation', 'label': 'Synthetic source'},
          ],
        },
      ],
      'next_cursor': 'opaque+/cursor',
    }));
    expect(page.nextCursor, 'opaque+/cursor');
    expect(page.changes.single.changeId, 'synthetic-change');
    expect(page.changes.single.undone, isTrue);
    expect(page.changes.single.kind, ReviewChangeKind.rename);
    expect(page.changes.single.refs.single.id, 'synthetic-conversation');
    expect(page.changes.single.createdAt.toUtc(), DateTime.utc(2026, 10, 8, 12));
  });

  test('generated changes reject malformed mandatory response fields', () {
    expect(() => wire.GeneratedReviewChangesResponse.fromJson({'changes': 'not a list'}), throwsFormatException);
    expect(() => wire.GeneratedReviewChange.fromJson({'change_id': 'synthetic'}), throwsFormatException);
  });

  test('generated empty review retains daily headroom', () {
    final items = ReviewItemsResponse.fromGenerated(
      wire.GeneratedReviewItemsResponse.fromJson({'items': [], 'remaining_today': 2}),
    );
    expect(items.items, isEmpty);
    expect(items.remainingToday, 2);
  });

  test('generated spelling context survives the domain adapter and remains optional', () {
    final question = {
      'item_id': 'spelling:synthetic',
      'kind': 'spelling',
      'title': 'Which spelling?',
      'created_at': '2026-10-14T12:00:00Z',
      'quote': 'UL',
      'spelling': {
        'term_id': 'synthetic',
        'options': ['UL', 'URL'],
        'allow_custom': true,
        'context': {
          'conversation_title': 'Launch planning',
          'conversation_date': '2026-10-14T12:00:00Z',
          'main_index': 0,
          'quote_start': 6,
          'quote_end': 8,
          'segments': [
            {'text': '🙂 请发 UL 给我', 'speaker_label': 'You', 'is_user': true}
          ],
        },
      },
    };
    for (final withContext in [true, false]) {
      final payload = Map<String, dynamic>.from(question);
      final spelling = Map<String, dynamic>.from(question['spelling']! as Map);
      if (!withContext) spelling.remove('context');
      payload['spelling'] = spelling;
      final result = ReviewItemsResponse.fromGeneratedV2(wire.GeneratedReviewItemsResponseV2.fromJson({
        'items': [payload],
        'remaining_today': 3,
      }));
      expect(result.items.single.spelling!.options, ['UL', 'URL']);
      final context = result.items.single.spelling!.context;
      if (withContext) {
        expect(context!.conversationTitle, 'Launch planning');
        expect(context.main.text.substring(context.quoteStart!, context.quoteEnd!), 'UL');
        expect(context.main.isUser, isTrue);
        expect(context.conversationDate!.toUtc(), DateTime.utc(2026, 10, 14, 12));
      } else {
        expect(context, isNull);
      }
    }
  });
}
