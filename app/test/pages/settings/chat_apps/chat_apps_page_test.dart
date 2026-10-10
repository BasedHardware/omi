import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_page.dart';
import 'package:omi/pages/settings/chat_apps/channel_link_waiter.dart';
import 'package:omi/pages/settings/chat_apps/imessage_connect_sheet.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import 'chat_apps_fixture.dart';

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));

  final launched = <Uri>[];
  setUp(() async {
    await initChatAppsTest();
    launched.clear();
    chatAppLauncher = (uri) async {
      launched.add(uri);
      return true;
    };
    ChannelLinkWaiter.interval = const Duration(milliseconds: 100);
  });

  Future<FakeMessagingBackend> pumpPage(
    WidgetTester tester, {
    FakeMessagingBackend? backend,
    ChatAppsConfig config = chatAppsOn,
    PlanType? plan = PlanType.architect,
    bool online = true,
  }) async {
    final b = backend ?? FakeMessagingBackend();
    usePhoneViewport(tester);
    await tester.pumpWidget(chatAppsHost(
      const ChatAppsPage(),
      provider: b.provider(config: config),
      usage: usageWith(plan),
      connectivity: StubConnectivity(online: online),
    ));
    await settle(tester);
    return b;
  }

  group('Chat apps page', () {
    testWidgets('Pro, nothing connected: header, three rows, what Omi does', (tester) async {
      await pumpPage(tester);
      expect(find.text('Chat with Omi where you already chat'), findsOneWidget);
      expect(find.text('INCLUDED WITH OMI PRO'), findsOneWidget);
      expect(find.text('Telegram'), findsOneWidget);
      expect(find.text('iMessage'), findsOneWidget);
      expect(find.text('WhatsApp'), findsOneWidget);
      expect(find.text('Connect'), findsNWidgets(2));
      expect(find.text('Notify Me'), findsOneWidget);
      expect(find.byKey(const ValueKey('chat_apps_what_omi_does')), findsOneWidget);
      expect(find.text('Never messages other people for you'), findsOneWidget);
    });

    for (final plan in PlanType.values.where((plan) => plan.isPaid)) {
      testWidgets('${plan.name} is eligible to connect both channels', (tester) async {
        await pumpPage(tester, plan: plan);
        expect(find.text('Connect'), findsNWidgets(2));
        expect(find.byIcon(Icons.lock_outline_rounded), findsNothing);
        expect(find.byKey(const ValueKey('chat_apps_pro_card')), findsNothing);
      });
    }

    testWidgets('a connected link shows its handle and Try asking', (tester) async {
      final backend = FakeMessagingBackend()..links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
      await pumpPage(tester, backend: backend);
      expect(find.text('Connected as @sam'), findsOneWidget);
      expect(find.text('Connected'), findsOneWidget);
      expect(find.byKey(const ValueKey('chat_apps_try_asking')), findsOneWidget);
      expect(find.byKey(const ValueKey('chat_apps_what_omi_does')), findsNothing);
    });

    testWidgets('free plan: rows locked, Pro card, connected links still open', (tester) async {
      final backend = FakeMessagingBackend()
        ..links = [linkJson(id: linkIdIMessage, channel: 'imessage', externalId: '+15550100')];
      await pumpPage(tester, backend: backend, plan: PlanType.basic);
      expect(find.byKey(const ValueKey('chat_apps_pro_card')), findsOneWidget);
      expect(find.text('Chat apps are part of Pro'), findsOneWidget);
      expect(find.byIcon(Icons.lock_outline_rounded), findsOneWidget); // Telegram is locked.
      expect(find.text('Connected as +15550100'), findsOneWidget);
      expect(find.text('Connect'), findsNothing);
    });

    testWidgets('a channel without an address is coming soon', (tester) async {
      await pumpPage(tester,
          config: const ChatAppsConfig(enabled: true, endpoints: {ChatChannel.telegram: telegramEndpoint}));
      expect(find.text('Coming Soon'), findsOneWidget);
      expect(find.text('Connect'), findsOneWidget);
    });

    testWidgets('first load failure shows the error state and retries', (tester) async {
      final backend = FakeMessagingBackend()..statusFor['GET v1/messaging/links'] = 500;
      await pumpPage(tester, backend: backend);
      expect(find.text("Couldn't load chat apps"), findsOneWidget);
      backend.statusFor.clear();
      await tester.tap(find.text('Try Again'));
      await settle(tester);
      expect(find.text('Telegram'), findsOneWidget);
    });

    testWidgets('offline shows a notice above the rows', (tester) async {
      await pumpPage(tester, online: false);
      expect(find.text("You're offline. Check your connection and try again."), findsOneWidget);
      expect(find.text('Telegram'), findsOneWidget);
    });
  });

  group('Telegram connect', () {
    testWidgets('opens t.me with a fresh token, waits, then shows connected', (tester) async {
      final backend = await pumpPage(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_telegram')));
      await settle(tester);
      expect(find.text('Connect Telegram'), findsOneWidget);
      expect(find.textContaining('also stored by Telegram'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('chat_apps_open_telegram')));
      await settle(tester);
      expect(launched.single.toString(), 'https://t.me/OmiBot?start=tok_1_abcdefghijklmnop');
      expect(find.text('Waiting for you to tap Start in Telegram…'), findsOneWidget);

      backend.links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
      await tester.pump(const Duration(milliseconds: 150));
      await settle(tester);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('chat_apps_connected_banner')), findsOneWidget);
      expect(find.text('Telegram is connected'), findsOneWidget);
      expect(find.byKey(const ValueKey('chat_apps_open_connected')), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('chat_apps_open_connected')));
      await settle(tester);
      expect(launched.last.toString(), 'https://t.me/OmiBot');
    });

    testWidgets('a refused mint says chat apps are unavailable and disables the buttons', (tester) async {
      final backend = FakeMessagingBackend()..statusFor['POST v1/messaging/link-proofs'] = 403;
      await pumpPage(tester, backend: backend);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_telegram')));
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_open_telegram')));
      await settle(tester);
      expect(find.byKey(const ValueKey('chat_apps_problem_unavailable')), findsOneWidget);
      expect(launched, isEmpty);
    });

    testWidgets('an expired token stops waiting and says so', (tester) async {
      final backend = FakeMessagingBackend()..proofTtl = const Duration(milliseconds: 20);
      await pumpPage(tester, backend: backend);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_telegram')));
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_open_telegram')));
      await settle(tester);
      // Expiry reads the wall clock.
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 300)));
      await tester.pump(const Duration(milliseconds: 150));
      await settle(tester);
      expect(find.byKey(const ValueKey('chat_apps_telegram_expired')), findsOneWidget);
    });
  });

  group('iMessage connect', () {
    testWidgets('prefills Messages with the code, then waits and connects', (tester) async {
      final backend = await pumpPage(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_imessage')));
      await settle(tester);
      expect(find.text('Text Omi to connect'), findsOneWidget);
      expect(find.textContaining('Hi Omi, link code 9F2C4A7B'), findsOneWidget);
      expect(find.text('The code works once and expires in 10 minutes.'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('chat_apps_open_messages')));
      await settle(tester);
      expect(launched.single.scheme, 'sms');
      expect(launched.single.toString(), contains('+15550100100'));
      expect(launched.single.toString(), contains('link%20code%209F2C4A7B'));
      expect(find.text('Waiting for your text'), findsOneWidget);
      expect(find.byKey(const ValueKey('chat_apps_link_code')), findsOneWidget);
      expect(find.textContaining('Code expires in 9:'), findsOneWidget);

      backend.links = [linkJson(id: linkIdIMessage, channel: 'imessage', externalId: '+15550100')];
      await tester.pump(const Duration(milliseconds: 150));
      await settle(tester);
      await tester.pumpAndSettle();
      expect(find.text('iMessage is connected'), findsOneWidget);
      expect(find.text('Open Messages'), findsOneWidget);
    });

    testWidgets('an expired code offers a new one', (tester) async {
      final backend = FakeMessagingBackend()..proofTtl = const Duration(milliseconds: 400);
      await pumpPage(tester, backend: backend);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_imessage')));
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_open_messages')));
      await settle(tester);
      // Expiry reads the wall clock.
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 500)));
      await tester.pump(const Duration(seconds: 1));
      expect(find.text('This code expired'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('chat_apps_new_code')));
      await settle(tester);
      expect(backend.count('POST', 'v1/messaging/link-proofs'), 2);
      expect(find.text('Text Omi to connect'), findsOneWidget);
    });

    testWidgets('Add Omi to Contacts opens the contact form with the number', (tester) async {
      final added = <String>[];
      addContactLauncher = (name, number) async => added.add('$name $number');
      await pumpPage(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_imessage')));
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_add_contact')));
      await settle(tester);
      expect(added, ['Omi +15550100100']);
    });
  });

  group('WhatsApp waitlist', () {
    testWidgets('Notify Me is remembered and the row says so', (tester) async {
      await pumpPage(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_whatsapp')));
      await settle(tester);
      expect(find.text('WhatsApp is coming'), findsOneWidget);
      expect(find.text('Use Telegram for Now'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('chat_apps_whatsapp_notify')));
      await settle(tester);
      expect(find.text('On the List'), findsWidgets);
    });
  });
}
