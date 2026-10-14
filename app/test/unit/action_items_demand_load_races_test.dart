import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Typed-API fake whose list responses wait for an explicit [resolve], so
/// tests can interleave creates with an in-flight first load exactly like the
/// cold-start Add Task quick action does.
class _HeldListApi extends api.ActionItemsApi {
  _HeldListApi() : super(baseUrl: 'http://localhost/');
  ApiResult<ActionItemsResponse> result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
  final List<Completer<ApiResult<ActionItemsResponse>>> _pending = [];
  final List<int> requestedOffsets = [];

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
  }) {
    requestedOffsets.add(offset);
    final completer = Completer<ApiResult<ActionItemsResponse>>();
    _pending.add(completer);
    return completer.future;
  }

  /// Fulfills every held request with [result].
  void resolve() {
    final pending = List.of(_pending);
    _pending.clear();
    for (final completer in pending) {
      completer.complete(result);
    }
  }

  /// Fulfills only the [index]-th still-pending request with [result].
  void completeAt(int index, ApiResult<ActionItemsResponse> result) {
    final completer = _pending.removeAt(index);
    completer.complete(result);
  }
}

ActionItemWithMetadata _row(String id) => ActionItemWithMetadata(
      id: id,
      description: 'task $id',
      completed: false,
    );

/// Server-shaped row with distinct created/updated timestamps, so it can be
/// distinguished from optimistic rows in pagination assertions.
const _serverRowDecription = 'server task';

ActionItemWithMetadata _serverRow(String id) => ActionItemWithMetadata(
      id: id,
      description: _serverRowDecription,
      completed: false,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('stale loads across sign-out', () {
    test('a fetch started before clearUserData cannot project error or loading state', () async {
      final typed = _HeldListApi();
      typed.result = const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 500));
      final provider = ActionItemsProvider(actionItemsApi: typed);

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      expect(provider.isLoading, isTrue, reason: 'successor shimmer flag sanity');

      provider.clearUserData();

      typed.resolve();
      await load;

      expect(provider.actionItems, isEmpty);
      // The stale server error must not replace the next account's screen.
      expect(provider.apiViewState.phase, ApiViewPhase.data);
      expect(provider.isLoading, isFalse, reason: 'the signed-out fetch must not clear successor shimmer state');
      provider.dispose();
    });
  });

  group('optimistic creates overlapping the demand load', () {
    test('create settles first: the stale list cannot drop the confirmed row', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
            _row('server-1'),
      );

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      // Add Task quick action: the create completes while the first list
      // fetch is still in flight.
      final created = provider.createActionItem(description: 'from quick action');
      await Future<void>.delayed(Duration.zero);
      await created;

      // The list response predates the create and does not contain it.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      typed.resolve();
      await load;

      expect(provider.actionItems.map((item) => item.id), contains('server-1'));
      provider.dispose();
    });

    test('create settles last: the temp row survives the wholesale list replacement', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-2');
        },
      );

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final created = provider.createActionItem(description: 'slow create');
      await Future<void>.delayed(Duration.zero);
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      typed.resolve();
      await load;

      createResolved = true;
      final item = await created;

      expect(provider.actionItems.map((row) => row.id), contains('server-2'),
          reason: 'the create must never disappear from the UI until another refresh');
      expect(item?.id, 'server-2');
      provider.dispose();
    });

    test('the confirmed row replaces both the temp row and any fetched copy: no duplicates', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-4');
        },
      );

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final created = provider.createActionItem(description: 'dup guard');
      await Future<void>.delayed(Duration.zero);

      // The concurrent list fetch already observed the committed server row
      // (server-side write visible before the create response settles here).
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [_serverRow('server-4')], hasMore: false),
      );
      typed.resolve();
      await load;

      createResolved = true;
      await created;

      final ids = provider.actionItems.map((item) => item.id).toList();
      expect(ids.where((id) => id == 'server-4').length, 1,
          reason: 'temp-row replacement must not leave a duplicate of the committed row');
      provider.dispose();
    });

    test('loadMore offsets by server-backed rows only, never preserved creates', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-5');
        },
      );

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final created = provider.createActionItem(description: 'offset guard');
      await Future<void>.delayed(Duration.zero);

      // Full first page of 100 server rows + the preserved create.
      typed.result = ApiSuccess(
        ActionItemsResponse(
          actionItems: [for (var i = 0; i < 100; i++) _serverRow('srv-$i')],
          hasMore: true,
        ),
      );
      typed.resolve();
      await load;
      createResolved = true;
      await created;
      expect(provider.actionItems.length, 101, reason: 'sanity: 100 server rows plus the preserved create');

      // Second page: offset must be 100 (server-backed rows), not 101.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await more;

      expect(typed.requestedOffsets.last, 100, reason: 'preserved creates must not shift the server pagination offset');
      provider.dispose();
    });

    test('a refresh observing the confirmed create retires it from the offset exclusion', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
            _row('server-9'),
      );

      // The common path: the create settles with no fetch in flight, so only
      // _preservedCreateIds tracks it.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;
      final created = provider.createActionItem(description: 'retire guard');
      await created;
      expect(provider.actionItems.map((item) => item.id), contains('server-9'));

      // A later refresh that contains the confirmed row must mark it
      // server-backed, even though there is nothing to preserve.
      typed.result = ApiSuccess(
        ActionItemsResponse(
          actionItems: [_serverRow('server-9'), for (var i = 0; i < 100; i++) _serverRow('srv-$i')],
          hasMore: true,
        ),
      );
      final refresh = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await refresh;
      expect(provider.actionItems.length, 101, reason: 'sanity: the observed create must not duplicate');

      // With the confirmed row retired, the next page offset counts all 101
      // server-backed rows instead of skipping one forever.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await more;

      expect(typed.requestedOffsets.last, 101,
          reason: 'a server-observed preserved create must rejoin the pagination offset');
      provider.dispose();
    });

    test('a load-more page observing the confirmed create retires it too', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
            _row('server-11'),
      );

      // First page: empty but hasMore so loadMore is allowed.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: true));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;
      final created = provider.createActionItem(description: 'load-more retire guard');
      await created;
      expect(provider.actionItems.map((item) => item.id), contains('server-11'));

      // Server now has 101 rows: the created task (server-11, newest) + 100
      // older ones. The initial page was fetched before the create existed, so
      // the next loadMore page (offset 0 after 0 server-backed rows) observes
      // the confirmed create and must retire it from the offset exclusion.
      typed.result = ApiSuccess(
        ActionItemsResponse(
          actionItems: [_serverRow('server-11'), for (var i = 0; i < 49; i++) _serverRow('old-$i')],
          hasMore: true,
        ),
      );
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await more;
      // sanity: rows landed
      expect(provider.actionItems.any((row) => row.id == 'server-11'), isTrue);

      // The next page's offset must now count the observed create as
      // server-backed (50 rows: server-11 + 49 old), not 49.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final more2 = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await more2;

      expect(typed.requestedOffsets.last, 50,
          reason: 'a preserved create observed by a load-more page must rejoin the pagination offset');
      provider.dispose();
    });

    test('a create that settles after its row was already fetched counts as server-backed immediately', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-15');
        },
      );

      // First page: full page of 100 + hasMore.
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [for (var i = 0; i < 100; i++) _serverRow('srv-$i')], hasMore: true),
      );
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final created = provider.createActionItem(description: 'observed before settle');
      await Future<void>.delayed(Duration.zero);

      // The list fetch already observed the committed server row (server-side
      // write visible before the create response settles).
      typed.result = ApiSuccess(
        ActionItemsResponse(
          actionItems: [_serverRow('server-15'), for (var i = 0; i < 99; i++) _serverRow('srv-$i')],
          hasMore: true,
        ),
      );
      typed.resolve();
      await load;
      createResolved = true;
      await created;
      expect(provider.actionItems.length, 100, reason: 'sanity: the confirmed row replaced the temp row, no duplicate');

      // The settled create was already inside an applied server response: it
      // must not be excluded from the pagination offset until a later page
      // observes it again.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await more;

      expect(typed.requestedOffsets.last, 100,
          reason: 'an already-observed create must count as server-backed at settle time');
      provider.dispose();
    });

    test('a stale load-more completion cannot clear the successor account fetch state', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(actionItemsApi: typed);

      // First page with hasMore so a load-more is possible.
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [for (var i = 0; i < 100; i++) _serverRow('srv-$i')], hasMore: true),
      );
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // A load-more starts, then the user signs out before it resolves.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      provider.clearUserData();
      expect(provider.isFetching, isFalse, reason: 'clearUserData resets fetch state for the successor account');

      // The successor account starts its own fetch and is mid-flight when the
      // stale load-more resolves.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final successorLoad = provider.fetchActionItems(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      expect(provider.isLoading, isTrue, reason: 'successor shimmer flag sanity');
      expect(provider.isFetching, isFalse, reason: 'successor has no load-more in flight');

      typed.resolve();
      await more;
      await successorLoad;

      // The stale load-more's finally must not have cleared the successor's
      // loading state early.
      expect(provider.isLoading, isFalse, reason: 'the successor load owns its own loading flag lifecycle');
      provider.dispose();
    });

    test('a Home preview that loses the navigation race still releases its shadow threat', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-12');
        },
      );

      // Home preview fetch starts and stays pending.
      final preview = provider.ensureHomeWidgetPreviewLoaded();
      await Future<void>.delayed(Duration.zero);

      // Quick-action create settles while the preview is in flight; the temp
      // row is visible, so the settle registers a shadow for the preview's
      // fetch ordinal.
      final created = provider.createActionItem(description: 'preview abort shadow');
      await Future<void>.delayed(Duration.zero);

      // Tasks is visited before the preview resolves: the authoritative
      // ensureLoaded starts (second held request) and its full first page —
      // which already contains the committed server row — replaces the list.
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [_serverRow('server-12')], hasMore: false),
      );
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      // Fulfill ensureLoaded's request (index 1); the preview (index 0) stays
      // pending and will abort on the navigation guard.
      typed.completeAt(1, typed.result);
      await load;
      createResolved = true;
      await created;

      // Now resolve the stale preview; it aborts (Tasks already loaded).
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      typed.completeAt(0, typed.result);
      await preview;

      // The aborted preview's ordinal must have been pruned from the shadow:
      // server-12 counts as server-backed now, so a later loadMore offsets by
      // every visible row instead of skipping one forever.
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [for (var i = 0; i < 50; i++) _serverRow('old-$i')], hasMore: true),
      );
      final refresh = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await refresh;
      // (fetchActionItems replaces the list with old-* rows; server-12 is gone
      // from the list but its shadow/pruning bookkeeping is what matters next.)

      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await more;

      expect(typed.requestedOffsets.last, 50,
          reason: 'the aborted preview must not keep a server-confirmed row out of the offset');
      provider.dispose();
    });

    test('a staged delete of a temp row transfers to the confirmed server row, never resurrects it', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-13');
        },
        deleteActionItemRequest: (String id) async => true,
      );

      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // Create starts; the temp row appears.
      final created = provider.createActionItem(description: 'delete race');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.first.id;
      expect(tempId.startsWith('temp_'), isTrue);

      // The user stages a delete of the temp row (D5 undo toast) while the
      // create request is still in flight.
      provider.stageDeleteActionItem(provider.actionItems.first);
      expect(provider.actionItems, isEmpty);

      // The create settles with the confirmed server row.
      createResolved = true;
      final item = await created;
      expect(item?.id, 'server-13');
      // The confirmed row must NOT be resurrected by the settle.
      expect(provider.actionItems, isEmpty, reason: 'a staged delete must not be resurrected by the create settle');
      expect(provider.isDeleteStaged('server-13'), isTrue, reason: 'the staged delete transfers to the server id');

      // Undo, addressed through the temp id the toast captured, restores the
      // confirmed row exactly once.
      expect(await provider.undoStagedDelete(tempId), isTrue);
      expect(provider.actionItems.map((row) => row.id), ['server-13']);

      // A late second resolution (commit via the same temp id) must be a no-op.
      expect(await provider.commitStagedDelete(tempId), isFalse);
      expect(provider.actionItems.map((row) => row.id), ['server-13']);
      provider.dispose();
    });

    test('commit after the transfer deletes the confirmed server row', () async {
      final typed = _HeldListApi();
      final deletedIds = <String>[];
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-14');
        },
        deleteActionItemRequest: (String id) async {
          deletedIds.add(id);
          return true;
        },
      );

      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      final created = provider.createActionItem(description: 'commit race');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.first.id;
      provider.stageDeleteActionItem(provider.actionItems.first);

      createResolved = true;
      await created;
      expect(provider.actionItems, isEmpty);

      // Commit addressed through the temp id must delete the confirmed id.
      expect(await provider.commitStagedDelete(tempId), isTrue);
      expect(deletedIds, ['server-14'], reason: 'the transferred staged delete must commit against the server id');
      expect(provider.actionItems, isEmpty);
      provider.dispose();
    });

    test('an aborted full refresh still releases its shadow threat from the pagination offset', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
            _row('server-16'),
      );

      // First page: three server rows, more available.
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [for (var i = 0; i < 3; i++) _serverRow('old-$i')], hasMore: true),
      );
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // A full refresh starts and stays pending; the create settles mid-flight.
      final refresh = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      final created = provider.createActionItem(description: 'abort race');
      await Future<void>.delayed(Duration.zero);
      await created;
      expect(provider.actionItems.first.id, 'server-16');

      // The refresh fails (typed outage): it aborts without replacing the list.
      typed.completeAt(0, const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 500)));
      await refresh;

      // First load-more observes the confirmed row server-side and retires the
      // preserved-create exclusion (offset excludes it until then — sanity).
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [_serverRow('server-16'), _serverRow('a-0')], hasMore: true),
      );
      var more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(0, typed.result);
      await more;
      expect(typed.requestedOffsets.last, 3, reason: 'the not-yet-observed create stays out of the offset');

      // The aborted refresh must have released its shadow threat: the
      // confirmed row now counts as server-backed, so the next page starts
      // after every visible row instead of re-requesting an overlapping
      // window on every load-more.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(0, typed.result);
      await more;

      expect(typed.requestedOffsets.last, 5,
          reason: 'an aborted full refresh must not keep a server-confirmed row out of the pagination offset');
      provider.dispose();
    });

    test('Undo before the overlapping fetch returns keeps the confirmed row in the replaced list', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-17');
        },
      );

      // The wholesale fetch starts first and stays pending.
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      // The create's temp row appears, then the user stages its delete (D5).
      final created = provider.createActionItem(description: 'undo race');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.first.id;
      provider.stageDeleteActionItem(provider.actionItems.first);
      expect(provider.actionItems, isEmpty);

      // The create settles while its row is hidden: the staged delete
      // transfers to the confirmed server id.
      createResolved = true;
      final item = await created;
      expect(item?.id, 'server-17');
      expect(provider.actionItems, isEmpty);

      // Undo — addressed through the temp id the toast captured — restores
      // the confirmed row while the older fetch is still pending.
      expect(await provider.undoStagedDelete(tempId), isTrue);
      expect(provider.actionItems.map((row) => row.id), ['server-17']);

      // The stale response predates the create and does not contain it.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      typed.completeAt(0, typed.result);
      await load;

      expect(provider.actionItems.map((row) => row.id), ['server-17'],
          reason: 'Undo must re-arm preservation so the wholesale replacement cannot drop the confirmed row');
      provider.dispose();
    });

    test('a committed staged delete is not resurrected by the overlapping fetch replacement', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-18');
        },
        deleteActionItemRequest: (String id) async => true,
      );

      // The wholesale fetch starts first and stays pending.
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final created = provider.createActionItem(description: 'commit race');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.first.id;
      provider.stageDeleteActionItem(provider.actionItems.first);

      createResolved = true;
      await created;
      expect(await provider.commitStagedDelete(tempId), isTrue);
      expect(provider.actionItems, isEmpty);

      // The stale response predates everything; it must not resurrect the
      // committed delete even though its shadow threats were registered.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_serverRow('old-0')], hasMore: false));
      typed.completeAt(0, typed.result);
      await load;

      expect(provider.actionItems.map((row) => row.id), ['old-0'],
          reason: 'a committed delete must stay deleted across the wholesale replacement');
      provider.dispose();
    });

    test('clearUserData releases wholesale fetches still in flight for the signed-out account', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
            _row('server-19'),
      );

      // The signed-out account's fetch starts and stays pending forever.
      // (Never awaited or resolved: the point is a stuck old-account fetch.)
      unawaited(provider.ensureLoaded(showShimmer: true));
      await Future<void>.delayed(Duration.zero);

      // Sign-out mid-flight, then the successor account creates a task.
      provider.clearUserData();
      final created = provider.createActionItem(description: 'successor account');
      await Future<void>.delayed(Duration.zero);
      await created;

      // The successor's confirmed row must count as server-backed immediately
      // (no page has observed it, so it stays out of the offset until one
      // does) — but the stuck old-account fetch must not be recorded as a
      // threat. A refresh that observes the row retires the exclusion; the
      // loadMore offset must then cover every visible row.
      typed.result = ApiSuccess(
        ActionItemsResponse(
          actionItems: [_serverRow('server-19')],
          // hasMore so the follow-up loadMore actually issues its request.
          hasMore: true,
        ),
      );
      final refresh = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(1, typed.result);
      await refresh;

      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [for (var i = 0; i < 50; i++) _serverRow('old-$i')], hasMore: true),
      );
      final more = provider.loadMoreActionItems();
      await Future<void>.delayed(Duration.zero);
      // Index 0 is the stuck signed-out fetch (never resolved); this
      // loadMore is the only other pending request.
      typed.completeAt(1, typed.result);
      await more;

      expect(
        typed.requestedOffsets.last,
        1,
        reason: 'a stuck signed-out fetch must not keep the successor row out of the pagination offset',
      );
      provider.dispose();
    });

    test('a fetch observing the confirmed row mid-toast does not outlive the transferred staged delete', () async {
      final typed = _HeldListApi();
      var createResolved = false;
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          while (!createResolved) {
            await Future<void>.delayed(const Duration(milliseconds: 1));
          }
          return _row('server-20');
        },
        deleteActionItemRequest: (String id) async => true,
      );

      // First load completes so later fetches replace the list.
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // The create starts and its temp row is staged for deletion (D5 toast).
      final created = provider.createActionItem(description: 'observed transfer');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.first.id;
      provider.stageDeleteActionItem(provider.actionItems.first);
      expect(provider.actionItems, isEmpty);

      // A wholesale refresh observes the committed server row while the
      // create future is still pending: the tombstone holds only the temp id,
      // so the confirmed row is admitted into the visible list.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_serverRow('server-20')], hasMore: false));
      final refresh = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(0, typed.result);
      await refresh;
      expect(
        provider.actionItems.map((row) => row.id),
        ['server-20'],
        reason: 'sanity: the concurrent fetch observed the confirmed row',
      );

      // The create settles: the staged delete transfers to the confirmed id
      // and must hide the observed row for the rest of the Undo window.
      createResolved = true;
      final item = await created;
      expect(item?.id, 'server-20');
      expect(
        provider.actionItems,
        isEmpty,
        reason: 'the transferred staged delete must hide the observed row',
      );

      // Commit (toast closes) deletes the confirmed row server-side; nothing
      // may reappear.
      expect(await provider.commitStagedDelete(tempId), isTrue);
      expect(provider.actionItems, isEmpty);
      provider.dispose();
    });
  });

  group('settled edits overlapping the demand load', () {
    test('a completed preview row is not resurrected incomplete by the stale demand load', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        updateActionItemRequest: (id, {description, completed, dueAt}) async =>
            _row(id).copyWith(completed: completed ?? false, description: 'edited $id'),
      );

      // Home's bounded preview populated the visible rows first.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      final preview = provider.ensureHomeWidgetPreviewLoaded();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await preview;

      // First Tasks visit: the authoritative wholesale fetch is held in flight
      // while the user completes a preview row and the mutation settles.
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final row = provider.actionItems.firstWhere((item) => item.id == 'a');
      await provider.updateActionItemState(row, true);

      // The demand-load response predates the completion.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      typed.resolve();
      await load;
      await Future<void>.delayed(Duration.zero);

      final completed = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(completed.completed, isTrue, reason: 'the settled edit must survive the stale wholesale replacement');
      expect(completed.description, 'edited a', reason: 'the substituted row is the server-confirmed edited row');
      provider.dispose();
    });

    test('the edit shadow retires once a fetch that started after the settle applies', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        updateActionItemRequest: (id, {description, completed, dueAt}) async =>
            _row(id).copyWith(completed: completed ?? false, description: 'edited $id'),
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      final preview = provider.ensureHomeWidgetPreviewLoaded();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await preview;

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      final row = provider.actionItems.firstWhere((item) => item.id == 'a');
      await provider.updateActionItemState(row, true);

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      typed.resolve();
      await load;
      await Future<void>.delayed(Duration.zero);

      // A fetch that started after the mutation settled sees the edit
      // server-side: its response is authoritative and must replace the
      // shadow copy, proving the shadow does not stick forever.
      typed.result = ApiSuccess(ActionItemsResponse(
        actionItems: [_row('a').copyWith(completed: true, description: 'authoritative'), _row('b')],
        hasMore: false,
      ));
      final refreshed = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(0, typed.result);
      await refreshed;

      final after = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(after.completed, isTrue);
      expect(after.description, 'authoritative',
          reason: 'a post-settle fetch response must not be overridden by the retired shadow');
      provider.dispose();
    });
  });

  group('round 4 review races', () {
    test('a completion that settles after an intervening list response still lands', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        updateActionItemRequest: (id, {description, completed, dueAt}) async {
          // The mutation response is slow: the wholesale fetch settles first.
          await Future<void>.delayed(const Duration(milliseconds: 5));
          return _row(id).copyWith(completed: completed ?? false, description: 'settled $id');
        },
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      final preview = provider.ensureHomeWidgetPreviewLoaded();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await preview;

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      // The user completes a preview row; the mutation is still awaiting its
      // response while the demand load completes and replaces the list.
      final mutation = provider.updateActionItemState(provider.actionItems.firstWhere((i) => i.id == 'a'), true);
      await Future<void>.delayed(Duration.zero);
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      typed.resolve();
      await load;
      await mutation;
      await Future<void>.delayed(Duration.zero);

      final completed = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(completed.completed, isTrue,
          reason: 'the settled completion must replace the pre-mutation row the intervening fetch restored');
      expect(completed.description, 'settled a',
          reason: 'the visible row is the server-confirmed settled row, not the stale list copy');
      provider.dispose();
    });

    test('pending reorder survives the wholesale list replacement', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        batchUpdateActionItemsRequest: (items) async => true,
      );

      typed.result = ApiSuccess(
        ActionItemsResponse(
          actionItems: [
            _row('a').copyWith(sortOrder: 1),
            _row('b').copyWith(sortOrder: 2),
          ],
          hasMore: false,
        ),
      );
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      // The user drags a/b; the debounced batch write has not fired yet.
      provider.batchUpdateSortOrders({'a': 2, 'b': 1});
      await Future<void>.delayed(Duration.zero);

      typed.resolve();
      await load;
      await Future<void>.delayed(Duration.zero);

      final a = provider.actionItems.firstWhere((item) => item.id == 'a');
      final b = provider.actionItems.firstWhere((item) => item.id == 'b');
      expect(a.sortOrder, 2, reason: 'the pending reorder must survive the replacement that predates its write');
      expect(b.sortOrder, 1);
      provider.dispose();
    });

    test('pending indent survives the wholesale list replacement', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        batchUpdateActionItemsRequest: (items) async => true,
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a')], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      provider.updateItemIndentLevel('a', 2);
      await Future<void>.delayed(Duration.zero);

      typed.resolve();
      await load;
      await Future<void>.delayed(Duration.zero);

      final a = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(a.indentLevel, 2, reason: 'the pending indent must survive the replacement that predates its write');
      provider.dispose();
    });

    test('a settled layout write stops shadowing later fetches', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        batchUpdateActionItemsRequest: (items) async => true,
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a').copyWith(sortOrder: 1)], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      provider.updateItemSortOrder('a', 5);
      await Future<void>.delayed(Duration.zero);

      typed.resolve();
      await load;
      await Future<void>.delayed(Duration.zero);

      // The debounce fires after the threat fetch applied: the write commits
      // with no fetches in flight, so the entry retires and a later fetch's
      // authoritative sortOrder wins.
      await Future<void>.delayed(const Duration(milliseconds: 600));
      typed.result = ApiSuccess(
        ActionItemsResponse(
            actionItems: [_row('a').copyWith(sortOrder: 9, description: 'authoritative')], hasMore: false),
      );
      final refreshed = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(0, typed.result);
      await refreshed;

      final a = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(a.sortOrder, 9, reason: 'a fetch that started after the layout write committed must be authoritative');
      provider.dispose();
    });

    test('bulk-deleting a slow optimistic create deletes the confirmed row, not the temp id', () async {
      final typed = _HeldListApi();
      final deletedIds = <String>[];
      final createReleased = Completer<void>();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          await createReleased.future;
          return _row('server-9');
        },
        deleteActionItemRequest: (id) async {
          deletedIds.add(id);
          return true;
        },
        bulkDeleteActionItemsRequest: (ids) async => ids.where((id) => !id.startsWith('temp_')).toList(),
      );

      // One real row loads so the screen is initialized.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('real-1')], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // A slow create lands in the list; the user selects it plus a real row
      // and bulk-deletes while the create request is still in flight.
      final created = provider.createActionItem(description: 'slow task');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.firstWhere((i) => i.id.startsWith('temp_')).id;
      provider.startSelectionWithItem(tempId);
      provider.selectItem('real-1');

      final bulk = provider.deleteSelectedItems();
      await Future<void>.delayed(Duration.zero);
      createReleased.complete();
      await created;
      final ok = await bulk;

      expect(ok, isTrue);
      expect(deletedIds, contains('server-9'),
          reason: 'the confirmed row must be deleted by a follow-up single delete of its server id');
      expect(provider.actionItems.any((i) => i.id == 'server-9'), isFalse,
          reason: 'the confirmed row must not be reinserted by the create settle');
      provider.dispose();
    });

    test('a failed bulk request restores real rows but not captured temp creates', () async {
      final typed = _HeldListApi();
      final createReleased = Completer<void>();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          await createReleased.future;
          return _row('server-7');
        },
        bulkDeleteActionItemsRequest: (ids) async => null,
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('real-1')], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      final created = provider.createActionItem(description: 'slow task');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.firstWhere((i) => i.id.startsWith('temp_')).id;
      provider.startSelectionWithItem(tempId);
      provider.selectItem('real-1');

      final bulk = provider.deleteSelectedItems();
      await Future<void>.delayed(Duration.zero);
      createReleased.complete();
      await created;
      final ok = await bulk;

      expect(ok, isFalse);
      expect(provider.actionItems.any((i) => i.id == 'real-1'), isTrue,
          reason: 'rollback re-inserts the real rows that were part of the failed request');
      expect(provider.actionItems.any((i) => i.id.startsWith('temp_')), isFalse,
          reason: 'rollback must not resurrect the captured temp row whose delete intent stands');
      provider.dispose();
    });

    test('home widget freshness refreshes after the Tasks screen has loaded', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(actionItemsApi: typed);

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a')], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;
      expect(provider.screenLoaded, isTrue);

      // Resume-time freshness: a changed server row must reach the visible
      // list even though the Tasks screen already initialized once.
      typed.result = ApiSuccess(
        ActionItemsResponse(actionItems: [_row('a').copyWith(description: 'refreshed elsewhere')], hasMore: false),
      );
      final refreshed = provider.ensureHomeWidgetPreviewLoaded();
      // refreshActionItems debounces 500 ms before its fetch is held in flight.
      await Future<void>.delayed(const Duration(milliseconds: 600));
      expect(typed.requestedOffsets.length, greaterThanOrEqualTo(2),
          reason: 'the freshness path must hit the server again after screen load');
      typed.completeAt(0, typed.result);
      await refreshed;
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);

      final a = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(a.description, 'refreshed elsewhere',
          reason: 'post-load widget freshness must flow through the authoritative refresh');
      provider.dispose();
    });
  });

  group('round 5 review races', () {
    test('a completion echo without layout fields keeps the visible indent and sort order', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        updateActionItemRequest: (id, {description, completed, dueAt}) async =>
            _row(id).copyWith(completed: completed ?? false),
      );

      typed.result = ApiSuccess(ActionItemsResponse(
        actionItems: [_row('a').copyWith(indentLevel: 2, sortOrder: 7)],
        hasMore: false,
      ));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      await provider.updateActionItemState(provider.actionItems.first, true);

      final row = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(row.completed, isTrue);
      expect(row.indentLevel, 2, reason: 'a completed-only echo must not flatten the visible hierarchy');
      expect(row.sortOrder, 7);
      provider.dispose();
    });

    test('an edit shadow reapplies the settled row with the visible layout', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        updateActionItemRequest: (id, {description, completed, dueAt}) async =>
            _row(id).copyWith(completed: completed ?? false, description: 'settled $id'),
      );

      typed.result = ApiSuccess(ActionItemsResponse(
        actionItems: [_row('a').copyWith(indentLevel: 1, sortOrder: 4), _row('b')],
        hasMore: false,
      ));
      final preview = provider.ensureHomeWidgetPreviewLoaded();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await preview;

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);

      await provider.updateActionItemState(provider.actionItems.firstWhere((i) => i.id == 'a'), true);

      typed.result = ApiSuccess(ActionItemsResponse(
        actionItems: [_row('a').copyWith(indentLevel: 1, sortOrder: 4), _row('b')],
        hasMore: false,
      ));
      typed.resolve();
      await load;
      await Future<void>.delayed(Duration.zero);

      final row = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(row.completed, isTrue);
      expect(row.description, 'settled a');
      expect(row.indentLevel, 1, reason: 'the shadow row must carry the visible layout, not the echo defaults');
      expect(row.sortOrder, 4);
      provider.dispose();
    });

    test('a partial bulk response rolls back only the real rows it failed to delete', () async {
      final typed = _HeldListApi();
      final createReleased = Completer<void>();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async {
          await createReleased.future;
          return _row('server-7');
        },
        deleteActionItemRequest: (id) async => true,
        bulkDeleteActionItemsRequest: (ids) async => ids.where((id) => id != 'real-2').toList(),
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('real-1'), _row('real-2')], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      final created = provider.createActionItem(description: 'slow task');
      await Future<void>.delayed(Duration.zero);
      final tempId = provider.actionItems.firstWhere((i) => i.id.startsWith('temp_')).id;
      provider.startSelectionWithItem(tempId);
      provider.selectItem('real-1');
      provider.selectItem('real-2');

      final bulk = provider.deleteSelectedItems();
      await Future<void>.delayed(Duration.zero);
      createReleased.complete();
      await created;
      final ok = await bulk;

      expect(ok, isFalse, reason: 'the bulk endpoint missed real-2');
      expect(provider.actionItems.any((i) => i.id == 'real-2'), isTrue,
          reason: 'the real row the server failed to delete is restored');
      expect(provider.actionItems.any((i) => i.id == 'real-1'), isFalse, reason: 'the deleted real row stays deleted');
      expect(provider.actionItems.any((i) => i.id.startsWith('temp_')), isFalse,
          reason: 'rollback must not resurrect the captured temp row');
      expect(provider.actionItems.any((i) => i.id == 'server-7'), isFalse,
          reason: 'the create settle must not reinsert the bulk-deleted confirmed row');
      provider.dispose();
    });

    test('an older batch response does not settle a newer staged layout edit', () async {
      final typed = _HeldListApi();
      final batches = <Completer<bool>>[];
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        batchUpdateActionItemsRequest: (items) {
          final c = Completer<bool>();
          batches.add(c);
          return c.future;
        },
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a').copyWith(sortOrder: 1)], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // First edit: the debounce fires batch 1, which is held in flight.
      provider.updateItemSortOrder('a', 5);
      await Future<void>.delayed(const Duration(milliseconds: 600));
      expect(batches, hasLength(1));

      // A newer edit lands while batch 1 awaits its response.
      provider.updateItemSortOrder('a', 9);
      await Future<void>.delayed(const Duration(milliseconds: 600));
      expect(batches, hasLength(2));

      // Batch 1 (sortOrder 5) commits successfully.
      batches[0].complete(true);
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);

      // A fetch predating the newer write returns the old sortOrder; the
      // newer staged edit must still protect the visible row.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a').copyWith(sortOrder: 1)], hasMore: false));
      final refreshed = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.completeAt(0, typed.result);
      await refreshed;
      await Future<void>.delayed(Duration.zero);

      final a = provider.actionItems.firstWhere((item) => item.id == 'a');
      expect(a.sortOrder, 9, reason: 'the older batch settle must not retire the newer staged edit');
      provider.dispose();
    });

    test('a drag changing order and indent commits one atomic batch', () async {
      final typed = _HeldListApi();
      final batches = <List<Map<String, dynamic>>>[];
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        batchUpdateActionItemsRequest: (items) {
          batches.add(List<Map<String, dynamic>>.from(items));
          return Future.value(true);
        },
      );

      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a').copyWith(sortOrder: 1)], hasMore: false));
      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await load;

      // One gesture moves the row across categories: new order and new indent
      // land together before the debounce fires.
      provider.updateItemSortOrder('a', 5);
      provider.updateItemIndentLevel('a', 2);
      await Future<void>.delayed(const Duration(milliseconds: 600));

      // A single batch request carries both fields for the row: whichever
      // single-field flush raced first under split debounces must not settle
      // the shared layout revision while the other field is still pending.
      expect(batches, hasLength(1));
      expect(batches.single, hasLength(1));
      expect(batches.single.single['id'], 'a');
      expect(batches.single.single['sort_order'], 5);
      expect(batches.single.single['indent_level'], 2);

      // Everything was submitted and settled; no second flush remains.
      await Future<void>.delayed(const Duration(milliseconds: 600));
      expect(batches, hasLength(1));
      provider.dispose();
    });
  });

  group('round 6 review races', () {
    test('a shimmer joined before sign-out cannot clear the successor account shimmer', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(actionItemsApi: typed);

      // A non-screen caller (Chat task card) starts the load without a shimmer.
      final load = provider.ensureLoaded();
      await Future<void>.delayed(Duration.zero);
      expect(provider.isLoading, isFalse, reason: 'the non-screen load does not shimmer');

      // The Tasks screen joins the in-flight load and upgrades to shimmer.
      final joined = provider.ensureLoaded(showShimmer: true);
      expect(provider.isLoading, isTrue, reason: 'the joined screen presentation shimmers');

      // Sign-out mid-flight; the successor account starts its own shimmer load.
      provider.clearUserData();
      final successorLoad = provider.fetchActionItems(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      expect(provider.isLoading, isTrue, reason: 'successor shimmer flag sanity');

      // The signed-out account's joined load resolves first, while the
      // successor's request is still held: its stale joined completion must
      // not clear the successor's shimmer (false empty state until the
      // successor request finishes).
      typed.completeAt(0, typed.result);
      await Future<void>.delayed(Duration.zero);
      expect(
        provider.isLoading,
        isTrue,
        reason: 'the stale joined completion must not clear the successor account shimmer',
      );

      typed.resolve();
      await load;
      await joined;
      await successorLoad;
      expect(provider.isLoading, isFalse);
      provider.dispose();
    });

    test('an out-of-order completion response cannot resurrect a superseded state', () async {
      final typed = _HeldListApi();
      final mutationResponses = <Completer<ActionItemWithMetadata>>[];
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        updateActionItemRequest: (id, {description, completed, dueAt}) {
          final responder = Completer<ActionItemWithMetadata>();
          mutationResponses.add(responder);
          return responder.future;
        },
      );

      // Populate the visible rows.
      typed.result = ApiSuccess(ActionItemsResponse(actionItems: [_row('a'), _row('b')], hasMore: false));
      final preview = provider.ensureHomeWidgetPreviewLoaded();
      await Future<void>.delayed(Duration.zero);
      typed.resolve();
      await preview;

      // First toggle (complete); its response is held.
      final first = provider.updateActionItemState(provider.actionItems.firstWhere((i) => i.id == 'a'), true);
      await Future<void>.delayed(Duration.zero);

      // The user toggles the same task again before the first response returns.
      final second = provider.updateActionItemState(provider.actionItems.firstWhere((i) => i.id == 'a'), false);
      await Future<void>.delayed(Duration.zero);

      // The newer response lands first: the server confirms not-completed.
      mutationResponses[1].complete(_row('a').copyWith(completed: false));
      await second;
      await Future<void>.delayed(Duration.zero);
      expect(provider.actionItems.firstWhere((i) => i.id == 'a').completed, isFalse);

      // The older response resolves last; it must not overwrite the row with
      // the superseded completed state.
      mutationResponses[0].complete(_row('a').copyWith(completed: true));
      await first;
      await Future<void>.delayed(Duration.zero);
      expect(
        provider.actionItems.firstWhere((item) => item.id == 'a').completed,
        isFalse,
        reason: 'a superseded completion response must not overwrite the newer confirmed state',
      );
      provider.dispose();
    });
  });
}
