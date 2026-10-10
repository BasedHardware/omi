import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/chat_apps/channel_chats_page.dart';
import 'package:omi/pages/settings/chat_apps/channel_settings_page.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_page.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import 'chat_apps_fixture.dart';

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));
  setUp(initChatAppsTest);

  Future<(FakeMessagingBackend, MessagingChannelsProvider)> pump(
    WidgetTester tester,
    Widget page, {
    bool visible = false,
  }) async {
    final backend = FakeMessagingBackend()
      ..links = [
        linkJson(id: linkIdTelegram, channel: 'telegram', visible: visible),
      ];
    final provider = backend.provider();
    await provider.load();
    usePhoneViewport(tester);
    await tester.pumpWidget(chatAppsHost(page, provider: provider));
    await settle(tester);
    return (backend, provider);
  }

  group('Manage a connection', () {
    testWidgets(
      'shows the handle, show-in-app off by default, and later settings as coming',
      (tester) async {
        await pump(tester, ChannelSettingsPage(linkId: linkIdTelegram));
        expect(find.text('@sam'), findsOneWidget);
        expect(find.textContaining('Connected Oct 10, 2026'), findsOneWidget);
        expect(find.text('Show these chats in the Omi app'), findsOneWidget);
        expect(
          find.text('Off: you only see them in Telegram.'),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('chat_apps_view_chats')),
          findsNothing,
        );
        await tester.scrollUntilVisible(find.text('Disconnect Telegram'), 200);
        expect(find.text('Coming later', skipOffstage: false), findsOneWidget);
        expect(
          find.byKey(const ValueKey('chat_apps_voice_notes')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('chat_apps_private_memories')),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'turning on show-in-app patches the link and offers its chats',
      (tester) async {
        final (backend, _) = await pump(
          tester,
          ChannelSettingsPage(linkId: linkIdTelegram),
        );
        await tester.tap(find.byKey(const ValueKey('chat_apps_show_in_app')));
        await settle(tester);
        expect(backend.count('PATCH', 'v1/messaging/links/'), 1);
        expect(jsonDecode(backend.requests.last.body), {
          'visible_in_app': true,
        });
        expect(
          find.byKey(const ValueKey('chat_apps_view_chats')),
          findsOneWidget,
        );
      },
    );

    testWidgets('voice notes and private memories patch their own fields', (
      tester,
    ) async {
      final (backend, provider) = await pump(
        tester,
        ChannelSettingsPage(linkId: linkIdTelegram),
      );
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('chat_apps_voice_notes')),
        200,
      );
      await tester.tap(find.byKey(const ValueKey('chat_apps_voice_notes')));
      await settle(tester);
      expect(jsonDecode(backend.requests.last.body), {'voice_notes': false});
      expect(provider.links.single.voiceNotes, isFalse);

      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('chat_apps_private_memories')),
        200,
      );
      await tester.tap(
        find.byKey(const ValueKey('chat_apps_private_memories')),
      );
      await settle(tester);
      expect(jsonDecode(backend.requests.last.body), {
        'keep_private_memories_in_app': false,
      });
      expect(provider.links.single.keepPrivateMemoriesInApp, isFalse);
    });

    testWidgets('a refused toggle reverts and says why', (tester) async {
      final (backend, provider) = await pump(
        tester,
        ChannelSettingsPage(linkId: linkIdTelegram),
      );
      backend.statusFor['PATCH v1/messaging/links'] = 503;
      await tester.tap(find.byKey(const ValueKey('chat_apps_show_in_app')));
      await settle(tester);
      expect(provider.links.single.visibleInApp, isFalse);
      expect(find.text('Something went wrong. Try again.'), findsOneWidget);
    });

    testWidgets('disconnect asks first, then unlinks and leaves', (
      tester,
    ) async {
      final backend = FakeMessagingBackend()..links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
      final provider = backend.provider();
      usePhoneViewport(tester);
      await tester.pumpWidget(
        chatAppsHost(const ChatAppsPage(), provider: provider),
      );
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('chat_apps_row_telegram')));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('chat_apps_disconnect')),
        200,
      );
      await tester.tap(find.byKey(const ValueKey('chat_apps_disconnect')));
      await tester.pumpAndSettle();
      expect(find.text('Disconnect Telegram?'), findsOneWidget);
      expect(
        find.textContaining('delete the chat history it keeps'),
        findsOneWidget,
      );
      await tester.tap(find.text('Disconnect').last);
      await tester.pumpAndSettle();

      expect(backend.count('DELETE', 'v1/messaging/links/'), 1);
      expect(provider.links, isEmpty);
      expect(find.byType(ChatAppsPage), findsOneWidget);
      expect(find.text('Connect'), findsNWidgets(2));
    });

    testWidgets('cancelling disconnect changes nothing', (tester) async {
      final (backend, _) = await pump(
        tester,
        ChannelSettingsPage(linkId: linkIdTelegram),
      );
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('chat_apps_disconnect')),
        200,
      );
      await tester.tap(find.byKey(const ValueKey('chat_apps_disconnect')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(backend.count('DELETE', 'v1/messaging/links/'), 0);
    });

    testWidgets('a link that is gone shows not connected', (tester) async {
      await pump(tester, ChannelSettingsPage(linkId: 'c' * 64));
      expect(find.text('Not connected'), findsOneWidget);
    });
  });

  group('Chat app history', () {
    ChatSessionsApi sessionsApi({
      List<Map<String, dynamic>> sessions = const [],
      int status = 200,
    }) =>
        ChatSessionsApi(
          baseUrl: 'http://127.0.0.1:1/',
          fallback: (_) {},
          send: (ApiRequest request) async {
            final uri = Uri.parse(request.url);
            if (status != 200) return http.Response('{}', status);
            if (uri.path == '/v2/chat-sessions') return http.Response(jsonEncode(sessions), 200);
            if (uri.path == '/v2/messages') {
              return http.Response(
                jsonEncode([
                  {
                    'id': 'm2',
                    'created_at': '2026-10-10T12:01:00Z',
                    'text': 'Added "Draft offsite agenda", due Friday.',
                    'sender': 'ai',
                    'type': 'text',
                  },
                  {
                    'id': 'm1',
                    'created_at': '2026-10-10T12:00:00Z',
                    'text': 'add that as a task for friday',
                    'sender': 'human',
                    'type': 'text',
                  },
                ]),
                200,
              );
            }
            return http.Response('[]', 404);
          },
        );

    Map<String, dynamic> session(
      String id, {
      String? link,
      String title = 'Offsite',
    }) =>
        {
          'id': id,
          'title': title,
          'preview': 'Lisbon, Nov 9',
          'updated_at': '2026-10-10T12:00:00Z',
          'created_at': '2026-10-10T11:00:00Z',
          'message_count': 2,
          if (link != null) ...{'channel': 'telegram', 'channel_link_id': link},
        };

    testWidgets(
      "lists only this link's sessions, with the channel badge, and opens them read-only",
      (tester) async {
        final api = sessionsApi(
          sessions: [
            session('app', title: 'Ask Omi chat'),
            session('tg', link: linkIdTelegram),
            session('im', link: linkIdIMessage, title: 'Other'),
          ],
        );
        await pump(
          tester,
          ChannelChatsPage(linkId: linkIdTelegram, api: api),
          visible: true,
        );
        expect(find.text('Telegram chats'), findsOneWidget);
        expect(find.text('Offsite'), findsOneWidget);
        expect(find.text('Ask Omi chat'), findsNothing);
        expect(find.text('Other'), findsNothing);
        expect(find.textContaining('Reply in Telegram.'), findsOneWidget);

        await tester.tap(find.text('Offsite'));
        await tester.pumpAndSettle();
        expect(
          find.byKey(const ValueKey('chat_apps_read_only_banner')),
          findsOneWidget,
        );
        expect(
          find.text('Read-only. Reply to Omi in Telegram.'),
          findsOneWidget,
        );
        expect(find.byType(TextField), findsNothing);
        final human = tester.getTopLeft(
          find.textContaining('add that as a task'),
        );
        final ai = tester.getTopLeft(
          find.textContaining('Draft offsite agenda'),
        );
        expect(
          human.dy,
          lessThan(ai.dy),
          reason: 'oldest first, like the chat app',
        );
      },
    );

    testWidgets('no sessions yet is an empty state', (tester) async {
      await pump(
        tester,
        ChannelChatsPage(linkId: linkIdTelegram, api: sessionsApi()),
        visible: true,
      );
      expect(find.text('No chats yet'), findsOneWidget);
    });

    testWidgets('a failed load is an error with retry, never empty', (
      tester,
    ) async {
      await pump(
        tester,
        ChannelChatsPage(linkId: linkIdTelegram, api: sessionsApi(status: 500)),
        visible: true,
      );
      expect(find.text('No chats yet'), findsNothing);
      expect(find.text('Try Again'), findsOneWidget);
    });
  });
}
