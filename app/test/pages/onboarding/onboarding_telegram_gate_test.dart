import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/pages/onboarding/chat_on_telegram_step.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import '../settings/chat_apps/chat_apps_fixture.dart';

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));
  setUp(initChatAppsTest);

  Future<MessagingChannelsProvider> provider({
    ChatAppsConfig config = chatAppsOn,
    List<Map<String, dynamic>> links = const [],
  }) async {
    final backend = FakeMessagingBackend()..links = [...links];
    final provider = backend.provider(config: config);
    await provider.load();
    return provider;
  }

  group('shouldOfferTelegramInvite', () {
    test('offers when the channel is on, has an endpoint, and is unlinked', () async {
      expect(shouldOfferTelegramInvite(await provider()), isTrue);
    });

    test('no offer when the entry is hidden (flag off, nothing linked)', () async {
      final p = await provider(config: ChatAppsConfig.off);
      expect(p.showEntry, isFalse);
      expect(shouldOfferTelegramInvite(p), isFalse);
    });

    test('no offer when Telegram has no usable endpoint', () async {
      final p = await provider(config: const ChatAppsConfig(enabled: true));
      expect(p.showEntry, isTrue);
      expect(p.config.endpoint(ChatChannel.telegram), isNull);
      expect(shouldOfferTelegramInvite(p), isFalse);
    });

    test('no offer when Telegram is already linked', () async {
      final p = await provider(links: [linkJson(id: linkIdTelegram, channel: 'telegram')]);
      expect(p.linkFor(ChatChannel.telegram), isNotNull);
      expect(shouldOfferTelegramInvite(p), isFalse);
    });
  });
}
