/// Clear Completed deletes a whole section behind a "cannot be undone" confirm. When the server
/// rejects the deletes, the rows come back; the page must say so instead of letting them reappear
/// in silence (the single-row delete already does, #21590 did the same for completion saves).
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/typed_action_items_screen.dart';

/// Two completed tasks due today on a fake server that accepts or rejects every delete.
class _TaskServer {
  _TaskServer({required this.accept});

  final bool accept;
  final deleted = <String>[];

  List<ActionItemWithMetadata> get _tasks => [
        for (final id in ['task-1', 'task-2'])
          if (!deleted.contains(id))
            ActionItemWithMetadata(id: id, description: 'Done $id', completed: true, dueAt: DateTime.now()),
      ];

  Future<ActionItemsResponse?> list({
    int limit = 100,
    int offset = 0,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
  }) async =>
      ActionItemsResponse(actionItems: _tasks);

  Future<bool> delete(String id) async {
    if (!accept) return false;
    deleted.add(id);
    return true;
  }
}

void main() {
  setUp(() async {
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<ActionItemsProvider> clearCompleted(WidgetTester tester, {required bool accept}) async {
    final server = _TaskServer(accept: accept);
    final provider = ActionItemsProvider(getActionItems: server.list, deleteActionItemRequest: server.delete);
    addTearDown(provider.dispose);
    await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    // Every task is done, so the list opens on the completed view with its Clear Completed control.
    expect(find.text('Done task-1'), findsOneWidget);
    expect(find.text('Done task-2'), findsOneWidget);

    // The section header's count and ✕ form one control labelled Clear Completed.
    await tester.tap(find.byWidgetPredicate((widget) => widget.runtimeType.toString() == '_SectionHeaderTapTarget'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    return provider;
  }

  testWidgets('rejected deletes put the tasks back and say so', (tester) async {
    final provider = await clearCompleted(tester, accept: false);

    expect(provider.actionItems.map((item) => item.id), unorderedEquals(['task-1', 'task-2']));
    expect(find.text('Failed to delete task'), findsOneWidget);
  });

  testWidgets('accepted deletes clear the section without a complaint', (tester) async {
    final provider = await clearCompleted(tester, accept: true);

    expect(provider.actionItems, isEmpty);
    expect(find.text('Failed to delete task'), findsNothing);
  });
}
