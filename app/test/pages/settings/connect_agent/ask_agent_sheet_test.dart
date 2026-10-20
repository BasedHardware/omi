import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/widgets/ask_agent_sheet.dart';
import 'package:omi/ui/ui.dart';

import 'connect_agent_fixture.dart';

ServerConversation _conversation(String id) => ServerConversation.fromJson({
      'id': id,
      'created_at': '2026-10-15T10:00:00Z',
      'started_at': '2026-10-15T10:00:00Z',
      'finished_at': '2026-10-15T10:42:00Z',
      'structured': {'title': 'Weekly product sync', 'overview': '', 'emoji': '', 'category': 'work'},
      'status': 'completed',
      'transcript_segments': [],
    });

void main() {
  Future<void> openAsk(WidgetTester tester, FakeAgentBackend backend, String conversationId) async {
    await tester.tap(find.byKey(ValueKey('open_ask_$conversationId')));
    await settle(tester);
  }

  Widget host(FakeAgentBackend backend) => connectAgentHost(
        Builder(
          builder: (context) => Scaffold(
            body: Column(
              children: [
                for (final id in ['c1', 'c2'])
                  OmiButton(
                    key: ValueKey('open_ask_$id'),
                    label: id,
                    onPressed: () => showAskAgentSheet(context, _conversation(id), service: backend.service()),
                  ),
              ],
            ),
          ),
        ),
      );

  testWidgets('a typed question survives closing the sheet to connect ChatGPT', (tester) async {
    usePhoneViewport(tester);
    final backend = FakeAgentBackend();
    await tester.pumpWidget(host(backend));
    await openAsk(tester, backend, 'c1');
    await tester.enterText(find.byKey(const ValueKey('ask_agent_question')), 'Who owns the launch?');
    await tester.tap(find.byKey(const ValueKey('ask_agent_connect_chatgpt')));
    await settle(tester);
    // The connect sheet replaced the ask sheet; close it and come back.
    expect(find.byKey(const ValueKey('connect_chatgpt_open')), findsOneWidget);
    await tester.tapAt(const Offset(195, 20));
    await settle(tester);

    await openAsk(tester, backend, 'c1');
    expect(find.text('Who owns the launch?'), findsOneWidget);

    // Drafts belong to their conversation.
    await tester.tapAt(const Offset(195, 20));
    await settle(tester);
    await openAsk(tester, backend, 'c2');
    expect(find.text('Who owns the launch?'), findsNothing);
  });

  testWidgets('a grant without conversation access offers Connect instead of Ask', (tester) async {
    usePhoneViewport(tester);
    final backend = FakeAgentBackend(chatGptConnected: true, chatGptScopes: ['memories.read']);
    await tester.pumpWidget(host(backend));
    await openAsk(tester, backend, 'c1');
    expect(find.byKey(const ValueKey('ask_agent_chatgpt')), findsNothing);
    expect(find.byKey(const ValueKey('ask_agent_connect_chatgpt')), findsOneWidget);
  });

  testWidgets('a failed ChatGPT check offers Try Again, not Connect', (tester) async {
    usePhoneViewport(tester);
    final backend = FakeAgentBackend(chatGptConnected: true, failLoad: true);
    await tester.pumpWidget(host(backend));
    await openAsk(tester, backend, 'c1');
    expect(find.byKey(const ValueKey('ask_agent_connect_chatgpt')), findsNothing);
    expect(find.byKey(const ValueKey('ask_agent_retry')), findsOneWidget);
    backend.failLoad = false;
    await tester.tap(find.byKey(const ValueKey('ask_agent_retry')));
    await settle(tester);
    expect(find.byKey(const ValueKey('ask_agent_chatgpt')), findsOneWidget);
  });
}
