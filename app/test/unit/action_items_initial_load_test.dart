import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('shares the Home preload with the Tasks page initial load', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    final firstResponse = Completer<ActionItemsResponse>();
    var requests = 0;
    final provider = ActionItemsProvider(
      getActionItems: (
          {limit = 50, offset = 0, completed, conversationId, startDate, endDate, dueStartDate, dueEndDate}) {
        requests++;
        return firstResponse.future;
      },
    );

    final tasksPageLoad = provider.ensureLoaded(showShimmer: true);

    expect(requests, 1);
    firstResponse.complete(const ActionItemsResponse(actionItems: [], hasMore: false));
    await tasksPageLoad;
    await provider.ensureLoaded(showShimmer: true);
    expect(requests, 1);

    provider.dispose();
  });

  test('retries the initial load after the preload fails', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    final firstResponse = Completer<ActionItemsResponse?>();
    var requests = 0;
    final provider = ActionItemsProvider(
      getActionItems: (
          {limit = 50, offset = 0, completed, conversationId, startDate, endDate, dueStartDate, dueEndDate}) {
        requests++;
        return requests == 1
            ? firstResponse.future
            : Future.value(const ActionItemsResponse(actionItems: [], hasMore: false));
      },
    );

    final initialLoad = provider.ensureLoaded(showShimmer: true);
    firstResponse.complete(null);
    await initialLoad;
    await provider.ensureLoaded(showShimmer: true);

    expect(requests, 2);
    provider.dispose();
  });

  test('a fetch from a cleared owner cannot repopulate tasks or Siri', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final response = Completer<ActionItemsResponse>();
    final provider = ActionItemsProvider(
      getActionItems: (
              {limit = 50, offset = 0, completed, conversationId, startDate, endDate, dueStartDate, dueEndDate}) =>
          response.future,
    );
    final pending = provider.ensureLoaded();
    provider.clearUserData();
    response.complete(const ActionItemsResponse(actionItems: [
      ActionItemWithMetadata(id: 'old-owner-task', description: 'Private', completed: false),
    ], hasMore: false));
    await pending;
    expect(provider.actionItems, isEmpty);
    provider.dispose();
  });
}
