import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
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
      expect(message.textIsStructuredFallback, isFalse);
    },
  );

  test(
    'keeps desktop goal and task chrome on the mobile timeline',
    () {
      final message = ServerMessage.fromJson(
        messageJson(
          text: '',
          contentBlocks: [
            {
              'type': 'goalLink',
              'id': 'block-goal',
              'goalId': 'goal-1',
              'summary': 'Make Omi Great Again',
            },
            {'type': 'taskCard', 'id': 'block-task-1', 'taskId': 'task-1'},
            {'type': 'taskCard', 'id': 'block-task-2', 'taskId': 'task-2'},
            {'type': 'taskCard', 'id': 'block-task-3', 'taskId': 'task-3'},
          ],
        ),
      );

      expect(message.text, 'Goal - Make Omi Great Again\nTask\nTask\nTask');
      // The body is nothing but the synthesized fallback, so the interactive
      // components replace it instead of repeating it.
      expect(message.textIsStructuredFallback, isTrue);
      expect(message.typedContentBlocks, hasLength(4));
      expect(message.typedContentBlocks.first, isA<GoalLinkContentBlock>());
      expect(message.typedContentBlocks.last, isA<TaskCardContentBlock>());
    },
  );

  test('keeps stored one-line goal/task fallback dumps renderable', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: 'Goal - Make Omi Great Again Task Task Task',
        contentBlocks: [
          {'type': 'goalLink', 'id': 'block-goal', 'goalId': 'goal-1', 'summary': 'Make Omi Great Again'},
          {'type': 'taskCard', 'id': 'block-task-1', 'taskId': 'task-1'},
          {'type': 'taskCard', 'id': 'block-task-2', 'taskId': 'task-2'},
          {'type': 'taskCard', 'id': 'block-task-3', 'taskId': 'task-3'},
        ],
      ),
    );

    expect(message.textIsStructuredFallback, isTrue);
    expect(message.typedContentBlocks, hasLength(4));
  });

  test('keeps question cards that have no other content', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: 'What should we focus on?',
        contentBlocks: [
          {
            'type': 'questionCard',
            'id': 'block-question',
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

    expect(message.textIsStructuredFallback, isTrue);
    expect(message.typedContentBlocks.single, isA<QuestionCardContentBlock>());
  });

  test('keeps meeting-note cards and mixed useful blocks', () {
    final meeting = ServerMessage.fromJson(
      messageJson(
        text: '',
        contentBlocks: [
          {
            'type': 'conversationLink',
            'id': 'block-conversation',
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
          {'type': 'text', 'id': 'block-text', 'text': 'I started tracking this.'},
          {'type': 'goalLink', 'id': 'block-goal', 'goalId': 'goal-1', 'summary': 'Make Omi Great Again'},
        ],
      ),
    );
    final prose = ServerMessage.fromJson(
      messageJson(
        text: 'Here is a real reply about the weather.',
        contentBlocks: [
          {'type': 'goalLink', 'id': 'block-goal', 'goalId': 'goal-1', 'summary': 'Make Omi Great Again'},
        ],
      ),
    );

    expect(meeting.typedContentBlocks.single, isA<ConversationLinkContentBlock>());
    expect(mixed.typedContentBlocks, hasLength(2));
    expect(prose.textIsStructuredFallback, isFalse);
  });

  test('decodes optional evidence envelope without changing the answer text', () {
    final json = messageJson(text: 'The answer stays readable.');
    json['evidence'] = {
      'schema_version': 1,
      'request_id': 'request-1',
      'references': [
        {
          'id': 'summary-1',
          'kind': 'conversation_summary',
          'state': 'available',
          'conversation_id': 'conversation-1',
          'title': 'Weekly summary',
        },
        {
          'id': 'frame-1',
          'kind': 'keyframe',
          'state': 'pruned',
          'frame_id': 'frame-1',
        },
      ],
    };

    final message = ServerMessage.fromJson(json);

    expect(message.text, 'The answer stays readable.');
    expect(message.evidenceEnvelope?.requestId, 'request-1');
    expect(message.evidenceEnvelope?.references, hasLength(2));
    expect(message.evidenceEnvelope?.references.last.canOpen, isFalse);
    expect(message.toJson()['evidence'], isA<Map<String, dynamic>>());
  });

  test(
    'keeps text readable for loading and offline frame requests',
    () {
      for (final state in ['loading', 'offline']) {
        final json = messageJson(text: 'The answer remains available.');
        json['evidence'] = {
          'schema_version': 1,
          'request_id': 'request-$state',
          'references': [
            {
              'id': 'request-$state',
              'kind': 'request',
              'state': state,
              'request_id': 'request-$state',
            },
          ],
        };

        expect(() => ServerMessage.fromJson(json), returnsNormally);
        final message = ServerMessage.fromJson(json);

        expect(message.text, 'The answer remains available.');
        expect(message.evidenceEnvelope?.references.single.kind.wireValue, 'request');
        expect(message.evidenceEnvelope?.references.single.state.wireValue, state);
        expect(message.evidenceEnvelope?.references.single.canOpen, isFalse);
      }
    },
  );

  test('ignores malformed or future evidence while preserving legacy text', () {
    final malformed = messageJson(text: 'Legacy answer');
    malformed['evidence'] = {'schema_version': 1, 'references': 'not-a-list'};
    final future = messageJson(text: 'Future answer');
    future['evidence'] = {
      'schema_version': 99,
      'references': [
        {
          'id': 'future-1',
          'kind': 'conversation_summary',
          'state': 'available',
          'conversation_id': 'conversation-1',
        },
      ],
    };

    final malformedMessage = ServerMessage.fromJson(malformed);
    final futureMessage = ServerMessage.fromJson(future);

    expect(malformedMessage.text, 'Legacy answer');
    expect(malformedMessage.evidenceEnvelope?.isEmpty, isTrue);
    expect(futureMessage.text, 'Future answer');
    expect(futureMessage.evidenceEnvelope?.references.single.canOpen, isFalse);
  });
}
