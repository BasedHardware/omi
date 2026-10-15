import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';

UserSubscriptionResponse _subscription(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

/// What the paywall's "switch to free" does (plans_sheet.dart).
Future<CustomSttConfig> _switchToFreeFromPaywall() async {
  final config = FreemiumTranscriptionService().createOnDeviceSttConfig();
  await SharedPreferencesUtil().saveCustomSttConfig(config);
  SharedPreferencesUtil().paywallOnDeviceSttConfigId = config.sttConfigId;
  return config;
}

Future<CustomSttConfig> _fetch(PlanType plan) async {
  await UsageProvider(subscriptionRequest: () async => _subscription(plan)).fetchSubscription();
  return SharedPreferencesUtil().customSttConfig;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a paid plan releases the paywall on-device pin back to Omi', () async {
    final pinned = await _switchToFreeFromPaywall();
    expect(pinned.sendRawAudioToOmi, isFalse, reason: 'the pin is what keeps audio from Omi');

    final after = await _fetch(PlanType.unlimited);

    expect(after.isEnabled, isFalse);
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
}
