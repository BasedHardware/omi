import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/sockets/transcription_service.dart';

const _default = CustomSttConfig.defaultConfig;

const _custom = CustomSttConfig(
  provider: SttProvider.deepgramLive,
  apiKey: 'dg-user-key',
  url: 'wss://api.deepgram.com/v1/listen',
);

TranscriptionAllowanceSnapshot _allowance(String mode, {String reason = 'test'}) {
  return TranscriptionAllowanceSnapshot(mode: mode, reason: reason, remainingSeconds: 0);
}

CustomSttConfig _onDevice() {
  return const CustomSttConfig(
    provider: SttProvider.onDeviceWhisper,
    language: 'en',
    identity: SttModeResolver.freemiumOnDeviceId,
  );
}

SttModeDecision _resolve({
  bool flag = true,
  CustomSttConfig persisted = _default,
  TranscriptionAllowanceSnapshot? allowance,
  FreemiumReadiness readiness = FreemiumReadiness.ready,
  BleAudioCodec codec = BleAudioCodec.opus,
}) {
  return SttModeResolver(
    onDeviceConfigBuilder: _onDevice,
  ).resolve(
    flagEnabled: flag,
    persistedCustomStt: persisted,
    allowance: allowance,
    readiness: readiness,
    codec: codec,
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('SttModeResolver matrix', () {
    test('flag off keeps today\'s managed path even for basic on_device', () {
      final decision = _resolve(
        flag: false,
        allowance: _allowance('on_device', reason: 'plan_allowance_exhausted'),
      );
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.opensManagedOmiSocket, isTrue);
      expect(decision.reason, 'flag_off');
    });

    test('explicit custom STT is honored before allowance', () {
      final decision = _resolve(
        persisted: _custom,
        allowance: _allowance('on_device', reason: 'plan_allowance_exhausted'),
      );
      expect(decision.path, SttResolvedPath.honorCustom);
      expect(decision.customSttConfig?.provider, SttProvider.deepgramLive);
      expect(decision.customSttConfig?.apiKey, 'dg-user-key');
      expect(decision.opensManagedOmiSocket, isFalse);
    });

    for (final case_ in [
      ('no-subscription / cache-miss', null, 'allowance_unavailable'),
      (
        'basic under cap still on_device from S16 inactive/exhausted shapes',
        _allowance('on_device', reason: 'subscription_inactive'),
        'subscription_inactive'
      ),
      ('basic over cap', _allowance('on_device', reason: 'plan_allowance_exhausted'), 'plan_allowance_exhausted'),
    ]) {
      test('iOS ready + ${case_.$1} ⇒ on-device, managed unreachable', () {
        final decision = _resolve(allowance: case_.$2, readiness: FreemiumReadiness.ready);
        expect(decision.path, SttResolvedPath.onDevice);
        expect(decision.opensManagedOmiSocket, isFalse);
        expect(decision.customSttConfig?.sttConfigId, SttModeResolver.freemiumOnDeviceId);
        expect(decision.reason, case_.$3);
      });

      test('Android not ready + ${case_.$1} ⇒ blocked, managed unreachable', () {
        final decision = _resolve(allowance: case_.$2, readiness: FreemiumReadiness.requiresSetup);
        expect(decision.path, SttResolvedPath.blocked);
        expect(decision.opensManagedOmiSocket, isFalse);
        expect(decision.blockSocket, isTrue);
        expect(decision.reason, 'on_device_not_ready');
      });
    }

    test('plus / managed stays on the Omi socket', () {
      final decision = _resolve(allowance: _allowance('managed', reason: 'plan_within_allowance'));
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.opensManagedOmiSocket, isTrue);
    });

    test('unlimited / plan_unlimited stays managed', () {
      final decision = _resolve(allowance: _allowance('managed', reason: 'plan_unlimited'));
      expect(decision.opensManagedOmiSocket, isTrue);
    });

    test('BYOK reason is managed (user key rides the server BYOK path)', () {
      final decision = _resolve(allowance: _allowance('managed', reason: 'byok'));
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.reason, 'byok');
    });

    test('trial-paywalled is blocked', () {
      final decision = _resolve(allowance: _allowance('blocked', reason: 'trial_paywalled'));
      expect(decision.path, SttResolvedPath.blocked);
      expect(decision.opensManagedOmiSocket, isFalse);
    });

    test('unsupported codec + on_device blocks instead of Omi fallback', () {
      final decision = _resolve(
        allowance: _allowance('on_device', reason: 'plan_allowance_exhausted'),
        codec: BleAudioCodec.aac,
      );
      expect(decision.path, SttResolvedPath.blocked);
      expect(decision.reason, 'unsupported_codec_on_device');
      expect(decision.opensManagedOmiSocket, isFalse);
    });

    test('unknown allowance mode fails closed', () {
      final decision = _resolve(allowance: _allowance('surprise', reason: 'future'));
      expect(decision.opensManagedOmiSocket, isFalse);
      expect(decision.path, SttResolvedPath.onDevice);
    });
  });

  group('shouldBlockUnsupportedCodecFallback S17', () {
    test('on_device allowance blocks an unsupported codec even without a custom config', () {
      expect(
        TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(
          BleAudioCodec.aac,
          null,
          allowanceOnDevice: true,
        ),
        isTrue,
      );
    });

    test('supported pendant codecs still pass on_device', () {
      expect(
        TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(
          BleAudioCodec.opus,
          null,
          allowanceOnDevice: true,
        ),
        isFalse,
      );
    });
  });

  group('subscription wire plumbs S16 allowance', () {
    test('UserSubscriptionResponse.roundtrips transcription_allowance', () {
      final response = UserSubscriptionResponse(
        subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 18000,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        transcriptionAllowance: const TranscriptionAllowanceSnapshot(
          mode: 'on_device',
          reason: 'plan_allowance_exhausted',
          remainingSeconds: 0,
        ),
      );

      final decoded = UserSubscriptionResponse.fromJson(response.toJson());
      expect(decoded.transcriptionAllowance?.mode, 'on_device');
      expect(decoded.transcriptionAllowance?.reason, 'plan_allowance_exhausted');
    });
  });
}
