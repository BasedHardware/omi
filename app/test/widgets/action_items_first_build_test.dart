import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/typed_action_items_screen.dart';

class _CountedTask extends ActionItemWithMetadata {
  _CountedTask(int i, DateTime? due)
      : super(id: 'task-$i', description: 'Task $i', completed: false, dueAt: due, sortOrder: 50 - i);

  int sortReads = 0;
  @override
  int get sortOrder {
    sortReads++;
    return super.sortOrder;
  }
}

void main() {
  testWidgets('first Tasks frame does not sort or build offscreen date sections', (tester) async {
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    addTearDown(Env.clearApiBaseUrlOverrideForTesting);
    tester.view.physicalSize = const Size(390, 320);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day, 12);
    final items = List.generate(
        50,
        (i) => _CountedTask(
            i,
            switch (i ~/ 10) {
              0 => today,
              1 => today.add(const Duration(days: 1)),
              2 => today.add(const Duration(days: 5)),
              3 => null,
              _ => today.subtract(const Duration(days: 5)),
            }));
    final provider = ActionItemsProvider(
        getActionItems: (
                {limit = 100,
                offset = 0,
                completed,
                conversationId,
                startDate,
                endDate,
                dueStartDate,
                dueEndDate}) async =>
            ActionItemsResponse(actionItems: items));
    addTearDown(provider.dispose);
    final screen = await buildTypedActionItemsScreen(provider);
    await provider.ensureLoaded();
    for (final item in items) {
      item.sortReads = 0;
    }
    await tester.pumpWidget(screen);
    expect(items.take(10).fold<int>(0, (sum, item) => sum + item.sortReads), greaterThan(0));
    expect(items.skip(10).every((item) => item.sortReads == 0), isTrue,
        reason: 'Tomorrow/Later/No Deadline/Overdue sorting waits until that section is visible');
    expect(find.text('Task 49'), findsNothing);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Task 49'), 250,
        maxScrolls: 30, scrollable: find.byType(Scrollable).first);
    expect(find.text('Task 49').hitTestable(), findsOneWidget);
    expect(items.last.sortReads, greaterThan(0));
  });
}
