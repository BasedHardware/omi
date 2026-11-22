import 'dart:convert';
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/on_device_stt_preparer.dart';
import 'package:omi/services/capture/phone_transcription_choice.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/services/sockets/apple_speech_readiness.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';

UserSubscriptionResponse _subscription(PlanType plan, {String? mode = 'managed'}) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      transcriptionAllowance:
          mode == null ? null : TranscriptionAllowanceSnapshot(mode: mode, reason: 'plan_within_allowance'),
    );

/// What the paywall's "switch to free" does (plans_sheet.dart).
Future<CustomSttConfig> _switchToFreeFromPaywall() async {
  final config = FreemiumTranscriptionService().createOnDeviceSttConfig();
  await SharedPreferencesUtil().saveCustomSttConfig(config);
  SharedPreferencesUtil().paywallOnDeviceSttConfigId = config.sttConfigId;
  return config;
}

Future<CustomSttConfig> _fetch(PlanType plan) async {
  await UsageProvider(
          subscriptionRequest: () async => _subscription(plan, mode: plan == PlanType.basic ? 'on_device' : 'managed'))
      .fetchSubscription();
  return SharedPreferencesUtil().customSttConfig;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TranscriptionAllowanceCache.clear();
  });

  for (final plan in [PlanType.plus, PlanType.unlimited, PlanType.unlimitedV2]) {
    test('older server paid ${plan.name} releases the pin without an allowance', () async {
      await _switchToFreeFromPaywall();
      final provider = UsageProvider(subscriptionRequest: () async => _subscription(plan, mode: null));
      addTearDown(provider.dispose);
      await provider.fetchSubscription();
      expect(provider.subscription!.transcriptionAllowance, isNull);
      expect(SharedPreferencesUtil().customSttConfig.isEnabled, isFalse);
      expect(SharedPreferencesUtil().customSttConfig.sendRawAudioToOmi, isTrue);
      expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
    });
  }

  test('older server Basic without an allowance keeps the pin', () async {
    final pinned = await _switchToFreeFromPaywall();
    final provider = UsageProvider(subscriptionRequest: () async => _subscription(PlanType.basic, mode: null));
    addTearDown(provider.dispose);
    await provider.fetchSubscription();
    expect(SharedPreferencesUtil().customSttConfig.sttConfigId, pinned.sttConfigId);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, pinned.sttConfigId);
  });

  test('explicit on-device allowance keeps a paid plan pinned', () async {
    final pinned = await _switchToFreeFromPaywall();
    final provider = UsageProvider(subscriptionRequest: () async => _subscription(PlanType.plus, mode: 'on_device'));
    addTearDown(provider.dispose);
    await provider.fetchSubscription();
    expect(SharedPreferencesUtil().customSttConfig.sttConfigId, pinned.sttConfigId);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, pinned.sttConfigId);
  });

  for (final throws in [false, true]) {
    test('failed older-server refresh releases the last paid plan pin (throws=$throws)', () async {
      await _switchToFreeFromPaywall();
      final provider = UsageProvider(subscriptionRequest: () async {
        if (throws) throw StateError('offline');
        return null;
      });
      addTearDown(provider.dispose);
      provider.debugSetSubscription(_subscription(PlanType.plus, mode: null));
      await provider.fetchSubscription();
      expect(provider.error, isNotNull);
      expect(provider.isLoading, isFalse);
      expect(SharedPreferencesUtil().customSttConfig.isEnabled, isFalse);
      expect(SharedPreferencesUtil().customSttConfig.sendRawAudioToOmi, isTrue);
      expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
    });
  }

  test('a paid plan releases the paywall on-device pin back to Omi', () async {
    final pinned = await _switchToFreeFromPaywall();
    expect(pinned.sendRawAudioToOmi, isFalse, reason: 'the pin is what keeps audio from Omi');

    final after = await _fetch(PlanType.unlimited);

    expect(after.isEnabled, isFalse);
    expect(after.sendRawAudioToOmi, isTrue);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
  });

  test('a paid plan releases an on-device pin saved before parser fields joined the identity', () async {
    final config = FreemiumTranscriptionService().createOnDeviceSttConfig();
    await SharedPreferencesUtil().saveCustomSttConfig(config);
    final legacyInput = config.toJson()
      ..remove('provider')
      ..remove('audio_field_name')
      ..remove('schema');
    final hash = jsonEncode(legacyInput).hashCode.abs().toRadixString(16).padLeft(8, '0').substring(0, 8);
    SharedPreferencesUtil().paywallOnDeviceSttConfigId = '${config.provider.name}:$hash';

    final after = await _fetch(PlanType.unlimited);

    expect(after.provider, SttProvider.omi);
    expect(after.sendRawAudioToOmi, isTrue);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
  });

  test('basic keeps the paywall pin: the user is still out of managed minutes', () async {
    final pinned = await _switchToFreeFromPaywall();

    final after = await _fetch(PlanType.basic);

    expect(after.sttConfigId, pinned.sttConfigId);
  });

  test('a Custom STT the user chose after the paywall survives the upgrade', () async {
    await _switchToFreeFromPaywall();
    const ownChoice = CustomSttConfig(provider: SttProvider.deepgramLive, apiKey: 'user-key', sendRawAudioToOmi: false);
    await SharedPreferencesUtil().saveCustomSttConfig(ownChoice);

    final after = await _fetch(PlanType.unlimited);

    expect(after.sttConfigId, ownChoice.sttConfigId);
  });

  test('a Custom STT never set by the paywall is untouched by a paid plan', () async {
    const ownChoice = CustomSttConfig(provider: SttProvider.onDeviceWhisper, language: 'en', sendRawAudioToOmi: false);
    await SharedPreferencesUtil().saveCustomSttConfig(ownChoice);

    final after = await _fetch(PlanType.unlimited);

    expect(after.sttConfigId, ownChoice.sttConfigId);
  });
  for (final throws in [false, true]) {
    test('failed refresh with no known plan keeps the phone choice (throws=$throws)', () async {
      TranscriptionAllowanceCache.replace(
          const TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'plan_unlimited'));
      final pinned = await _switchToFreeFromPaywall();
      final provider = UsageProvider(subscriptionRequest: () async {
        if (throws) throw StateError('offline');
        return null;
      });
      await provider.fetchSubscription();
      expect(SharedPreferencesUtil().customSttConfig.sttConfigId, pinned.sttConfigId);
      expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, pinned.sttConfigId);
      expect(provider.isLoading, false);
    });
  }

  test('credit invalidation waits for the server and keeps that answer on failure', () async {
    final reply = Completer<UserSubscriptionResponse?>();
    final provider = UsageProvider(subscriptionRequest: () => reply.future);
    provider.debugSetSubscription(_subscription(PlanType.basic, mode: 'managed'));
    final refresh = provider.markAsOutOfCreditsAndRefresh();
    expect(provider.isOutOfCredits, false);
    reply.complete(_subscription(PlanType.basic, mode: 'on_device'));
    await refresh;
    expect(provider.isOutOfCredits, true);
    provider.dispose();
  });

  test('failed credit invalidation preserves the server exhausted answer', () async {
    final provider = UsageProvider(subscriptionRequest: () async => null);
    provider.debugSetSubscription(_subscription(PlanType.plus, mode: 'on_device'));
    await provider.markAsOutOfCreditsAndRefresh();
    expect(provider.isOutOfCredits, true);
    provider.dispose();
  });

  test('the monthly reset keeps a Free plan on the phone: the choice is permanent', () async {
    final pinned = await _switchToFreeFromPaywall();
    await UsageProvider(subscriptionRequest: () async => _subscription(PlanType.basic)).fetchSubscription();
    expect(SharedPreferencesUtil().customSttConfig.sttConfigId, pinned.sttConfigId);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, pinned.sttConfigId);
  });

  test('a paid plan releases the phone choice and tells capture to reconnect', () async {
    await _switchToFreeFromPaywall();
    var released = 0;
    final provider = UsageProvider(subscriptionRequest: () async => _subscription(PlanType.unlimitedV2));
    addTearDown(provider.dispose);
    provider.onPhoneChoiceChanged = () => released++;
    await provider.fetchSubscription();
    expect(SharedPreferencesUtil().customSttConfig.isEnabled, isFalse);
    expect(released, 1);
  });

  test('sign-out releases the phone choice so the next account starts on Omi', () async {
    await _switchToFreeFromPaywall();
    SharedPreferencesUtil().phoneModelOnWifiPending = 'pin';
    final provider = UsageProvider(subscriptionRequest: () async => null);
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpEventQueue();
    expect(SharedPreferencesUtil().customSttConfig.isEnabled, isFalse);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
    expect(SharedPreferencesUtil().phoneModelOnWifiPending, isEmpty);
  });

  group('Android "On Wi-Fi later"', () {
    var prepared = 0;
    setUp(() {
      prepared = 0;
      final freemium = FreemiumTranscriptionService()
        ..iosOverride = true
        ..appleReadinessReader = (_) async => const AppleSpeechReadiness('fake', 'ready');
      OnDeviceSttPreparer.debugOverride = ({String? language}) async {
        prepared++;
        await freemium.checkReadiness();
      };
    });
    tearDown(() {
      OnDeviceSttPreparer.debugOverride = null;
      FreemiumTranscriptionService()
        ..iosOverride = null
        ..appleReadinessReader = null
        ..reset();
    });

    Future<int> finish(PlanType plan, {String mode = 'on_device'}) async {
      var changed = 0;
      final provider = UsageProvider(subscriptionRequest: () async => _subscription(plan, mode: mode))
        ..onPhoneChoiceChanged = () => changed++;
      addTearDown(provider.dispose);
      await provider.fetchSubscription();
      // The completion runs beside the refresh; let it land.
      for (var i = 0; i < 5; i++) {
        await Future<void>.delayed(Duration.zero);
      }
      return changed;
    }

    test('a free plan\'s choice is pinned once the model is ready, and capture is told', () async {
      SharedPreferencesUtil().phoneModelOnWifiPending = 'pin';
      expect(await finish(PlanType.basic), 1);
      expect(PhoneTranscriptionChoice.isPinned(SharedPreferencesUtil()), isTrue);
      expect(SharedPreferencesUtil().customSttConfig.sendRawAudioToOmi, isFalse);
      expect(SharedPreferencesUtil().phoneModelOnWifiPending, isEmpty);
    });

    test('upgraded while the model downloaded: the choice is kept unpinned', () async {
      SharedPreferencesUtil().phoneModelOnWifiPending = 'pin';
      await finish(PlanType.unlimited, mode: 'managed');
      expect(SharedPreferencesUtil().customSttConfig.provider, SttProvider.onDeviceWhisper);
      expect(PhoneTranscriptionChoice.isPinned(SharedPreferencesUtil()), isFalse);
    });

    test('a Custom STT chosen since is never overridden', () async {
      const own = CustomSttConfig(provider: SttProvider.deepgramLive, apiKey: 'k');
      await SharedPreferencesUtil().saveCustomSttConfig(own);
      SharedPreferencesUtil().phoneModelOnWifiPending = 'pin';
      expect(await finish(PlanType.basic), 0);
      expect(prepared, 0);
      expect(SharedPreferencesUtil().customSttConfig.provider, SttProvider.deepgramLive);
      expect(SharedPreferencesUtil().phoneModelOnWifiPending, isEmpty);
    });

    test('not ready yet: the choice stays pending', () async {
      FreemiumTranscriptionService().appleReadinessReader = (_) async => const AppleSpeechReadiness('fake', 'no_wifi');
      SharedPreferencesUtil().phoneModelOnWifiPending = 'pin';
      expect(await finish(PlanType.basic), 0);
      expect(SharedPreferencesUtil().phoneModelOnWifiPending, 'pin');
      expect(SharedPreferencesUtil().customSttConfig.isEnabled, isFalse);
    });
  });
}
