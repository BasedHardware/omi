// Ask Omi: starters, composing, a reply and its actions, the Chat Apps drawer and Clear Chat.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/chat/page.dart';
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
      expect(a.server.countOf('POST', '/v2/messages'), 1);
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
      await a.pump(const ChatPage(), providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)]);
      expect(find.text('Summarize my recent activity'), findsOneWidget);
      expect(find.text('How can I improve?'), findsOneWidget);
      expect(find.text('What can you do for me?'), findsNothing);
      await a.shot('Open empty chat with a saved memory');
      await a.tap(find.byKey(const Key('chat_starter_activity')));
      expect(_composer(a), 'Summarize my recent activity');
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
];
