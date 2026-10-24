import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/task_categorization.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _CountedTasks extends TaskCategorizationList {
  _CountedTasks()
      : super(List.generate(
            500, (i) => ActionItemWithMetadata(id: '$i', description: 'Task $i', completed: false, sortOrder: i + 1)));
  int reads = 0;
  @override
  ActionItemWithMetadata operator [](int index) {
    reads++;
    return super[index];
  }
}

class _Tasks extends ActionItemsProvider {
  _Tasks(this.rows)
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
                const ActionItemsResponse(actionItems: []));
  final _CountedTasks rows;
  @override
  List<ActionItemWithMetadata> get actionItems => rows;
  void ping() => notifyListeners();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('500-task categorization reuses buckets on no-op notifies', (tester) async {
    final rows = _CountedTasks();
    final provider = _Tasks(rows);
    addTearDown(provider.dispose);
    var runs = 0;
    var consumerBuilds = 0;
    Object? previous;
    // Reproduce the exact Consumer -> categorizeTasks call in ActionItemsPage.
    // That page is owned by #23432; this intentionally avoids modifying it.
    await tester.pumpWidget(ChangeNotifierProvider<ActionItemsProvider>.value(
      value: provider,
      child: MaterialApp(home: Consumer<ActionItemsProvider>(builder: (_, p, __) {
        consumerBuilds++;
        final categories = categorizeTasks(p.actionItems, p.showCompletedView);
        if (!identical(categories, previous)) runs++;
        previous = categories;
        return ListView.builder(
            itemCount: categories[TaskCategory.noDeadline]!.length,
            itemBuilder: (_, i) => SizedBox(height: 60, child: Text('Task $i')));
      })),
    ));
    runs = 0;
    consumerBuilds = 0;
    rows.reads = 0;
    for (var i = 0; i < 20; i++) {
      provider.ping();
      await tester.pump();
    }
    debugPrint(
        'SCROLL_TASK_DERIVATION no_op_notifies=20 consumer_builds=$consumerBuilds categorize_runs=$runs row_reads=${rows.reads}');
    expect(runs, 0);
    expect(rows.reads, 0);
    runs = 0;
    consumerBuilds = 0;
    rows.reads = 0;
    await tester.fling(find.byType(ListView), const Offset(0, -700), 2000);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    debugPrint(
        'SCROLL_TASK_DERIVATION pure_scroll_frames=30 consumer_builds=$consumerBuilds categorize_runs=$runs row_reads=${rows.reads}');
    expect(runs, 0);
    expect(rows.reads, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
