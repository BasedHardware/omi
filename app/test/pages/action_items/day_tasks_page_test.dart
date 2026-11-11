import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/day_tasks_page.dart';
import 'package:omi/ui/ui.dart';

ActionItemWithMetadata _task(String id, String description, {bool completed = false}) =>
    ActionItemWithMetadata(id: id, description: description, completed: completed);

class _Fetch {
  _Fetch({this.items = const [], this.hasMore = false});

  List<ActionItemWithMetadata> items;
  List<ActionItemWithMetadata> Function(int offset)? pages;
  bool hasMore = false;
  bool fail = false;
  bool truncated = false;
  int rejectedRows = 0;
  Object? error;
  Completer<ApiResult<ActionItemsResponse>>? gate;
  final calls = <({DateTime start, DateTime end, int offset})>[];

  Future<ApiResult<ActionItemsResponse>> call(
      {required DateTime startDate, required DateTime endDate, int limit = 50, int offset = 0}) {
    calls.add((start: startDate, end: endDate, offset: offset));
    final pending = gate;
    if (pending != null) return pending.future;
    final thrown = error;
    if (thrown != null) return Future.error(thrown);
    if (fail) return Future.value(const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 500)));
    return Future.value(ApiSuccess(ActionItemsResponse(actionItems: pages?.call(offset) ?? items, hasMore: hasMore),
        rejectedRows: rejectedRows, truncated: truncated));
  }
}

Future<void> _pumpPage(WidgetTester tester, DateTime date, DayTasksFetcher fetch) {
  return tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: DayTasksPage(date: date, fetchTasks: fetch),
  ));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  final day = DateTime(2026, 9, 12);

  testWidgets('fetches the exact recap-day created_at bounds and renders tasks', (tester) async {
    final fetch = _Fetch(items: [_task('t1', 'Send the logs')]);
    await _pumpPage(tester, day, fetch.call);
    expect(find.byType(OmiSpinner), findsOneWidget);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(fetch.calls, hasLength(1));
    expect(fetch.calls.first.start, DateTime(2026, 9, 12));
    expect(fetch.calls.first.end, DateTime(2026, 9, 13).subtract(const Duration(microseconds: 1)));
    expect(fetch.calls.first.offset, 0);
    expect(find.text('Send the logs'), findsOneWidget);
  });

  testWidgets('an empty day shows the localized empty state', (tester) async {
    await _pumpPage(tester, day, _Fetch().call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.textContaining('No tasks on'), findsOneWidget);
  });

  testWidgets('a failed fetch shows the error state and retry reloads', (tester) async {
    final fetch = _Fetch()..fail = true;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(OmiErrorState), findsOneWidget);

    fetch.fail = false;
    fetch.items = [_task('t1', 'Recovered task')];
    await tester.tap(find.text('Try Again'));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Recovered task'), findsOneWidget);
    expect(fetch.calls, hasLength(2));
  });

  testWidgets('previous day refetches with shifted bounds', (tester) async {
    final fetch = _Fetch();
    await _pumpPage(tester, day, fetch.call);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('day_previous')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.start, DateTime(2026, 9, 11));
  });

  testWidgets('next day is disabled when the page already shows today', (tester) async {
    await _pumpPage(tester, DateTime.now(), _Fetch().call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(tester.widget<OmiIconButton>(find.byKey(const ValueKey('day_next'))).onPressed, isNull);
  });

  testWidgets('an unexpected throw lands on the error state and retry recovers', (tester) async {
    final fetch = _Fetch()..error = StateError('boom');
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(OmiErrorState), findsOneWidget);
    expect(find.byType(OmiSpinner), findsNothing);

    fetch.error = null;
    fetch.items = [_task('t1', 'Recovered task')];
    await tester.tap(find.text('Try Again'));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Recovered task'), findsOneWidget);
  });

  testWidgets('a header-truncated page keeps rows and stops paging', (tester) async {
    final fetch = _Fetch(items: [_task('t1', 'Kept Task')], hasMore: true)..truncated = true;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Kept Task'), findsOneWidget);
    expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget);
    expect(find.byKey(const ValueKey('day_tasks_load_more')), findsNothing);
    expect(fetch.calls, hasLength(1), reason: 'a truncated page must not keep paging');
  });

  testWidgets('rejected rows keep pagination alive: later valid tasks stay reachable', (tester) async {
    final firstPage = List.generate(50, (i) => _task('p1-$i', 'Task $i'));
    final secondPage = [_task('p2-0', 'Page Two Task')];
    final fetch = _Fetch(hasMore: true);
    fetch.pages = (offset) => offset == 0 ? firstPage : secondPage;
    fetch.rejectedRows = 3;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    // The partial-data notice is visible, but pagination continues.
    await tester.scrollUntilVisible(find.byKey(const ValueKey('search_partial_retry')), 200);
    expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget);
    expect(find.byKey(const ValueKey('day_tasks_load_more')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('day_tasks_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();

    // The offset skipped the rejected rows; the second page's task is reachable.
    expect(fetch.calls.last.offset, 53, reason: 'offset includes the rejected wire rows');
    expect(find.text('Page Two Task'), findsOneWidget);
  });

  testWidgets('an empty truncated page is an error, not an empty day', (tester) async {
    final fetch = _Fetch()..truncated = true;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(OmiErrorState), findsOneWidget);
    expect(find.textContaining('No tasks on'), findsNothing);
  });

  testWidgets('a failed second page keeps rows and its retry appends without duplicates', (tester) async {
    final firstPage = List.generate(50, (i) => _task('p1-$i', 'Task $i'));
    final secondPage = List.generate(50, (i) => _task('p2-$i', 'Page Two $i'));
    final fetch = _Fetch(hasMore: true)..pages = (offset) => offset == 0 ? firstPage : secondPage;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_tasks_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_tasks_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.offset, 50);

    fetch.fail = true;
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_tasks_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_tasks_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.offset, 100);
    expect(find.byKey(const ValueKey('day_tasks_retry')), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Task 0'), -200, scrollable: find.byType(Scrollable));

    fetch.fail = false;
    fetch.hasMore = false;
    fetch.pages = (offset) => [_task('p1-0', 'Task 0 dup'), _task('p3-0', 'New Task')];
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_tasks_retry')), 200,
        scrollable: find.byType(Scrollable));
    await tester.tap(find.byKey(const ValueKey('day_tasks_retry')));
    await tester.pump();
    await tester.pumpAndSettle();
    for (var i = 0; i < 8 && find.text('New Task').evaluate().isEmpty; i++) {
      await tester.fling(find.byType(ListView), const Offset(0, -1500), 8000);
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(find.text('New Task'), findsOneWidget);
    expect(find.text('Task 0 dup'), findsNothing);
    expect(find.byKey(const ValueKey('day_tasks_load_more')), findsNothing);
  });

  testWidgets('a full page followed by an empty page ends normally, not partial', (tester) async {
    final firstPage = List.generate(50, (i) => _task('p1-$i', 'Task $i'));
    final fetch = _Fetch(hasMore: true)..pages = (offset) => offset == 0 ? firstPage : [];
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    fetch.hasMore = false;
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_tasks_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_tasks_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(fetch.calls.last.offset, 50);
    expect(find.byKey(const ValueKey('day_tasks_load_more')), findsNothing);
    expect(find.byKey(const ValueKey('day_tasks_retry')), findsNothing);
    expect(find.byKey(const ValueKey('search_partial_retry')), findsNothing);
    await tester.scrollUntilVisible(find.text('Task 0'), -200, scrollable: find.byType(Scrollable));
    expect(find.text('Task 0'), findsOneWidget);
  });

  testWidgets('a pending page on a changed day leaves no latched footer spinner', (tester) async {
    final firstPage = List.generate(50, (i) => _task('p1-$i', 'Task $i'));
    final gate = Completer<ApiResult<ActionItemsResponse>>();
    final fetch = _Fetch(hasMore: true)..pages = (offset) => offset == 0 ? firstPage : [];
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    fetch.gate = gate;
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_tasks_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_tasks_load_more')));
    await tester.pump();
    expect(find.byType(OmiSpinner), findsOneWidget);

    fetch.gate = null;
    fetch.hasMore = false;
    fetch.pages = (offset) => [_task('t-prev', 'Previous Day Task')];
    await tester.tap(find.byKey(const ValueKey('day_previous')));
    await tester.pump();
    gate.complete(ApiSuccess(ActionItemsResponse(actionItems: firstPage, hasMore: true)));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byType(OmiSpinner), findsNothing);
    expect(find.text('Previous Day Task'), findsOneWidget);
  });
}
