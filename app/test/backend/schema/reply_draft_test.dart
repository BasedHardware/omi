import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/reply_draft.dart';

void main() {
  test('reply draft response requires a non-empty draft', () {
    expect(
      () => ReplyDraftResponse.fromJson({
        'alternatives': [],
        'needs_review': true,
        'safety_notes': [],
        'used_context': {'memories_used': 0, 'recent_chat_messages_used': 0},
      }),
      throwsFormatException,
    );

    expect(
      () => ReplyDraftResponse.fromJson({
        'draft': '   ',
        'alternatives': [],
        'needs_review': true,
        'safety_notes': [],
        'used_context': {'memories_used': 0, 'recent_chat_messages_used': 0},
      }),
      throwsFormatException,
    );

    final response = ReplyDraftResponse.fromJson({
      'draft': '  sounds good  ',
      'alternatives': [],
      'needs_review': true,
      'safety_notes': [],
      'used_context': {'memories_used': 0, 'recent_chat_messages_used': 0},
    });

    expect(response.draft, 'sounds good');
  });
}
