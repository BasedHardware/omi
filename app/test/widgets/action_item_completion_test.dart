import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/widgets/action_item_tile_widget.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';

/// Checking a task off has to *show* the completion before the item is handed
/// to the provider that moves it into Completed — fill the circle green, strike
/// the text through, and only then report the toggle. These tests pin that
/// ordering, which is invisible to a static read of the widget: the delay is a
/// bare `Future.delayed` between the setState and the callback.
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

  Future<void> pumpTile(
    WidgetTester tester, {
    required ActionItemWithMetadata item,
    required void Function(bool) onToggle,
  }) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => TaskIntegrationProvider()),
          ChangeNotifierProvider<UsageProvider>(create: (_) => UsageProvider()),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: ActionItemTileWidget(actionItem: item, onToggle: onToggle),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  /// The circle is the only 24x24 [AnimatedContainer] in the tile.
  BoxDecoration checkboxDecoration(WidgetTester tester) {
    final container = tester.widget<AnimatedContainer>(
      find.byWidgetPredicate((w) => w is AnimatedContainer && w.constraints?.maxWidth == 24.0),
    );
    return container.decoration! as BoxDecoration;
  }

  TextStyle descriptionStyle(WidgetTester tester) {
    return tester.widget<Text>(find.text('Audit spacing and type scale')).style!;
  }

  testWidgets('an open task shows an empty circle and undecorated text', (tester) async {
    await pumpTile(tester, item: buildItem(), onToggle: (_) {});

    expect(checkboxDecoration(tester).color, Colors.transparent);
    expect(descriptionStyle(tester).decoration, isNull);
  });

  testWidgets('tapping fills the circle green and strikes the text through before reporting', (tester) async {
    final toggles = <bool>[];
    await pumpTile(tester, item: buildItem(), onToggle: toggles.add);

    await tester.tap(find.byWidgetPredicate((w) => w is AnimatedContainer && w.constraints?.maxWidth == 24.0));
    await tester.pump();

    // Mid-animation: the user sees completion, but the provider has not been
    // told yet — so the row is still sitting in its original section.
    expect(checkboxDecoration(tester).color, const Color(0xFF34C759));
    expect(descriptionStyle(tester).decoration, TextDecoration.lineThrough);
    expect(toggles, isEmpty, reason: 'onToggle must not fire until the completed state has been shown');

    await tester.pump(const Duration(milliseconds: 500));

    expect(toggles, [true], reason: 'onToggle fires once the completion has been shown');
    await tester.pumpAndSettle();
  });

  testWidgets('un-checking reports immediately, with no completion animation', (tester) async {
    final toggles = <bool>[];
    await pumpTile(tester, item: buildItem(completed: true), onToggle: toggles.add);

    await tester.tap(find.byWidgetPredicate((w) => w is AnimatedContainer && w.constraints?.maxWidth == 24.0));
    await tester.pump();

    // Undo is not an accomplishment — it should not be paced by the celebration.
    expect(toggles, [false]);
    await tester.pumpAndSettle();
  });
}
