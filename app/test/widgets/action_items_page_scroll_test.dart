import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';

/// Reproduction harness for "the Todos page won't scroll".
///
/// Pumps the real page with enough items to overflow the viewport and drags it,
/// asserting the scroll offset actually moved.
void main() {
  ActionItemWithMetadata item(int i) {
    final now = DateTime(2026, 8, 7, 9);
    return ActionItemWithMetadata(
      id: 'item-$i',
      description: 'Task number $i that is long enough to occupy a full row',
      completed: false,
      createdAt: now,
      updatedAt: now,
      sortOrder: i,
      source: 'test',
      status: 'active',
    );
  }

  testWidgets('the task list scrolls when its content overflows', (tester) async {
    final actionItems = ActionItemsProvider();
    actionItems.seedItems(List.generate(40, item));

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ActionItemsProvider>.value(value: actionItems),
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

    final scrollable = find.byType(Scrollable).first;
    final before = tester.state<ScrollableState>(scrollable).position.pixels;

    await tester.drag(find.byType(CustomScrollView), const Offset(0, -400));
    await tester.pump();

    final after = tester.state<ScrollableState>(scrollable).position.pixels;
    expect(after, greaterThan(before), reason: 'dragging up should scroll the list down');
  });
}
