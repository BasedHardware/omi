import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/chat_session.dart';

/// `ChatSessionSummary` decodes through the generated `ChatSessionResponse` wire type, while
/// keeping the tolerance the hand-written decoder had for rows that omit contract fields.
void main() {
  test('a full contract row decodes, with the time in the local zone', () {
    final s = ChatSessionSummary.fromJson({
      'id': 's1',
      'title': 'Roadmap',
      'preview': 'Ship Friday',
      'created_at': '2026-09-28T01:00:00Z',
      'updated_at': '2026-09-29T01:00:00Z',
      'app_id': null,
      'plugin_id': null,
      'message_count': 4,
      'starred': true,
    });
    expect(s.id, 's1');
    expect(s.title, 'Roadmap');
    expect(s.preview, 'Ship Friday');
    expect(s.messageCount, 4);
    expect(s.updatedAt.isUtc, isFalse, reason: 'shown in the reader zone');
    expect(s.updatedAt.isAtSameMomentAs(DateTime.utc(2026, 9, 29, 1)), isTrue);
  });

  test('updated_at wins over created_at when both are present', () {
    final s = ChatSessionSummary.fromJson(
        {'id': 's', 'created_at': '2026-09-28T01:00:00Z', 'updated_at': '2026-09-29T01:00:00Z'});
    expect(s.updatedAt.isAtSameMomentAs(DateTime.utc(2026, 9, 29, 1)), isTrue);
  });

  test('a row without updated_at falls back to created_at (the create route answer)', () {
    final s = ChatSessionSummary.fromJson({'id': 'new', 'created_at': '2026-09-29T01:00:00Z'});
    expect(s.updatedAt.isAtSameMomentAs(DateTime.utc(2026, 9, 29, 1)), isTrue);
    expect(s.updatedAt.isUtc, isFalse);
  });

  test('missing or mistyped optional content reads as empty, zero and unstarred', () {
    final s = ChatSessionSummary.fromJson({
      'id': 's',
      'updated_at': '2026-09-29T01:00:00Z',
      'title': 7,
      'preview': ['x'],
      'message_count': 3.0,
      'starred': 'yes',
      'app_id': 12,
    });
    expect(s.title, '');
    expect(s.preview, '');
    expect(s.messageCount, 3);
    expect(s.hasContent, isTrue);
  });

  test('a row with no count reads as 0 messages', () {
    final s = ChatSessionSummary.fromJson({'id': 's', 'title': 'Thread', 'updated_at': '2026-09-29T01:00:00Z'});
    expect(s.messageCount, 0);
    expect(s.title, 'Thread');
  });

  for (final (name, row) in [
    ('no id', {'updated_at': '2026-09-29T01:00:00Z'}),
    ('an empty id', {'id': '', 'updated_at': '2026-09-29T01:00:00Z'}),
    ('no timestamp', {'id': 's'}),
    (
      'an unparseable updated_at (no fallback past a present value)',
      {'id': 's', 'updated_at': 'yesterday', 'created_at': '2026-09-29T01:00:00Z'}
    ),
  ]) {
    test('a row with $name is rejected', () {
      expect(() => ChatSessionSummary.fromJson(Map<String, dynamic>.from(row)), throwsFormatException);
    });
  }
}
