import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';

const _open = ActionItemWithMetadata(id: 'open', description: 'Draft the update', completed: false);
const _locked = ActionItemWithMetadata(id: 'locked', description: 'Older task…', completed: false, isLocked: true);
const _exported = ActionItemWithMetadata(
    id: 'sent', description: 'Book the venue', completed: false, exported: true, exportPlatform: 'google_tasks');

/// Two pages of fifty-item requests: the first says more follow, the second ends the set.
Future<ActionItemsResponse?> _twoPages({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async {
  if (offset == 0) return const ActionItemsResponse(actionItems: [_open, _locked], hasMore: true);
  return const ActionItemsResponse(
    actionItems: [ActionItemWithMetadata(id: 'page2', description: 'Renew the passport', completed: false)],
    hasMore: false,
  );
}

Future<ActionItemsResponse?> _onePage({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    const ActionItemsResponse(actionItems: [_open, _exported], hasMore: false);

/// Bulk selection skips what the backend would refuse, reaches past the loaded page, and an export
/// trusts the provider's record over the caller's copy.
void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('Select All leaves paywalled tasks out and reports "all selected" from the same set', () async {
    // A fully loaded set: Select All is "all" at once.
    final provider = ActionItemsProvider(getActionItems: _onePage);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    provider.startSelection();
    provider.selectAllItems();
    expect(provider.selectedCount, 2);
    expect(provider.allSelectableSelected, isTrue);

    final lockedProvider = ActionItemsProvider(getActionItems: _twoPages);
    addTearDown(lockedProvider.dispose);
    await lockedProvider.ensureLoaded();
    expect(lockedProvider.hasMore, isTrue);

    lockedProvider.startSelection();
    lockedProvider.selectAllItems();
    expect(lockedProvider.isItemSelected('open'), isTrue);
    expect(lockedProvider.isItemSelected('locked'), isFalse);
    // A page is still unloaded, so this is not yet "all".
    expect(lockedProvider.allSelectableSelected, isFalse);
  });

  test('selectAllTasks loads the remaining pages before selecting', () async {
    final provider = ActionItemsProvider(getActionItems: _twoPages);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    expect(provider.actionItems.length, 2);

    await provider.selectAllTasks();

    expect(provider.isSelectionMode, isTrue);
    expect(provider.hasMore, isFalse);
    expect(provider.actionItems.map((i) => i.id), containsAll(['open', 'locked', 'page2']));
    expect(provider.selectedCount, 2);
    expect(provider.isItemSelected('page2'), isTrue);
    expect(provider.isItemSelected('locked'), isFalse);
    expect(provider.allSelectableSelected, isTrue);
  });

  test('a task completed just now sorts first in the Completed section, before the server answers', () async {
    Future<ActionItemsResponse?> items({
      int limit = 100,
      int offset = 0,
      bool? completed,
      String? conversationId,
      DateTime? startDate,
      DateTime? endDate,
      DateTime? dueStartDate,
      DateTime? dueEndDate,
    }) async =>
        ActionItemsResponse(actionItems: [
          _open,
          ActionItemWithMetadata(
              id: 'old-done', description: 'Pay the invoice', completed: true, completedAt: DateTime(2026, 9, 1)),
        ]);
    final provider = ActionItemsProvider(
      getActionItems: items,
      // A slow server: the local record is all the list has for a while.
      updateActionItemRequest: (id, {description, completed, dueAt}) =>
          Future.delayed(const Duration(milliseconds: 50), () => null),
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();

    final pending = provider.updateActionItemState(_open, true);
    expect(provider.completedItemsNewestFirst.map((i) => i.id).toList(), ['open', 'old-done']);
    await pending;
  });

  test('a slow answer to an earlier toggle does not undo a newer one', () async {
    Future<ActionItemsResponse?> items({
      int limit = 100,
      int offset = 0,
      bool? completed,
      String? conversationId,
      DateTime? startDate,
      DateTime? endDate,
      DateTime? dueStartDate,
      DateTime? dueEndDate,
    }) async =>
        const ActionItemsResponse(actionItems: [_open]);
    // Completing answers late; the restore that follows answers at once.
    final provider = ActionItemsProvider(
      getActionItems: items,
      updateActionItemRequest: (id, {description, completed, dueAt}) => Future.delayed(
        Duration(milliseconds: completed == true ? 80 : 1),
        () => ActionItemWithMetadata(
            id: id,
            description: 'Draft the update',
            completed: completed!,
            completedAt: completed ? DateTime.now() : null),
      ),
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();

    final complete = provider.updateActionItemState(_open, true);
    final restore = provider.updateActionItemState(_open, false);
    await Future.wait([complete, restore]);

    final item = provider.actionItems.firstWhere((i) => i.id == 'open');
    // The late "completed" answer is stale and must not win over the restore.
    expect(item.completed, isFalse);
    expect(provider.completedItems, isEmpty);
  });

  test('an export platform is named the way Task Integrations names the app', () {
    expect(taskExportPlatformLabel('google_tasks'), 'Google Tasks');
    expect(taskExportPlatformLabel('apple_reminders'), TaskIntegrationApp.appleReminders.displayName);
    expect(taskExportPlatformLabel('trello'), 'Trello');
    expect(taskExportPlatformLabel('something_new'), 'something_new');
  });

  testWidgets('exporting a stale copy of an already-exported task is skipped, with the app named', (tester) async {
    final provider = ActionItemsProvider(getActionItems: _onePage);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();

    late BuildContext pageContext;
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
        ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => TaskIntegrationProvider()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: Builder(builder: (context) {
          pageContext = context;
          return const SizedBox.shrink();
        })),
      ),
    ));

    // The page still holds the task as it was before the export: not yet exported.
    const stale = ActionItemWithMetadata(id: 'sent', description: 'Book the venue', completed: false);
    await provider.exportItems(pageContext, [stale], TaskIntegrationApp.googleTasks);
    await tester.pump();

    expect(find.text('Already exported to Google Tasks'), findsOneWidget);
    expect(provider.actionItems.firstWhere((i) => i.id == 'sent').exported, isTrue);
  });
}
