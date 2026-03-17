import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

/// Creates a minimal ServerConversation for testing getTag().
ServerConversation _makeConversation({
  String category = 'other',
  bool discarded = false,
  ConversationSource? source,
}) {
  return ServerConversation(
    id: 'test-id',
    createdAt: DateTime.now(),
    structured: Structured('Test Title', 'Test Overview', category: category),
    discarded: discarded,
    source: source,
  );
}

void main() {
  group('ServerConversation.getTag()', () {
    test('returns capitalized category for normal conversations', () {
      final conv = _makeConversation(category: 'personal');
      expect(conv.getTag(), 'Personal');
    });

    test('returns capitalized multi-word category', () {
      final conv = _makeConversation(category: 'health & wellness');
      expect(conv.getTag(), 'Health & wellness');
    });

    test('returns "Other" for empty category string — the crash fix', () {
      // This is the exact scenario that caused RangeError before the fix.
      // structured.category = '' → substring(0, 1) throws RangeError
      final conv = _makeConversation(category: '');
      expect(conv.getTag(), 'Other');
    });

    test('empty category does not throw RangeError', () {
      final conv = _makeConversation(category: '');
      // Before the fix, this would throw:
      // RangeError (end): Invalid value: Not in inclusive range 0..0: 1
      expect(() => conv.getTag(), returnsNormally);
    });

    test('returns "Discarded" for discarded conversations', () {
      final conv = _makeConversation(discarded: true);
      expect(conv.getTag(), 'Discarded');
    });

    test('returns "Screenpipe" for screenpipe source', () {
      final conv = _makeConversation(source: ConversationSource.screenpipe);
      expect(conv.getTag(), 'Screenpipe');
    });

    test('returns "OmiGlass" for openglass source', () {
      final conv = _makeConversation(source: ConversationSource.openglass);
      expect(conv.getTag(), 'OmiGlass');
    });

    test('returns "SD Card" for sdcard source', () {
      final conv = _makeConversation(source: ConversationSource.sdcard);
      expect(conv.getTag(), 'SD Card');
    });

    test('source takes precedence over category', () {
      final conv = _makeConversation(source: ConversationSource.screenpipe, category: 'personal');
      expect(conv.getTag(), 'Screenpipe');
    });

    test('discarded takes precedence over empty category', () {
      final conv = _makeConversation(discarded: true, category: '');
      expect(conv.getTag(), 'Discarded');
    });

    test('single character category works', () {
      final conv = _makeConversation(category: 'a');
      expect(conv.getTag(), 'A');
    });
  });
}
