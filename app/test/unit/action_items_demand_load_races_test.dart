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

    test('a fetch that starts after the create settles sees the row server-side', () async {
      final typed = _HeldListApi();
      final provider = ActionItemsProvider(
        actionItemsApi: typed,
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async =>
            _row('server-3'),
      );

      final load = provider.ensureLoaded(showShimmer: true);
      await Future<void>.delayed(Duration.zero);
      final created = provider.createActionItem(description: 'quick task');
      await Future<void>.delayed(Duration.zero);
      await created;

      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      typed.resolve();
      await load;

      // A refresh that starts now reflects the server list (still racing the
      // server-side write visibility), so preservation must not stick forever.
      final refresh = provider.fetchActionItems();
      await Future<void>.delayed(Duration.zero);
      typed.result = const ApiSuccess(ActionItemsResponse(actionItems: [], hasMore: false));
      typed.resolve();
      await refresh;

      expect(provider.actionItems, isEmpty,
          reason: 'later fetches are authoritative; preservation covers only fetches that predate the create');
      provider.dispose();
    });
  });
}
