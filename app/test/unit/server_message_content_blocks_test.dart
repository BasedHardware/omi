import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  Map<String, dynamic> messageJson({
    required String text,
    Object? contentBlocks,
    String? metadata,
  }) {
    return {
      'id': 'message-1',
      'created_at': '2026-08-18T12:00:00Z',
      'text': text,
      'sender': 'ai',
      'type': 'text',
      if (contentBlocks != null) 'content_blocks': contentBlocks,
      if (metadata != null) 'metadata': metadata,
    };
  }

  test(
    'uses first-class conversation block fallback instead of a blank bubble',
    () {
      final message = ServerMessage.fromJson(
        messageJson(
          text: '',
          contentBlocks: [
            {
              'type': 'conversationLink',
              'conversationId': 'conversation-1',
              'summary': 'Founders explore AI memory',
            },
          ],
        ),
      );

      expect(message.text, 'Meeting notes ready - Founders explore AI memory');
      expect(message.contentBlocks.single['conversationId'], 'conversation-1');
    },
  );

  test('keeps legacy metadata blocks readable during wire migration', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: '',
        metadata:
            '{"content_blocks":[{"type":"conversationLink","conversationId":"conversation-legacy","summary":"Legacy weekly planning"}]}',
      ),
    );

    expect(message.text, 'Meeting notes ready - Legacy weekly planning');
    expect(
      message.contentBlocks.single['conversationId'],
      'conversation-legacy',
    );
  });

  test(
    'preserves canonical backend fallback text when the client knows the block',
    () {
      final message = ServerMessage.fromJson(
        messageJson(
          text: 'Meeting notes ready - Canonical title',
          contentBlocks: [
            {
              'type': 'conversationLink',
              'summary': 'Different local rendering',
            },
          ],
        ),
      );

      expect(message.text, 'Meeting notes ready - Canonical title');
      expect(message.hideFromMobileChat, isFalse);
    },
  );

  test(
    'hides desktop goal and task chrome fallbacks from the mobile timeline',
    () {
      final message = ServerMessage.fromJson(
        messageJson(
          text: '',
          contentBlocks: [
            {
              'type': 'goalLink',
              'goalId': 'goal-1',
              'summary': 'Make Omi Great Again',
            },
            {'type': 'taskCard', 'taskId': 'task-1'},
            {'type': 'taskCard', 'taskId': 'task-2'},
            {'type': 'taskCard', 'taskId': 'task-3'},
          ],
        ),
      );

      expect(message.text, 'Goal - Make Omi Great Again\nTask\nTask\nTask');
      expect(message.hideFromMobileChat, isTrue);
      expect(ServerMessage.visibleOnMobile([message]), isEmpty);
    },
  );

  test('hides stored one-line goal/task fallback dumps', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: 'Goal - Make Omi Great Again Task Task Task',
        contentBlocks: [
          {'type': 'goalLink', 'summary': 'Make Omi Great Again'},
          {'type': 'taskCard', 'taskId': 'task-1'},
          {'type': 'taskCard', 'taskId': 'task-2'},
          {'type': 'taskCard', 'taskId': 'task-3'},
        ],
      ),
    );

    expect(message.hideFromMobileChat, isTrue);
  });

  test('hides question cards that have no other content', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: 'What should we focus on?',
        contentBlocks: [
          {
            'type': 'questionCard',
            'questionId': 'question-1',
            'text': 'What should we focus on?',
            'subject': {'kind': 'goal', 'id': 'goal-1'},
            'options': [
              {'optionId': 'a', 'label': 'Ship', 'preparedAnswer': 'Ship'},
            ],
          },
        ],
      ),
    );

    expect(message.hideFromMobileChat, isTrue);
  });

  test('keeps meeting-note cards and mixed useful blocks', () {
    final meeting = ServerMessage.fromJson(
      messageJson(
        text: '',
        contentBlocks: [
          {
            'type': 'conversationLink',
            'conversationId': 'conversation-1',
            'summary': 'Founders explore AI memory',
          },
        ],
      ),
    );
    final mixed = ServerMessage.fromJson(
      messageJson(
        text: 'I started tracking this.',
        contentBlocks: [
          {'type': 'text', 'text': 'I started tracking this.'},
          {'type': 'goalLink', 'summary': 'Make Omi Great Again'},
        ],
      ),
    );
    final prose = ServerMessage.fromJson(
      messageJson(
        text: 'Here is a real reply about the weather.',
        contentBlocks: [
          {'type': 'goalLink', 'summary': 'Make Omi Great Again'},
        ],
      ),
    );

    expect(meeting.hideFromMobileChat, isFalse);
    expect(mixed.hideFromMobileChat, isFalse);
    expect(prose.hideFromMobileChat, isFalse);
    expect(ServerMessage.visibleOnMobile([meeting, mixed, prose]), [
      meeting,
      mixed,
      prose,
    ]);
  });
}
