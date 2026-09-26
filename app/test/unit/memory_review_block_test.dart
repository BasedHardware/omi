import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';

/// The `day_summary` message reaches mobile only as an FCM push, and FCM data
/// payloads are `Dict[str, str]`: `content_blocks` therefore arrives as JSON
/// text, not as a list.
Map<String, dynamic> _fcmDaySummaryData({Object? contentBlocks, String text = 'A busy day.'}) {
  return {
    'id': 'summary-message-1',
    'created_at': '2026-09-01T23:00:00Z',
    'text': text,
    'sender': 'ai',
    'type': 'day_summary',
    'notification_type': 'daily_summary',
    if (contentBlocks != null) 'content_blocks': contentBlocks,
  };
}

const _reviewBlock = {
  'type': 'memoryReviewCard',
  'id': 'summary-1:memories',
  'summaryId': 'summary-1',
  'date': '2026-09-01',
  'items': [
    {'memoryId': 'mem-1', 'content': 'Prefers async standups', 'category': 'work'},
    {'memoryId': 'mem-2', 'content': 'Runs on Tuesday mornings', 'category': 'lifestyle'},
  ],
};

void main() {
  test('decodes a memoryReviewCard delivered as FCM JSON text', () {
    final message = ServerMessage.fromJson(_fcmDaySummaryData(contentBlocks: jsonEncode([_reviewBlock])));

    final card = message.memoryReviewCard;
    expect(card, isNotNull);
    expect(card!.summaryId, 'summary-1');
    expect(card.date, '2026-09-01');
    expect(card.items.map((item) => item.memoryId), ['mem-1', 'mem-2']);
    expect(card.items.first.content, 'Prefers async standups');
    expect(card.items.first.categoryLabel, 'Work');
    // The push text is untouched by the block.
    expect(message.text, 'A busy day.');
  });

  test('decodes the same block when it arrives as a real list', () {
    final message = ServerMessage.fromJson(_fcmDaySummaryData(contentBlocks: [_reviewBlock]));

    expect(message.memoryReviewCard?.items.length, 2);
  });

  test('absent, empty, and malformed content_blocks degrade to no card', () {
    for (final payload in <Object?>[null, '', '   ', 'not json', '{"unclosed":', '"a string"', 12]) {
      final message = ServerMessage.fromJson(_fcmDaySummaryData(contentBlocks: payload));
      expect(message.contentBlocks, isEmpty, reason: 'payload: $payload');
      expect(message.memoryReviewCard, isNull, reason: 'payload: $payload');
      expect(message.text, 'A busy day.', reason: 'payload: $payload');
    }
  });

  test('a card with no usable items is not rendered as an empty card', () {
    final message = ServerMessage.fromJson(
      _fcmDaySummaryData(
        contentBlocks: jsonEncode([
          {
            'type': 'memoryReviewCard',
            'id': 'summary-2:memories',
            'summaryId': 'summary-2',
            'date': '2026-09-01',
            'items': [
              {'memoryId': '', 'content': 'no identity'},
              {'memoryId': 'mem-3', 'content': '   '},
            ],
          },
        ]),
      ),
    );

    expect(message.contentBlocks, hasLength(1));
    expect(message.memoryReviewCard, isNull);
  });

  test('caps the card at three rows', () {
    final message = ServerMessage.fromJson(
      _fcmDaySummaryData(
        contentBlocks: [
          {
            'type': 'memoryReviewCard',
            'items': List.generate(6, (i) => {'memoryId': 'mem-$i', 'content': 'fact $i'}),
          },
        ],
      ),
    );

    expect(message.memoryReviewCard?.items, hasLength(3));
  });

  test('exposes the one follow-up question a typed answer invites', () {
    final message = ServerMessage.fromJson({
      'id': 'message-2',
      'created_at': '2026-09-01T12:00:00Z',
      'text': 'You met Priya on Tuesday.',
      'sender': 'ai',
      'type': 'text',
      'content_blocks': [
        {'type': 'followUp', 'id': 'message-2:followup', 'text': 'Want the rest of what she said?'},
      ],
    });

    expect(message.followUpQuestion, 'Want the rest of what she said?');
    expect(message.text, 'You met Priya on Tuesday.');
    // Mobile renders the desktop chat-first blocks now rather than hiding the
    // messages that carry them, so `hideFromMobileChat` is gone. What this test
    // was protecting — the answer still shows — is now that the body is real
    // prose rather than fallback text the blocks would replace.
    expect(message.textIsStructuredFallback, isFalse);
  });

  test('a blank follow-up question is not a chip', () {
    final message = ServerMessage.fromJson({
      'id': 'message-3',
      'created_at': '2026-09-01T12:00:00Z',
      'text': 'Answer.',
      'sender': 'ai',
      'type': 'text',
      'content_blocks': [
        {'type': 'followUp', 'text': '   '},
      ],
    });

    expect(message.followUpQuestion, isNull);
  });

  test('neither natively rendered block invents fallback prose that repeats it', () {
    // MemoryReviewCard draws "Things I learned today" itself and
    // ChatFollowUpChip draws the question, so a prose copy would either say the
    // same words twice or — when the block is too malformed to render a card —
    // leave a heading standing over nothing.
    final reviewOnly = ServerMessage.fromJson(_fcmDaySummaryData(text: '', contentBlocks: [_reviewBlock]));
    expect(reviewOnly.text, '');
    expect(reviewOnly.memoryReviewCard, isNotNull);

    final malformedReviewOnly = ServerMessage.fromJson(
      _fcmDaySummaryData(
        text: '',
        contentBlocks: [
          {'type': 'memoryReviewCard', 'id': 'summary-9:memories', 'items': []},
        ],
      ),
    );
    expect(malformedReviewOnly.memoryReviewCard, isNull);
    expect(malformedReviewOnly.text, '');

    final followUpOnly = ServerMessage.fromJson({
      'id': 'message-4',
      'created_at': '2026-09-01T12:00:00Z',
      'text': '',
      'sender': 'ai',
      'type': 'text',
      'content_blocks': [
        {'type': 'followUp', 'text': 'Should I pull the rest?'},
      ],
    });
    expect(followUpOnly.text, '');
    expect(followUpOnly.followUpQuestion, 'Should I pull the rest?');
  });

  test('unknown and existing block types keep their previous fallback', () {
    final unknown = ServerMessage.fromJson({
      'id': 'message-5',
      'created_at': '2026-09-01T12:00:00Z',
      'text': '',
      'sender': 'ai',
      'type': 'text',
      'content_blocks': [
        {'type': 'somethingBrandNew', 'title': 'Title', 'summary': 'Summary'},
      ],
    });
    expect(unknown.text, 'Chat item - Title - Summary');
    expect(unknown.memoryReviewCard, isNull);
    expect(unknown.followUpQuestion, isNull);

    final conversation = ServerMessage.fromJson({
      'id': 'message-6',
      'created_at': '2026-09-01T12:00:00Z',
      'text': '',
      'sender': 'ai',
      'type': 'text',
      'content_blocks': [
        {'type': 'conversationLink', 'conversationId': 'c-1', 'summary': 'Weekly planning'},
      ],
    });
    expect(conversation.text, 'Meeting notes ready - Weekly planning');
  });
}
