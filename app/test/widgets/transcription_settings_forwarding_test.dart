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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('source changes restore each provider raw audio setting', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    const onDeviceConfig = CustomSttConfig(
      provider: SttProvider.onDeviceWhisper,
      privacyPolicy: SttPrivacyPolicy.transcriptOnly,
    );
    const cloudConfig = CustomSttConfig(
      provider: SttProvider.openai,
      privacyPolicy: SttPrivacyPolicy.full,
    );
    await SharedPreferencesUtil().saveCustomSttConfig(onDeviceConfig);
    await SharedPreferencesUtil().saveConfigForProvider(SttProvider.onDeviceWhisper, onDeviceConfig);
    await SharedPreferencesUtil().saveConfigForProvider(SttProvider.openai, cloudConfig);

    final captureProvider = CaptureProvider();
    addTearDown(captureProvider.dispose);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ChangeNotifierProvider<CaptureProvider>.value(
        value: captureProvider,
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

    SwitchListTile forwardingTile() => tester.widget<SwitchListTile>(
          find.widgetWithText(SwitchListTile, 'Send raw audio to Omi'),
        );

    expect(forwardingTile().value, isFalse);

    final sourceDropdown = tester.widget<DropdownButton<TranscriptionMode>>(
      find.byType(DropdownButton<TranscriptionMode>),
    );
    sourceDropdown.onChanged!(TranscriptionMode.cloudProvider);
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    expect(forwardingTile().value, isTrue);

    final cloudSourceDropdown = tester.widget<DropdownButton<TranscriptionMode>>(
      find.byType(DropdownButton<TranscriptionMode>),
    );
    cloudSourceDropdown.onChanged!(TranscriptionMode.onDevice);
    await tester.pumpAndSettle(const Duration(milliseconds: 100));
    await tester.tap(find.text('I Understand'));
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    expect(forwardingTile().value, isFalse);
    expect(
      SharedPreferencesUtil().getConfigForProvider(SttProvider.onDeviceWhisper)?.forwardsRawAudioToOmi,
      isFalse,
    );
  });

  testWidgets('imported localOnly shows a read-only policy state without transcriptOnly copy', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        privacyPolicy: SttPrivacyPolicy.localOnly,
      ),
    );

    final captureProvider = CaptureProvider();
    addTearDown(captureProvider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<CaptureProvider>.value(
        value: captureProvider,
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

    expect(find.text('localOnly'), findsOneWidget);
    expect(
        find.text(
            'Turn off to prevent raw audio from being sent to Omi. Transcripts and data needed by cloud features may still be sent to Omi.'),
        findsNothing);
    expect(find.byType(SwitchListTile), findsNothing);
  });
}
