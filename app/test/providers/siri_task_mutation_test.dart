import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/services/siri_integration.dart';

class _SiriTaskHost extends SiriIndexApi {
  final indexed = <String, SiriTask>{};
  final deleted = <String>[];

  @override
  Future<void> reconcileTasks(String uid, List<SiriTask> rows, bool includeCompleted) async {
    final ids = rows.map((row) => row.id).toSet();
    indexed.removeWhere((id, row) => (includeCompleted || !row.completed) && !ids.contains(id));
    await upsertTasks(uid, rows);
  }

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

class _TypedTaskApi extends api.ActionItemsApi {
  _TypedTaskApi(this.result) : super(baseUrl: 'http://localhost/');
  ApiResult<ActionItemsResponse> result;

  @override
  Future<ApiResult<ActionItemsResponse>> list({
    int limit = 50,
    int offset = 0,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
  }) async =>
      result;
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
    await SiriIntegration.current.drainIndexForTest();
    return (provider, host);
  }

  test('confirmed create immediately indexes the server ID', () async {
    final (provider, host) = await makeProvider();
    expect(await provider.createActionItem(description: 'Created task'), isNotNull);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.indexed['created']?.title, 'Created task');
  });

  test('confirmed completion, title and due date refresh the indexed projection', () async {
    final original = _item('task');
    final (provider, host) = await makeProvider(rows: [original]);
    expect(await provider.updateActionItemState(original, true), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.indexed['task']?.completed, isTrue);
    expect(await provider.updateActionItemDescription(original, 'Renamed'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.indexed['task']?.title, 'Renamed');
    final dueAt = DateTime.utc(2026, 10, 1);
    expect(await provider.updateActionItemDueDate(original, dueAt), isTrue);
    await SiriIntegration.current.drainIndexForTest();
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
    await SiriIntegration.current.drainIndexForTest();
    expect(confirmedHost.deleted, ['task']);
  });

  test('confirmed bulk delete removes every returned task ID from the index', () async {
    final (provider, host) = await makeProvider(rows: [_item('a'), _item('b')]);
    provider.startSelectionWithItem('a');
    provider.selectItem('b');
    expect(await provider.deleteSelectedItems(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.deleted.toSet(), {'a', 'b'});
  });

  test('a staged task remains indexed across a complete refresh and Undo restores it', () async {
    final item = _item('staged');
    final (provider, host) = await makeProvider(rows: [item]);
    expect(host.indexed.keys, contains('staged'));
    provider.stageDeleteActionItem(item);
    await provider.fetchActionItems();
    await SiriIntegration.current.drainIndexForTest();
    expect(host.indexed.keys, contains('staged'));
    expect(await provider.undoStagedDelete('staged'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.indexed.keys, contains('staged'));
  });

  test('partial bulk failure preserves an unrelated pending delete tombstone', () async {
    final rows = [_item('unrelated'), _item('bulk-a'), _item('bulk-b')];
    final (provider, _) = await makeProvider(rows: rows, bulkDeleted: ['bulk-a']);
    provider.stageDeleteActionItem(rows.first);
    provider.startSelectionWithItem('bulk-a');
    provider.selectItem('bulk-b');
    expect(await provider.deleteSelectedItems(), isFalse);
    await SiriIntegration.current.drainIndexForTest();
    await provider.fetchActionItems();
    expect(provider.actionItems.map((item) => item.id), isNot(contains('unrelated')));
  });

  test('a typed page with rejected rows cannot prune an unseen valid task', () async {
    final host = _SiriTaskHost();
    host.indexed['unseen'] = SiriTask(
        id: 'unseen', title: 'Still valid', completed: false, createdAtMs: DateTime.now().millisecondsSinceEpoch);
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final typed = _TypedTaskApi(ApiSuccess(ActionItemsResponse(actionItems: [_item('visible')]), rejectedRows: 1));
    final provider = ActionItemsProvider(actionItemsApi: typed);
    addTearDown(provider.dispose);
    expect(await provider.fetchActionItems(), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.indexed.keys, contains('unseen'));
    expect(host.indexed.keys, contains('visible'));
  });

  test('a rejected staged row keeps its tombstone until a complete server page', () async {
    final staged = _item('staged');
    final visible = _item('visible');
    final host = _SiriTaskHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final typed = _TypedTaskApi(ApiSuccess(ActionItemsResponse(actionItems: [staged, visible])));
    final provider = ActionItemsProvider(actionItemsApi: typed);
    addTearDown(provider.dispose);
    await provider.fetchActionItems();
    provider.stageDeleteActionItem(staged);
    typed.result = ApiSuccess(ActionItemsResponse(actionItems: [visible]), rejectedRows: 1);
    await provider.fetchActionItems();
    typed.result = ApiSuccess(ActionItemsResponse(actionItems: [staged, visible]));
    await provider.fetchActionItems();
    expect(provider.actionItems.map((row) => row.id), isNot(contains('staged')));
    expect(host.indexed.keys, contains('staged'));
  });

  test('a later clean page cannot make an earlier rejected page authoritative', () async {
    final host = _SiriTaskHost();
    host.indexed['rejected'] = SiriTask(
        id: 'rejected', title: 'Still valid', completed: false, createdAtMs: DateTime.now().millisecondsSinceEpoch);
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final typed =
        _TypedTaskApi(ApiSuccess(ActionItemsResponse(actionItems: [_item('first')], hasMore: true), rejectedRows: 1));
    final provider = ActionItemsProvider(actionItemsApi: typed);
    addTearDown(provider.dispose);
    await provider.fetchActionItems();
    typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_item('last')], hasMore: false));
    await provider.loadMoreActionItems();
    expect(host.indexed.keys, contains('rejected'));
  });

  test('a staged task stays masked until Undo or commit even if a refresh omits it', () async {
    final staged = _item('staged');
    final host = _SiriTaskHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final typed = _TypedTaskApi(ApiSuccess(ActionItemsResponse(actionItems: [staged])));
    final provider = ActionItemsProvider(actionItemsApi: typed);
    addTearDown(provider.dispose);
    await provider.fetchActionItems();
    provider.stageDeleteActionItem(staged);
    typed.result = const ApiSuccess(ActionItemsResponse(actionItems: []));
    await provider.fetchActionItems();
    typed.result = ApiSuccess(ActionItemsResponse(actionItems: [staged]));
    await provider.fetchActionItems();
    expect(provider.actionItems.map((row) => row.id), isNot(contains('staged')));
  });

  test('a task mutation finishing after account clear cannot index into the next owner', () async {
    final host = _SiriTaskHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final created = Completer<ActionItemWithMetadata?>();
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
          const ActionItemsResponse(actionItems: []),
      createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) => created.future,
    );
    addTearDown(provider.dispose);
    await provider.fetchActionItems();
    final pending = provider.createActionItem(description: 'Old account task');
    provider.clearUserData();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-b');
    created.complete(_item('old-account-created'));
    await pending;
    await Future<void>.delayed(Duration.zero);
    expect(host.indexed, isEmpty);
  });
}
