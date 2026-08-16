import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';

void main() {
  group('CustomSttConfig privacy policy migration', () {
    test('missing or unknown providers are rejected instead of becoming Omi', () {
      expect(() => CustomSttConfig.fromJson({}), throwsFormatException);
      expect(() => CustomSttConfig.fromJson({'provider': 'bogus'}), throwsFormatException);
    });

    test('legacy config without a field keeps full forwarding', () {
      final config = CustomSttConfig.fromJson({'provider': 'customLive'});

      expect(config.privacyPolicy, SttPrivacyPolicy.full);
      expect(config.forwardsRawAudioToOmi, isTrue);
    });

    test('legacy send_raw_audio_to_omi false migrates to transcriptOnly', () {
      final config = CustomSttConfig.fromJson({'provider': 'customLive', 'send_raw_audio_to_omi': false});

      expect(config.privacyPolicy, SttPrivacyPolicy.transcriptOnly);
      expect(config.forwardsRawAudioToOmi, isFalse);
    });

    test('legacy send_raw_audio_to_omi true migrates to full', () {
      final config = CustomSttConfig.fromJson({'provider': 'customLive', 'send_raw_audio_to_omi': true});

      expect(config.privacyPolicy, SttPrivacyPolicy.full);
    });

    test('explicit privacy_policy takes precedence over the legacy boolean', () {
      for (final policy in SttPrivacyPolicy.values) {
        final config = CustomSttConfig.fromJson({
          'provider': 'customLive',
          'privacy_policy': policy.name,
          'send_raw_audio_to_omi': policy == SttPrivacyPolicy.full ? false : true,
        });

        expect(config.privacyPolicy, policy);
      }
    });

    test('unknown privacy_policy fails privacy-closed to localOnly', () {
      final config = CustomSttConfig.fromJson({
        'provider': 'customLive',
        'privacy_policy': 'not_a_real_policy',
        'send_raw_audio_to_omi': true,
      });

      expect(config.privacyPolicy, SttPrivacyPolicy.localOnly);
      expect(config.forwardsRawAudioToOmi, isFalse);
    });

    test('invalid privacy_policy types fail privacy-closed', () {
      final config = CustomSttConfig.fromJson({
        'provider': 'customLive',
        'privacy_policy': 42,
        'send_raw_audio_to_omi': true,
      });

      expect(config.privacyPolicy, SttPrivacyPolicy.localOnly);
    });

    test('toJson dual-writes typed and legacy forwarding fields', () {
      for (final policy in SttPrivacyPolicy.values) {
        final config = CustomSttConfig(provider: SttProvider.customLive, privacyPolicy: policy);
        final json = config.toJson();

        expect(json['privacy_policy'], policy.name);
        expect(json['send_raw_audio_to_omi'], policy == SttPrivacyPolicy.full);
        expect(CustomSttConfig.fromJson(json).privacyPolicy, policy);
      }
    });

    test('privacy policy participates in the socket identity', () {
      final full = CustomSttConfig.fromJson({'provider': 'customLive', 'privacy_policy': 'full'});
      final transcriptOnly = CustomSttConfig.fromJson({'provider': 'customLive', 'privacy_policy': 'transcriptOnly'});
      final localOnly = CustomSttConfig.fromJson({'provider': 'customLive', 'privacy_policy': 'localOnly'});

      expect(full.sttConfigId, isNot(transcriptOnly.sttConfigId));
      expect(transcriptOnly.sttConfigId, isNot(localOnly.sttConfigId));
      expect(full.sttConfigId, isNot(localOnly.sttConfigId));
    });

    test('copyWith preserves or changes the typed policy', () {
      const config = CustomSttConfig(provider: SttProvider.customLive, privacyPolicy: SttPrivacyPolicy.transcriptOnly);

      expect(config.copyWith().privacyPolicy, SttPrivacyPolicy.transcriptOnly);
      expect(config.copyWith(privacyPolicy: SttPrivacyPolicy.localOnly).privacyPolicy, SttPrivacyPolicy.localOnly);
    });
  });
}
