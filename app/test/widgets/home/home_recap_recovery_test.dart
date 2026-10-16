import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/daily_recap_recovery_action.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/services/recap_events.dart';
import 'package:omi/ui/ui.dart';
import '../../helpers/proactivity_fakes.dart';

final recap = DailySummary(
    id: 'recovered',
    date: '2026-10-04',
    createdAt: DateTime.utc(2026, 10, 13),
    headline: 'Recovered October day',
    overview: 'Saved conversations',
    stats: DayStats(totalConversations: 1));
typedef Page = ({List<DailySummary> items, bool ok});

Future<void> pump(WidgetTester tester, RecentRecapsLoader load, {bool recover = false}) async {
  final h = OutcomeHarness();
  addTearDown(h.outbox.dispose);
  await h.bind();
  await tester.pumpWidget(MaterialApp(
    theme: buildOmiTheme(),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
        body: SingleChildScrollView(
            child: Column(children: [
      if (recover)
        DailyRecapRecoveryAction(
          now: () => DateTime(2026, 10, 13),
          create: (_) async => ApiSuccess(recap),
          onCreated: (_) async {},
        ),
      HomeDailyRecaps(load: load, outbox: h.outbox, loadFeed: (_) async => ApiSuccess(feedResponse(enabled: false))),
    ]))),
  ));
  await tester.pump();
}

Future<void> recover(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('daily_recap_generate')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('4'));
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);
  tearDown(() => VisibilityDetectorController.instance.updateInterval = const Duration(milliseconds: 500));

  testWidgets('recovery from another screen reveals a previously empty Home recap section', (tester) async {
    var reads = 0;
    await pump(tester, () async => (items: reads++ == 0 ? <DailySummary>[] : [recap], ok: true), recover: true);
    await tester.pumpAndSettle();
    expect(find.text('Daily Recaps'), findsNothing);
    await recover(tester);
    expect(reads, 2);
    expect(find.text('Daily Recaps'), findsOneWidget);
    expect(find.text(recap.headline), findsOneWidget);
  });

  testWidgets('an older Home read cannot hide recovery after the new read completes', (tester) async {
    final old = Completer<Page>();
    var reads = 0;
    await pump(tester, () => reads++ == 0 ? old.future : Future.value((items: [recap], ok: true)), recover: true);
    await recover(tester);
    expect(find.text(recap.headline), findsOneWidget);
    old.complete((items: <DailySummary>[], ok: true));
    await tester.pumpAndSettle();
    expect(find.text(recap.headline), findsOneWidget);
  });

  testWidgets('a Home recap read failure offers retry instead of disappearing', (tester) async {
    var reads = 0;
    await pump(tester, () async => reads++ == 0 ? (items: <DailySummary>[], ok: false) : (items: [recap], ok: true));
    await tester.pumpAndSettle();
    expect(find.byType(OmiErrorState), findsOneWidget);
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(find.text(recap.headline), findsOneWidget);
    expect(find.byType(OmiErrorState), findsNothing);
  });

  testWidgets('shared arrivals refresh Home while a late read cannot resurrect a deleted recap', (tester) async {
    final late = Completer<Page>();
    var reads = 0;
    await pump(tester, () => reads++ == 0 ? Future.value((items: [recap], ok: true)) : late.future);
    await tester.pumpAndSettle();
    expect(find.text(recap.headline), findsOneWidget);
    announceRecapArrived();
    await tester.pump();
    expect(reads, 2);
    announceRecapDeleted(recap.id);
    await tester.pump();
    expect(find.text(recap.headline), findsNothing);
    late.complete((items: [recap], ok: true));
    await tester.pumpAndSettle();
    expect(find.text(recap.headline), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
