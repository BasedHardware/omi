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

void main() {
  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a webhook switch the server did not confirm goes back and says so', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(),
      ),
    );
    final provider = DeveloperModeProvider();
    addTearDown(provider.dispose);
    provider.transcriptsToggled = true;
    provider.daySummaryToggled = true;

    provider.onConversationEventsToggled(true);
    provider.onTranscriptsToggled(false);
    provider.onAudioBytesToggled(true);
    provider.onDaySummaryToggled(false);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
    await tester.pump();

    expect(provider.conversationEventsToggled, isFalse);
    expect(provider.transcriptsToggled, isTrue);
    expect(provider.audioBytesToggled, isFalse);
    expect(provider.daySummaryToggled, isTrue);
    expect(find.text('Failed to save. Please check your connection.'), findsOneWidget);
  });
}
