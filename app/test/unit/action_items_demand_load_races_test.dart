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
  });
}
