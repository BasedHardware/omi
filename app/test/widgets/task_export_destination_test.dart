import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/services/action_item_export_service.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';

TaskIntegrationsResponse status(String? app, {bool todoist = true}) =>
    TaskIntegrationsResponse(defaultApp: app, integrations: {
      'apple_reminders': {'connected': true},
      'todoist': {'connected': todoist}
    });

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  TaskIntegrationProvider integrations(Future<TaskIntegrationsResponse?> Function() fetch) =>
      TaskIntegrationProvider(supportsAppleReminders: true, readApplePermission: () async => true, fetchStatus: fetch);

  for (final invalid in [null, '', 'unknown', 'trello']) {
    test('unconfirmed or disconnected default $invalid cannot fall back to Apple', () async {
      final provider = integrations(() async => status(invalid));
      addTearDown(provider.dispose);
      expect(await provider.resolveExportTarget(), isNull);
    });
  }
  test('failed status and disconnected Todoist cannot fall back to permitted Apple', () async {
    var response = status('todoist', todoist: false);
    final provider = integrations(() async => response);
    addTearDown(provider.dispose);
    expect(await provider.resolveExportTarget(), isNull);
    response = status('todoist');
    expect(await provider.resolveExportTarget(), TaskIntegrationApp.todoist);
    final offline = integrations(() async => null);
    addTearDown(offline.dispose);
    expect(await offline.resolveExportTarget(), isNull);
  });
  test('selection or account changes while resolving invalidate the export', () async {
    final read = Completer<TaskIntegrationsResponse?>();
    final provider = TaskIntegrationProvider(
        supportsAppleReminders: true,
        readApplePermission: () async => true,
        fetchStatus: () => read.future,
        setDefaultTaskIntegrationFn: (_) async => true);
    addTearDown(provider.dispose);
    final resolving = provider.resolveExportTarget();
    await Future<void>.value();
    await provider.setSelectedApp(TaskIntegrationApp.appleReminders);
    read.complete(status('todoist'));
    expect(await resolving, isNull);
    final next = Completer<TaskIntegrationsResponse?>();
    final other = integrations(() => next.future);
    addTearDown(other.dispose);
    final stale = other.resolveExportTarget();
    await Future<void>.value();
    other.clearUserData();
    next.complete(status('todoist'));
    expect(await stale, isNull);
  });
  test('bulk resolution waits for a pending saved choice before reading', () async {
    final write = Completer<bool>();
    var saved = 'apple_reminders';
    final provider = TaskIntegrationProvider(
        supportsAppleReminders: true,
        readApplePermission: () async => true,
        fetchStatus: () async => status(saved),
        setDefaultTaskIntegrationFn: (key) async {
          await write.future;
          saved = key;
          return true;
        });
    addTearDown(provider.dispose);
    final saving = provider.setSelectedApp(TaskIntegrationApp.todoist);
    final resolving = provider.resolveExportTarget();
    write.complete(true);
    expect(await saving, isTrue);
    expect(await resolving, TaskIntegrationApp.todoist);
  });

  testWidgets('a stalled permission read releases export without using cached choice', (tester) async {
    final permission = Completer<bool>();
    final provider = TaskIntegrationProvider(
        supportsAppleReminders: true,
        readApplePermission: () => permission.future,
        fetchStatus: () async => status('todoist'),
        statusTimeout: const Duration(seconds: 1));
    addTearDown(provider.dispose);
    final result = provider.resolveExportTarget();
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(await result, isNull);
    permission.complete(true);
    await tester.pump();
  });
  test('a superseding status load cannot authorize export from the cached selection', () async {
    final pending = <Completer<TaskIntegrationsResponse?>>[];
    final provider = integrations(() {
      final read = Completer<TaskIntegrationsResponse?>();
      pending.add(read);
      return read.future;
    });
    addTearDown(provider.dispose);
    final resolving = provider.resolveExportTarget();
    await Future<void>.value();
    final latest = provider.loadFromBackend(forceRefresh: true);
    pending.first.complete(status('todoist'));
    expect(await resolving, isNull);
    pending.last.complete(status('apple_reminders'));
    await latest;
  });

  Future<ActionItemsProvider> pumpBar(
      WidgetTester tester, TaskIntegrationProvider connections, List<TaskIntegrationApp> writes) async {
    const row = ActionItemWithMetadata(id: 'task', description: 'Synthetic task', completed: false);
    final tasks = ActionItemsProvider(
        getActionItems: (
                {int limit = 50,
                int offset = 0,
                bool? completed,
                String? conversationId,
                DateTime? startDate,
                DateTime? endDate,
                DateTime? dueStartDate,
                DateTime? dueEndDate}) async =>
            ActionItemsResponse(actionItems: [row]),
        exportActionItem: (item, app) async {
          writes.add(app);
          return ExportResult.success;
        });
    addTearDown(tasks.dispose);
    addTearDown(connections.dispose);
    await tasks.ensureLoaded();
    tasks.startSelectionWithItem(row.id);
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<ActionItemsProvider>.value(value: tasks),
          ChangeNotifierProvider<TaskIntegrationProvider>.value(value: connections),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            theme: buildOmiTheme(brightness: Brightness.dark),
            home: const Scaffold(body: Align(alignment: Alignment.bottomCenter, child: TaskSelectionActionBar())))));
    await tester.pumpAndSettle();
    return tasks;
  }

  testWidgets('real Export uses saved Todoist when Apple is also connected', (tester) async {
    final writes = <TaskIntegrationApp>[];
    final provider = integrations(() async => status('todoist'));
    await provider.loadFromBackend();
    expect(provider.isAppConnected(TaskIntegrationApp.appleReminders), isTrue);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isTrue);
    final tasks = await pumpBar(tester, provider, writes);
    await tester.tap(find.text('Export · 1'));
    await tester.pumpAndSettle();
    expect(writes, [TaskIntegrationApp.todoist]);
    expect(tasks.isSelectionMode, isFalse);
    expect(find.textContaining('Todoist'), findsOneWidget);
  });
  testWidgets('repeated taps during status resolution produce one export', (tester) async {
    final pending = Completer<TaskIntegrationsResponse?>();
    var reads = 0;
    final writes = <TaskIntegrationApp>[];
    await pumpBar(tester, integrations(() {
      reads++;
      return pending.future;
    }), writes);
    await tester.tap(find.text('Export · 1'));
    await tester.pump();
    await tester.tap(find.text('Export · 1'));
    await tester.pump();
    expect(reads, 1);
    pending.complete(status('todoist'));
    await tester.pumpAndSettle();
    expect(writes, [TaskIntegrationApp.todoist]);
  });
  testWidgets('cancel during destination read prevents export', (tester) async {
    final pending = Completer<TaskIntegrationsResponse?>();
    final writes = <TaskIntegrationApp>[];
    final tasks = await pumpBar(tester, integrations(() => pending.future), writes);
    await tester.tap(find.text('Export · 1'));
    await tester.pump();
    await tester.tap(find.text('Cancel'));
    pending.complete(status('todoist'));
    await tester.pumpAndSettle();
    expect(writes, isEmpty);
    expect(tasks.isSelectionMode, isFalse);
  });
}
