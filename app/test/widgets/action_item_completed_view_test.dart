import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';

import 'support/fake_action_item_api.dart';

/// A checked-off task has to leave the active list and turn up under the
/// Completed toggle. The page filters purely on `item.completed`, so this is
/// really a guard on the completed state surviving the toggle round-trip.
void main() {
  ActionItemWithMetadata item(String id, String description) {
    final now = DateTime(2026, 8, 7, 9);
    return ActionItemWithMetadata(
      id: id,
      description: description,
      completed: false,
      createdAt: now,
      updatedAt: now,
      sortOrder: 0,
      source: 'test',
      status: 'active',
    );
  }

  Future<ActionItemsProvider> pumpPage(WidgetTester tester) async {
    final provider = ActionItemsProvider(updateActionItemRequest: fakeUpdate);
    provider.seedItems([item('a', 'Reply to Priya'), item('b', 'Book the dinner reservation')]);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
          ChangeNotifierProvider<GoalsProvider>(create: (_) => GoalsProvider()),
          ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => TaskIntegrationProvider()),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: ActionItemsPage(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    return provider;
  }

  testWidgets('a checked task stays completed and leaves the active list', (tester) async {
    final provider = await pumpPage(tester);

    expect(find.text('Reply to Priya'), findsOneWidget);

    final circle = find.byWidgetPredicate((w) => w is SizedBox && w.width == 44 && w.height == 48);
    await tester.tap(circle.first, warnIfMissed: false);
    await tester.pump();

    // Let the 500ms completion window and the provider write drain.
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();

    final completed = provider.actionItems.where((i) => i.completed).toList();
    expect(completed, hasLength(1), reason: 'the completion must survive, not roll back');

    // Gone from the active list...
    expect(find.text(completed.single.description), findsNothing);
    // ...and still the other one is there.
    expect(provider.actionItems.where((i) => !i.completed), hasLength(1));
  });

  testWidgets('a completed task appears in the inline Completed section', (tester) async {
    final provider = await pumpPage(tester);

    // Nothing done yet — no section at all.
    expect(find.text('COMPLETED'), findsNothing);

    final circle = find.byWidgetPredicate((w) => w is SizedBox && w.width == 44 && w.height == 48);
    await tester.tap(circle.first, warnIfMissed: false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();

    expect(find.text('COMPLETED'), findsOneWidget, reason: 'the section appears once something is done');

    final done = provider.actionItems.firstWhere((i) => i.completed);
    // Collapsed by default, so the row is not rendered until expanded.
    expect(find.text(done.description), findsNothing);

    await tester.tap(find.text('COMPLETED'));
    await tester.pumpAndSettle();

    expect(find.text(done.description), findsOneWidget, reason: 'expanding reveals the completed task');
  });

  testWidgets('the completed view surfaces the checked task', (tester) async {
    final provider = await pumpPage(tester);

    final circle = find.byWidgetPredicate((w) => w is SizedBox && w.width == 44 && w.height == 48);
    await tester.tap(circle.first, warnIfMissed: false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();

    final done = provider.actionItems.firstWhere((i) => i.completed);

    provider.toggleShowCompletedView();
    await tester.pumpAndSettle();

    expect(find.text(done.description), findsOneWidget, reason: 'completed tasks belong in the completed view');
  });
}
