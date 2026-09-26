import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/services/siri_integration.dart';

class _SiriTaskHost extends SiriIndexApi {
  final indexed = <String, SiriTask>{};
  final deleted = <String>[];

  @override
  Future<void> upsertTasks(String uid, List<SiriTask> rows) async {
    for (final row in rows) {
      indexed[row.id] = row;
    }
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {
    if (type == 'task') deleted.addAll(ids);
  }
}

ActionItemWithMetadata _item(String id, {String title = 'Original', bool completed = false, DateTime? dueAt}) =>
    ActionItemWithMetadata(
        id: id,
        description: title,
        completed: completed,
        createdAt: DateTime.utc(2026, 9, 26),
        dueAt: dueAt,
        completedAt: completed ? DateTime.now() : null);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<(ActionItemsProvider, _SiriTaskHost)> makeProvider({
    List<ActionItemWithMetadata> rows = const [],
    bool deleteSucceeds = true,
    List<String>? bulkDeleted,
  }) async {
    final host = _SiriTaskHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
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
          ActionItemsResponse(actionItems: rows),
      deleteActionItemRequest: (id) async => deleteSucceeds,
      bulkDeleteActionItemsRequest: (ids) async => bulkDeleted ?? ids,
      createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
          _item('created', title: description, completed: completed, dueAt: dueAt),
      updateActionItemRequest: (id, {description, completed, dueAt}) async => _item(id,
          title: description ?? rows.first.description,
          completed: completed ?? rows.first.completed,
          dueAt: dueAt ?? rows.first.dueAt),
      updateDueDateRequest: (id, {dueAt, clearDueAt = false}) async =>
          _item(id, title: rows.first.description, completed: rows.first.completed, dueAt: clearDueAt ? null : dueAt),
    );
    addTearDown(provider.dispose);
    await provider.fetchActionItems();
    return (provider, host);
  }

  test('confirmed create immediately indexes the server ID', () async {
    final (provider, host) = await makeProvider();
    expect(await provider.createActionItem(description: 'Created task'), isNotNull);
    expect(host.indexed['created']?.title, 'Created task');
  });

  test('confirmed completion, title and due date refresh the indexed projection', () async {
    final original = _item('task');
    final (provider, host) = await makeProvider(rows: [original]);
    expect(await provider.updateActionItemState(original, true), isTrue);
    expect(host.indexed['task']?.completed, isTrue);
    expect(await provider.updateActionItemDescription(original, 'Renamed'), isTrue);
    expect(host.indexed['task']?.title, 'Renamed');
    final dueAt = DateTime.utc(2026, 10, 1);
    expect(await provider.updateActionItemDueDate(original, dueAt), isTrue);
    expect(host.indexed['task']?.dueAtMs, dueAt.millisecondsSinceEpoch);
  });

  test('rejected delete leaves the index intact; confirmed staged delete removes it', () async {
    final original = _item('task');
    final (rejected, rejectedHost) = await makeProvider(rows: [original], deleteSucceeds: false);
    expect(await rejected.deleteActionItem(original), isFalse);
    expect(rejectedHost.deleted, isEmpty);

    final (confirmed, confirmedHost) = await makeProvider(rows: [original]);
    confirmed.stageDeleteActionItem(original);
    expect(await confirmed.commitStagedDelete(original.id), isTrue);
    expect(confirmedHost.deleted, ['task']);
  });

  test('confirmed bulk delete removes every returned task ID from the index', () async {
    final (provider, host) = await makeProvider(rows: [_item('a'), _item('b')]);
    provider.startSelectionWithItem('a');
    provider.selectItem('b');
    expect(await provider.deleteSelectedItems(), isTrue);
    expect(host.deleted.toSet(), {'a', 'b'});
  });
}
