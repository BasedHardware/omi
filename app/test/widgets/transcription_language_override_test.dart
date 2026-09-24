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

/// Language is chosen in one place: a Custom STT provider shows the primary language read-only
/// until the reader explicitly overrides it (docs/ux-contract.md §12).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> pumpPage(WidgetTester tester, {required String primary}) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().userPrimaryLanguage = primary;
    const config = CustomSttConfig(provider: SttProvider.openai, apiKey: 'key');
    await SharedPreferencesUtil().saveCustomSttConfig(config);
    await SharedPreferencesUtil().saveConfigForProvider(SttProvider.openai, config);

    final captureProvider = CaptureProvider();
    addTearDown(captureProvider.dispose);
    final homeProvider = HomeProvider();
    addTearDown(homeProvider.dispose);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
          ChangeNotifierProvider<HomeProvider>.value(value: homeProvider),
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

  testWidgets('follows the primary language until overridden, and can go back', (tester) async {
    await pumpPage(tester, primary: 'es');

    expect(find.text('Spanish'), findsOneWidget);
    expect(find.text('Follows your primary language'), findsOneWidget);
    expect(find.byType(Autocomplete<String>), findsNothing, reason: 'model has its own picker only under Advanced');

    await tester.ensureVisible(find.text('Override'));
    await tester.tap(find.text('Override'));
    await tester.pumpAndSettle();

    expect(find.text('Follows your primary language'), findsNothing);
    expect(find.widgetWithText(TextField, 'es (Spanish)'), findsOneWidget);

    await tester.ensureVisible(find.text('Use Primary Language'));
    await tester.tap(find.text('Use Primary Language'));
    await tester.pumpAndSettle();

    expect(find.text('Follows your primary language'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'es (Spanish)'), findsNothing);
  });

  testWidgets('says so when the provider cannot use the primary language', (tester) async {
    await pumpPage(tester, primary: 'tl');

    expect(find.text("Tagalog isn't supported by this provider, so it uses English."), findsOneWidget);
  });
}
