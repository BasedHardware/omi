import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/chat_apps_gate.dart';

void main() {
  final payload = {
    'telegram': {'provider': 'telegram', 'address': 'test_bot'},
    'imessage': {'provider': 'test', 'address': '+10000000000'},
  };

  test('public key exposes only Telegram even if its payload includes private channels', () async {
    final config = await ChatAppsGate.read(
      readFlag: (key) async => key == ChatAppsGate.enabledFlag,
      readPayload: (_) async => payload,
    );
    expect(config.enabled, isTrue);
    expect(config.endpoints.keys, [ChatChannel.telegram]);
  });

  test('separate allowlist key selects all-channels payload', () async {
    final keys = <String>[];
    final config = await ChatAppsGate.read(
        readFlag: (key) async => key == ChatAppsGate.enabledFlag || key == ChatAppsGate.allChannelsFlag,
        readPayload: (key) async {
          keys.add(key);
          return payload;
        });
    expect(keys, [ChatAppsGate.allChannelsFlag]);
    expect(config.endpoints.keys, [ChatChannel.telegram, ChatChannel.imessage]);
  });

  test('absent or failed store remains off', () async {
    expect((await ChatAppsGate.read(readFlag: (_) async => false)).enabled, isFalse);
    expect((await ChatAppsGate.read(readFlag: (_) async => throw StateError('offline'))).enabled, isFalse);
  });

  test('public switch disables private channels too', () async {
    var payloadRead = false;
    final config = await ChatAppsGate.read(
      readFlag: (key) async => key == ChatAppsGate.allChannelsFlag,
      readPayload: (_) async {
        payloadRead = true;
        return payload;
      },
    );
    expect(config.enabled, isFalse);
    expect(payloadRead, isFalse);
  });
}
