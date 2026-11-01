import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/developer_mode_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Developer Settings creates this provider in a ChangeNotifierProvider, which disposes it when the page
/// closes. These tests dispose it the same way while its requests are still running.
void main() {
  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('leaving the page before it finishes loading does not use the closed provider', () async {
    final provider = DeveloperModeProvider();

    final loading = provider.initialize();
    provider.dispose();

    // The load ends by clearing its spinner, which notified the disposed provider and threw.
    await expectLater(loading, completes);
  });

  testWidgets('a save that finishes after the page closed still reports its result', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(),
      ),
    );
    final provider = DeveloperModeProvider();
    provider.webhookOnTranscriptReceived.text = 'https://example.com/hook';

    provider.saveSettings();
    provider.dispose();
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
    await tester.pump();

    // The API is unreachable, so the save fails. Clearing the spinner used to throw before this error showed.
    expect(find.text('Failed to save. Please check your connection.'), findsOneWidget);
  });
}
