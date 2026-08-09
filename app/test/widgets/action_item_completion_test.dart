import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/utils/ui_guidelines.dart';

import 'support/fake_action_item_api.dart';

/// Checking a task off has to *show* the completion before the item is handed
/// to the provider: fill the circle with the completion accent, strike the text
/// through, and only then report it.
///
/// These run against [ActionItemsPage] rather than a tile widget on purpose —
/// the page owns the checkbox and the toggle handler, and an earlier version of
/// this test exercised an unused tile widget instead, which passed while the
/// real screen was untouched.
void main() {
  ActionItemWithMetadata buildItem({bool completed = false}) {
    final now = DateTime(2026, 8, 7, 9);
    return ActionItemWithMetadata(
      id: 'item-1',
      description: 'Audit spacing and type scale',
      completed: completed,
      createdAt: now,
      updatedAt: now,
      completedAt: completed ? now : null,
      sortOrder: 0,
      source: 'test',
      status: 'active',
    );
  }

  Future<ActionItemsProvider> pumpPage(WidgetTester tester, {bool completed = false}) async {
    final provider = ActionItemsProvider(updateActionItemRequest: fakeUpdate);
    provider.seedItems([buildItem(completed: completed)]);

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

  /// The completed circle is the only Container filled with the completion
  /// accent on the page.
  bool hasCompletedCheck(WidgetTester tester) {
    return tester.widgetList<Container>(find.byType(Container)).any((c) {
      final decoration = c.decoration;
      return decoration is BoxDecoration && decoration.color == AppStyles.completedAccent;
    });
  }

  bool isStruckThrough(WidgetTester tester) {
    final text = tester.widget<Text>(find.text('Audit spacing and type scale'));
    return text.style?.decoration == TextDecoration.lineThrough;
  }

  testWidgets('an open task shows no completed check and no strikethrough', (tester) async {
    await pumpPage(tester);

    expect(hasCompletedCheck(tester), isFalse);
    expect(isStruckThrough(tester), isFalse);
  });

  testWidgets('tapping the circle fills the check and strikes the text through', (tester) async {
    await pumpPage(tester);

    // The tap target is the 44x48 box around the circle, left of the text.
    final circle = find.byWidgetPredicate(
      (w) => w is SizedBox && w.width == 44 && w.height == 48,
    );
    expect(circle, findsWidgets, reason: 'the completion circle should have a 44x48 tap target');

    await tester.tap(circle.first, warnIfMissed: false);
    await tester.pump();

    expect(hasCompletedCheck(tester), isTrue, reason: 'the circle fills on tap');
    expect(isStruckThrough(tester), isTrue, reason: 'the text strikes through on tap');

    // Let the 500ms completion window and the provider call drain.
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
  });
}
