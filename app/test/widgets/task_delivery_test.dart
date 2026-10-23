import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_task_recovery.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import '../../integration_test/support/task_delivery_fixture.dart';

class _LoadedIntegrations extends TaskIntegrationProvider {
  @override
  bool get hasLoaded => true;
  @override
  Future<void> loadFromBackend({bool forceRefresh = false}) async {}
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    Env.overrideApiBaseUrl('http://127.0.0.1:18965/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<void> pump(WidgetTester tester, ActionItemsProvider provider, Widget child,
      {Locale locale = const Locale('en'), double scale = 1}) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
        ChangeNotifierProvider(create: (_) => GoalsProvider()),
        ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => _LoadedIntegrations()),
      ],
      child: MaterialApp(
        locale: locale,
        theme: buildOmiTheme(brightness: Brightness.dark),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: child!),
        home: Scaffold(body: child),
      ),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('empty Tasks offers approval and displays exactly one saved task', (tester) async {
    final fixture = TaskDeliveryFixture();
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    await pump(tester, provider, const ActionItemsPage());
    expect(find.byKey(const ValueKey('task_suggestions')), findsOneWidget);
    expect(fixture.acceptCalls, 0);
    expect(provider.actionItems, isEmpty);
    await tester.tap(find.byKey(const ValueKey('accept_task_synthetic-candidate')));
    await tester.pumpAndSettle();
    expect(provider.actionItems.single.id, 'synthetic-task');
    expect(find.text(TaskDeliveryFixture.description), findsOneWidget);
    expect(find.byKey(const ValueKey('task_suggestions')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final locale in [const Locale('pt'), const Locale('ar')]) {
    testWidgets('review controls wrap at 200% text in ${locale.languageCode}', (tester) async {
      final fixture = TaskDeliveryFixture()..failHydration = true;
      final provider = createProductionActionItemsProvider(send: fixture.send);
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      await pump(tester, provider, const ActionItemsPage(), locale: locale, scale: 2);
      await tester.tap(find.byKey(const ValueKey('accept_task_synthetic-candidate')));
      await tester.pumpAndSettle();
      expect(provider.suggestions!.saved('synthetic-candidate'), isTrue);
      expect(find.byKey(const ValueKey('dismiss_task_synthetic-candidate')), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('project suggestions show their context before approving the anchor task', (tester) async {
    final fixture = TaskDeliveryFixture()..projectSuggestion = true;
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    await pump(tester, provider, const ActionItemsPage(), locale: const Locale('pt'), scale: 2);
    expect(find.text('Project launch'), findsOneWidget);
    expect(find.text('Share the agreed launch notes'), findsOneWidget);
    expect(fixture.acceptCalls, 0);
    await tester.tap(find.byKey(const ValueKey('accept_task_synthetic-candidate')));
    await tester.pumpAndSettle();
    expect(provider.actionItems.single.id, 'synthetic-task');
    expect(tester.takeException(), isNull);
  });

  testWidgets('old desktop summary has explicit recovery; phone summaries have no second writer', (tester) async {
    final fixture = TaskDeliveryFixture();
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    ServerConversation conversation(ConversationSource source) => ServerConversation(
          id: 'synthetic-conversation',
          createdAt: DateTime.utc(2026, 9, 1),
          source: source,
          status: ConversationStatus.completed,
          transcriptSegments: [],
          structured: Structured('Project notes', '')..actionItems = [ActionItem(TaskDeliveryFixture.description)],
        );
    await pump(tester, provider, SummaryTaskRecovery(conversation: conversation(ConversationSource.phone)));
    expect(find.byKey(const ValueKey('summary_add_tasks')), findsNothing);
    expect(fixture.requests.where((r) => r.method == 'POST'), isEmpty);
    await pump(tester, provider, SummaryTaskRecovery(conversation: conversation(ConversationSource.desktop)));
    await tester.tap(find.byKey(const ValueKey('summary_add_tasks')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('summary_add_task_0')));
    await tester.pumpAndSettle();
    expect(provider.actionItems.single.id, 'synthetic-task');
    expect(fixture.acceptCalls, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Portuguese Settings search opens Task Integrations with zero tasks', (tester) async {
    final fixture = TaskDeliveryFixture();
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    await pump(
        tester,
        provider,
        Builder(
            builder: (context) => TextButton(
                  onPressed: () {
                    final result = searchSettings(context.l10n, context.l10n.taskIntegrations,
                        const SettingsSearchScope(deviceConnected: false, supportLinks: true, android: false));
                    openSettingsDestination(context, result.first.destination);
                  },
                  child: const Text('Search fixture'),
                )),
        locale: const Locale('pt'));
    await tester.tap(find.text('Search fixture'));
    await tester.pumpAndSettle();
    expect(find.byType(TaskIntegrationsPage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final cached in [false, true]) {
    testWidgets('summary recovery uses stored row 3 after skipped rows (cached: $cached)', (tester) async {
      final fixture = TaskDeliveryFixture()..expectedSummaryIndex = 3;
      final provider = createProductionActionItemsProvider(send: fixture.send);
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      var conversation = ServerConversation(
        id: 'synthetic-conversation',
        createdAt: DateTime.utc(2026, 9, 1),
        source: ConversationSource.desktop,
        status: ConversationStatus.completed,
        transcriptSegments: [],
        structured: Structured.fromJson({
          'title': 'Project notes',
          'overview': '',
          'action_items': [
            '',
            null,
            {'description': 'Bad date', 'completed': false, 'due_at': 'bad-date'},
            {'description': TaskDeliveryFixture.description, 'completed': false},
            {'description': 'Already completed', 'completed': true},
          ],
        }),
      );
      if (cached) conversation = ServerConversation.fromJson(jsonDecode(jsonEncode(conversation.toJson())));
      await pump(tester, provider, SummaryTaskRecovery(conversation: conversation));
      await tester.tap(find.byKey(const ValueKey('summary_add_tasks')));
      await tester.pumpAndSettle();
      expect(find.text('Already completed'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('summary_add_task_3')));
      await tester.pumpAndSettle();
      expect(provider.actionItems.single.id, 'synthetic-task');
      final prepared = fixture.requests.singleWhere((r) => r.url.endsWith('/from-conversation'));
      expect(jsonDecode(prepared.body)['action_item_index'], 3);
      final accepted = fixture.requests.singleWhere((r) => r.url.endsWith('/accept'));
      expect(jsonDecode(accepted.body)['summary_item']['action_item_index'], 3);
      expect(tester.takeException(), isNull);
    });
  }
}
