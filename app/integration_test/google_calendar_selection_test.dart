import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/google_calendar_selection_page.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _CalendarEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Run with the loopback backend/testing/google_calendar_fixture.py server and
/// Firestore emulator. Google is synthetic; the page, transport, routes and
/// persisted preference document are real. Never point this at a live API.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('calendar picker persists multiple calendars and controls event reads', (tester) async {
    const base = String.fromEnvironment('OMI_CALENDAR_FIXTURE_BASE');
    expect(Uri.parse(base).host, '127.0.0.1');
    SharedPreferences.setMockInitialValues({'uid': 'calendar-qa'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    Env.init(_CalendarEnv());
    Env.overrideApiBaseUrl(base);
    addTearDown(Env.clearApiBaseUrlOverrideForTesting);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Builder(
          builder: (context) => Scaffold(
                  body: TextButton(
                child: const Text('Choose Calendars'),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => const GoogleCalendarSelectionPage(),
                )),
              ))),
    ));
    Future<void> settleUntil(Finder finder) async {
      for (var i = 0; i < 100 && finder.evaluate().isEmpty; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(finder, findsOneWidget);
      await tester.pumpAndSettle();
    }

    Future<List<String>> titles() async {
      final response = await makeApiCall(
        url: '${base}v1/calendar/google/events?time_min=2026-11-10T00:00:00Z&time_max=2026-11-11T00:00:00Z',
        headers: {},
        method: 'GET',
        body: '',
      );
      expect(response?.statusCode, 200);
      return (jsonDecode(response!.body) as List).map((e) => e['title'] as String).toList();
    }

    expect(await titles(), ['Primary meeting']);
    await tester.tap(find.text('Choose Calendars'));
    await settleUntil(find.text('Project team'));
    expect(find.text('Read selected calendars. New events use Personal.'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('calendar-work@group.calendar.test')));
    await tester.pump();
    await tester.tap(find.text('Save'));
    await settleUntil(find.text('Choose Calendars'));
    expect(await titles(), ['Primary meeting', 'Team meeting']);

    // A fresh screen loads the persisted draft; exclude primary while writes
    // remain explicitly primary in the UI.
    await tester.tap(find.text('Choose Calendars'));
    await settleUntil(find.text('Project team'));
    await tester.tap(find.byKey(const ValueKey('calendar-personal@example.test')));
    await tester.pump();
    await tester.tap(find.text('Save'));
    await settleUntil(find.text('Choose Calendars'));
    expect(await titles(), ['Team meeting']);
    await tester.tap(find.text('Choose Calendars'));
    await settleUntil(find.text('Project team'));
    if (Platform.isAndroid) {
      await binding.convertFlutterSurfaceToImage();
      await tester.pump();
    }
    final image = await binding.takeScreenshot('google-calendar-selection');
    expect(image, isNotEmpty);
  });
}
