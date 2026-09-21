import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  setUpAll(() => Env.init(_TestEnvFields()));

  testWidgets('NotificationsSettingsPage displays Generate Past Summary button and triggers picker', (tester) async {
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: const NotificationsSettingsPage(),
      ),
    );

    // Initial load shimmer may be visible or loaded
    await tester.pumpAndSettle();

    // Verify Generate Past Summary row is rendered with calendar icon
    final generateText = find.text('Generate Past Summary');
    expect(generateText, findsOneWidget);
    expect(find.byIcon(FontAwesomeIcons.calendar), findsOneWidget);

    // Tap the generate summary row
    await tester.tap(generateText);
    await tester.pumpAndSettle();

    // Verify date picker modal opens
    expect(find.byType(DatePickerDialog), findsOneWidget);
  });
}
