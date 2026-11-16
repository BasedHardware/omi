import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/pages/on_device/free_cap_sheet.dart';
import 'package:omi/pages/on_device/on_phone_banner.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/phone_transcription_choice.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';

const _atCap =
    TranscriptionAllowanceSnapshot(mode: 'on_device', reason: 'plan_allowance_exhausted', remainingSeconds: 0);

UsageProvider _usage({PlanType plan = PlanType.basic, TranscriptionAllowanceSnapshot? allowance = _atCap}) {
  return UsageProvider()
    ..debugSetSubscription(UserSubscriptionResponse(
        subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
        transcriptionSecondsUsed: 18000,
        transcriptionSecondsLimit: 18000,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        transcriptionAllowance: allowance));
}

Widget _app(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('free cap sheet', () {
    testWidgets('Omi Pro comes first and each choice is returned', (tester) async {
      final choices = <FreeCapChoice>[];
      await tester.pumpWidget(_app(FreeCapSheet(capMinutes: 300, onChoice: choices.add)));
      final upgrade = tester.getTopLeft(find.byKey(const Key('free_cap_upgrade')));
      final phone = tester.getTopLeft(find.byKey(const Key('free_cap_phone')));
      expect(upgrade.dy, lessThan(phone.dy));
      await tester.tap(find.byKey(const Key('free_cap_upgrade')));
      await tester.tap(find.byKey(const Key('free_cap_phone')));
      expect(choices, [FreeCapChoice.upgrade, FreeCapChoice.transcribeOnPhone]);
    });

    test('only a free plan at the cap is eligible', () {
      expect(FreemiumSwitchHandler.freeCapEligible(_usage()), isTrue);
      expect(FreemiumSwitchHandler.freeCapEligible(_usage(plan: PlanType.unlimited)), isFalse);
      expect(FreemiumSwitchHandler.freeCapEligible(_usage(allowance: null)), isFalse);
      expect(
          FreemiumSwitchHandler.freeCapEligible(_usage(
              allowance: const TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'plan_within_allowance'))),
          isFalse);
      for (final reason in SttModeResolver.transientAllowanceReasons) {
        expect(
            FreemiumSwitchHandler.freeCapEligible(
                _usage(allowance: TranscriptionAllowanceSnapshot(mode: 'on_device', reason: reason))),
            isFalse,
            reason: reason);
      }
    });

    test('a Custom STT the reader set up is not asked again', () async {
      await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(
          provider: SttProvider.deepgramLive, apiKey: 'k', url: 'wss://api.deepgram.com/v1/listen'));
      expect(FreemiumSwitchHandler.freeCapEligible(_usage()), isFalse);
    });

    test('the phone choice made automatically at the cap still gets the sheet', () async {
      await PhoneTranscriptionChoice.adopt(
          const CustomSttConfig(
              provider: SttProvider.onDeviceWhisper, language: 'en', identity: SttModeResolver.freemiumOnDeviceId),
          SharedPreferencesUtil());
      expect(FreemiumSwitchHandler.freeCapEligible(_usage()), isTrue);
    });
  });

  group('on-phone banner', () {
    test('shows only for a free plan transcribing on the phone', () {
      expect(showOnPhoneBanner(transcribingOnPhone: true, usage: _usage()), isTrue);
      expect(showOnPhoneBanner(transcribingOnPhone: false, usage: _usage()), isFalse);
      expect(showOnPhoneBanner(transcribingOnPhone: true, usage: _usage(plan: PlanType.unlimited)), isFalse);
      expect(showOnPhoneBanner(transcribingOnPhone: true, usage: UsageProvider()), isFalse);
    });

    testWidgets('tapping it opens the plans', (tester) async {
      var opened = 0;
      await tester.pumpWidget(_app(OnPhoneTranscriptionBanner(onUpgrade: () => opened++)));
      expect(find.text('Transcribing on this phone'), findsOneWidget);
      expect(find.text('Get Pro'), findsOneWidget);
      await tester.tap(find.byKey(const Key('on_phone_banner')));
      expect(opened, 1);
    });
  });
}
