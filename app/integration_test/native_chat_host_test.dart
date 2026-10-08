import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/message_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// The chat's real provider over a transcript that is already loaded. Only the network edges are
/// replaced: no history or chat-app read, and the rating request (which the shared fixture backend
/// does not route) answers success, after which the rating is recorded as the provider does.
class _HostMessages extends MessageProvider {
  final rated = <int>[];

  @override
  Future<void> fetchChatApps() async {}

  @override
  Future<void> refreshMessages({bool dropdownSelected = false}) async {}

  @override
  Future<bool> setMessageNps(ServerMessage message, int value, {String? reason}) async {
    rated.add(value);
    message.askForNps = false;
    message.rating = value == 0 ? null : value;
    notifyListeners();
    return true;
  }
}

ServerMessage _message(String id, String sender, String text, {List<Map<String, dynamic>> blocks = const []}) =>
    ServerMessage.fromJson({
      'id': id,
      'created_at': '2026-10-01T09:00:00Z',
      'text': text,
      'sender': sender,
      'type': 'text',
      'content_blocks': blocks,
    });

void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('chat replies render their rich body, actions and task cards inline', (tester) async {
      // The fixture principal, local API base and harness platform services: nothing reaches the network.
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final messages = _HostMessages()
        ..messages = [
          _message('host-user-1', 'human', 'What should I focus on this week?'),
          _message('host-ai-1', 'ai',
              '## This week\n\n1. **Ship** the launch email\n2. Review the [plan](https://omi.me)\n\n> Keep Friday free.'),
          _message('host-ai-2', 'ai', '', blocks: [
            {'id': 'host-block', 'type': 'taskCard', 'taskId': 'host-task-1'},
          ]),
        ];
      final updates = <(String, bool?)>[];
      final tasks = ActionItemsProvider(
        getActionItems: ({
          limit = 100,
          offset = 0,
          completed,
          conversationId,
          startDate,
          endDate,
          dueStartDate,
          dueEndDate,
        }) async =>
            const ActionItemsResponse(actionItems: [
          ActionItemWithMetadata(id: 'host-task-1', description: 'Send the launch email', completed: false),
        ]),
        updateActionItemRequest: (id, {description, completed, dueAt}) async {
          updates.add((id, completed));
          return ActionItemWithMetadata(id: id, description: 'Send the launch email', completed: completed ?? false);
        },
      );
      await tester.pumpWidget(nativeHostApp(const ChatPage(), providers: [
        ChangeNotifierProvider<MessageProvider>.value(value: messages),
        ChangeNotifierProvider<ActionItemsProvider>.value(value: tasks),
      ]));
      await checkNativeHost(tester, 'native-chat-structured-messages-transcript-dark');

      final body = nativeProjectedRow(tester, 'chat_message_host-ai-1');
      expect(body.kind, 'message_ai');
      expect(body.blocks.map((block) => block['kind']), containsAll(['heading', 'text', 'quote']));
      expect(body.options.keys, contains('https://omi.me'));

      await nativeProjectedRow(tester, 'chat_actions_host-ai-1_0').action!('helpful');
      await tester.pump();
      expect(messages.rated, [1]);
      expect(messages.messages[1].rating, 1);
      expect(nativeProjectedRow(tester, 'chat_actions_host-ai-1_0').subtitle, isNotEmpty);

      await tester.pump(const Duration(seconds: 1));
      final task = nativeProjectedRow(tester, 'chat_task_host-ai-2_0');
      expect((task.kind, task.value), ('task', false));
      await task.action!(true);
      await tester.pump();
      expect(updates, [('host-task-1', true)]);
      expect(nativeProjectedRow(tester, 'chat_task_host-ai-2_0').value, true);
      await checkNativeHost(tester, 'native-chat-structured-messages-actions-dark');
    });
  });
}
