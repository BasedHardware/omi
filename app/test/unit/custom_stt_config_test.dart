import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/custom_stt_config.dart';

void main() {
  group('CustomSttConfig raw audio forwarding', () {
    test('legacy configs keep forwarding raw audio to Omi', () {
      final config = CustomSttConfig.fromJson({'provider': 'customLive'});

      expect(config.toJson()['send_raw_audio_to_omi'], isTrue);
    });

    test('disabled forwarding survives a JSON round trip', () {
      final config = CustomSttConfig.fromJson({
        'provider': 'customLive',
        'send_raw_audio_to_omi': false,
      });

      expect(config.toJson()['send_raw_audio_to_omi'], isFalse);
    });

    test('forwarding policy participates in the config identity', () {
      final forwarding = CustomSttConfig.fromJson({
        'provider': 'customLive',
        'send_raw_audio_to_omi': true,
      });
      final transcriptOnly = CustomSttConfig.fromJson({
        'provider': 'customLive',
        'send_raw_audio_to_omi': false,
      });

      expect(forwarding.sttConfigId, isNot(transcriptOnly.sttConfigId));
    });
  });
}
