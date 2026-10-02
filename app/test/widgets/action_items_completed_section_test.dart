import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/action_items/task_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';
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

/// One list: done tasks fold under the open sections, and a row opens its own page.
void main() {
  setUp(() {
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<(ActionItemsProvider, List<bool>)> pumpPage(WidgetTester tester) async {
    final completions = <bool>[];
    final provider = ActionItemsProvider(
      getActionItems: _items,
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
    expect(find.text('3'), findsOneWidget);
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

  testWidgets('a paywalled task shows a lock instead of a ring and offers no completion', (tester) async {
    await pumpPage(tester);
    expect(find.byIcon(Icons.lock_outline), findsOneWidget);
    expect(find.text('An older task behind the…'), findsOneWidget);
    // Two open rows: only the unlocked one can be completed.
    expect(find.bySemanticsLabel('Mark Complete'), findsOneWidget);
  });

  testWidgets('tapping a paywalled task goes to the plan page, with no task menu or page', (tester) async {
    await pumpApp(tester);

    await tester.tap(find.text('An older task behind the…'));
    // The plan page animates while it loads, so settle by time rather than by quiescence.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byType(UsagePage), findsOneWidget);
    expect(find.byType(TaskPage), findsNothing);
    expect(find.text('Open'), findsNothing);
    // Tear the route down so its timers don't outlive the test.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });

  testWidgets('a paywalled done task shows a lock and holding it opens no menu', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Completed'));
    await tester.pumpAndSettle();

    expect(find.text('A done task behind the…'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline), findsNWidgets(2));
    // Holding it ends like a tap on any locked row: the plan page, never the task menu.
    await tester.longPress(find.text('A done task behind the…'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Delete Task'), findsNothing);
    expect(find.text('Mark Incomplete'), findsNothing);
    expect(find.byType(UsagePage), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
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

  testWidgets('the task page rows stay activatable for assistive tech', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpPage(tester);
    await tester.tap(find.text('Draft the update'));
    await tester.pumpAndSettle();

    // The merged nodes keep their tap action: a screen reader can open the conversation and the rows.
    bool tappable(String label) =>
        tester.getSemantics(find.bySemanticsLabel(label)).getSemanticsData().hasAction(SemanticsAction.tap);
    expect(tappable('Open conversation'), isTrue);
    expect(tappable('Mark Complete'), isTrue);
    handle.dispose();
  });

  testWidgets('the page sends one completion toggle at a time', (tester) async {
    // A slow server: the second tap lands while the first toggle is still in flight.
    final (_, completions) = await pumpApp(tester, updateDelay: const Duration(milliseconds: 300));
    await tester.tap(find.text('Draft the update'));
    await tester.pumpAndSettle();

    final toggle = find.byKey(const Key('task_completed_toggle'));
    await tester.tap(toggle);
    await tester.pump();
    await tester.tap(toggle);
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(completions, [true]);
    expect(find.text('Completed'), findsOneWidget);
  });

  testWidgets('tapping a task opens its page with the conversation line, and Save wakes up on an edit', (tester) async {
    await pumpPage(tester);

    await tester.tap(find.text('Draft the update'));
    await tester.pumpAndSettle();
    expect(find.byType(TaskPage), findsOneWidget);
    expect(find.text('Open conversation'), findsOneWidget);
    expect(find.text('Mark Complete'), findsOneWidget);
    expect(find.text('Delete Task'), findsOneWidget);
    final save = find.byKey(const Key('task_save_button'));
    expect(tester.widget<OmiButton>(save).onPressed, isNull);

    await tester.enterText(find.byKey(const Key('task_description')), 'Draft the investor update');
    await tester.pump();
    expect(tester.widget<OmiButton>(save).onPressed, isNotNull);
  });
}
