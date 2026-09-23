import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> _pumpPage(WidgetTester tester) async {
  await tester.pumpWidget(
    const MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: NotificationsSettingsPage(),
    ),
  );
  // Allow async settings loading to complete and dismiss shimmer loading safely
  await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
  await tester.pump();
}

void main() {
  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().notificationFrequency = 2;
  });

  testWidgets('NotificationsSettingsPage displays Generate Past Summary button and triggers picker', (tester) async {
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pumpPage(tester);

    // 1. Verify Generate Past Summary row is rendered with calendar icon
    final generateText = find.text('Generate Past Summary');
    expect(generateText, findsOneWidget);
    expect(find.byIcon(FontAwesomeIcons.calendar), findsOneWidget);

    // 2. Tap the generate summary row
    await tester.tap(generateText);
    await tester.pumpAndSettle();

    // 3. Verify date picker modal opens
    expect(find.byType(DatePickerDialog), findsOneWidget);

    // 4. Verify canceling dismisses the date picker modal cleanly
    final cancelButton = find.text('Cancel');
    if (cancelButton.evaluate().isNotEmpty) {
      await tester.tap(cancelButton);
      await tester.pumpAndSettle();
      expect(find.byType(DatePickerDialog), findsNothing);
    }
  });

  testWidgets('daily summary backfill row remains accessible even under network failure', (tester) async {
    await _pumpPage(tester);

    // Page must not get stuck in shimmer or error state
    expect(find.text('Generate Past Summary'), findsOneWidget);
  });
}
