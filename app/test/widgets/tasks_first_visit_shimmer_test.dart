import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/pages/action_items/widgets/action_item_shimmer_widget.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';

import '../support/typed_action_items_screen.dart';

void main() {
  testWidgets('first Tasks visit shimmers when only the Home preview has loaded', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    // Home's bounded preview completed with zero tasks: hasLoaded is true but
    // the screen never ran ensureLoaded. The first visit must still shimmer
    // through its own load instead of flashing the empty state.
    var requests = 0;
    final screenLoad = Completer<ActionItemsResponse>();
    final provider = ActionItemsProvider(
      getActionItems: (
          {limit = 50, offset = 0, completed, conversationId, startDate, endDate, dueStartDate, dueEndDate}) {
        requests++;
        if (requests == 1) {
          // The Home preview resolves immediately with zero tasks.
          return Future.value(const ActionItemsResponse(actionItems: [], hasMore: false));
        }
        // Keep the screen's own load pending so the shimmer window is
        // observable. A completer (never a Timer) avoids pending-timer
        // invariants at teardown.
        return screenLoad.future;
      },
    );
    addTearDown(provider.dispose);
    await provider.ensureHomeWidgetPreviewLoaded();
    expect(provider.hasLoaded, isTrue, reason: 'sanity: preview readiness feeds hasLoaded');
    expect(provider.screenLoaded, isFalse, reason: 'sanity: the screen has not initialized');

    final screen = await buildTypedActionItemsScreen(provider) as MaterialApp;
    await tester.pumpWidget(screen);
    // First frame: _initialLoadScheduled is still true (post-frame callback
    // has not run), so the shimmer shows even though hasLoaded is true.
    expect(find.byType(ActionItemsShimmerList), findsOneWidget,
        reason: 'preview readiness must not satisfy the screen\'s first-load shimmer');
    expect(provider.actionItems, isEmpty);
  });
}
