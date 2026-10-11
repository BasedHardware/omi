import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import '../pages/settings/chat_apps/chat_apps_fixture.dart';

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));
  setUp(initChatAppsTest);

  group('ChatAppsConfig', () {
    test('off when the flag is off, whatever the payload', () {
      final config = ChatAppsConfig.fromPayload(
        enabled: false,
        payload: {'telegram': {}},
      );
      expect(config.enabled, isFalse);
      expect(config.endpoint(ChatChannel.telegram), isNull);
    });

    test('reads a map or a JSON string payload', () {
      const payload = {
        'telegram': {'provider': 'telegram', 'address': '@OmiBot'},
        'imessage': {'provider': 'linq', 'address': ' +15550100100 '},
      };
      for (final value in [payload, jsonEncode(payload)]) {
        final config = ChatAppsConfig.fromPayload(
          enabled: true,
          payload: value,
        );
        expect(config.endpoint(ChatChannel.telegram)?.address, '@OmiBot');
        expect(config.endpoint(ChatChannel.imessage)?.address, '+15550100100');
        expect(config.endpoint(ChatChannel.imessage)?.provider, 'linq');
      }
    });

    test(
      'a malformed payload or bad provider id offers no channel but stays on',
      () {
        for (final payload in [
          'not json',
          null,
          {
            'telegram': {'provider': 'Tele Gram', 'address': 'x'},
          },
          {
            'telegram': {'provider': 'telegram', 'address': ' '},
          },
        ]) {
          final config = ChatAppsConfig.fromPayload(
            enabled: true,
            payload: payload,
          );
          expect(config.enabled, isTrue);
          expect(
            config.endpoint(ChatChannel.telegram),
            isNull,
            reason: '$payload',
          );
        }
      },
    );

    test('the gate fails closed when the flag read throws', () async {
      final config = await ChatAppsGate.read(
        readFlag: (_) async => throw StateError('no identity'),
      );
      expect(config.enabled, isFalse);
    });

    test('a minted deep link wins and the flag address is the fallback', () {
      final fromApi = chatAppProofUri(
        channel: ChatChannel.telegram,
        endpoint: telegramEndpoint,
        deepLink: 'https://t.me/ServerBot?start=tok',
        startToken: 'ignored',
        platform: TargetPlatform.iOS,
      );
      expect(fromApi.toString(), 'https://t.me/ServerBot?start=tok');
      final fallback = chatAppProofUri(
        channel: ChatChannel.telegram,
        endpoint: telegramEndpoint,
        startToken: 'tok',
        platform: TargetPlatform.iOS,
      );
      expect(fallback.toString(), 'https://t.me/OmiBot?start=tok');
      final number = chatAppProofUri(
        channel: ChatChannel.imessage,
        endpoint: imessageEndpoint,
        address: '+19995550100',
        body: 'code',
        platform: TargetPlatform.iOS,
      );
      expect(number.toString(), contains('+19995550100'));
    });

    test('the gate passes the flag key to both reads', () async {
      final keys = <String>[];
      final config = await ChatAppsGate.read(
        readFlag: (key) async {
          keys.add(key);
          return true;
        },
        readPayload: (key) async {
          keys.add(key);
          return {
            'telegram': {'provider': 'telegram', 'address': 'OmiBot'},
          };
        },
      );
      expect(keys, [ChatAppsGate.enabledFlag, ChatAppsGate.enabledFlag]);
      expect(config.endpoint(ChatChannel.telegram)?.address, 'OmiBot');
    });
  });

  group('ChannelLink.handle', () {
    ChannelLink link(String channel, String externalId) => ChannelLink(
          id: 'x',
          channelId: channel,
          provider: 'p',
          externalId: externalId,
          linkedAt: DateTime(2026),
        );

    test(
      'a Telegram username gets an @; a numeric Telegram id has no handle',
      () {
        expect(link('telegram', 'sam').handle, '@sam');
        expect(link('telegram', '@sam').handle, '@sam');
        expect(link('telegram', '123456789').handle, isNull);
      },
    );

    test('iMessage shows the number as stored', () {
      expect(link('imessage', '+15550100').handle, '+15550100');
    });

    test('a stored Telegram username wins over the numeric id', () {
      final linked = ChannelLink(
        id: 'x',
        channelId: 'telegram',
        provider: 'p',
        externalId: '123456789',
        linkedAt: DateTime(2026),
        displayHandle: 'sam',
      );
      expect(linked.handle, '@sam');
    });
  });

  group('MessagingChannelsProvider', () {
    test('shows the entry when on, or when a link exists while off', () async {
      final backend = FakeMessagingBackend();
      final off = backend.provider(config: ChatAppsConfig.off);
      await off.load();
      expect(off.showEntry, isFalse);

      backend.links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
      await off.load();
      expect(off.showEntry, isTrue, reason: 'Disconnect stays reachable');

      final on = FakeMessagingBackend().provider();
      await on.load();
      expect(on.showEntry, isTrue);
    });

    test(
      'a failed refresh keeps the known links and reports the problem',
      () async {
        final backend = FakeMessagingBackend()..links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
        final provider = backend.provider();
        await provider.load();
        backend.statusFor['GET v1/messaging/links'] = 503;
        final result = await provider.refreshLinks();
        expect(result, isA<ApiFailure<List<ChannelLink>>>());
        expect(provider.links, hasLength(1));
        expect(provider.linksProblem?.kind, ApiProblemKind.server);
      },
    );

    test('mint posts channel, provider and kind; 403 is forbidden', () async {
      final backend = FakeMessagingBackend();
      final provider = backend.provider();
      await provider.load();
      final ok = await provider.mintProof(ChatChannel.imessage, kind: 'code');
      expect(ok, isA<ApiSuccess>());
      final body = jsonDecode(backend.requests.last.body);
      expect(body, {'channel': 'imessage', 'provider': 'linq', 'kind': 'code'});

      backend.statusFor['POST v1/messaging/link-proofs'] = 403;
      final denied = await provider.mintProof(
        ChatChannel.telegram,
        kind: 'token',
      );
      expect((denied as ApiFailure).problem.kind, ApiProblemKind.forbidden);
    });

    test('mint is refused locally for a channel without an address', () async {
      final backend = FakeMessagingBackend();
      final provider = backend.provider(
        config: const ChatAppsConfig(enabled: true),
      );
      await provider.load();
      final result = await provider.mintProof(
        ChatChannel.telegram,
        kind: 'token',
      );
      expect((result as ApiFailure).problem.kind, ApiProblemKind.forbidden);
      expect(backend.count('POST', 'v1/messaging/link-proofs'), 0);
    });

    test('unlink removes the link; a 404 counts as already gone', () async {
      final backend = FakeMessagingBackend()
        ..links = [
          linkJson(id: linkIdTelegram, channel: 'telegram'),
          linkJson(id: linkIdIMessage, channel: 'imessage'),
        ];
      final provider = backend.provider();
      await provider.load();
      expect(
        await provider.unlink(provider.linkFor(ChatChannel.telegram)!),
        isA<ApiSuccess>(),
      );
      expect(provider.linkFor(ChatChannel.telegram), isNull);

      final stale = provider.linkFor(ChatChannel.imessage)!;
      backend.links.clear();
      expect(await provider.unlink(stale), isA<ApiSuccess>());
      expect(provider.links, isEmpty);
    });

    test('a failed unlink keeps the link', () async {
      final backend = FakeMessagingBackend()..links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
      final provider = backend.provider();
      await provider.load();
      backend.statusFor['DELETE v1/messaging/links'] = 500;
      expect(await provider.unlink(provider.links.single), isA<ApiFailure>());
      expect(provider.links, hasLength(1));
    });

    test('show-in-app applies at once and reverts when refused', () async {
      final backend = FakeMessagingBackend()..links = [linkJson(id: linkIdTelegram, channel: 'telegram')];
      final provider = backend.provider();
      await provider.load();
      await provider.setVisibleInApp(provider.links.single, true);
      expect(provider.links.single.visibleInApp, isTrue);
      expect(jsonDecode(backend.requests.last.body), {'visible_in_app': true});

      backend.statusFor['PATCH v1/messaging/links'] = 500;
      await provider.setVisibleInApp(provider.links.single, false);
      expect(provider.links.single.visibleInApp, isTrue);
    });

    test('the WhatsApp waitlist is remembered on the device', () async {
      final provider = FakeMessagingBackend().provider();
      expect(provider.whatsAppWaitlisted, isFalse);
      await provider.joinWhatsAppWaitlist();
      expect(provider.whatsAppWaitlisted, isTrue);
    });
  });

  group('deep links', () {
    test('Telegram opens t.me with the start token', () {
      final uri = chatAppUri(
        ChatChannel.telegram,
        const ChatChannelEndpoint(provider: 'telegram', address: '@OmiBot'),
        startToken: 'tok_1-_x',
        platform: TargetPlatform.iOS,
      );
      expect(uri.toString(), 'https://t.me/OmiBot?start=tok_1-_x');
    });

    test(
      'iMessage prefills the body with the platform separator and %20 spaces',
      () {
        const endpoint = ChatChannelEndpoint(
          provider: 'linq',
          address: '+1 (555) 010-0100',
        );
        expect(
          chatAppUri(
            ChatChannel.imessage,
            endpoint,
            body: 'Hi Omi, link code AB12',
            platform: TargetPlatform.iOS,
          ).toString(),
          'sms:+15550100100&body=Hi%20Omi%2C%20link%20code%20AB12',
        );
        expect(
          chatAppUri(
            ChatChannel.imessage,
            endpoint,
            body: 'x y',
            platform: TargetPlatform.android,
          ).toString(),
          'sms:+15550100100?body=x%20y',
        );
      },
    );

    test('codes are grouped by four for reading', () {
      expect(groupedLinkCode('9F2C4A7B1D'), '9F2C 4A7B 1D');
    });
  });

  group('ChatSessionSummary channel fields', () {
    Map<String, dynamic> row(Map<String, dynamic> extra) => {
          'id': 's1',
          'title': 'Hi',
          'updated_at': '2026-10-10T12:00:00Z',
          'message_count': 2,
          ...extra,
        };

    test('a channel session carries its channel and link', () {
      final session = ChatSessionSummary.fromJson(
        row({'channel': 'telegram', 'channel_link_id': linkIdTelegram}),
      );
      expect(session.isChannelSession, isTrue);
      expect(session.channel, 'telegram');
      expect(session.channelLinkId, linkIdTelegram);
    });

    test('an app session has neither', () {
      final session = ChatSessionSummary.fromJson(row({'channel': 'telegram'}));
      expect(session.isChannelSession, isFalse);
      expect(session.channel, isNull);
    });
  });
}
