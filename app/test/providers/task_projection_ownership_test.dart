import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../integration_test/support/task_delivery_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  final fixture = TaskDeliveryFixture();
  Map<String, Object> row(String id) => {'id': id, 'description': id, 'completed': false};
  http.Response page(List<String> ids, {bool more = false}) =>
      fixture.response({'action_items': ids.map(row).toList(), 'has_more': more});
  ActionItemsProvider provider(ApiSend send) {
    final state = ActionItemsProvider(actionItemsApi: ActionItemsApi(baseUrl: 'http://fixture.invalid/', send: send));
    addTearDown(state.dispose);
    return state;
  }

  for (final oldStatus in [200, 403]) {
    test('a late $oldStatus full read cannot hide a newer remote task', () async {
      final old = Completer<http.Response>();
      var calls = 0;
      final state = provider((_) async {
        calls++;
        if (calls == 1) return page([]);
        if (calls == 2) return old.future;
        return page(['new-phone-task']);
      });
      await state.ensureLoaded();
      final first = state.fetchActionItems();
      await state.fetchActionItems();
      old.complete(oldStatus == 200 ? page([]) : fixture.response({}, oldStatus));
      await first;
      expect(state.actionItems.single.id, 'new-phone-task');
      expect(state.apiViewState.phase, ApiViewPhase.data);
      expect(state.isFetching, isFalse);
    });
  }

  test('a saved receipt during preload retries the initial snapshot and retains existing tasks', () async {
    final old = Completer<http.Response>();
    var lists = 0;
    final state = provider((request) async {
      if (Uri.parse(request.url).path == '/v1/action-items/saved') return fixture.response(row('saved'));
      lists++;
      if (lists == 1) return old.future;
      return page(['saved', 'existing-phone-task']);
    });
    final preload = state.ensureLoaded();
    expect(await state.receiveSavedTask('saved'), isTrue);
    old.complete(page(['existing-phone-task']));
    await preload;
    expect(lists, 2);
    expect(state.actionItems.map((item) => item.id), ['saved', 'existing-phone-task']);
    expect(state.hasLoaded, isTrue);
    expect(state.isLoading, isFalse);
  });

  test('a page from before refresh cannot restore a task removed on another client', () async {
    final oldPage = Completer<http.Response>();
    var calls = 0;
    final state = provider((_) async {
      calls++;
      if (calls == 1) return page(['before-refresh'], more: true);
      if (calls == 2) return oldPage.future;
      return page(['current']);
    });
    await state.ensureLoaded();
    final pagination = state.loadMoreActionItems();
    await state.fetchActionItems();
    oldPage.complete(page(['removed-on-desktop']));
    await pagination;
    expect(state.actionItems.map((item) => item.id), ['current']);
    expect(state.hasMore, isFalse);
  });

  test('an old account load cannot clear the next account loader or coalescing future', () async {
    final old = Completer<http.Response>();
    final current = Completer<http.Response>();
    var calls = 0;
    final state = provider((_) {
      calls++;
      return calls == 1 ? old.future : current.future;
    });
    final oldLoad = state.ensureLoaded();
    state.clearUserData();
    final currentLoad = state.ensureLoaded(showShimmer: true);
    old.complete(page(['old-account-private-task']));
    await oldLoad;
    expect(state.isLoading, isTrue);
    expect(identical(state.ensureLoaded(), currentLoad), isTrue);
    expect(calls, 2);
    current.complete(page(['current-account-task']));
    await currentLoad;
    expect(state.actionItems.single.id, 'current-account-task');
    expect(state.hasLoaded, isTrue);
    expect(state.isLoading, isFalse);
  });

  test('an empty old account does not prevent the next account initial read', () async {
    var calls = 0;
    final state = provider((request) async {
      calls++;
      if (calls <= 2) return page([]);
      expect(Uri.parse(request.url).queryParameters.containsKey('start_date'), isFalse);
      return page(['new-account-task']);
    });
    await state.ensureLoaded();
    state.setDateRangeFilter(DateTime.utc(2026, 1, 1), null);
    await Future<void>.delayed(Duration.zero);
    state.setSearchQuery('Previous account query');
    state.startSelection();
    state.toggleShowCompletedView();
    expect(state.apiViewState.phase, ApiViewPhase.empty);
    state.clearUserData();
    expect(state.apiViewState.phase, ApiViewPhase.data);
    expect(state.hasLoaded, isFalse);
    expect(state.isSearching, isFalse);
    expect(state.isSelectionMode, isFalse);
    expect(state.showCompletedView, isFalse);
    await state.ensureLoaded();
    expect(calls, 3);
    expect(state.actionItems.single.id, 'new-account-task');
  });

  test('a receipt during a date-query change cannot advance past the new query first page', () async {
    final filteredRead = Completer<http.Response>();
    final offsets = <String>[];
    var lists = 0;
    final state = provider((request) async {
      final uri = Uri.parse(request.url);
      if (uri.path == '/v1/action-items/just-saved') return fixture.response(row('just-saved'));
      lists++;
      if (lists == 1) return page(['old-scope-a', 'old-scope-b'], more: true);
      if (lists == 2) return filteredRead.future;
      offsets.add(uri.queryParameters['offset']!);
      expect(uri.queryParameters.containsKey('start_date'), isTrue);
      return page(['filtered-first-row']);
    });
    await state.ensureLoaded();
    state.setDateRangeFilter(DateTime.utc(2026, 10, 20), null);
    expect(await state.receiveSavedTask('just-saved'), isTrue);
    filteredRead.complete(page(['older-snapshot']));
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await state.loadMoreActionItems();
    expect(offsets, ['0']);
    expect(state.actionItems.map((item) => item.id), ['just-saved', 'filtered-first-row']);
  });
}
