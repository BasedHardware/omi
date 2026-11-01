import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';

void main() {
  test('configs without parser overrides retain their persisted legacy identity', () {
    // Historical hash input before parser fields joined the identity. Preserve
    // IDs saved by released clients, including paywall-selected on-device STT.
    const legacyInput = {
      'api_key': null,
      'language': null,
      'model': null,
      'url': null,
      'host': null,
      'port': null,
      'request_type': null,
      'headers': null,
      'params': null,
      'send_raw_audio_to_omi': true,
    };
    final legacyHash = jsonEncode(legacyInput).hashCode.abs().toRadixString(16).padLeft(8, '0').substring(0, 8);
    const config = CustomSttConfig(provider: SttProvider.onDeviceWhisper);
    expect(config.sttConfigId, 'onDeviceWhisper:$legacyHash');
    expect(CustomSttConfig.fromJson(config.toJson()).sttConfigId, config.sttConfigId);
  });

  test('response parser edits change the live config identity', () {
    const before = CustomSttConfig(provider: SttProvider.deepgramLive, schemaJson: {'text_path': 'before'});
    const after = CustomSttConfig(provider: SttProvider.deepgramLive, schemaJson: {'text_path': 'after'});
    expect(before.sttConfigId, isNot(after.sttConfigId));
  });

  test('audio field edits change the batch config identity', () {
    const before = CustomSttConfig(provider: SttProvider.custom, audioFieldName: 'audio');
    const after = CustomSttConfig(provider: SttProvider.custom, audioFieldName: 'file');
    expect(before.sttConfigId, isNot(after.sttConfigId));
  });

  group('CustomSttConfig raw audio forwarding', () {
    test('legacy configs keep forwarding raw audio to Omi', () {
      final config = CustomSttConfig.fromJson({'provider': 'customLive'});

      expect(config.toJson()['send_raw_audio_to_omi'], isTrue);
    });

    test('disabled forwarding survives a JSON round trip', () {
      final config = CustomSttConfig.fromJson({'provider': 'customLive', 'send_raw_audio_to_omi': false});

      expect(config.toJson()['send_raw_audio_to_omi'], isFalse);
    });

    test('forwarding policy participates in the config identity', () {
      final forwarding = CustomSttConfig.fromJson({'provider': 'customLive', 'send_raw_audio_to_omi': true});
      final transcriptOnly = CustomSttConfig.fromJson({'provider': 'customLive', 'send_raw_audio_to_omi': false});

      expect(forwarding.sttConfigId, isNot(transcriptOnly.sttConfigId));
    });

    test('identity override is the socket id without entering JSON', () {
      const config = CustomSttConfig(
        provider: SttProvider.onDeviceWhisper,
        identity: 'freemium:on-device',
      );

      expect(config.sttConfigId, 'freemium:on-device');
      expect(config.toJson().containsKey('identity'), isFalse);
    });
  });
}
