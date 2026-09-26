import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';

ActionItemWithMetadata _item(String id) => ActionItemWithMetadata(id: id, description: id, completed: false);

Future<ActionItemsResponse?> _empty({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    const ActionItemsResponse(actionItems: []);

/// The deferred single-task delete behind every task Undo toast (docs/ux-contract.md §4, D5).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<(ActionItemsProvider, List<String>)> provider({bool serverAccepts = true}) async {
    final calls = <String>[];
    final p = ActionItemsProvider(
      getActionItems: _empty,
      deleteActionItemRequest: (id) async {
        calls.add(id);
        return serverAccepts;
      },
    );
    await p.ensureLoaded();
    addTearDown(p.dispose);
    p.actionItems.addAll([_item('a'), _item('b'), _item('c')]);
    return (p, calls);
  }

  test('staging hides the task without touching the server', () async {
    final (p, calls) = await provider();

    p.stageDeleteActionItem(p.actionItems[1]);

    expect(p.actionItems.map((i) => i.id), ['a', 'c']);
    expect(calls, isEmpty);
    expect(p.isDeleteStaged('b'), isTrue);
  });

  test('undo puts the task back where it was and never deletes it', () async {
    final (p, calls) = await provider();

    p.stageDeleteActionItem(p.actionItems[1]);
    expect(p.undoStagedDelete('b'), isTrue);

    expect(p.actionItems.map((i) => i.id), ['a', 'b', 'c']);
    expect(await p.commitStagedDelete('b'), isFalse, reason: 'an undone delete has nothing to commit');
    expect(calls, isEmpty);
  });

  test('commit deletes on the server and keeps the task gone', () async {
    final (p, calls) = await provider();

    p.stageDeleteActionItem(p.actionItems[1]);
    expect(await p.commitStagedDelete('b'), isTrue);

    expect(calls, ['b']);
    expect(p.actionItems.map((i) => i.id), ['a', 'c']);
    expect(p.undoStagedDelete('b'), isFalse, reason: 'a committed delete cannot be undone');
  });

  test('a rejected commit brings the task back', () async {
    final (p, calls) = await provider(serverAccepts: false);

    p.stageDeleteActionItem(p.actionItems[1]);
    expect(await p.commitStagedDelete('b'), isFalse);

    expect(calls, ['b']);
    expect(p.actionItems.map((i) => i.id), ['a', 'b', 'c']);
  });
}
