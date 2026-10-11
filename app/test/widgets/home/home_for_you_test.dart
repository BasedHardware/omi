import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/home_for_you.dart';
import 'package:omi/ui/ui.dart';
import '../../helpers/proactivity_fakes.dart';

void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);
  tearDown(() => VisibilityDetectorController.instance.updateInterval = const Duration(milliseconds: 500));
  Future<void> pump(
    WidgetTester tester,
    OutcomeHarness h, {
    ProactivityFeedLoader? load,
    bool success = true,
    double top = 0,
  }) async {
    await h.bind();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SingleChildScrollView(
            child: Column(
              children: [
                SizedBox(height: top),
                HomeForYou(
                  outbox: h.outbox,
                  load: load ?? (_) async => ApiSuccess(feedResponse(items: [feedItem()])),
                  open: (route, {canOpen}) async => success,
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('For You and Daily Recaps headers share the Home section inset', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    await tester.pumpWidget(MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
          body: SingleChildScrollView(
              child: HomeDailyRecaps(
        outbox: h.outbox,
        load: () async => (
          items: [
            DailySummary(
                id: 'recap',
                date: '2026-10-03',
                createdAt: DateTime.utc(2026, 10, 3),
                headline: 'Synthetic recap',
                overview: 'Fixture',
                stats: DayStats(totalConversations: 1, actionItemsCount: 1))
          ],
          ok: true
        ),
        loadFeed: (_) async => ApiSuccess(feedResponse(items: [feedItem()])),
      ))),
    ));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('For You')).dx, tester.getTopLeft(find.text('Daily Recaps')).dx);
  });

  testWidgets('populated renders neutral card; visible shown only once across refresh', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await pump(tester, h);
    expect(find.text('For You'), findsOneWidget);
    expect(find.text('Revisit Your Commitment'), findsOneWidget);
    expect(h.events.where((e) => e.action == 'shown'), hasLength(1));
    await tester.state<HomeForYouState>(find.byType(HomeForYou)).refresh();
    await tester.pumpAndSettle();
    expect(h.events.where((e) => e.action == 'shown'), hasLength(1));
    await tester.pump(const Duration(hours: 1));
    expect(h.events.any((e) => e.action == 'timeout'), isFalse);
  });
  testWidgets('empty, disabled, typed failure and thrown failure quietly hide section', (tester) async {
    for (final load in <ProactivityFeedLoader>[
      (_) async => ApiSuccess(feedResponse()),
      (_) async => ApiSuccess(feedResponse(enabled: false, items: [feedItem()])),
      (_) async => const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503)),
      (_) async => throw StateError('synthetic failure'),
    ]) {
      final h = OutcomeHarness();
      await pump(tester, h, load: load);
      expect(find.text('For You'), findsNothing);
      expect(h.events, isEmpty);
      await tester.pumpWidget(const SizedBox());
      h.outbox.dispose();
    }
  });
  testWidgets('offscreen fetch sends no shown until scrolled into view', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await pump(tester, h, top: 1000);
    expect(h.events, isEmpty);
    await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -950));
    await tester.pumpAndSettle();
    expect(h.events.where((e) => e.action == 'shown'), hasLength(1));
  });
  testWidgets('successful open, thumbs selected, dismiss; no implicit open on feedback', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await pump(tester, h);
    await tester.tap(find.byKey(const ValueKey('for-you-up-item-1')));
    await tester.pumpAndSettle();
    expect(h.outbox.feedback['item-1'], 'thumbs_up');
    await tester.tap(find.byKey(const ValueKey('for-you-down-item-1')));
    await tester.pumpAndSettle();
    expect(h.outbox.feedback['item-1'], 'thumbs_down');
    expect(h.events.where((e) => e.action == 'opened'), isEmpty);
    await tester.tap(find.byKey(const ValueKey('for-you-open-item-1')));
    await tester.pumpAndSettle();
    expect(h.events.where((e) => e.action == 'opened'), hasLength(1));
    await tester.tap(find.byKey(const ValueKey('for-you-dismiss-item-1')));
    await tester.pumpAndSettle();
    expect(find.text('For You'), findsNothing);
    expect(h.events.last.action, 'dismissed');
  });
  testWidgets('failed open does not emit opened; overflow disables all same-producer cards', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await pump(
      tester,
      h,
      success: false,
      load: (_) async => ApiSuccess(
        feedResponse(
          items: [
            feedItem(),
            feedItem(id: 'item-2'),
          ],
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('for-you-open-item-1')));
    await tester.pumpAndSettle();
    expect(h.events.where((e) => e.action == 'opened'), isEmpty);
    await tester.tap(find.byKey(const ValueKey('for-you-more-item-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Stop These'));
    await tester.pumpAndSettle();
    expect(find.text('For You'), findsNothing);
    expect(h.events.last.action, 'producer_disabled');
  });
  testWidgets('fetch failure clears previously visible cards; account change hides old content', (tester) async {
    var fail = false;
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await pump(
      tester,
      h,
      load: (_) async =>
          fail ? const ApiFailure(ApiProblem(ApiProblemKind.server)) : ApiSuccess(feedResponse(items: [feedItem()])),
    );
    fail = true;
    await tester.state<HomeForYouState>(find.byType(HomeForYou)).refresh();
    await tester.pumpAndSettle();
    expect(find.text('For You'), findsNothing);
    await h.bind(null);
    await tester.pumpAndSettle();
    expect(find.text('For You'), findsNothing);
  });
  testWidgets('empty scanned page follows cursor to populated page', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    final cursors = <String>[];
    await pump(
      tester,
      h,
      load: (cursor) async {
        cursors.add(cursor);
        return ApiSuccess(
          cursor.isEmpty ? feedResponse(hasMore: true, nextCursor: 'next') : feedResponse(items: [feedItem()]),
        );
      },
    );
    expect(cursors, ['', 'next']);
    expect(find.text('For You'), findsOneWidget);
  });
  testWidgets('covered cards do not claim exposure; returning to Home does', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    final pending = Completer<ApiResult<GeneratedProactivityFeedResponse>>();
    final nav = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: nav,
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: HomeForYou(outbox: h.outbox, load: (_) => pending.future),
        ),
      ),
    );
    nav.currentState!.push(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: Text('Detail'))));
    await tester.pumpAndSettle();
    pending.complete(ApiSuccess(feedResponse(items: [feedItem()])));
    await tester.pumpAndSettle();
    expect(h.events, isEmpty);
    nav.currentState!.pop();
    await tester.pumpAndSettle();
    expect(h.events.where((e) => e.action == 'shown'), hasLength(1));
  });
  testWidgets('late feed response and open menu action are fenced on account switch', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await pump(tester, h);
    await tester.tap(find.byKey(const ValueKey('for-you-more-item-1')));
    await tester.pumpAndSettle();
    await h.bind('owner-b');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Stop These'));
    await tester.pumpAndSettle();
    expect(h.events.where((e) => e.action == 'producer_disabled'), isEmpty);
    expect(h.outbox.disabledProducers, isEmpty);
  });

  testWidgets('feed response from previous account cannot render under next owner', (tester) async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    final pending = Completer<ApiResult<GeneratedProactivityFeedResponse>>();
    var calls = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: HomeForYou(
            outbox: h.outbox,
            load: (_) => ++calls == 1 ? pending.future : Future.value(ApiSuccess(feedResponse())),
          ),
        ),
      ),
    );
    await h.bind('owner-b');
    await tester.pumpAndSettle();
    pending.complete(ApiSuccess(feedResponse(items: [feedItem()])));
    await tester.pumpAndSettle();
    expect(find.text('For You'), findsNothing);
    expect(h.events, isEmpty);
  });
}
