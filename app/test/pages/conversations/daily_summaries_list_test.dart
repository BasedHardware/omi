import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/ui/ui.dart';

DailySummary _summary(String id) => DailySummary(
      id: id,
      date: '2026-09-20',
      createdAt: DateTime.utc(2026, 9, 20, 12),
      headline: 'Recap $id',
      overview: 'Nothing much happened',
      stats: DayStats(totalConversations: 5, actionItemsCount: 3),
    );

List<DailySummary> _page(int offset, int count) => [for (var i = 0; i < count; i++) _summary('summary-${offset + i}')];

Widget _app(DailySummariesFetcher fetcher, {Key? key}) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: CustomScrollView(
          slivers: [DailySummariesList(key: key, fetchSummaries: fetcher)],
        ),
      ),
    );

void main() {
  testWidgets('a throwing initial load shows the error state; Try Again reloads', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) async {
      calls++;
      if (calls == 1) throw StateError('backend unreachable');
      return (items: [_summary('summary-1')], ok: true);
    }));
    await tester.pumpAndSettle();

    expect(find.byType(OmiErrorState), findsOneWidget);
    expect(find.byType(OmiSpinner), findsNothing, reason: 'the loading flag is released after a throw');

    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('Recap summary-1'), findsOneWidget);
    expect(find.byType(OmiErrorState), findsNothing);
  });

  testWidgets('a failed refresh keeps the loaded rows and hasMore', (tester) async {
    var failRefresh = false;
    final key = GlobalKey<DailySummariesListState>();
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) async {
      if (failRefresh) throw StateError('refresh blew up');
      return (items: _page(0, 20), ok: true);
    }, key: key));
    await tester.pumpAndSettle();
    expect(find.text('Recap summary-0'), findsOneWidget);

    failRefresh = true;
    await key.currentState!.refresh();
    await tester.pumpAndSettle();

    expect(find.text('Recap summary-0'), findsOneWidget, reason: 'rows survive a failed refresh');
    expect(find.byKey(const ValueKey('recaps_refresh_failed_banner')), findsOneWidget);
  });

  testWidgets('a failed refresh shows a first-viewport retry that keeps rows and scroll position', (tester) async {
    final pending = Completer<({List<DailySummary> items, bool ok})>();
    var mode = 0;
    final key = GlobalKey<DailySummariesListState>();
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) {
      if (mode == 2) return pending.future;
      if (mode == 1) return Future.value((items: <DailySummary>[], ok: false));
      return Future.value((items: _page(0, 20), ok: true));
    }, key: key));
    await tester.pumpAndSettle();
    expect(find.text('Recap summary-0'), findsOneWidget);

    mode = 1;
    await key.currentState!.refresh();
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('recaps_refresh_failed_banner')), findsOneWidget,
        reason: 'the refresh failure is visible without scrolling to the tail');
    final positionBefore = tester.state<ScrollableState>(find.byType(Scrollable)).position.pixels;

    mode = 2;
    await tester.tap(find.text('Try Again'));
    await tester.pump();
    expect(find.text('Recap summary-0'), findsOneWidget, reason: 'rows stay put while the retry is pending');
    expect(tester.state<ScrollableState>(find.byType(Scrollable)).position.pixels, positionBefore);
    expect(find.byKey(const ValueKey('recaps_refresh_failed_banner')), findsOneWidget,
        reason: 'the notice remains while the retry runs');

    pending.complete((items: _page(0, 20), ok: true));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('recaps_refresh_failed_banner')), findsNothing);
  });

  testWidgets('a throwing page load releases the spinner and offers a user retry, once', (tester) async {
    var calls = 0;
    var failNext = true;
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) async {
      calls++;
      if (offset > 0 && failNext) throw StateError('page two unreachable');
      return (items: _page(offset, 20), ok: true);
    }));
    await tester.pumpAndSettle();

    await tester.fling(find.byType(CustomScrollView), const Offset(0, -3000), 1000);
    await tester.pumpAndSettle();
    final callsAfterFailure = calls;
    expect(callsAfterFailure, greaterThan(1), reason: 'the prefetch should have fired');

    expect(find.byType(OmiSpinner), findsNothing);
    expect(find.text('Try Again'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    expect(calls, callsAfterFailure, reason: 'pagination failures do not auto-retry');

    failNext = false;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(calls, callsAfterFailure + 1);
    expect(find.text('Recap summary-20'), findsOneWidget);
  });

  testWidgets('a successful refresh clears a failed pagination so paging can resume', (tester) async {
    var pageTwoFails = true;
    var pageTwoCalls = 0;
    final key = GlobalKey<DailySummariesListState>();
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) async {
      if (offset == 0) return (items: _page(0, 20), ok: true);
      pageTwoCalls++;
      if (pageTwoFails) throw StateError('page two unreachable');
      return (items: _page(offset, 5), ok: true);
    }, key: key));
    await tester.pumpAndSettle();

    await tester.fling(find.byType(CustomScrollView), const Offset(0, -3000), 1000);
    await tester.pumpAndSettle();
    expect(find.text('Try Again'), findsOneWidget, reason: 'failed page two offers retry');
    expect(pageTwoCalls, 1);

    pageTwoFails = false;
    await key.currentState!.refresh();
    await tester.pumpAndSettle();

    expect(find.text('Try Again'), findsNothing, reason: 'a good first page clears the stuck tail');

    await tester.fling(find.byType(CustomScrollView), const Offset(0, -3000), 1000);
    await tester.pumpAndSettle();
    expect(pageTwoCalls, 2, reason: 'prefetch is live again after the refresh');
    expect(find.text('Recap summary-20'), findsOneWidget);
  });

  testWidgets('a page started before a refresh cannot append its stale rows afterwards', (tester) async {
    final pendingPage = Completer<({List<DailySummary> items, bool ok})>();
    var pendingIssued = false;
    final key = GlobalKey<DailySummariesListState>();
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) {
      if (offset == 0) return Future.value((items: _page(0, 20), ok: true));
      if (!pendingIssued) {
        pendingIssued = true;
        return pendingPage.future;
      }
      return Future.value((items: <DailySummary>[], ok: true));
    }, key: key));
    await tester.pumpAndSettle();

    await tester.fling(find.byType(CustomScrollView), const Offset(0, -3000), 1000);
    await tester.pump();
    // Completing a future nothing awaits would make the stale-marker assertion vacuous.
    expect(pendingIssued, isTrue, reason: 'the deferred page request must be in flight to be invalidated');

    await key.currentState!.refresh();
    await tester.pumpAndSettle();

    pendingPage.complete((items: [_summary('stale-marker')], ok: true));
    await tester.pumpAndSettle();

    final position = tester.state<ScrollableState>(find.byType(Scrollable)).position;
    position.jumpTo(position.maxScrollExtent);
    await tester.pump();
    expect(find.text('Recap stale-marker'), findsNothing,
        reason: 'the superseded page load must not append after a fresh first page');
  });

  testWidgets('a failed refresh with rows still offers a retry affordance', (tester) async {
    var failRefresh = false;
    final key = GlobalKey<DailySummariesListState>();
    await tester.pumpWidget(_app(({int limit = 20, int offset = 0}) async {
      if (failRefresh) throw StateError('refresh blew up');
      return (items: _page(0, 5), ok: true);
    }, key: key));
    await tester.pumpAndSettle();
    expect(find.text('Recap summary-0'), findsOneWidget);

    failRefresh = true;
    await key.currentState!.refresh();
    await tester.pumpAndSettle();

    expect(find.text('Recap summary-0'), findsOneWidget);
    // The retry affordance must sit at the viewport with the rows, not only in
    // the tail below the fold.
    expect(find.byKey(const ValueKey('recaps_refresh_failed_banner')), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.byType(OmiSpinner), findsNothing, reason: 'rows stay on screen: retry keeps the scroll position');

    failRefresh = false;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('recaps_refresh_failed_banner')), findsNothing);
    expect(find.text('Recap summary-0'), findsOneWidget);
  });
}
