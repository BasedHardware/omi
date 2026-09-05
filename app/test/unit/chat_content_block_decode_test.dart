import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/chat_content_block.dart';

void main() {
  ChatContentBlock? decode(Map<String, dynamic> raw) => ChatContentBlock.tryDecode(raw);

  group('camelCase wire (desktop/agent dialect)', () {
    test('decodes every interactable block type', () {
      final blocks = ChatContentBlock.decodeList([
        {'type': 'taskCard', 'id': 'b1', 'taskId': 'task-1'},
        {'type': 'goalLink', 'id': 'b2', 'goalId': 'goal-1', 'summary': 'Ship the release'},
        {
          'type': 'captureLink',
          'id': 'b3',
          'conversationId': 'conversation-1',
          'summary': 'Standup',
          'momentTimestampMs': 1234,
        },
        {
          'type': 'conversationLink',
          'id': 'b4',
          'conversationId': 'conversation-2',
          'summary': 'Weekly planning',
          'recommendedActionItems': [
            {'description': 'Draft the plan', 'taskId': 'task-9'},
            {'description': '   '},
          ],
        },
        {'type': 'memoryLink', 'id': 'b5', 'memoryId': 'memory-1', 'summary': 'Prefers dark mode'},
        {
          'type': 'questionCard',
          'id': 'b6',
          'questionId': 'question-1',
          'text': 'What next?',
          'subject': {'kind': 'goal', 'id': 'goal-1'},
          'options': [
            {'optionId': 'ship', 'label': 'Ship it', 'preparedAnswer': 'Ship it today'},
            {'optionId': 'later', 'label': 'Later', 'preparedAnswer': 'Ask me later', 'defer': true},
          ],
          'selectedOptionId': 'ship',
        },
      ]);

      expect(blocks, hasLength(6));
      expect((blocks[0] as TaskCardContentBlock).taskId, 'task-1');
      expect((blocks[1] as GoalLinkContentBlock).goalId, 'goal-1');

      final capture = blocks[2] as CaptureLinkContentBlock;
      expect(capture.conversationId, 'conversation-1');
      expect(capture.momentTimestampMs, 1234);

      final conversation = blocks[3] as ConversationLinkContentBlock;
      expect(conversation.recommendedActionItems, hasLength(1));
      expect(conversation.recommendedActionItems.single.taskId, 'task-9');

      expect((blocks[4] as MemoryLinkContentBlock).memoryId, 'memory-1');

      final question = blocks[5] as QuestionCardContentBlock;
      expect(question.subjectKind, 'goal');
      expect(question.selectedOptionId, 'ship');
      expect(question.options, hasLength(2));
      expect(question.options.last.isDeferral, isTrue);
      expect(question.options.last.preparedAnswer, 'Ask me later');
    });

    test('decodes the non-interactable types without dropping them', () {
      expect(decode({'type': 'text', 'id': 'b1', 'text': 'hi'}), isA<TextContentBlock>());
      expect(decode({'type': 'thinking', 'id': 'b2', 'text': 'hmm'}), isA<ThinkingContentBlock>());
      expect(
        decode({'type': 'toolCall', 'id': 'b3', 'name': 'search', 'status': 'running'}),
        isA<ToolCallContentBlock>(),
      );
      expect(
        decode({'type': 'discoveryCard', 'id': 'b4', 'title': 'T', 'summary': 'S', 'fullText': 'F'}),
        isA<DiscoveryCardContentBlock>(),
      );
      expect(
        decode({'type': 'citation', 'id': 'b5', 'ordinal': 1, 'kind': 'conversation', 'sourceId': 'c1'}),
        isA<CitationContentBlock>(),
      );
      expect(
        decode({'type': 'agentSpawn', 'id': 'b6', 'sessionId': 's1', 'runId': 'r1'}),
        isA<AgentSpawnContentBlock>(),
      );
      expect(decode({'type': 'agentCompletion', 'id': 'b7'}), isA<AgentCompletionContentBlock>());
    });
  });

  group('snake_case wire (validated chat-first specs)', () {
    test('reads every renamed field', () {
      final blocks = ChatContentBlock.decodeList([
        {'type': 'task_card', 'id': 'b1', 'task_id': 'task-1'},
        {'type': 'goal_link', 'id': 'b2', 'goal_id': 'goal-1', 'summary': 'Ship'},
        {
          'type': 'capture_link',
          'id': 'b3',
          'conversation_id': 'conversation-1',
          'summary': 'Standup',
          'moment_timestamp_ms': 99,
        },
        {
          'type': 'conversation_link',
          'id': 'b4',
          'conversation_id': 'conversation-2',
          'summary': 'Planning',
          'recommended_action_items': [
            {'description': 'Draft', 'task_id': 'task-9'},
          ],
        },
        {'type': 'memory_link', 'id': 'b5', 'memory_id': 'memory-1', 'summary': 'Dark mode'},
        {
          'type': 'question_card',
          'id': 'b6',
          'question_id': 'question-1',
          'text': 'What next?',
          'subject': {'kind': 'task', 'id': 'task-1'},
          'options': [
            {'option_id': 'ship', 'label': 'Ship it', 'prepared_answer': 'Ship it today'},
          ],
          'selected_option_id': 'ship',
        },
      ]);

      expect(blocks, hasLength(6));
      expect((blocks[0] as TaskCardContentBlock).taskId, 'task-1');
      expect((blocks[1] as GoalLinkContentBlock).goalId, 'goal-1');
      expect((blocks[2] as CaptureLinkContentBlock).momentTimestampMs, 99);
      expect((blocks[3] as ConversationLinkContentBlock).recommendedActionItems.single.taskId, 'task-9');
      expect((blocks[4] as MemoryLinkContentBlock).memoryId, 'memory-1');

      final question = blocks[5] as QuestionCardContentBlock;
      expect(question.subjectId, 'task-1');
      expect(question.selectedOptionId, 'ship');
      expect(question.options.single.preparedAnswer, 'Ship it today');
    });
  });

  group('required fields', () {
    test('drops blocks that the macOS codec would also drop', () {
      expect(decode({'type': 'taskCard', 'id': 'b1'}), isNull);
      expect(decode({'type': 'taskCard', 'taskId': 'task-1'}), isNull, reason: 'missing id');
      expect(decode({'id': 'b1', 'taskId': 'task-1'}), isNull, reason: 'missing type');
      expect(decode({'type': 'goalLink', 'id': 'b1', 'goalId': 'goal-1'}), isNull, reason: 'missing summary');
      expect(decode({'type': 'goalLink', 'id': 'b1', 'summary': 'Ship'}), isNull, reason: 'missing goalId');
      expect(decode({'type': 'memoryLink', 'id': 'b1', 'summary': 'Ship'}), isNull);
      expect(decode({'type': 'conversationLink', 'id': 'b1', 'summary': 'Ship'}), isNull);
      expect(decode({'type': 'toolCall', 'id': 'b1', 'status': 'running'}), isNull, reason: 'missing name');
      expect(
        decode({
          'type': 'questionCard',
          'id': 'b1',
          'questionId': 'q1',
          'text': 'What next?',
          'subject': {'kind': 'goal', 'id': 'goal-1'},
          'options': <Map<String, dynamic>>[],
        }),
        isNull,
        reason: 'no usable options',
      );
      expect(
        decode({
          'type': 'questionCard',
          'id': 'b1',
          'questionId': 'q1',
          'text': 'What next?',
          'options': [
            {'optionId': 'a', 'label': 'A', 'preparedAnswer': 'A'},
          ],
        }),
        isNull,
        reason: 'missing subject',
      );
    });

    test('drops malformed entries but keeps the rest of the list', () {
      final blocks = ChatContentBlock.decodeList([
        {'type': 'taskCard', 'id': 'b1'},
        {'type': 'taskCard', 'id': 'b2', 'taskId': 'task-2'},
      ]);
      expect(blocks, hasLength(1));
      expect((blocks.single as TaskCardContentBlock).taskId, 'task-2');
    });

    test('falls back to the option label when no prepared answer is sent', () {
      final question = decode({
        'type': 'questionCard',
        'id': 'b1',
        'questionId': 'q1',
        'text': 'What next?',
        'subject': {'kind': 'cold_start', 'id': 'seq-1'},
        'options': [
          {'optionId': 'a', 'label': 'Ship it'},
        ],
      })! as QuestionCardContentBlock;
      expect(question.options.single.preparedAnswer, 'Ship it');
    });
  });

  test('an unknown type becomes an unknown block instead of being dropped', () {
    final block = decode({'type': 'somethingNew', 'id': 'b1', 'title': 'Future'});
    expect(block, isA<UnknownContentBlock>());
    expect(block!.type, 'somethingNew');
    expect((block as UnknownContentBlock).raw['title'], 'Future');
  });
}
