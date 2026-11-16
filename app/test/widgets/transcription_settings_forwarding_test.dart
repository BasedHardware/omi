import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/phone_transcription_choice.dart';
import 'package:omi/ui/ui.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> openPage(WidgetTester tester) async {
    final captureProvider = CaptureProvider();
    addTearDown(captureProvider.dispose);
    final usage = UsageProvider(subscriptionRequest: () async => null);
    addTearDown(usage.dispose);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final homeProvider = HomeProvider();
    addTearDown(homeProvider.dispose);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
          ChangeNotifierProvider<HomeProvider>.value(value: homeProvider),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ],
        child: const MaterialApp(
          localizationsDelegates: [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: TranscriptionSettingsPage(),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('this phone keeps audio local; the cloud provider restores its raw audio setting', (tester) async {
    // iOS needs no model file, so picking the phone persists it in this test.
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    const onDeviceConfig = CustomSttConfig(provider: SttProvider.onDeviceWhisper, sendRawAudioToOmi: false);
    const cloudConfig = CustomSttConfig(provider: SttProvider.openai, sendRawAudioToOmi: true);
    await SharedPreferencesUtil().saveCustomSttConfig(onDeviceConfig);
    await SharedPreferencesUtil().saveConfigForProvider(SttProvider.onDeviceWhisper, onDeviceConfig);
    await SharedPreferencesUtil().saveConfigForProvider(SttProvider.openai, cloudConfig);

    await openPage(tester);

    final forwardingRow = find.widgetWithText(OmiSettingsRow, 'Send raw audio to Omi');
    OmiSwitch forwardingTile() =>
        tester.widget<OmiSwitch>(find.descendant(of: forwardingRow, matching: find.byType(OmiSwitch)));

    // On this phone audio never leaves it, so there is no forwarding switch to show.
    expect(forwardingRow, findsNothing);

    await tester.ensureVisible(find.byKey(const Key('transcription_source_cloud_provider')));
    await tester.tap(find.byKey(const Key('transcription_source_cloud_provider')));
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    expect(forwardingTile().value, isTrue);

    await tester.ensureVisible(find.byKey(const Key('transcription_source_phone')));
    await tester.tap(find.byKey(const Key('transcription_source_phone')));
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    expect(find.text('I Understand'), findsNothing, reason: 'choosing the phone needs no warning on a capable phone');
    expect(forwardingRow, findsNothing);
    final active = SharedPreferencesUtil().customSttConfig;
    expect(active.provider, SttProvider.onDeviceWhisper);
    expect(active.sendRawAudioToOmi, isFalse);
    expect(PhoneTranscriptionChoice.isPinned(SharedPreferencesUtil()), isTrue,
        reason: 'a free plan picking This phone is the permanent phone choice');
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('a language edit saves an on-device config set up before, without pinning it', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().userPrimaryLanguage = 'en';
    const own = CustomSttConfig(provider: SttProvider.onDeviceWhisper, language: 'es', sendRawAudioToOmi: false);
    await SharedPreferencesUtil().saveCustomSttConfig(own);
    await SharedPreferencesUtil().saveConfigForProvider(SttProvider.onDeviceWhisper, own);

    await openPage(tester);
    await tester.ensureVisible(find.text('Use Primary Language'));
    await tester.tap(find.text('Use Primary Language'));
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    final active = SharedPreferencesUtil().customSttConfig;
    expect(active.provider, SttProvider.onDeviceWhisper);
    expect(active.language, 'en', reason: 'iOS has no Save bar for the phone; the edit applies at once');
    expect(PhoneTranscriptionChoice.isPinned(SharedPreferencesUtil()), isFalse,
        reason: 'the reader set this up themselves; a paid plan or sign-out must not reset it');
    debugDefaultTargetPlatformOverride = null;
  });
}
