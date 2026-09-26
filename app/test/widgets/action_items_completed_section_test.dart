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
    ActionItemsResponse(
      actionItems: [
        const ActionItemWithMetadata(id: 'open', description: 'Plan the launch', completed: false, sortOrder: 1000),
        ActionItemWithMetadata(
          id: 'done',
          description: 'Book the venue',
          completed: true,
          completedAt: DateTime.utc(2026, 9, 24, 10),
          sortOrder: 2000,
        ),
      ],
    );

/// To do keeps what was ticked in view under Completed, and lets it be cleared.
void main() {
  setUp(() {
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<(ActionItemsProvider, List<String>)> pumpPage(WidgetTester tester) async {
    final deletes = <String>[];
    final provider = ActionItemsProvider(
      getActionItems: _items,
      deleteActionItemRequest: (id) async {
        deletes.add(id);
        return true;
      },
      updateActionItemRequest: (id, {description, completed, dueAt}) async =>
          ActionItemWithMetadata(id: id, description: id, completed: completed ?? false),
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    return (provider, deletes);
  }

  Finder inCompleted(String text) =>
      find.descendant(of: find.byKey(const ValueKey('tasks_completed_section')), matching: find.text(text));

  testWidgets('a ticked task shows under Completed', (tester) async {
    await pumpPage(tester);
    expect(inCompleted('Book the venue'), findsOneWidget);
    expect(inCompleted('Plan the launch'), findsNothing);

    await tester.tap(find.bySemanticsLabel('Mark Complete'));
    await tester.pumpAndSettle();

    expect(inCompleted('Plan the launch'), findsOneWidget, reason: 'the check shows where the task went');
  });

  testWidgets('✕ deletes every completed task, after asking', (tester) async {
    final (_, deletes) = await pumpPage(tester);

    final clear = find.byKey(const ValueKey('tasks_completed_clear'));
    await tester.ensureVisible(clear);
    await tester.tap(clear);
    await tester.pumpAndSettle();
    expect(find.text('Delete 1 Task?'), findsOneWidget);

    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(deletes, ['done']);
    expect(find.byKey(const ValueKey('tasks_completed_section')), findsNothing);
  });
}
