import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/app_provider.dart';

void main() {
  group('AppProvider.toggleApp', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    late AppProvider provider;

    tearDown(() {
      provider.dispose();
    });

    /// Creates a minimal MaterialApp so [AppDialog.show] (called inside
    /// [toggleApp] on failure) has a navigator context and does not crash.
    Future<void> pumpNavigator(WidgetTester tester) async {
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
          home: const Scaffold(body: Text('test')),
        ),
      );
      await tester.pump();
    }

    testWidgets('returns false when enableAppServer fails (regression guard)', (tester) async {
      await pumpNavigator(tester);

      provider = AppProvider();
      provider.enableAppOverride = (String id) async {
        expect(id, equals('app_123'));
        return false;
      };

      final result = await provider.toggleApp('app_123', true, null);

      // The entire purpose of the #10100 fix: the caller can now
      // distinguish failure from success instead of assuming success.
      expect(result, isFalse);
    });

    testWidgets('returns true when enableAppServer succeeds', (tester) async {
      await pumpNavigator(tester);

      provider = AppProvider();
      // Set up local app so the success path can find and update it.
      provider.apps = [
        App(
            id: 'app_123',
            name: 'Test',
            author: 'tester',
            description: 'test',
            image: '',
            capabilities: {'memories'},
            status: 'approved',
            category: 'test',
            approved: true,
            ratingCount: 0,
            enabled: true,
            deleted: false,
            isPaid: false,
            isUserPaid: false),
      ];
      var enableCalled = false;
      provider.enableAppOverride = (String id) async {
        enableCalled = true;
        expect(id, equals('app_123'));
        return true;
      };

      final result = await provider.toggleApp('app_123', true, null);
      // Flush both debounced timers (updatePrefApps 500ms + _scheduleAppsRefresh 2s)
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();

      expect(result, isTrue);
      expect(enableCalled, isTrue);
    });
  });
}
