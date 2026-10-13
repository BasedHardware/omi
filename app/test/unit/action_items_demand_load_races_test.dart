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
  });
}
