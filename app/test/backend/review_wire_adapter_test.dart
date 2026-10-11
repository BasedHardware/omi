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
}
