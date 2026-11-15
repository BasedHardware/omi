import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';

ActionItemWithMetadata _item(String id, {int indent = 0}) =>
    ActionItemWithMetadata(id: id, description: id, completed: false, indentLevel: indent);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  late List<ActionItemWithMetadata> serverRows;
  late List<List<Map<String, dynamic>>> writes;
  late List<Completer<bool>> receipts;
  // When set, the next read takes its server snapshot now but resolves only when completed.
  Completer<void>? holdRead;

  Future<ActionItemsProvider> provider() async {
    serverRows = [_item('parent'), _item('child')];
    writes = [];
    receipts = [];
    holdRead = null;
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
      }) async {
        final snapshot = List.of(serverRows);
        final hold = holdRead;
        holdRead = null;
        if (hold != null) await hold.future;
        return ActionItemsResponse(actionItems: snapshot);
      },
      batchUpdateActionItemsRequest: (items) {
        writes.add(items);
        final receipt = Completer<bool>();
        receipts.add(receipt);
        return receipt.future;
      },
    );
    await p.ensureLoaded();
    addTearDown(p.dispose);
    return p;
  }

  int indentOf(ActionItemsProvider p, String id) => p.actionItems.firstWhere((item) => item.id == id).indentLevel;

  Future<void> debounce() => Future<void>.delayed(const Duration(milliseconds: 600));

  test('a list read during an unsaved indent does not revert the sub-task', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await p.fetchActionItems(); // server still has indent 0
    expect(indentOf(p, 'child'), 1);

    await debounce();
    expect(writes, [
      [
        {'id': 'child', 'indent_level': 1}
      ]
    ]);
    await p.fetchActionItems(); // write still in flight
    expect(indentOf(p, 'child'), 1);

    serverRows = [_item('parent'), _item('child', indent: 1)];
    receipts.single.complete(true);
    await Future<void>.delayed(Duration.zero);
    await p.fetchActionItems();
    expect(indentOf(p, 'child'), 1);
    expect(writes, hasLength(1));
  });

  test('a failed indent write stays visible and is retried after the next list read', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await debounce();
    receipts.single.complete(false);
    await Future<void>.delayed(Duration.zero);

    await p.fetchActionItems();
    expect(indentOf(p, 'child'), 1);

    await debounce();
    expect(writes, hasLength(2));
    expect(writes.last, [
      {'id': 'child', 'indent_level': 1}
    ]);
    serverRows = [_item('parent'), _item('child', indent: 1)];
    receipts.last.complete(true);
    await Future<void>.delayed(Duration.zero);

    await p.fetchActionItems();
    await debounce();
    expect(writes, hasLength(2), reason: 'an acknowledged indent is not written again');
  });

  test('an older acknowledgement cannot clear a newer indent or race it to the server', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await debounce();
    p.updateItemIndentLevel('child', 2);
    await debounce();
    expect(writes, hasLength(1), reason: 'one layout write at a time');

    receipts.first.complete(true);
    await Future<void>.delayed(Duration.zero);
    expect(writes, hasLength(2));
    expect(writes.last, [
      {'id': 'child', 'indent_level': 2}
    ]);

    await p.fetchActionItems(); // server still has the first value
    expect(indentOf(p, 'child'), 2);
    receipts.last.complete(true);
  });

  test('an edit made while a failing write is in flight is still sent', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await debounce();
    p.updateItemIndentLevel('child', 2);
    await debounce(); // its timer fires while the first write is in flight
    expect(writes, hasLength(1));

    receipts.first.complete(false);
    await debounce();
    expect(writes, hasLength(2), reason: 'no further edit or list read is needed');
    expect(writes.last, [
      {'id': 'child', 'indent_level': 2}
    ]);
    receipts.last.complete(true);
  });

  test('a read whose snapshot predates the acknowledgement cannot revert the indent', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await debounce();
    final released = Completer<void>();
    holdRead = released;
    final read = p.fetchActionItems(); // snapshot taken now: indent 0
    await Future<void>.delayed(Duration.zero);

    serverRows = [_item('parent'), _item('child', indent: 1)];
    receipts.single.complete(true);
    await Future<void>.delayed(Duration.zero);
    released.complete();
    await read;
    expect(indentOf(p, 'child'), 1);

    await p.fetchActionItems(); // a read after the acknowledgement uses the server value
    expect(indentOf(p, 'child'), 1);
  });

  test('a successful Home read retries a failed indent write', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await debounce();
    receipts.single.complete(false);
    await Future<void>.delayed(Duration.zero);

    await p.ensureHomeTodayTasksLoaded();
    await debounce();
    expect(writes, hasLength(2));
    receipts.last.complete(true);
  });

  test('a successful read during a write that then fails still retries it', () async {
    final p = await provider();

    p.updateItemIndentLevel('child', 1);
    await debounce();
    await p.fetchActionItems(); // succeeds while the write is in flight
    receipts.single.complete(false);
    await debounce();
    expect(writes, hasLength(2), reason: 'the read proved the server reachable');
    receipts.last.complete(true);
  });
}
