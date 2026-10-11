import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/spine/contract.dart';
import '../support/spine/widgets.dart';
import '../support/typed_action_items_screen.dart';
import 'c3_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractWidgets('C3 action-items outage renders error, retry recovers, valid empty alone renders empty', (
    tester,
  ) async {
    final fixture = await tester.runAsync(C3Fixture.start);
    addTearDown(fixture!.close);
    fixture.backend.failNext('GET', '/v1/action-items', status: 503);
    late final ActionItemsProvider p;
    await tester.runAsync(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      p = composeTypedActionItemsProvider(ActionItemsApi(baseUrl: fixture.backend.baseUrl, send: fixture.send));
      await p.ensureLoaded();
    });
    expect(p.runtimeType, ActionItemsProvider);
    addTearDown(p.dispose);
    expect(fixture.backend.countOf('GET', '/v1/action-items'), 1);
    expect(p.apiViewState.phase, ApiViewPhase.error);
    expect(p.isLoading, isFalse);
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: ActionItemsApiStatus(provider: p)),
      ),
    );
    await tester.pump();
    expect(find.byKey(const ValueKey('omi.action_items.error')), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.action_items.empty')), findsNothing);
    final semantics = tester.ensureSemantics();
    final errorNode = tester.getSemantics(find.byKey(const ValueKey('omi.action_items.error')));
    expect(errorNode.label.trim(), isNotEmpty);
    semantics.dispose();
    await tester.runAsync(() async => await p.forceRefreshActionItems());
    await tester.pump();
    expect(p.apiViewState.phase, ApiViewPhase.empty);
    expect(find.byKey(const ValueKey('omi.action_items.error')), findsNothing);
    expect(find.byKey(const ValueKey('omi.action_items.empty')), findsOneWidget);
    expect(fixture.backend.countOf('GET', '/v1/action-items'), 2);
  });

  contractTest('C3 action-items parser keeps exact valid records around a malformed row', () async {
    final fixture = await C3Fixture.start();
    addTearDown(fixture.close);
    fixture.backend.actionItems.addAll([
      {'id': 'first', 'description': 'Synthetic first', 'completed': false},
      {'id': 42},
      {'id': 'last', 'description': 'Synthetic last', 'completed': false},
    ]);
    final result = await ActionItemsApi(baseUrl: fixture.backend.baseUrl, send: fixture.send).list();
    final success = result as ApiSuccess;
    expect(success.data.actionItems.map((item) => item.id), ['first', 'last']);
    expect(success.data.actionItems.map((item) => item.description), ['Synthetic first', 'Synthetic last']);
    expect(success.rejectedRows, 1);
    expect(fixture.backend.countOf('GET', '/v1/action-items'), 1);
  });

  contractWidgets('C3 actual action-items page never renders empty tasks hero for a persistent outage', (tester) async {
    final fixture = await tester.runAsync(C3Fixture.start);
    addTearDown(fixture!.close);
    var outage = true;
    final api = ActionItemsApi(
      baseUrl: fixture.backend.baseUrl,
      send: (request) async {
        if (outage && request.method == 'GET' && Uri.parse(request.url).path == '/v1/action-items') {
          fixture.backend.failNext('GET', '/v1/action-items', status: 503);
        }
        return fixture.send(request);
      },
    );
    late final ActionItemsProvider provider;
    final screen = await tester.runAsync(() async {
      provider = composeTypedActionItemsProvider(api);
      final widget = await buildTypedActionItemsScreen(provider);
      await provider.ensureLoaded();
      await pumpEventQueue();
      return widget;
    });
    expect(provider.runtimeType, ActionItemsProvider);
    addTearDown(provider.dispose);
    await tester.pumpWidget(screen!);
    await tester.pump();
    final page = find.byType(ActionItemsPage);
    expect(page, findsOneWidget);
    expect(tester.widget(page).runtimeType, ActionItemsPage);
    expect(identical(tester.element(page).read<ActionItemsProvider>(), provider), isTrue);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.action_items.error'))), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.action_items.empty')), findsNothing);
    expect(find.textContaining('Create Action Item'), findsNothing);
    expect(provider.apiViewState.phase, ApiViewPhase.error);
    outage = false;
    await tester.runAsync(() async => await provider.forceRefreshActionItems());
    await tester.pump();
    expect(provider.apiViewState.phase, ApiViewPhase.empty);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.action_items.error'))), findsNothing);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.action_items.empty'))), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });
}
