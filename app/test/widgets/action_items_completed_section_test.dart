import 'package:flutter/material.dart';
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
            id: 'done1', description: 'Reply to the review', completed: true, completedAt: DateTime(2026, 10, 1)),
        ActionItemWithMetadata(
            id: 'done2', description: 'Pay the invoice', completed: true, completedAt: DateTime(2026, 10, 2)),
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

  testWidgets('completed tasks sit folded at the bottom of the list, newest first, with Clear', (tester) async {
    final (_, completions) = await pumpPage(tester);

    expect(find.text('Completed'), findsOneWidget);
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
    final provider = ActionItemsProvider(getActionItems: _items);
    addTearDown(provider.dispose);
    // The shared harness has no UsageProvider; the plan page needs an inert one.
    // Providers above the navigator: the plan page is pushed as a route, so it must find them too.
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
        ChangeNotifierProvider<GoalsProvider>(create: (_) => GoalsProvider()),
        ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => TaskIntegrationProvider()),
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
