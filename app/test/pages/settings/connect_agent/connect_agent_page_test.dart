import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/connect_agent/chatgpt_page.dart';
import 'package:omi/pages/settings/connect_agent/connect_agent_page.dart';

import 'connect_agent_fixture.dart';

void main() {
  Future<FakeAgentBackend> pumpPage(WidgetTester tester, FakeAgentBackend backend) async {
    usePhoneViewport(tester);
    await tester.pumpWidget(connectAgentHost(ConnectAgentPage(service: backend.service())));
    await settle(tester);
    return backend;
  }

  testWidgets('lists ChatGPT and the computer agents with their state', (tester) async {
    await pumpPage(
      tester,
      FakeAgentBackend(chatGptConnected: true, keys: {'Muse': null}),
    );
    expect(find.text('Use your Omi memory in ChatGPT and your AI agents'), findsOneWidget);
    expect(find.text('ChatGPT'), findsOneWidget);
    expect(find.text('Connected'), findsOneWidget);
    for (final name in ['Grok Bot', 'Muse', 'Instinct', 'Other Agent']) {
      expect(find.text(name), findsOneWidget);
    }
    expect(find.text('Key active'), findsOneWidget);
    // ChatGPT and Muse are connected; Grok Bot, Instinct and Other Agent offer Connect.
    expect(find.text('Connect'), findsNWidgets(3));
  });

  testWidgets('a failed load says so and retries', (tester) async {
    final backend = await pumpPage(tester, FakeAgentBackend(failLoad: true));
    expect(find.text("Couldn't load your connections."), findsOneWidget);
    backend.failLoad = false;
    await tester.tap(find.text('Try Again'));
    await settle(tester);
    expect(find.text('ChatGPT'), findsOneWidget);
  });

  testWidgets('opening an agent sheet makes nothing; Copy Prompt makes one key and copies the link', (tester) async {
    final copied = captureClipboard(tester);
    final backend = await pumpPage(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_instinct')));
    await settle(tester);
    expect(find.text('Connect Instinct'), findsOneWidget);
    expect(backend.created, isEmpty);

    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await settle(tester);
    expect(backend.created, ['Instinct']);
    expect(find.text('Key “Instinct” created'), findsOneWidget);
    expect(copied.single, contains(fakeAgentLink));
    expect(copied.single, isNot(contains('omi_mcp_secret')));

    // Copying again reuses the same key and link.
    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await settle(tester);
    expect(backend.created, ['Instinct']);
    expect(copied, hasLength(2));

    // A new link replaces the key instead of adding a second one.
    await tester.tap(find.byKey(const ValueKey('agent_key_new_link')));
    await settle(tester);
    expect(backend.created, ['Instinct', 'Instinct']);
    expect(backend.revokedKeys, ['key-Instinct-1']);
  });

  testWidgets('an active agent can be revoked after confirming', (tester) async {
    final backend = await pumpPage(tester, FakeAgentBackend(keys: {'Muse': DateTime(2026, 10, 15, 9, 30)}));
    await tester.tap(find.byKey(const ValueKey('connect_agent_muse')));
    await settle(tester);
    expect(find.text('Muse Is Connected'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('agent_key_revoke')));
    await settle(tester);
    expect(find.text("Revoke Muse's Key?"), findsOneWidget);
    await tester.tap(find.text('Revoke').last);
    await settle(tester);
    expect(backend.revokedKeys, ['key-Muse']);
    expect(find.text('Key active'), findsNothing);
  });

  testWidgets('ChatGPT not connected opens the one-tap sheet', (tester) async {
    await pumpPage(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_chatgpt')));
    await settle(tester);
    expect(find.text('Connect ChatGPT'), findsOneWidget);
    expect(find.byKey(const ValueKey('connect_chatgpt_open')), findsOneWidget);
  });

  testWidgets('connected ChatGPT shows questions to try and disconnects after confirming', (tester) async {
    final backend = await pumpPage(tester, FakeAgentBackend(chatGptConnected: true));
    await tester.tap(find.byKey(const ValueKey('connect_agent_chatgpt')));
    await settle(tester);
    expect(find.byType(ChatGptPage), findsOneWidget);
    expect(find.text("What did I agree to in yesterday's meetings?"), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('chatgpt_disconnect')));
    await settle(tester);
    await tester.tap(find.text('Disconnect').last);
    await settle(tester);
    expect(backend.revokedGrants, ['grant-chatgpt']);
    expect(find.byType(ChatGptPage), findsNothing);
    expect(find.text('Connected'), findsNothing);
  });
}
