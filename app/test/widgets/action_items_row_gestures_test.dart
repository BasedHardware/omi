import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
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
    const ActionItemsResponse(
      actionItems: [
        ActionItemWithMetadata(id: 'parent', description: 'Plan the launch', completed: false, sortOrder: 1000),
        ActionItemWithMetadata(
          id: 'child',
          description: 'Book the venue',
          completed: false,
          sortOrder: 2000,
          indentLevel: 1,
        ),
      ],
    );

/// Swipes mean the same thing on every task row (hub #4) and deletes offer Undo (hub #3, D5).
void main() {
  setUp(() {
    PlatformManager.initializeForLocalHarness();
    // Indent/sort persistence is not injectable; point it at a dead loopback port (the test
    // binding's HTTP client answers every request locally anyway).
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<(ActionItemsProvider, List<String>, List<bool>)> pumpPage(WidgetTester tester) async {
    final deletes = <String>[];
    final completions = <bool>[];
    final provider = ActionItemsProvider(
      getActionItems: _items,
      deleteActionItemRequest: (id) async {
        deletes.add(id);
        return true;
      },
      updateActionItemRequest: (id, {description, completed, dueAt}) async {
        if (completed != null) completions.add(completed);
        return ActionItemWithMetadata(id: id, description: id, completed: completed ?? false);
      },
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    return (provider, deletes, completions);
  }

  testWidgets('swiping right on an indented task completes it instead of changing its indent', (tester) async {
    final (provider, _, completions) = await pumpPage(tester);
    expect(find.text('Book the venue'), findsOneWidget);

    await tester.drag(find.text('Book the venue'), const Offset(400, 0));
    await tester.pumpAndSettle();

    expect(completions, [true]);
    expect(provider.actionItems.firstWhere((i) => i.id == 'child').indentLevel, 1);
  });

  testWidgets('swiping left on an indented task deletes it with Undo, no dialog', (tester) async {
    final (provider, deletes, _) = await pumpPage(tester);

    await tester.drag(find.text('Book the venue'), const Offset(-400, 0));
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text('Book the venue'), findsNothing);
    expect(find.text('Task deleted'), findsOneWidget);
    expect(deletes, isEmpty, reason: 'the server delete waits for the Undo window');

    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(find.text('Book the venue'), findsOneWidget);
    expect(deletes, isEmpty);
    expect(provider.isDeleteStaged('child'), isFalse);
  });

  testWidgets('long-press opens the row menu with Select and the indent controls', (tester) async {
    final (provider, _, _) = await pumpPage(tester);

    await tester.longPress(find.text('Book the venue'));
    await tester.pumpAndSettle();

    expect(find.text('Open'), findsOneWidget);
    expect(find.text('Select'), findsOneWidget);
    expect(find.text('Outdent'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);

    await tester.tap(find.text('Outdent'));
    await tester.pumpAndSettle();
    expect(provider.actionItems.firstWhere((i) => i.id == 'child').indentLevel, 0);

    await tester.longPress(find.text('Book the venue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Select'));
    await tester.pumpAndSettle();
    expect(provider.isSelectionMode, isTrue);
    expect(provider.isItemSelected('child'), isTrue);
  });
}
