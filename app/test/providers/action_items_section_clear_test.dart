import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';

ActionItemWithMetadata _item(String id, {bool completed = false}) =>
    ActionItemWithMetadata(id: id, description: id, completed: completed);

// Clearing a section must be one batch request. One DELETE per task makes every request
// write the owner's server-side vector route document at once, and the commits fail.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  late List<String> singleDeletes;
  late List<List<String>> bulkCalls;

  Future<ActionItemsProvider> provider(List<ActionItemWithMetadata> rows,
      {List<String>? Function(List<String>)? bulk}) async {
    singleDeletes = [];
    bulkCalls = [];
    final p = ActionItemsProvider(
      getActionItems: ({
        int limit = 100,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async =>
          ActionItemsResponse(actionItems: List.of(rows)),
      deleteActionItemRequest: (id) async {
        singleDeletes.add(id);
        return true;
      },
      bulkDeleteActionItemsRequest: (ids) async {
        bulkCalls.add(List.of(ids));
        return bulk == null ? ids : bulk(ids);
      },
    );
    await p.ensureLoaded();
    addTearDown(p.dispose);
    return p;
  }

  test('deleting a section sends one batch request and no single deletes', () async {
    final rows = [for (var i = 0; i < 40; i++) _item('done$i', completed: true), _item('open')];
    final p = await provider(rows);

    final section = p.actionItems.where((item) => item.completed).toList();
    expect(await p.deleteActionItems(section), isTrue);

    expect(singleDeletes, isEmpty);
    expect(bulkCalls, hasLength(1));
    expect(bulkCalls.single.toSet(), section.map((item) => item.id).toSet());
    expect(p.actionItems.map((item) => item.id), ['open']);
  });

  test('clearCompletedItems goes through the same single batch request', () async {
    final p = await provider([_item('a', completed: true), _item('b', completed: true), _item('c')]);

    expect(await p.clearCompletedItems(), isTrue);

    expect(singleDeletes, isEmpty);
    expect(bulkCalls.map((ids) => ids.toSet()), [
      {'a', 'b'}
    ]);
    expect(p.actionItems.map((item) => item.id), ['c']);
  });

  test('a failed batch puts every row back in place and reports failure', () async {
    final p = await provider([_item('a', completed: true), _item('b'), _item('c', completed: true)], bulk: (_) => null);
    final before = p.actionItems.map((item) => item.id).toList();

    expect(await p.deleteActionItems(p.actionItems.where((item) => item.completed).toList()), isFalse);

    expect(p.actionItems.map((item) => item.id), before);
    expect(singleDeletes, isEmpty);
  });

  test('a partial batch keeps the deleted rows gone and restores the rejected ones', () async {
    final p =
        await provider([_item('a', completed: true), _item('b', completed: true), _item('c')], bulk: (_) => ['a']);

    expect(await p.deleteActionItems(p.actionItems.where((item) => item.completed).toList()), isFalse);

    expect(p.actionItems.map((item) => item.id).toSet(), {'b', 'c'});
  });

  test('a locked task stays put and the rest of the section is still deleted', () async {
    // The batch endpoint rejects a whole request containing a locked task (402); a single
    // delete rejected only that task. Locked tasks are left out of the batch.
    const locked = ActionItemWithMetadata(id: 'locked', description: 'locked', completed: true, isLocked: true);
    final p = await provider([_item('a', completed: true), locked, _item('b', completed: true), _item('c')]);

    expect(await p.deleteActionItems(p.actionItems.where((item) => item.completed).toList()), isFalse);

    expect(bulkCalls.map((ids) => ids.toSet()), [
      {'a', 'b'}
    ]);
    expect(p.actionItems.map((item) => item.id).toSet(), {'locked', 'c'});
  });

  test('a section of only locked tasks sends nothing', () async {
    const locked = ActionItemWithMetadata(id: 'locked', description: 'locked', completed: true, isLocked: true);
    final p = await provider([locked, _item('c')]);

    expect(await p.deleteActionItems([locked]), isFalse);
    expect(bulkCalls, isEmpty);
    expect(singleDeletes, isEmpty);
  });

  test('a large section is sent in sequential all-or-nothing requests of at most 450', () async {
    // The server commits in 499-document batches, so one larger request can fail half done.
    final rows = [for (var i = 0; i < 1000; i++) _item('done$i', completed: true)];
    final p = await provider(rows);

    expect(await p.deleteActionItems(p.actionItems.toList()), isTrue);

    expect(bulkCalls.map((ids) => ids.length), [450, 450, 100]);
    expect(bulkCalls.expand((ids) => ids).toSet(), rows.map((item) => item.id).toSet());
    expect(singleDeletes, isEmpty);
    expect(p.actionItems, isEmpty);
  });

  test('a failed later request restores only its own and later rows', () async {
    final rows = [for (var i = 0; i < 1000; i++) _item('done$i', completed: true)];
    var calls = 0;
    final p = await provider(rows, bulk: (ids) => ++calls == 2 ? null : ids);

    expect(await p.deleteActionItems(p.actionItems.toList()), isFalse);

    // The first 450 were confirmed and stay gone; the failed chunk and the unsent rest return.
    expect(bulkCalls, hasLength(2));
    expect(p.actionItems.map((item) => item.id).toList(), [for (var i = 450; i < 1000; i++) 'done$i']);
  });

  test('an empty section is a no-op', () async {
    final p = await provider([_item('c')]);

    expect(await p.deleteActionItems(const []), isTrue);
    expect(bulkCalls, isEmpty);
    expect(singleDeletes, isEmpty);
  });
}
