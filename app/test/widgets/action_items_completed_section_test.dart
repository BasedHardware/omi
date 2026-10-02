import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/task_page.dart';
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
