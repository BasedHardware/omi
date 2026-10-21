import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/ui/ui.dart';

DailySummary _summary() => DailySummary(
      id: 'summary-1',
      date: '2026-09-20',
      createdAt: DateTime.utc(2026, 9, 20, 12),
      headline: 'A quiet day',
      overview: 'Nothing much happened',
      stats: DayStats(totalConversations: 5, actionItemsCount: 3),
    );

Widget _app(Widget home) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

void main() {
  testWidgets('Daily Recaps is a pushed page with a back button', (tester) async {
    await tester.pumpWidget(
      _app(
          DailyRecapsPage(fetchSummaries: ({int limit = 20, int offset = 0}) async => (items: [_summary()], ok: true))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Daily Recaps'), findsOneWidget);
    expect(find.byType(OmiBackButton), findsOneWidget);
    // Counts say what they count (hub audit #20).
    expect(find.textContaining('5 conversations · 3 tasks'), findsOneWidget);
  });

  testWidgets('a failed load offers Try Again, which reloads', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _app(
        DailyRecapsPage(
          fetchSummaries: ({int limit = 20, int offset = 0}) async {
            calls++;
            return calls == 1 ? (items: const <DailySummary>[], ok: false) : (items: [_summary()], ok: true);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Try Again'), findsOneWidget);
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('A quiet day'), findsOneWidget);
  });

  testWidgets('pull-to-refresh reloads the recaps', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _app(
        DailyRecapsPage(
          fetchSummaries: ({int limit = 20, int offset = 0}) async {
            calls++;
            return (items: [_summary()], ok: true);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(calls, 1);

    await tester.fling(find.text('A quiet day'), const Offset(0, 400), 1000);
    await tester.pumpAndSettle();

    expect(calls, 2);
  });
}
