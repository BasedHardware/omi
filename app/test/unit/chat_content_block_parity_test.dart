import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/content_blocks/chat_content_block_list.dart';

/// The desktop transcript draws nine block kinds as their own control. A kind
/// the phone cannot draw degrades to one synthesized line — "Discovery - <title>",
/// "Agent started - <title>" — so the same turn reads as a card on one client
/// and a stray label on the other. These pin the parity in both directions.
void main() {
  ServerMessage messageWith(List<Map<String, dynamic>> blocks, {String text = ''}) {
    return ServerMessage.fromJson({
      'id': 'message-1',
      'created_at': '2026-09-02T12:00:00Z',
      'text': text,
      'sender': 'ai',
      'type': 'text',
      'content_blocks': blocks,
    });
  }

  /// Every kind the desktop renders as a control, with the payload the runtime
  /// sends for it.
  const desktopRenderedBlocks = <String, Map<String, dynamic>>{
    'taskCard': {'id': 'b-task', 'type': 'taskCard', 'taskId': 'task-1'},
    'goalLink': {'id': 'b-goal', 'type': 'goalLink', 'goalId': 'goal-1', 'summary': 'Make Omi Great Again'},
    'captureLink': {'id': 'b-capture', 'type': 'captureLink', 'conversationId': 'conversation-1', 'summary': 'Standup'},
    'conversationLink': {
      'id': 'b-conversation',
      'type': 'conversationLink',
      'conversationId': 'conversation-2',
      'summary': 'Founders explore AI memory',
    },
    'memoryLink': {'id': 'b-memory', 'type': 'memoryLink', 'memoryId': 'memory-1', 'summary': 'Prefers dark mode'},
    'questionCard': {
      'id': 'b-question',
      'type': 'questionCard',
      'questionId': 'question-1',
      'text': 'Which one first?',
      'subject': {'kind': 'task', 'id': 'task-1'},
      'options': [
        {'optionId': 'option-1', 'label': 'The hackathon'},
      ],
    },
    'discoveryCard': {
      'id': 'b-discovery',
      'type': 'discoveryCard',
      'title': 'You ship on Fridays',
      'summary': 'Nine of your last ten releases landed on a Friday.',
      'fullText': 'Nine of your last ten releases landed on a Friday afternoon.',
    },
    'agentSpawn': {
      'id': 'b-spawn',
      'type': 'agentSpawn',
      'sessionId': 'session-1',
      'runId': 'run-1',
      'title': 'Fix the scroll',
      'objective': 'Keep the transcript pinned while streaming',
    },
    'agentCompletion': {
      'id': 'b-completion',
      'type': 'agentCompletion',
      'sessionId': 'session-1',
      'runId': 'run-1',
      'title': 'Fix the scroll',
      'output': 'Reply no longer collapses when it settles',
      'status': 'completed',
    },
  };

  test('every block the desktop draws as a control has a mobile component', () {
    for (final entry in desktopRenderedBlocks.entries) {
      expect(
        ChatContentBlockList.hasRenderableBlocks(messageWith([entry.value])),
        isTrue,
        reason: '${entry.key} renders as a card on desktop and must not degrade to a label here',
      );
    }
  });

  test('a body that is only the blocks own projection is left to the components', () {
    final message = messageWith([
      desktopRenderedBlocks['goalLink']!,
      desktopRenderedBlocks['taskCard']!,
      desktopRenderedBlocks['taskCard']!,
    ]);

    // What the runtime synthesizes for an unaware client, verbatim.
    expect(message.text, 'Goal - Make Omi Great Again\nTask\nTask');
    expect(message.textIsStructuredFallback, isTrue);
  });

  test('prose the model actually wrote survives alongside its cards', () {
    final message = messageWith(
      [desktopRenderedBlocks['taskCard']!],
      text: 'Start with the hackathon — the deadline is closest.',
    );

    expect(message.textIsStructuredFallback, isFalse);
  });

  test('blocks with no component still leave the body alone', () {
    final message = messageWith([
      {'id': 'b-thinking', 'type': 'thinking', 'text': 'weighing the options'},
    ], text: 'Here is what I would do.');

    expect(ChatContentBlockList.hasRenderableBlocks(message), isFalse);
    expect(message.textIsStructuredFallback, isFalse);
  });
}
