import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
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

  testWidgets('a failed daily summary toggle puts the switch back', (tester) async {
    await _pumpPage(tester);
    expect(tester.widget<Switch>(find.byType(Switch)).value, isTrue);

    await tester.tap(find.byType(Switch));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
    await tester.pump();

    expect(tester.widget<Switch>(find.byType(Switch)).value, isTrue);
  });

  testWidgets('a failed frequency change keeps the saved frequency', (tester) async {
    await _pumpPage(tester);
    expect(tester.widget<Slider>(find.byType(Slider)).value, 2);

    tester.widget<Slider>(find.byType(Slider)).onChanged!(4);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
    await tester.pump();

    expect(tester.widget<Slider>(find.byType(Slider)).value, 2);
    expect(SharedPreferencesUtil().notificationFrequency, 2);
  });
}
