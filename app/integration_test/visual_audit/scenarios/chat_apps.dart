// Chat apps: the Integrations entry, connecting Telegram and iMessage, managing a connection, the
// WhatsApp waitlist, the free-plan upsell, and a chat app's read-only history.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api/messaging_channels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/chat_apps/channel_chats_page.dart';
import 'package:omi/pages/settings/chat_apps/channel_link_waiter.dart';
import 'package:omi/pages/settings/chat_apps/channel_settings_page.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/providers/usage_provider.dart';

import '../harness.dart';

const _linkTelegram = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

const _config = ChatAppsConfig(enabled: true, endpoints: {
  ChatChannel.telegram: ChatChannelEndpoint(provider: 'telegram', address: 'OmiBot'),
  ChatChannel.imessage: ChatChannelEndpoint(provider: 'imessage', address: '+1 415 555 0100'),
});

/// The `/v1/messaging/*` routes in memory; links can be added mid-scenario.
class _Messaging {
  final links = <Map<String, Object?>>[];

  void link(String channel, String externalId, {bool visible = false}) => links.add({
        'id': channel == 'telegram' ? _linkTelegram : 'b' * 64,
        'channel': channel,
        'provider': channel,
        'external_id': externalId,
        'visible_in_app': visible,
        'linked_at': '2026-10-10T12:00:00Z',
      });

  Future<http.Response> send(ApiRequest request) async {
    final path = Uri.parse(request.url).path;
    if (path.endsWith('/v1/messaging/links') && request.method == 'GET') {
      return http.Response(jsonEncode({'links': links}), 200);
    }
    if (path.endsWith('/v1/messaging/link-proofs')) {
      final kind = (jsonDecode(request.body) as Map)['kind'];
      return http.Response(
        jsonEncode({
          'proof': kind == 'code' ? '9F2C4A7B1D3E5F60A1B2C3D4E5F6A7B8' : 'r8Kq2vXbT0nW5yLm3pZc7sJd',
          'kind': kind,
          'expires_at': DateTime.now().toUtc().add(const Duration(minutes: 9, seconds: 12)).toIso8601String(),
        }),
        200,
      );
    }
    return http.Response('{"status":"updated"}', 200);
  }

  MessagingChannelsProvider provider({ChatAppsConfig config = _config}) =>
      MessagingChannelsProvider(api: MessagingChannelsApi(send: send), readConfig: () async => config);
}

class _Online extends ChangeNotifier implements ConnectivityProvider {
  _Online(this.isConnected);

  @override
  final bool isConnected;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

UsageProvider _usage(PlanType plan) {
  final subscription = UserSubscriptionResponse(
    subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  );
  return UsageProvider(subscriptionRequest: () async => subscription)..debugSetSubscription(subscription);
}

Future<_Messaging> _pumpChatApps(
  AuditRun a, {
  void Function(_Messaging)? seed,
  PlanType plan = PlanType.architect,
  bool online = true,
  ChatAppsConfig config = _config,
  Widget? page,
}) async {
  chatAppLauncher = (_) async => true;
  ChannelLinkWaiter.interval = const Duration(milliseconds: 200);
  final messaging = _Messaging();
  seed?.call(messaging);
  final provider = messaging.provider(config: config);
  await a.tester.runAsync(provider.load);
  await a.pump(page ?? const ChatAppsPage(), providers: [
    ChangeNotifierProvider<MessagingChannelsProvider>.value(value: provider),
    ChangeNotifierProvider<UsageProvider>.value(value: _usage(plan)),
    ChangeNotifierProvider<ConnectivityProvider>.value(value: _Online(online)),
  ]);
  return messaging;
}

ChatSessionsApi _sessionsApi() => ChatSessionsApi(
      fallback: (_) {},
      send: (request) async {
        final path = Uri.parse(request.url).path;
        if (path.endsWith('/v2/chat-sessions')) {
          return http.Response(
            jsonEncode([
              for (final (id, title, preview) in [
                ('s1', 'Offsite planning', 'Added "Draft offsite agenda", due Friday.'),
                ('s2', 'Sam is vegetarian', 'Saved to your memories: Sam is vegetarian.'),
              ])
                {
                  'id': id,
                  'title': title,
                  'preview': preview,
                  'created_at': '2026-10-10T18:00:00Z',
                  'updated_at': '2026-10-10T18:04:00Z',
                  'message_count': 4,
                  'channel': 'telegram',
                  'channel_link_id': _linkTelegram,
                },
              {
                'id': 'app',
                'title': 'Ask Omi chat',
                'created_at': '2026-10-10T09:00:00Z',
                'updated_at': '2026-10-10T09:00:00Z',
                'message_count': 2,
              },
            ]),
            200,
          );
        }
        final rows = [
          ('m4', 'ai', 'Added "Draft offsite agenda", due Friday.'),
          ('m3', 'human', 'add that as a task for friday'),
          (
            'm2',
            'ai',
            'From your chat in the Omi app this morning: Lisbon, the week of Nov 9. '
                'You said you would draft the agenda.'
          ),
          ('m1', 'human', 'what did we land on for the offsite'),
        ];
        return http.Response(
          jsonEncode([
            for (final (id, sender, text) in rows)
              {'id': id, 'created_at': '2026-10-10T18:0${id[1]}:00Z', 'text': text, 'sender': sender, 'type': 'text'},
          ]),
          200,
        );
      },
    );

const _state = 'Pro (Architect) account; mobile-chat-apps on with Telegram and iMessage addresses';

final chatAppsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'chat-apps-entry',
    title: 'Integrations › Chat apps entry',
    page: 'lib/pages/settings/chat_apps/chat_apps_page.dart (ChatAppsIntegrationsEntry)',
    state: _state,
    run: (a) async {
      await _pumpChatApps(
        a,
        page: const SingleChildScrollView(
          padding: EdgeInsets.symmetric(horizontal: 20, vertical: 60),
          child: ChatAppsIntegrationsEntry(),
        ),
      );
      await a.shot('The Chat apps group at the top of Integrations');
    },
  ),
  AuditScenario(
    id: 'chat-apps-page',
    title: 'Chat apps › nothing connected',
    page: 'lib/pages/settings/chat_apps/chat_apps_page.dart (ChatAppsPage)',
    state: '$_state; no links',
    run: (a) async {
      await _pumpChatApps(a);
      await a.scrollSeries('Chat apps page');
    },
  ),
  AuditScenario(
    id: 'chat-apps-telegram',
    title: 'Chat apps › connect Telegram',
    page: 'lib/pages/settings/chat_apps/telegram_connect_sheet.dart (TelegramConnectSheet)',
    state: '$_state; the link arrives while waiting',
    run: (a) async {
      final messaging = await _pumpChatApps(a);
      await a.tap(find.byKey(const ValueKey('chat_apps_row_telegram')));
      await a.shot('Connect Telegram sheet', step: 'sheet');
      await a.tap(find.byKey(const ValueKey('chat_apps_open_telegram')));
      await a.shot('After Open Telegram: waiting for Start', step: 'waiting');
      messaging.link('telegram', 'yourname');
      await a.tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 300)));
      await a.tester.pump(const Duration(milliseconds: 250));
      await a.settle();
      await a.tester.pumpAndSettle();
      await a.shot('Telegram connected', step: 'connected');
    },
  ),
  AuditScenario(
    id: 'chat-apps-imessage',
    title: 'Chat apps › connect iMessage',
    page: 'lib/pages/settings/chat_apps/imessage_connect_sheet.dart (IMessageConnectSheet)',
    state: '$_state; a one-time code minted',
    run: (a) async {
      await _pumpChatApps(a);
      await a.tap(find.byKey(const ValueKey('chat_apps_row_imessage')));
      await a.shot('Text Omi to connect', step: 'sheet');
      await a.tap(find.byKey(const ValueKey('chat_apps_open_messages')));
      await a.shot('Waiting for your text', step: 'waiting');
    },
  ),
  AuditScenario(
    id: 'chat-apps-manage',
    title: 'Chat apps › manage Telegram',
    page: 'lib/pages/settings/chat_apps/channel_settings_page.dart (ChannelSettingsPage)',
    state: '$_state; Telegram linked as @yourname, show in app off',
    run: (a) async {
      await _pumpChatApps(
        a,
        seed: (m) => m.link('telegram', 'yourname'),
        page: const ChannelSettingsPage(linkId: _linkTelegram),
      );
      await a.scrollSeries('Manage Telegram');
      await a.tester.scrollUntilVisible(find.byKey(const ValueKey('chat_apps_disconnect')), 200);
      await a.tap(find.byKey(const ValueKey('chat_apps_disconnect')));
      await a.shot('Disconnect confirmation', step: 'confirm');
    },
  ),
  AuditScenario(
    id: 'chat-apps-connected',
    title: 'Chat apps › Telegram connected, iMessage not',
    page: 'lib/pages/settings/chat_apps/chat_apps_page.dart (ChatAppsPage)',
    state: '$_state; Telegram linked',
    run: (a) async {
      await _pumpChatApps(a, seed: (m) => m.link('telegram', 'yourname'));
      await a.scrollSeries('Chat apps with Telegram connected');
    },
  ),
  AuditScenario(
    id: 'chat-apps-whatsapp',
    title: 'Chat apps › WhatsApp waitlist',
    page: 'lib/pages/settings/chat_apps/whatsapp_waitlist_sheet.dart (WhatsAppWaitlistSheet)',
    state: _state,
    run: (a) async {
      await _pumpChatApps(a);
      await a.tap(find.byKey(const ValueKey('chat_apps_row_whatsapp')));
      await a.shot('WhatsApp is coming');
    },
  ),
  AuditScenario(
    id: 'chat-apps-free',
    title: 'Chat apps › free plan',
    page: 'lib/pages/settings/chat_apps/chat_apps_page.dart (ChatAppsPage)',
    state: 'Free (basic) account; mobile-chat-apps on',
    run: (a) async {
      await _pumpChatApps(a, plan: PlanType.basic);
      await a.scrollSeries('Chat apps locked behind Pro');
    },
  ),
  AuditScenario(
    id: 'chat-apps-offline',
    title: 'Chat apps › offline',
    page: 'lib/pages/settings/chat_apps/chat_apps_page.dart (ChatAppsPage)',
    state: '$_state; no network',
    run: (a) async {
      await _pumpChatApps(a, online: false);
      await a.shot('Offline notice above the rows');
    },
  ),
  AuditScenario(
    id: 'chat-apps-history',
    title: 'Chat apps › Telegram chats in the Omi app',
    page: 'lib/pages/settings/chat_apps/channel_chats_page.dart (ChannelChatsPage)',
    state: '$_state; Telegram linked with show in app on; two Telegram sessions and one app chat',
    run: (a) async {
      await _pumpChatApps(
        a,
        seed: (m) => m.link('telegram', 'yourname', visible: true),
        page: ChannelChatsPage(linkId: _linkTelegram, api: _sessionsApi()),
      );
      await a.shot('Telegram chats, read-only', step: 'list');
      await a.tap(find.text('Offsite planning'));
      await a.shot('A Telegram chat, read-only', step: 'transcript');
    },
  ),
];
