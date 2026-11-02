import 'dart:async';

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
    // Muse's key was never used: the prompt has not been run yet.
    expect(find.text('Waiting for the agent to use its key'), findsOneWidget);
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
    expect(backend.created, ['Instinct (Omi app)']);
    expect(find.text('Key “Instinct (Omi app)” created'), findsOneWidget);
    expect(copied.single, contains(fakeAgentLink));
    expect(copied.single, isNot(contains('omi_mcp_secret')));

    // Copying again reuses the same key and link.
    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await settle(tester);
    expect(backend.created, ['Instinct (Omi app)']);
    expect(copied, hasLength(2));

    // A new link replaces the key instead of adding a second one, once the new one exists.
    await tester.tap(find.byKey(const ValueKey('agent_key_new_link')));
    await settle(tester);
    expect(backend.created, ['Instinct (Omi app)', 'Instinct (Omi app)']);
    expect(backend.revokedKeys, ['key-new-1']);
    expect(backend.keys.keys, ['key-new-2']);
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

  testWidgets('closing the sheet while the link is made revokes the key nobody received', (tester) async {
    final backend = FakeAgentBackend()..holdShare = Completer<void>();
    await pumpPage(tester, backend);
    await tester.tap(find.byKey(const ValueKey('connect_agent_instinct')));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await tester.pump();
    await tester.tapAt(const Offset(195, 20)); // the scrim
    await settle(tester);
    backend.holdShare!.complete();
    await settle(tester);
    expect(backend.created, ['Instinct (Omi app)']);
    expect(backend.revokedKeys, ['key-new-1']);
    expect(find.text('Key active'), findsNothing);
  });

  testWidgets('a link that fails after the sheet closed leaves no ghost key on the list', (tester) async {
    final backend = FakeAgentBackend()..holdShare = Completer<void>();
    await pumpPage(tester, backend);
    await tester.tap(find.byKey(const ValueKey('connect_agent_instinct')));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await tester.pump();
    await tester.tapAt(const Offset(195, 20)); // the scrim
    await settle(tester);
    // The list reloaded while the key existed; the link then fails and the key is deleted.
    backend.holdShare!.completeError(Exception('zkr down'));
    await settle(tester);
    expect(backend.created, ['Instinct (Omi app)']);
    expect(backend.revokedKeys, ['key-new-1']);
    expect(find.text('Waiting for the agent to use its key'), findsNothing);
    expect(find.text('Connect'), findsNWidgets(5));
  });

  testWidgets('a revoke shows at once even when the refresh after it fails, and the failure is said', (tester) async {
    final backend = await pumpPage(tester, FakeAgentBackend(keys: {'Muse': null}));
    await tester.tap(find.byKey(const ValueKey('connect_agent_muse')));
    await settle(tester);
    backend.failLoad = true;
    await tester.tap(find.byKey(const ValueKey('agent_key_revoke')));
    await settle(tester);
    await tester.tap(find.text('Revoke').last);
    await settle(tester);
    expect(backend.revokedKeys, ['key-Muse']);
    expect(find.text('Key active'), findsNothing);
    expect(find.text("Couldn't load your connections."), findsOneWidget);
  });

  testWidgets('ChatGPT approved without the access the screens need offers Reconnect', (tester) async {
    await pumpPage(tester, FakeAgentBackend(chatGptConnected: true, chatGptScopes: ['memories.read']));
    expect(find.text('Needs more access. Reconnect to fix.'), findsOneWidget);
    await tester.tap(find.text('Reconnect'));
    await settle(tester);
    expect(find.byKey(const ValueKey('connect_chatgpt_open')), findsOneWidget);
  });

  testWidgets('a partial ChatGPT grant can be disconnected from the reconnect sheet', (tester) async {
    final backend = await pumpPage(tester, FakeAgentBackend(chatGptConnected: true, chatGptScopes: ['memories.read']));
    await tester.tap(find.text('Reconnect'));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('connect_chatgpt_disconnect')));
    await settle(tester);
    await tester.tap(find.text('Disconnect').last);
    await settle(tester);
    expect(backend.revokedGrants, ['grant-chatgpt']);
    expect(find.byKey(const ValueKey('connect_chatgpt_open')), findsNothing);
    expect(find.text('Needs more access. Reconnect to fix.'), findsNothing);
  });

  testWidgets('ChatGPT not connected offers no Disconnect on the sheet', (tester) async {
    await pumpPage(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_chatgpt')));
    await settle(tester);
    expect(find.byKey(const ValueKey('connect_chatgpt_disconnect')), findsNothing);
  });

  testWidgets('a new link abandoned mid-request keeps the working key', (tester) async {
    captureClipboard(tester);
    final backend = await pumpPage(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_instinct')));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await settle(tester);
    expect(backend.keys.keys, ['key-new-1']);

    backend.holdShare = Completer<void>();
    await tester.tap(find.byKey(const ValueKey('agent_key_new_link')));
    await tester.pump();
    await tester.tapAt(const Offset(195, 20)); // the scrim
    await settle(tester);
    backend.holdShare!.complete();
    await settle(tester);
    // The unreceived replacement is revoked; the key the agent already has is untouched.
    expect(backend.revokedKeys, ['key-new-2']);
    expect(backend.keys.keys, ['key-new-1']);
  });
}
