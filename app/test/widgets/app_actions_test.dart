/// One app action button with one meaning everywhere, and one consent question before an app
/// that works outside Omi gets data (mobile UX contract, lane 3 #18/#19).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/providers/app_provider.dart';

App _app({
  bool enabled = false,
  bool external = false,
  bool paid = false,
  List<AuthStep> authSteps = const [],
}) {
  return App(
    id: 'app-1',
    name: 'Notes Sync',
    author: 'Omi',
    description: 'Syncs notes',
    image: '',
    capabilities: {'chat', if (external) 'external_integration'},
    status: 'approved',
    category: 'productivity',
    approved: true,
    ratingCount: 0,
    enabled: enabled,
    deleted: false,
    isPaid: paid,
    isUserPaid: false,
    externalIntegration: external ? ExternalIntegration(authSteps: authSteps) : null,
  );
}

void main() {
  late AppProvider provider;
  late List<String> enabledIds;
  late List<String> disabledIds;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    enabledIds = [];
    disabledIds = [];
    provider = AppProvider()
      ..enableAppOverride = (id) async {
        enabledIds.add(id);
        return (true, '');
      }
      ..disableAppOverride = (id) async {
        disabledIds.add(id);
        return true;
      };
  });

  Future<void> pump(WidgetTester tester, App app) async {
    provider.apps = [app];
    await tester.pumpWidget(
      ChangeNotifierProvider<AppProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(body: Center(child: AppListActionButton(app: app, onOpen: () {}))),
        ),
      ),
    );
  }

  Future<void> tearDownProvider(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox());
    provider.dispose();
  }

  testWidgets('an enabled app reads Open', (tester) async {
    await pump(tester, _app(enabled: true));
    expect(find.text('Open'), findsOneWidget);
    await tearDownProvider(tester);
  });

  testWidgets('an app that needs payment or setup reads View, never a decorative Install', (tester) async {
    await pump(tester, _app(paid: true));
    expect(find.text('View'), findsOneWidget);
    expect(find.text('Install'), findsNothing);

    await pump(tester, _app(external: true, authSteps: [AuthStep(name: 'Sign in', url: 'https://example.com')]));
    expect(find.text('View'), findsOneWidget);
    await tearDownProvider(tester);
  });

  testWidgets('Enable on an in-Omi app enables it in place', (tester) async {
    await pump(tester, _app());
    await tester.tap(find.text('Enable'));
    await tester.pumpAndSettle();
    expect(enabledIds, ['app-1']);
    await tearDownProvider(tester);
  });

  testWidgets('Enable on an external app asks the one consent question first', (tester) async {
    await pump(tester, _app(external: true));
    await tester.tap(find.text('Enable'));
    await tester.pumpAndSettle();

    expect(find.text('Allow Notes Sync Access?'), findsOneWidget);
    expect(find.textContaining("developer's server"), findsOneWidget);
    expect(enabledIds, isEmpty, reason: 'nothing is sent before the reader answers');

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(enabledIds, isEmpty);

    await tester.tap(find.text('Enable'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Enable').last);
    await tester.pumpAndSettle();
    expect(enabledIds, ['app-1']);
    await tearDownProvider(tester);
  });

  group('Disable is immediate with a 5 s Undo, no confirmation (§4)', () {
    late List<String> events;
    bool? outcome;

    Future<void> startDisable(WidgetTester tester) async {
      final app = _app(enabled: true);
      provider.apps = [app];
      events = [];
      outcome = null;
      await tester.pumpWidget(
        ChangeNotifierProvider<AppProvider>.value(
          value: provider,
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(
              body: Builder(
                builder: (context) => TextButton(
                  onPressed: () => disableAppWithUndo(
                    context,
                    app,
                    onHidden: () => events.add('hidden'),
                    onRestored: () => events.add('restored'),
                  ).then((value) => outcome = value),
                  child: const Text('go'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('go'));
      await tester.pump();
    }

    testWidgets('the app hides at once and the server hears nothing until the toast ends', (tester) async {
      await startDisable(tester);
      expect(events, ['hidden']);
      expect(find.text('Notes Sync disabled'), findsOneWidget);
      expect(find.text('Undo'), findsOneWidget);
      expect(find.byType(AlertDialog), findsNothing, reason: 'no confirmation dialog');
      expect(disabledIds, isEmpty);

      for (var i = 0; i < 70; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(outcome, isTrue);
      expect(disabledIds, ['app-1']);
      expect(events, ['hidden']);
      await tearDownProvider(tester);
    });

    testWidgets('Undo restores the app and never disables it', (tester) async {
      await startDisable(tester);
      await tester.pump(const Duration(milliseconds: 500)); // let the toast finish arriving
      await tester.tap(find.text('Undo'));
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(outcome, isFalse);
      expect(disabledIds, isEmpty);
      expect(events, ['hidden', 'restored']);
      await tearDownProvider(tester);
    });

    testWidgets('a refused disable brings the app back', (tester) async {
      provider.disableAppOverride = (id) async {
        disabledIds.add(id);
        return false;
      };
      await startDisable(tester);
      for (var i = 0; i < 70; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(outcome, isFalse);
      expect(disabledIds, ['app-1']);
      expect(events, ['hidden', 'restored']);
      await tearDownProvider(tester);
    });

    testWidgets('enabling again inside the Undo window cancels the pending disable', (tester) async {
      await startDisable(tester);
      await provider.toggleApp('app-1', true, null);
      for (var i = 0; i < 70; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(outcome, isFalse);
      expect(disabledIds, isEmpty, reason: 'the later Enable wins');
      await tearDownProvider(tester);
    });
  });
}
