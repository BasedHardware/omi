import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

TranscriptSegment _segment(String text) {
  return TranscriptSegment(
    id: 'seg',
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0,
    end: 1,
    translations: [],
  );
}

ServerConversation _conversation({
  String title = '',
  ConversationStatus status = ConversationStatus.completed,
  List<TranscriptSegment> segments = const [],
  bool discarded = false,
  bool isLocked = false,
}) {
  return ServerConversation(
    id: 'c1',
    createdAt: DateTime.utc(2020),
    structured: Structured(title, ''),
    status: status,
    transcriptSegments: segments,
    discarded: discarded,
    isLocked: isLocked,
  );
}

void main() {
  group('ServerConversation.isFailedTitleRecoverable', () {
    test('completed + empty title + 5-word segment is recoverable', () {
      final conv = _conversation(
        segments: [_segment('one two three four five')],
      );
      expect(conv.hasSubstantialTranscriptSegment, isTrue);
      expect(conv.isFailedTitleRecoverable, isTrue);
    });

    test('completed + empty title + 4-word segment stays quiet', () {
      final conv = _conversation(
        segments: [_segment('one two three four')],
      );
      expect(conv.hasSubstantialTranscriptSegment, isFalse);
      expect(conv.isFailedTitleRecoverable, isFalse);
    });

    test('a later substantial segment is enough', () {
      final conv = _conversation(
        segments: [
          _segment('um'),
          _segment('ok'),
          _segment('this is the substantive part of the conversation'),
        ],
      );
      expect(conv.isFailedTitleRecoverable, isTrue);
    });

    test('no transcript stays quiet', () {
      expect(_conversation().isFailedTitleRecoverable, isFalse);
    });

    test('a titled conversation is not recoverable', () {
      final conv = _conversation(
        title: 'Morning standup',
        segments: [_segment('one two three four five six')],
      );
      expect(conv.isFailedTitleRecoverable, isFalse);
    });

    test('discarded rows stay quiet even with a substantial transcript', () {
      final conv = _conversation(
        discarded: true,
        segments: [_segment('one two three four five six')],
      );
      expect(conv.isFailedTitleRecoverable, isFalse);
    });

    test('locked rows stay quiet', () {
      final conv = _conversation(
        isLocked: true,
        segments: [_segment('one two three four five six')],
      );
      expect(conv.isFailedTitleRecoverable, isFalse);
    });

    test('processing rows are not the failed-title state', () {
      final conv = _conversation(
        status: ConversationStatus.processing,
        segments: [_segment('one two three four five six')],
      );
      expect(conv.isFailedTitleRecoverable, isFalse);
    });

    test('whitespace-only titles count as empty', () {
      final conv = _conversation(
        title: '   ',
        segments: [_segment('one two three four five')],
      );
      expect(conv.isFailedTitleRecoverable, isTrue);
    });
  });

  group('TranscriptSegment.wordCount', () {
    test('splits on whitespace and ignores empties', () {
      expect(_segment('  one   two three  ').wordCount, 3);
      expect(_segment('').wordCount, 0);
      expect(_segment('five').wordCount, 1);
    });
  });
}
