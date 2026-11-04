import 'dart:convert';
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
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
    test('failed refresh releases a pin from the last managed server answer (throws=$throws)', () async {
      TranscriptionAllowanceCache.replace(
          const TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'plan_unlimited'));
      await _switchToFreeFromPaywall();
      final provider = UsageProvider(subscriptionRequest: () async {
        if (throws) throw StateError('offline');
        return null;
      });
      await provider.fetchSubscription();
      expect(SharedPreferencesUtil().customSttConfig.isEnabled, false);
      expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
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

  test('managed allowance releases the pin even on the Free plan', () async {
    await _switchToFreeFromPaywall();
    await UsageProvider(subscriptionRequest: () async => _subscription(PlanType.basic)).fetchSubscription();
    expect(SharedPreferencesUtil().customSttConfig.isEnabled, false);
    expect(SharedPreferencesUtil().paywallOnDeviceSttConfigId, isEmpty);
  });
}
