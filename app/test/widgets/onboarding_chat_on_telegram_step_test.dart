import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/pages/onboarding/chat_on_telegram_step.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import '../pages/settings/chat_apps/chat_apps_fixture.dart';

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));
  setUp(initChatAppsTest);

  // A loaded provider so the connect sheet sees Telegram's endpoint and opens its normal flow.
  Future<MessagingChannelsProvider> loadedProvider() async {
    final provider = FakeMessagingBackend().provider();
    await provider.load();
    return provider;
  }

  Future<void> pumpStep(
    WidgetTester tester, {
    required MessagingChannelsProvider provider,
    required VoidCallback onContinue,
  }) async {
    usePhoneViewport(tester);
    await tester.pumpWidget(chatAppsHost(
      OnboardingChatOnTelegramStep(onContinue: onContinue),
      provider: provider,
    ));
    await settle(tester);
  }

  testWidgets('Not Now finishes the step', (tester) async {
    var continued = false;
    await pumpStep(tester, provider: await loadedProvider(), onContinue: () => continued = true);

    await tester.tap(find.text('Not Now'));
    await settle(tester);

    expect(continued, isTrue);
  });

  testWidgets('a dismissed connect sheet leaves the reader on the step', (tester) async {
    var continued = false;
    await pumpStep(tester, provider: await loadedProvider(), onContinue: () => continued = true);

    await tester.tap(find.text('Connect Telegram')); // the step's button, before the sheet opens
    await settle(tester);
    // The sheet is open (its close X is drawn) and nothing has advanced yet.
    expect(find.byIcon(Icons.close), findsOneWidget);
    expect(continued, isFalse);

    // Close the sheet without linking: it resolves to null, so the reader stays here.
    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();

    expect(continued, isFalse);
  });

  testWidgets('a system back routes through onContinue (skip, not a raw pop)', (tester) async {
    var continued = false;
    await pumpStep(tester, provider: await loadedProvider(), onContinue: () => continued = true);

    final navigator = tester.state<NavigatorState>(find.byType(Navigator).first);
    await navigator.maybePop();
    await settle(tester);

    expect(continued, isTrue);
  });
}
