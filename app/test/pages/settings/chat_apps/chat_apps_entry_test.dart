import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_page.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import 'chat_apps_fixture.dart';

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));
  setUp(initChatAppsTest);

  Future<void> pumpEntry(WidgetTester tester, MessagingChannelsProvider provider) async {
    await provider.load();
    usePhoneViewport(tester);
    await tester.pumpWidget(chatAppsHost(
      const Scaffold(body: SingleChildScrollView(child: ChatAppsIntegrationsEntry())),
      provider: provider,
    ));
    await settle(tester);
  }

  testWidgets('hidden while the flag is off and nothing is linked', (tester) async {
    await pumpEntry(tester, FakeMessagingBackend().provider(config: ChatAppsConfig.off));
    expect(find.byKey(const ValueKey('chat_apps_integrations_entry')), findsNothing);
  });

  testWidgets('shown with NEW when the flag is on, and opens the Chat apps page', (tester) async {
    await pumpEntry(tester, FakeMessagingBackend().provider());
    expect(find.text('Chat apps'), findsOneWidget);
    expect(find.text('NEW'), findsOneWidget);
    expect(find.text('Chat with Omi'), findsOneWidget);
    expect(find.text('Telegram, iMessage, and more'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('chat_apps_open')));
    await tester.pumpAndSettle();
    expect(find.byType(ChatAppsPage), findsOneWidget);
  });

  testWidgets('still shown when off but a link exists, so it can be disconnected', (tester) async {
    final backend = FakeMessagingBackend()..links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
    await pumpEntry(tester, backend.provider(config: ChatAppsConfig.off));
    expect(find.byKey(const ValueKey('chat_apps_integrations_entry')), findsOneWidget);
  });
}
