import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/typed_action_items_screen.dart';

Future<ActionItemsResponse?> _items({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    ActionItemsResponse(
      actionItems: [
        const ActionItemWithMetadata(
            id: 'open', description: 'Draft the update', completed: false, conversationId: 'conv-1'),
        ActionItemWithMetadata(
            id: 'done1',
            description: 'Reply to the review',
            completed: true,
            completedAt: DateTime(2026, 10, 1),
            indentLevel: 1),
        ActionItemWithMetadata(
            id: 'done2', description: 'Pay the invoice', completed: true, completedAt: DateTime(2026, 10, 2)),
        ActionItemWithMetadata(
            id: 'done-locked',
            description: 'A done task behind the…',
            completed: true,
            isLocked: true,
            completedAt: DateTime(2026, 9, 30)),
        ActionItemWithMetadata(
            id: 'locked',
            description: 'An older task behind the…',
            completed: false,
            isLocked: true,
            dueAt: DateTime.now()),
      ],
    );

/// Nothing but locked tasks: what a free account past its limit can have.
Future<ActionItemsResponse?> _lockedOnly({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    ActionItemsResponse(
      actionItems: [
        ActionItemWithMetadata(
            id: 'done-locked',
            description: 'A done task behind the…',
            completed: true,
            isLocked: true,
            completedAt: DateTime(2026, 9, 30)),
        const ActionItemWithMetadata(
            id: 'locked', description: 'An older task behind the…', completed: false, isLocked: true),
      ],
    );

/// A first page of locked tasks, then a page with an open one.
Future<ActionItemsResponse?> _lockedFirstPage({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    offset == 0
        ? const ActionItemsResponse(
            actionItems: [
              ActionItemWithMetadata(
                  id: 'locked', description: 'An older task behind the…', completed: false, isLocked: true),
            ],
            hasMore: true,
          )
        : const ActionItemsResponse(
            actionItems: [ActionItemWithMetadata(id: 'older', description: 'Book the venue', completed: false)],
          );

/// One list: done tasks fold under the open sections, and a row opens its own page. Locked tasks
/// are left off it for now.
final deletes = <String>[];

void main() {
  setUp(() {
    deletes.clear();
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<(ActionItemsProvider, List<bool>)> pumpPage(WidgetTester tester,
      {ActionItemsFetcher getActionItems = _items}) async {
    final completions = <bool>[];
    final provider = ActionItemsProvider(
      getActionItems: getActionItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async {
        if (completed != null) completions.add(completed);
        return ActionItemWithMetadata(id: id, description: id, completed: completed ?? false);
      },
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    return (provider, completions);
  }

  /// Like [pumpPage], with the providers above the navigator the way the app has them, so a pushed
  /// route (the task page, the plan page) can read them too.
  Future<(ActionItemsProvider, List<bool>)> pumpApp(WidgetTester tester, {Duration updateDelay = Duration.zero}) async {
    final completions = <bool>[];
    final provider = ActionItemsProvider(
      getActionItems: _items,
      deleteActionItemRequest: (id) async {
        deletes.add(id);
        return true;
      },
      updateActionItemRequest: (id, {description, completed, dueAt}) async {
        await Future<void>.delayed(updateDelay);
        if (completed != null) completions.add(completed);
        return ActionItemWithMetadata(id: id, description: id, completed: completed ?? false);
      },
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
        ChangeNotifierProvider<GoalsProvider>(create: (_) => GoalsProvider()),
        ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => TaskIntegrationProvider()),
        // The plan page needs an inert UsageProvider.
        ChangeNotifierProvider<UsageProvider>(
          create: (_) => UsageProvider(
            deviceTimeZone: () async => 'UTC',
            usageRequest: ({required period, required timeZone}) async => null,
          ),
        ),
      ],
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: Scaffold(body: ActionItemsPage()),
      ),
    ));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    return (provider, completions);
  }

  testWidgets('completed tasks sit folded at the bottom of the list, newest first, with Clear', (tester) async {
    final (_, completions) = await pumpPage(tester);

    expect(find.text('Completed'), findsOneWidget);
    // Two done tasks are listed; the locked one is not, and is not counted.
    expect(find.text('2'), findsOneWidget);
    expect(find.text('Pay the invoice'), findsNothing);
    expect(find.text('Clear'), findsNothing);

    await tester.tap(find.text('Completed'));
    await tester.pumpAndSettle();
    expect(find.text('Clear'), findsOneWidget);
    expect(tester.getTopLeft(find.text('Pay the invoice')).dy,
        lessThan(tester.getTopLeft(find.text('Reply to the review')).dy));
    expect(tester.getTopLeft(find.text('Draft the update')).dy, lessThan(tester.getTopLeft(find.text('Completed')).dy));
    expect(tester.widget<Text>(find.text('Pay the invoice')).style?.decoration, TextDecoration.lineThrough);

    // A nested task keeps its indent once done.
    expect(tester.getTopLeft(find.text('Reply to the review')).dx,
        greaterThan(tester.getTopLeft(find.text('Pay the invoice')).dx));

    // The ring on a done row brings it back.
    await tester.tap(find.bySemanticsLabel('Mark Incomplete').first);
    await tester.pumpAndSettle();
    expect(completions, [false]);
  });

  testWidgets('a locked task is not listed and not counted', (tester) async {
    await pumpPage(tester);
    // Its only dated task is locked, so no dated section shows.
    expect(find.text('An older task behind the…'), findsNothing);
    expect(find.text('Today'), findsNothing);
    expect(find.text('Overdue'), findsNothing);
    expect(find.byIcon(Icons.lock_outline), findsNothing);
    // One open row, and its ring completes it.
    expect(find.bySemanticsLabel('Mark Complete'), findsOneWidget);
  });

  testWidgets('a locked done task is not listed under Completed', (tester) async {
    await pumpPage(tester);
    await tester.tap(find.text('Completed'));
    await tester.pumpAndSettle();

    expect(find.text('A done task behind the…'), findsNothing);
    expect(find.byIcon(Icons.lock_outline), findsNothing);
    expect(find.bySemanticsLabel('Mark Incomplete'), findsNWidgets(2));
  });

  testWidgets('a list of only locked tasks shows the empty state, with nothing locked on it', (tester) async {
    await pumpPage(tester, getActionItems: _lockedOnly);
    expect(find.byKey(const ValueKey('omi.action_items.empty')), findsOneWidget);
    expect(find.text('An older task behind the…'), findsNothing);
    expect(find.text('Completed'), findsNothing);
    expect(find.byIcon(Icons.lock_outline), findsNothing);
  });

  testWidgets('a first page of locked tasks still loads the next page, and its tasks are listed', (tester) async {
    // Hidden rows leave nothing to scroll, and a scroll is what asks for the next page.
    await pumpPage(tester, getActionItems: _lockedFirstPage);
    expect(find.text('Book the venue'), findsOneWidget);
    expect(find.text('An older task behind the…'), findsNothing);
    expect(find.byKey(const ValueKey('omi.action_items.empty')), findsNothing);
  });

  testWidgets('a next page that does not load is asked for once, with a toast, not on every frame', (tester) async {
    var requests = 0;
    // A first page of locked tasks (so the list is too short to scroll and the page asks for the
    // next one itself), then a page that never lands.
    Future<ActionItemsResponse?> lockedThenOffline({
      int limit = 100,
      int offset = 0,
      bool? completed,
      String? conversationId,
      DateTime? startDate,
      DateTime? endDate,
      DateTime? dueStartDate,
      DateTime? dueEndDate,
    }) async {
      if (offset == 0) {
        return const ActionItemsResponse(
          actionItems: [
            ActionItemWithMetadata(
                id: 'locked', description: 'An older task behind the…', completed: false, isLocked: true),
          ],
          hasMore: true,
        );
      }
      requests++;
      throw Exception('offline');
    }

    final (provider, _) = await pumpPage(tester, getActionItems: lockedThenOffline);
    // Every notification rebuilds the page; a few more frames must not ask again.
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(requests, 1);
    expect(provider.lastPageFailed, isTrue);
    expect(provider.hasMore, isTrue);
    expect(find.text("Couldn't load more tasks. Pull down to try again."), findsOneWidget);
  });

  testWidgets('selecting a done task never selects the rows under it', (tester) async {
    final (provider, _) = await pumpPage(tester);
    await tester.tap(find.text('Completed'));
    await tester.pumpAndSettle();
    provider.startSelection();
    await tester.pumpAndSettle();

    // Newest first puts the indented 'Reply to the review' right under 'Pay the invoice', which is
    // not its parent; a hierarchy cascade would take it along.
    await tester.tap(find.text('Pay the invoice'));
    await tester.pumpAndSettle();
    expect(provider.isItemSelected('done2'), isTrue);
    expect(provider.isItemSelected('done1'), isFalse);
    expect(provider.selectedCount, 1);
  });

  testWidgets('selecting boxes every listed task, and Clear deletes only the listed done tasks', (tester) async {
    final (provider, _) = await pumpApp(tester);
    provider.startSelection();
    await tester.pumpAndSettle();
    // One open row is listed (the locked one is not): one selection box.
    expect(find.byType(TaskSelectionSquare), findsOneWidget);
    provider.clearSelection();
    await tester.pumpAndSettle();

    await tester.tap(find.text('Completed'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    // The locked done task is neither listed nor sent for deletion.
    expect(deletes.toSet(), {'done1', 'done2'});
  });

  testWidgets('holding a done task offers Mark Incomplete and Delete Task', (tester) async {
    await pumpPage(tester);
    await tester.tap(find.text('Completed'));
    await tester.pumpAndSettle();

    await tester.longPress(find.text('Pay the invoice'));
    await tester.pumpAndSettle();
    expect(find.text('Mark Incomplete'), findsOneWidget);
    expect(find.text('Delete Task'), findsOneWidget);
    expect(find.text('Indent'), findsNothing);
  });

  testWidgets('tapping a task heard in a conversation opens the edit sheet with Open conversation', (tester) async {
    await pumpPage(tester);

    await tester.tap(find.text('Draft the update'));
    await tester.pumpAndSettle();
    expect(find.byType(ActionItemFormSheet), findsOneWidget);
    expect(find.byKey(const Key('task_open_conversation')), findsOneWidget);
    expect(find.text('Open conversation'), findsOneWidget);
    expect(find.text('Mark Complete'), findsOneWidget);
    expect(find.byKey(const Key('task_save_button')), findsOneWidget);
  });
}
