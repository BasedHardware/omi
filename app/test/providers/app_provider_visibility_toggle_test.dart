import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/app_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

App _privateApp() => App.fromJson({
      'id': 'app_journal',
      'name': 'Journal',
      'author': 'Test Author',
      'description': 'test',
      'image': '',
      'capabilities': ['memories'],
      'status': 'approved',
      'category': 'productivity',
      'approved': true,
      'private': true,
      'enabled': true,
      'deleted': false,
    });

void main() {
  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a visibility change the server rejected keeps the app private and says so', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(),
      ),
    );
    final provider = AppProvider();
    addTearDown(provider.dispose);
    provider.apps = [_privateApp()];

    await tester.runAsync(() async {
      provider.toggleAppPublic('app_journal', true);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    expect(provider.apps.single.private, isTrue);
    expect(provider.appPublicToggled, isFalse);
    expect(find.text('App visibility changed successfully. It may take a few minutes to reflect.'), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);

    await tester.pumpAndSettle(const Duration(seconds: 3));
  });
}
