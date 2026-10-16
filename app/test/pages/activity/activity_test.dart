import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/activity/activity_bell_button.dart';
import 'package:omi/pages/activity/activity_page.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';

/// An in-memory bell state starting at [stored] (0: never visited).
(ActivitySeen, int Function()) _seen(int stored) {
  var value = stored;
  return (ActivitySeen(read: () => value, write: (v) => value = v), () => value);
}

DailySummary _recap(String id, DateTime createdAt) => DailySummary(
      id: id,
      date: createdAt.toIso8601String().substring(0, 10),
      createdAt: createdAt,
      headline: 'Recap $id',
      overview: '',
      dayEmoji: '📊',
      stats: DayStats(totalConversations: 1, actionItemsCount: 0),
    );

/// No server pending work or attention items, and no I/O.
PendingWorkStore _noWork() => PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );

Widget _app(Widget home) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

void main() {
  final yesterday = DateTime.now().subtract(const Duration(days: 1));
  final anHourAgo = DateTime.now().subtract(const Duration(hours: 1));

  group('ActivitySeen', () {
    test('first successful load on an install is the baseline, not news', () {
      final (seen, stored) = _seen(0);
      final now = DateTime.now();
      seen.observe([yesterday], now: now);
      expect(seen.hasNew.value, isFalse);
      expect(stored(), now.millisecondsSinceEpoch);
    });

    test('an empty first load still sets the baseline, so the first recap lights the bell', () {
      final (seen, _) = _seen(0);
      seen.observe(const [], now: anHourAgo);
      expect(seen.hasNew.value, isFalse);
      seen.observe([DateTime.now()]);
      expect(seen.hasNew.value, isTrue);
    });

    test('a recap newer than the last visit lights the bell; visiting clears it', () {
      final (seen, stored) = _seen(yesterday.millisecondsSinceEpoch);
      seen.observe([yesterday]);
      expect(seen.hasNew.value, isFalse);
      seen.observe([anHourAgo]);
      expect(seen.hasNew.value, isTrue);

      final now = DateTime.now();
      seen.markSeen(through: now);
      expect(seen.hasNew.value, isFalse);
      expect(stored(), now.millisecondsSinceEpoch);
      seen.observe([anHourAgo]);
      expect(seen.hasNew.value, isFalse);
    });
  });

  test('leaving Activity marks seen only through what it showed', () {
    final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
    final shown = DateTime.now().subtract(const Duration(minutes: 10));
    seen.observe([DateTime.now()]); // Home saw a recap after Activity last loaded.
    seen.markSeen(through: shown);
    expect(seen.hasNew.value, isTrue);
  });

  test('deleting the only unseen recap turns the bell off', () {
    final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
    seen.observe([anHourAgo, yesterday]);
    expect(seen.hasNew.value, isTrue);
    seen.observe([yesterday]);
    expect(seen.hasNew.value, isFalse);
  });

  test('a different signed-in account starts from its own watermark, never the last one\'s dot', () {
    final stores = <String, int>{'a': yesterday.millisecondsSinceEpoch, 'b': 0};
    var owner = 'a';
    final seen = ActivitySeen(owner: () => owner, read: () => stores[owner] ?? 0, write: (v) => stores[owner] = v);
    seen.observe([anHourAgo]);
    expect(seen.hasNew.value, isTrue);

    owner = 'b';
    seen.observe([yesterday]);
    expect(seen.hasNew.value, isFalse, reason: 'first load for account b is its baseline');
    owner = 'a';
    seen.observe([anHourAgo]);
    owner = 'b';
    expect(seen.describesCurrentOwner, isFalse, reason: 'a bell built for b hides a\'s dot before b loads');
    expect(stores['a'], yesterday.millisecondsSinceEpoch);
  });

  group('ActivityBellButton', () {
    testWidgets('is always there, with a dot only when something is new', (tester) async {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      await tester
          .pumpWidget(_app(Scaffold(body: Center(child: ActivityBellButton(pendingWork: _noWork(), seen: seen)))));
      expect(find.byKey(const ValueKey('home_activity_button')), findsOneWidget);
      expect(find.byKey(const ValueKey('home_activity_dot')), findsNothing);
      expect(find.bySemanticsLabel('Activity'), findsOneWidget);

      seen.observe([anHourAgo]);
      await tester.pump();
      expect(find.byKey(const ValueKey('home_activity_dot')), findsOneWidget);
      expect(find.bySemanticsLabel('Activity, new items'), findsOneWidget);
    });
  });

  group('ActivityPage', () {
    testWidgets('a failed recap load leaves an unseen recap unseen', (tester) async {
      final (seen, stored) = _seen(yesterday.millisecondsSinceEpoch);
      seen.observe([anHourAgo]);
      await tester.pumpWidget(_app(ActivityPage(
        pendingWork: _noWork(),
        seen: seen,
        probeDreamReport: () async => false,
        loadRecaps: () async => (items: <DailySummary>[], ok: false),
        loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])),
      )));
      await tester.pumpAndSettle();
      await tester.pumpWidget(const SizedBox());
      expect(stored(), yesterday.millisecondsSinceEpoch);
      expect(seen.hasNew.value, isTrue);
    });

    Widget page(ActivitySeen seen, {bool changesOk = true, ApiProblemKind failure = ApiProblemKind.notFound}) =>
        ActivityPage(
          pendingWork: _noWork(),
          seen: seen,
          probeDreamReport: () async => false,
          loadRecaps: () async => (items: [_recap('new', anHourAgo), _recap('old', yesterday)], ok: true),
          loadChanges: ({cursor}) async => changesOk
              ? ApiSuccess(ReviewChangesPage(changes: [
                  ReviewChange(
                    changeId: 'c1',
                    kind: ReviewChangeKind.mergeMemories,
                    title: 'Merged two memories',
                    createdAt: DateTime.now().subtract(const Duration(minutes: 30)),
                  ),
                ]))
              : ApiFailure<ReviewChangesPage>(ApiProblem(failure)),
        );

    testWidgets('lists recaps and changes newest first, dots only the recap new since the last visit', (tester) async {
      final (seen, stored) = _seen(DateTime.now().subtract(const Duration(hours: 3)).millisecondsSinceEpoch);
      await tester.pumpWidget(_app(page(seen)));
      await tester.pumpAndSettle();

      final change = tester.getTopLeft(find.text('Merged two memories')).dy;
      final fresh = tester.getTopLeft(find.text('Recap new')).dy;
      final old = tester.getTopLeft(find.text('Recap old')).dy;
      expect(change, lessThan(fresh));
      expect(fresh, lessThan(old));
      expect(find.byKey(const Key('activity_new_dot')), findsOneWidget);
      expect(find.byKey(const Key('activity_recent_changes')), findsOneWidget);

      // Opening it marked everything seen: the bell is dark, with no "mark all read" anywhere.
      expect(seen.hasNew.value, isFalse);
      expect(stored(), greaterThanOrEqualTo(anHourAgo.millisecondsSinceEpoch));
      expect(find.textContaining('Mark'), findsNothing);
    });

    testWidgets('still shows recaps when changes are unavailable for the account', (tester) async {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      await tester.pumpWidget(_app(page(seen, changesOk: false)));
      await tester.pumpAndSettle();
      expect(find.text('Recap new'), findsOneWidget);
      expect(find.byKey(const Key('activity_recent_changes')), findsNothing);
    });

    testWidgets('a real failure of one source shows what loaded, with a retry', (tester) async {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      await tester.pumpWidget(_app(page(seen, changesOk: false, failure: ApiProblemKind.server)));
      await tester.pumpAndSettle();
      expect(find.text('Recap new'), findsOneWidget);
      expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget);
    });

    testWidgets('rows stay activatable for screen readers', (tester) async {
      final handle = tester.ensureSemantics();
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      await tester.pumpWidget(_app(page(seen)));
      await tester.pumpAndSettle();
      final node = tester.getSemantics(find.byKey(const ValueKey('activity_recap_new')));
      expect(node.label, startsWith('Recap new, '));
      expect(node.label, endsWith(', New'));
      expect(tester.getSemantics(find.byKey(const ValueKey('activity_recap_old'))).label, isNot(endsWith(', New')));
      expect(node.getSemanticsData().hasAction(SemanticsAction.tap), isTrue);
      handle.dispose();
    });

    testWidgets('a refresh where one source fails keeps that source\'s rows', (tester) async {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      var recapsOk = true;
      await tester.pumpWidget(_app(ActivityPage(
        pendingWork: _noWork(),
        seen: seen,
        probeDreamReport: () async => false,
        loadRecaps: () async => (items: recapsOk ? [_recap('kept', anHourAgo)] : <DailySummary>[], ok: recapsOk),
        loadChanges: ({cursor}) async => ApiSuccess(ReviewChangesPage(changes: [
          ReviewChange(
              changeId: 'c1', kind: ReviewChangeKind.rename, title: 'Renamed a person', createdAt: DateTime.now()),
        ])),
      )));
      await tester.pumpAndSettle();
      expect(find.text('Recap kept'), findsOneWidget);

      recapsOk = false;
      await tester.drag(find.byType(ListView), const Offset(0, 300));
      await tester.pumpAndSettle();
      expect(find.text('Recap kept'), findsOneWidget);
      expect(find.text("Couldn't load all of your activity"), findsOneWidget);
    });

    testWidgets('says so when there is nothing yet', (tester) async {
      final (seen, _) = _seen(0);
      await tester.pumpWidget(_app(ActivityPage(
        pendingWork: _noWork(),
        seen: seen,
        probeDreamReport: () async => false,
        loadRecaps: () async => (items: <DailySummary>[], ok: true),
        loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])),
      )));
      await tester.pumpAndSettle();
      expect(find.text('No activity yet'), findsOneWidget);
    });

    testWidgets('a recap stamped ahead of the phone clock is seen once shown', (tester) async {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      final ahead = DateTime.now().add(const Duration(minutes: 10));
      await tester.pumpWidget(_app(ActivityPage(
        pendingWork: _noWork(),
        seen: seen,
        probeDreamReport: () async => false,
        loadRecaps: () async => (items: [_recap('ahead', ahead)], ok: true),
        loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])),
      )));
      await tester.pumpAndSettle();
      expect(find.text('Recap ahead'), findsOneWidget);
      expect(seen.hasNew.value, isFalse);
    });

    test('a recap without a server creation time never lights the bell', () {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      final unstamped = DailySummary(
        id: 'legacy',
        date: '2026-10-15',
        createdAt: DateTime.now(),
        createdAtKnown: false,
        headline: 'Recap legacy',
        overview: '',
        dayEmoji: '📊',
        stats: DayStats(totalConversations: 1, actionItemsCount: 0),
      );
      seen.observe(ActivitySeen.recapArrivals([unstamped]));
      expect(seen.hasNew.value, isFalse);
      seen.observe(ActivitySeen.recapArrivals([unstamped, _recap('real', anHourAgo)]));
      expect(seen.hasNew.value, isTrue);
    });

    testWidgets('an empty feed still pulls to refresh', (tester) async {
      final (seen, _) = _seen(yesterday.millisecondsSinceEpoch);
      var recaps = <DailySummary>[];
      await tester.pumpWidget(_app(ActivityPage(
        pendingWork: _noWork(),
        seen: seen,
        probeDreamReport: () async => false,
        loadRecaps: () async => (items: recaps, ok: true),
        loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])),
      )));
      await tester.pumpAndSettle();
      expect(find.text('No activity yet'), findsOneWidget);

      recaps = [_recap('arrived', anHourAgo)];
      await tester.drag(find.text('No activity yet'), const Offset(0, 300));
      await tester.pumpAndSettle();
      expect(find.text('Recap arrived'), findsOneWidget);
    });
  });
}
