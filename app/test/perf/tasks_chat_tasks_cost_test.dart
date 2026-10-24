import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/project_task_sections.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/typed_action_items_screen.dart';

class _Tasks extends ActionItemsProvider {
  _Tasks(List<ActionItemWithMetadata> items)
      : super(
            getActionItems: (
                    {limit = 100,
                    offset = 0,
                    completed,
                    conversationId,
                    startDate,
                    endDate,
                    dueStartDate,
                    dueEndDate}) async =>
                ActionItemsResponse(actionItems: items),
            updateActionItemRequest: (id, {description, completed, dueAt}) async =>
                ActionItemWithMetadata(id: id, description: 'Task $id', completed: completed ?? false));
  void ping() => notifyListeners();
}

void main() {
  setUp(() {
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);
  for (final semantics in [false, true]) {
    for (final overdue in [false, true]) {
      testWidgets('240 ${overdue ? 'overdue' : 'undated'} tasks stay lazy, semantics=$semantics', (tester) async {
        final handle = semantics ? tester.ensureSemantics() : null;
        try {
          final provider = _Tasks(List.generate(
              240,
              (i) => ActionItemWithMetadata(
                  id: '$i',
                  description: 'Task $i',
                  completed: false,
                  sortOrder: i + 1,
                  dueAt: overdue ? DateTime(2020) : null)));
          addTearDown(provider.dispose);
          await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
          await provider.ensureLoaded();
          await tester.pumpAndSettle();
          final mounted = find.byType(TaskCompletionMark).evaluate().length;
          var rows = 0;
          debugOnRebuildDirtyWidget = (element, builtOnce) {
            if (element.widget is TaskCompletionMark) rows++;
          };
          addTearDown(() => debugOnRebuildDirtyWidget = null);
          for (var i = 0; i < 5; i++) {
            provider.ping();
            await tester.pump();
          }
          final noOpRows = rows;
          rows = 0;
          await provider.updateActionItemState(provider.actionItems.first, true);
          await tester.pumpAndSettle();
          debugPrint('TASKS_COST overdue=$overdue semantics=$semantics mounted=$mounted noop5=$noOpRows toggle=$rows');
          expect(mounted, lessThan(40));
          expect(noOpRows, lessThan(200));
          expect(rows, lessThan(80));
          await tester.scrollUntilVisible(find.text('Task 239'), 600,
              scrollable: find.byType(Scrollable).first, maxScrolls: 30);
          expect(find.text('Task 239'), findsOneWidget);
          await tester.pumpAndSettle();
          final endMounted = find.byType(TaskCompletionMark).evaluate().length;
          debugPrint(
              'TASKS_SCROLL overdue=$overdue semantics=$semantics endpoint_mounted=$endMounted idle_callbacks=${tester.binding.transientCallbackCount}');
          expect(endMounted, lessThan(40));
          expect(tester.binding.transientCallbackCount, 0);
          await tester.pumpWidget(const SizedBox.shrink());
        } finally {
          handle?.dispose();
        }
      });
    }
  }

  testWidgets('lazy sections retain the expanded first-position drag target', (tester) async {
    final provider = _Tasks(List.generate(
        20, (i) => ActionItemWithMetadata(id: '$i', description: 'Task $i', completed: false, sortOrder: i + 1)));
    addTearDown(provider.dispose);
    await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    final before = tester.getTopLeft(find.text('Task 0')).dy;
    final gesture = await tester.startGesture(tester.getCenter(find.text('Task 1')));
    await tester.pump(const Duration(milliseconds: 450));
    await gesture.moveBy(const Offset(0, 70));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    final expansion = tester.getTopLeft(find.text('Task 0')).dy - before;
    debugPrint('TASKS_DRAG first_position_expansion=$expansion');
    await gesture.cancel();
    await tester.pumpAndSettle();
    expect(expansion, closeTo(16, 0.5), reason: 'the first-position target expands from 4 to 20 during a section drag');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('one 240-task project only builds visible rows', (tester) async {
    final handle = tester.ensureSemantics();
    try {
      var built = 0;
      final items = List.generate(
          240,
          (i) => ActionItemWithMetadata(
              id: '$i', description: 'Task $i', completed: false, sortOrder: i + 1, workstreamId: 'p'));
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: Builder(
                builder: (context) => CustomScrollView(
                    slivers: projectTaskSections(
                        context: context,
                        items: items,
                        projects: const {'p': EntityRef(entityId: 'p', type: EntityType.project, name: 'Project')},
                        buildRow: (item, group) {
                          built++;
                          return SizedBox(height: 50, child: Text(item.description));
                        })))),
      ));
      debugPrint('PROJECT_COST initial_row_builds=$built');
      expect(built, lessThan(40));
      await tester.scrollUntilVisible(find.text('Task 239'), 600, maxScrolls: 30);
      expect(find.text('Task 239'), findsOneWidget);
    } finally {
      handle.dispose();
    }
  });
}
