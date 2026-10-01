// Ask Omi: starters, composing, a reply and its actions, the Chat Apps drawer and Clear Chat.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/providers/memories_provider.dart';

import '../../journeys/support/hermetic_boot.dart';
import '../harness.dart';

const _page = 'lib/pages/chat/page.dart (ChatPage)';
const _input = ValueKey('omi.chat.input');
const _send = ValueKey('omi.chat.send');

String _composer(AuditRun a) => a.tester.widget<TextField>(find.byKey(_input)).controller!.text;

/// Sends [question] and waits for the fixture backend's deterministic reply.
Future<void> _ask(AuditRun a, String question) async {
  await a.enterText(find.byKey(_input), question);
  await a.tap(find.byKey(_send));
}

final chatScenarios = <AuditScenario>[
  AuditScenario(
    id: 'chat-current-thread',
    title: 'Ask Omi resumes the current conversation after a provider restart',
    page: _page,
    state: 'The existing current-thread endpoint returns one saved assistant reply',
    run: (a) async {
      final saved = ServerMessage('saved-answer', DateTime.utc(2026, 9, 29), 'Your existing conversation',
          MessageSender.ai, MessageType.text, null, false, [], [], []);
      final body = jsonEncode([saved.toJson()]);
      a.server.failNext('GET', '/v2/messages', status: 200, body: body);
      await a.pump(const ChatPage());
      expect(find.text(saved.text), findsOneWidget);
      expect(find.byKey(const Key('chat_history')), findsNothing);
      await a.shot('Load the existing current conversation', step: 'loaded');
      // Dispose the page and provider, as an app restart does; reload the same server-current thread.
      await a.tester.pumpWidget(const SizedBox.shrink());
      await a.settle();
      a.server.failNext('GET', '/v2/messages', status: 200, body: body);
      await a.pump(const ChatPage());
      expect(find.text(saved.text), findsOneWidget);
      expect(a.server.countOf('GET', '/v2/messages'), 2);
      await _ask(a, 'Continue this conversation');
      expect(find.text(saved.text), findsOneWidget);
      expect(a.server.countOf('POST', '/v2/messages'), 1);
      expect(a.server.countOf('POST', '/v2/chat-sessions'), 0);
      expect(a.server.countOf('GET', '/v2/chat-sessions'), 0);
      await a.shot('Continue the same conversation after restarting', step: 'continued');
    },
  ),
  AuditScenario(
    id: 'chat-ask',
    title: 'Ask Omi: empty, starter, draft, reply and copy',
    page: _page,
    state: 'No saved personal data; the fixture backend streams a fixed assistant reply',
    run: (a) async {
      a.server.assistantReplyText =
          'You agreed to send Alex the revised design notes on Friday. Start with the recording flow and memory search.';
      await a.pump(const ChatPage());
      expect(find.text('What can you do for me?'), findsOneWidget);
      expect(find.text('Summarize my recent activity'), findsNothing);
      await a.shot('Open Ask Omi with no saved personal data', step: 'empty');
      await a.tap(find.byKey(const Key('chat_starter_goal')));
      expect(_composer(a), 'Help me set a goal');
      expect(a.server.countOf('POST', '/v2/messages'), 0);
      await a.shot('Select a starter; it fills the composer without sending', step: 'starter');
      await a.enterText(find.byKey(_input), 'What did I agree to send Alex?');
      await a.shot('Compose a question', step: 'draft');
      await a.tap(find.byKey(_send));
      // A normal send continues the server-current conversation without creating or naming a session.
      await a.settle();
      expect(a.server.countOf('POST', '/v2/messages'), 1);
      expect(a.server.countOf('POST', '/v2/chat/generate-title'), 0);
      expect(a.server.countOf('POST', '/v2/chat-sessions'), 0);
      await a.shot('Send and receive the fixture reply', step: 'reply');
      mockCommonPlatformChannels();
      await a.tester.tap(find.bySemanticsLabel('Copy Message'));
      await a.tester.pump();
      await a.tester.pump(const Duration(milliseconds: 300));
      await a.shot('Tap Copy and inspect its confirmation', step: 'copy');
    },
  ),
  AuditScenario(
    id: 'chat-starters-with-memories',
    title: 'Ask Omi starters for an account with saved data',
    page: _page,
    state: 'Fixture-backed MemoriesProvider holding one saved private memory',
    run: (a) async {
      final memories = MemoriesProvider();
      await a.tester.runAsync(() => memories.createMemory('I prefer morning meetings.', MemoryVisibility.private));
      await a.pump(
        const ChatPage(),
        providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)],
      );
      expect(find.text('What did I decide today?'), findsOneWidget);
      expect(find.text('What do I still owe people?'), findsOneWidget);
      expect(find.text('What did Omi notice?'), findsOneWidget);
      expect(find.text('What can you do for me?'), findsNothing);
      await a.shot('Open empty chat with a saved memory');
      await a.tap(find.byKey(const Key('chat_starter_decide')));
      expect(_composer(a), 'What did I decide today?');
      expect(a.server.countOf('POST', '/v2/messages'), 0);
    },
  ),
  AuditScenario(
    id: 'chat-apps-drawer',
    title: 'Chat Apps drawer and the Clear Chat confirmation',
    page: _page,
    state: 'No saved personal data and no enabled chat apps',
    run: (a) async {
      await a.pump(const ChatPage());
      await a.tap(find.bySemanticsLabel('Chat Apps'));
      await a.shot('Open the Chat Apps drawer', step: 'drawer');
      await a.tap(find.text('Clear Chat').first);
      await a.shot('Tap Clear Chat at the bottom of the drawer', step: 'clear-confirm');
    },
  ),
  AuditScenario(
    id: 'chat-feedback',
    title: 'Not Helpful feedback sheet on a reply',
    page: _page,
    state: 'One question answered by the fixture backend',
    run: (a) async {
      a.server.assistantReplyText = 'You agreed to send Alex the revised design notes on Friday.';
      await a.pump(const ChatPage());
      await _ask(a, 'What did I agree to?');
      await a.tap(find.bySemanticsLabel('Not Helpful'));
      await a.shot('Tap Not Helpful on the reply: the feedback reason sheet');
    },
  ),
  AuditScenario(
    id: 'chat-sheet',
    title: 'Ask Omi rising over Home',
    page: 'lib/pages/chat/chat_route.dart (ChatSheetTransition)',
    state: 'The rise at 70% of its run over a stand-in Home list; empty chat; signed in as Alex',
    run: (a) async {
      SharedPreferencesUtil().givenName = 'Alex';
      await a.pump(
        Stack(children: [
          Positioned.fill(
            child: ColoredBox(
              color: const Color(0xFFF2F2F7),
              child: ListView(padding: const EdgeInsets.fromLTRB(16, 80, 16, 0), children: [
                for (final title in ['Device Connection Troubleshooting', 'Trying to Identify a Place', 'Weekly sync'])
                  Container(
                    height: 96,
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22)),
                    child: Text(title, style: const TextStyle(fontSize: 17)),
                  ),
              ]),
            ),
          ),
          const ChatSheetTransition(
            animation: AlwaysStoppedAnimation(0.7),
            child: ChatPage(),
          ),
        ]),
        scaffold: false,
      );
      await a.shot('Tap Ask Omi: the page blurs and the chat sheet rises');
    },
  ),
  AuditScenario(
    id: 'chat-steps',
    title: 'Tool steps while a reply works, folded after, and the Activity sheet',
    page: 'lib/pages/chat/widgets/ai_message.dart (ChatActivitySteps)',
    state: 'One reply mid-stream with three steps; one finished reply with the same steps',
    run: (a) async {
      ServerMessage reply(String id, String text) => ServerMessage(
          id, DateTime(2026, 9, 29, 10, 5), text, MessageSender.ai, MessageType.text, null, false, [], [], [],
          askForNps: false)
        ..thinkings.addAll(['Searching conversations', 'Loaded calendar', 'Searching memories']);
      Widget message(ServerMessage m, {required bool working}) => AIMessage(
            message: m,
            sendMessage: (_) {},
            displayOptions: false,
            updateConversation: (_) {},
            setMessageNps: (_, {reason}) {},
            showTypingIndicator: working,
          );
      await a.pump(
        ListView(padding: const EdgeInsets.all(18), children: [
          const Align(alignment: Alignment.centerRight, child: Text('What did I do today?')),
          const SizedBox(height: 16),
          message(reply('working', ''), working: true),
          const SizedBox(height: 32),
          const Align(alignment: Alignment.centerRight, child: Text('What did I do yesterday?')),
          const SizedBox(height: 16),
          message(
            reply('done',
                'Yesterday you had:\n\n- **9:12 AM** troubleshooting the pendant\'s Bluetooth level\n- **10:18 PM** trying to identify a place on a walk'),
            working: false,
          ),
        ]),
      );
      await a.shot('A reply works through its steps; a finished reply keeps one line', step: 'lines');
      await a.tap(find.byKey(const ValueKey('chat_activity_summary')));
      await a.shot('Tap the step line: the Activity sheet', step: 'activity');
    },
  ),
];
