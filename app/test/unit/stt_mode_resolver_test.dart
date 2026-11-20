import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/free_tier_on_device_stt_flag.dart';
import 'package:omi/services/capture/on_device_stt_preparer.dart';
import 'package:omi/services/capture/phone_transcription_choice.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/services/experiments/free_tier_on_device_stt_gate.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/sockets/transcription_service.dart';

const _default = CustomSttConfig.defaultConfig;

const atCapSnapshot =
    TranscriptionAllowanceSnapshot(mode: 'on_device', reason: 'plan_allowance_exhausted', remainingSeconds: 0);

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
    sendRawAudioToOmi: false,
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
      ('inactive subscription', _allowance('on_device', reason: 'subscription_inactive'), 'subscription_inactive'),
      ('basic over cap', _allowance('on_device', reason: 'plan_allowance_exhausted'), 'plan_allowance_exhausted'),
    ]) {
      test('ready + ${case_.$1} ⇒ on-device, managed unreachable', () {
        final decision = _resolve(allowance: case_.$2, readiness: FreemiumReadiness.ready);
        expect(decision.path, SttResolvedPath.onDevice);
        expect(decision.opensManagedOmiSocket, isFalse);
        expect(decision.customSttConfig?.sttConfigId, SttModeResolver.freemiumOnDeviceId);
        expect(decision.customSttConfig?.sendRawAudioToOmi, isFalse);
        expect(decision.reason, case_.$3);
      });

      test('not ready + ${case_.$1} ⇒ today\'s Omi socket, never blocked', () {
        final decision = _resolve(allowance: case_.$2, readiness: FreemiumReadiness.requiresSetup);
        expect(decision.path, SttResolvedPath.managed);
        expect(decision.blockSocket, isFalse);
        expect(decision.allowanceOnDevice, isFalse);
        expect(decision.reason, SttModeResolver.reasonNotReady);
      });
    }

    test('no snapshot yet ⇒ today\'s Omi socket (paid users never land on-device at cold start)', () {
      final decision = _resolve(allowance: null);
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.reason, SttModeResolver.reasonAllowanceUnknown);
    });

    for (final reason in ['allowance_unavailable', 'usage_invalid']) {
      test('transient on_device reason $reason ⇒ Omi socket, not on-device', () {
        final decision = _resolve(allowance: _allowance('on_device', reason: reason));
        expect(decision.path, SttResolvedPath.managed);
        expect(decision.reason, reason);
      });
    }

    test('on-device config unavailable ⇒ Omi socket', () {
      final decision = SttModeResolver(onDeviceConfigBuilder: () => null).resolve(
        flagEnabled: true,
        persistedCustomStt: _default,
        allowance: _allowance('on_device', reason: 'plan_allowance_exhausted'),
        readiness: FreemiumReadiness.ready,
        codec: BleAudioCodec.opus,
      );
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.reason, SttModeResolver.reasonConfigUnavailable);
    });

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

    test('unsupported codec + on_device keeps today\'s Omi socket', () {
      final decision = _resolve(
        allowance: _allowance('on_device', reason: 'plan_allowance_exhausted'),
        codec: BleAudioCodec.aac,
      );
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.reason, SttModeResolver.reasonUnsupportedCodec);
    });

    test('unknown allowance mode is not proof of the cap: today\'s Omi socket', () {
      final decision = _resolve(allowance: _allowance('surprise', reason: 'future'));
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.reason, 'allowance_unrecognized');
    });
  });

  group('decide(): default-on flag, kill switch, model preparation', () {
    SttModeResolver resolver({
      bool flag = true,
      bool killed = false,
      TranscriptionAllowanceSnapshot? allowance,
      FreemiumReadiness readiness = FreemiumReadiness.ready,
      List<String>? prepared,
    }) {
      return SttModeResolver(
        flagReader: () => flag,
        killSwitchReader: () async => killed,
        allowanceReader: () => allowance,
        readinessReader: ({String? language}) async => readiness,
        onDeviceConfigBuilder: _onDevice,
        prepareOnDevice: ({String? language}) => prepared?.add('prepare'),
      );
    }

    final atCap = _allowance('on_device', reason: 'plan_allowance_exhausted');

    test('the local flag defaults on', () {
      expect(FreeTierOnDeviceSttFlag.isEnabled(environment: const {}), isTrue);
    });

    test('prefs false still forces the local flag off', () {
      expect(FreeTierOnDeviceSttFlag.isEnabled(environment: const {}, prefsOverride: false), isFalse);
    });

    test('at cap and ready ⇒ on-device', () async {
      final decision = await resolver(allowance: atCap).decide(persistedCustomStt: _default, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.onDevice);
    });

    test('kill switch on ⇒ today\'s managed path', () async {
      final decision = await resolver(allowance: atCap, killed: true)
          .decide(persistedCustomStt: _default, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.managed);
      expect(decision.reason, 'flag_off');
    });

    test('kill switch read failing keeps the feature on', () async {
      expect(await FreeTierOnDeviceSttFlag.killed(readFlag: (_) async => throw StateError('offline')), isFalse);
    });

    test('at cap and not ready ⇒ managed and the model is prepared', () async {
      final prepared = <String>[];
      final decision = await resolver(allowance: atCap, readiness: FreemiumReadiness.requiresSetup, prepared: prepared)
          .decide(persistedCustomStt: _default, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.managed);
      expect(prepared, ['prepare']);
    });

    test('within allowance never prepares from the socket path', () async {
      final prepared = <String>[];
      await resolver(allowance: _allowance('managed', reason: 'plan_within_allowance'), prepared: prepared)
          .decide(persistedCustomStt: _default, codec: BleAudioCodec.opus);
      expect(prepared, isEmpty);
    });

    test('explicit custom STT ignores the kill switch read and stays honored', () async {
      var reads = 0;
      final r = SttModeResolver(
        flagReader: () => true,
        killSwitchReader: () async {
          reads++;
          return false;
        },
        allowanceReader: () => atCap,
        readinessReader: ({String? language}) async => FreemiumReadiness.ready,
        onDeviceConfigBuilder: _onDevice,
        prepareOnDevice: ({String? language}) {},
      );
      final decision = await r.decide(persistedCustomStt: _custom, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.honorCustom);
      expect(reads, 0);
    });
  });

  group('the free plan\'s phone choice', () {
    final atCap = _allowance('on_device', reason: 'plan_allowance_exhausted');
    final within = _allowance('managed', reason: 'plan_within_allowance');

    SttModeResolver resolver({bool killed = false, TranscriptionAllowanceSnapshot? allowance}) {
      return SttModeResolver(
        flagReader: () => true,
        killSwitchReader: () async => killed,
        allowanceReader: () => allowance,
        readinessReader: ({String? language}) async => FreemiumReadiness.ready,
        onDeviceConfigBuilder: _onDevice,
        prepareOnDevice: ({String? language}) {},
      );
    }

    test('switching to the phone at the cap persists and pins the choice', () async {
      final decision = await resolver(allowance: atCap).decide(persistedCustomStt: _default, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.onDevice);
      expect(PhoneTranscriptionChoice.isPinned(SharedPreferencesUtil()), isTrue);
      final persisted = SharedPreferencesUtil().customSttConfig;
      expect(persisted.provider, SttProvider.onDeviceWhisper);
      expect(persisted.sendRawAudioToOmi, isFalse);
      expect(decision.customSttConfig?.sttConfigId, persisted.sttConfigId);
    });

    test('the pinned choice stays on the phone after the monthly reset', () async {
      final pinned = await PhoneTranscriptionChoice.adopt(_onDevice(), SharedPreferencesUtil());
      final decision = await resolver(allowance: within).decide(persistedCustomStt: pinned, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.honorCustom);
      expect(decision.opensManagedOmiSocket, isFalse);
    });

    test('the kill switch returns a pinned phone choice to the cloud', () async {
      final pinned = await PhoneTranscriptionChoice.adopt(_onDevice(), SharedPreferencesUtil());
      final decision =
          await resolver(allowance: within, killed: true).decide(persistedCustomStt: pinned, codec: BleAudioCodec.opus);
      expect(decision.path, SttResolvedPath.managed);
    });

    test('release leaves a Custom STT the reader set up themselves', () async {
      await SharedPreferencesUtil().saveCustomSttConfig(_custom);
      SharedPreferencesUtil().paywallOnDeviceSttConfigId = 'something-else';
      expect(await PhoneTranscriptionChoice.release(SharedPreferencesUtil()), isFalse);
      expect(SharedPreferencesUtil().customSttConfig.provider, SttProvider.deepgramLive);
      expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
    });
  });

  group('OnDeviceSttPreparer.shouldPrepareFor', () {
    test('prepares at the cap and in the last two hours, not before', () {
      expect(OnDeviceSttPreparer.shouldPrepareFor(atCapSnapshot), isTrue);
      expect(
          OnDeviceSttPreparer.shouldPrepareFor(const TranscriptionAllowanceSnapshot(
              mode: 'managed', reason: 'plan_within_allowance', remainingSeconds: 3600)),
          isTrue);
      expect(
          OnDeviceSttPreparer.shouldPrepareFor(const TranscriptionAllowanceSnapshot(
              mode: 'managed', reason: 'plan_within_allowance', remainingSeconds: 9000)),
          isFalse);
      expect(
          OnDeviceSttPreparer.shouldPrepareFor(
              const TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'plan_unlimited')),
          isFalse);
      expect(OnDeviceSttPreparer.shouldPrepareFor(null), isFalse);
      expect(OnDeviceSttPreparer.shouldPrepareFor(const TranscriptionAllowanceSnapshot(mode: 'blocked', reason: 'x')),
          isFalse);
    });
  });

  group('review round 1', () {
    test('transient on_device reasons never prepare a model', () {
      for (final reason in SttModeResolver.transientAllowanceReasons) {
        expect(OnDeviceSttPreparer.shouldPrepareFor(_allowance('on_device', reason: reason)), isFalse);
      }
      expect(OnDeviceSttPreparer.shouldPrepareFor(_allowance('surprise', reason: 'future')), isFalse);
    });

    test('an at-cap snapshot older than a day is not trusted by the default reader', () {
      final now = DateTime(2026, 11, 16, 12);
      TranscriptionAllowanceCache.replace(atCapSnapshot, now: now.subtract(const Duration(hours: 25)));
      expect(TranscriptionAllowanceCache.currentWithin(SttModeResolver.onDeviceSnapshotMaxAge, now: now), isNull);
      TranscriptionAllowanceCache.replace(atCapSnapshot, now: now.subtract(const Duration(hours: 2)));
      expect(TranscriptionAllowanceCache.currentWithin(SttModeResolver.onDeviceSnapshotMaxAge, now: now)?.mode,
          'on_device');
    });

    test('a snapshot saved before ages were tracked is not trusted', () {
      TranscriptionAllowanceCache.replace(atCapSnapshot);
      SharedPreferencesUtil().saveInt(TranscriptionAllowanceCache.savedAtPrefsKey, 0);
      expect(TranscriptionAllowanceCache.currentWithin(SttModeResolver.onDeviceSnapshotMaxAge), isNull);
    });

    test('live on-device language: primary language first', () {
      expect(
          FreemiumTranscriptionService.liveOnDeviceLanguage(primary: 'de', deviceLocale: 'fr_FR', isIOS: true), 'de');
    });

    test('live on-device language: iOS uses the phone language instead of multi (which Apple maps to English)', () {
      expect(FreemiumTranscriptionService.liveOnDeviceLanguage(primary: '', deviceLocale: 'es_MX', isIOS: true), 'es');
      expect(FreemiumTranscriptionService.liveOnDeviceLanguage(primary: 'multi', deviceLocale: 'ja-JP', isIOS: true),
          'ja');
      expect(FreemiumTranscriptionService.liveOnDeviceLanguage(primary: '', deviceLocale: 'C', isIOS: true), 'multi');
    });

    test('live on-device language: Android keeps multi for Whisper language detection', () {
      expect(
          FreemiumTranscriptionService.liveOnDeviceLanguage(primary: '', deviceLocale: 'es_MX', isIOS: false), 'multi');
    });

    test('kill switch refreshes the cached flags at most every ten minutes', () async {
      FreeTierOnDeviceSttGate.debugReset();
      var reloads = 0;
      var t = DateTime(2026, 11, 16, 12);
      Future<bool> read(String _) async => true;
      Future<bool> reload() async {
        reloads++;
        return true;
      }

      expect(await FreeTierOnDeviceSttGate.killed(readFlag: read, reloadFlags: reload, now: () => t), isTrue);
      t = t.add(const Duration(minutes: 5));
      await FreeTierOnDeviceSttGate.killed(readFlag: read, reloadFlags: reload, now: () => t);
      expect(reloads, 1);
      t = t.add(const Duration(minutes: 6));
      await FreeTierOnDeviceSttGate.killed(readFlag: read, reloadFlags: reload, now: () => t);
      expect(reloads, 2);
    });

    test('a failing flag refresh still reads the cached answer', () async {
      FreeTierOnDeviceSttGate.debugReset();
      expect(
        await FreeTierOnDeviceSttGate.killed(
            readFlag: (_) async => true, reloadFlags: () async => throw StateError('offline')),
        isTrue,
      );
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
