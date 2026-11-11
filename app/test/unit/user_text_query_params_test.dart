import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';

void main() {
  Map<String, String> sent(String path) => Uri.parse('https://api.test/$path').queryParameters;

  const texts = ['Q&A with Bob', 'Meeting #3', 'C++ review', '100% done', 'Plan: a=b?'];

  test('a conversation title reaches the server unchanged', () {
    for (final title in texts) {
      final query = sent(conversationTitlePath('conversation-1', title));
      expect(query, {'title': title});
    }
  });

  test('a thumbs down comment reaches the server unchanged', () {
    for (final comment in texts) {
      final query = sent(chatMessageRatingPath('message-1', -1, reason: 'incorrect_or_hallucination: $comment'));
      expect(query, {'message_id': 'message-1', 'value': '-1', 'reason': 'incorrect_or_hallucination: $comment'});
    }
  });

  test('a rating without a reason sends no reason', () {
    expect(sent(chatMessageRatingPath('message-1', 1)), {'message_id': 'message-1', 'value': '1'});
  });

  test('a summary rating reason reaches the server unchanged', () {
    for (final reason in texts) {
      final query = sent(conversationSummaryRatingPath('conversation-1', -1, reason: reason));
      expect(query, {'memory_id': 'conversation-1', 'value': '-1', 'reason': reason});
    }
  });

  test('a summary rating without a reason sends no reason', () {
    expect(sent(conversationSummaryRatingPath('conversation-1', 1)), {'memory_id': 'conversation-1', 'value': '1'});
  });
}
