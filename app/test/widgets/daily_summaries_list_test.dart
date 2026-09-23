import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';

Widget _wrap(Widget sliver) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: const [Locale('en')],
    home: Scaffold(body: CustomScrollView(slivers: [sliver])),
  );
}

DailySummary _summary() => DailySummary(
      id: 'summary-1',
      date: '2026-09-20',
      createdAt: DateTime.utc(2026, 9, 20, 12),
      headline: 'A quiet day',
      overview: 'Nothing much happened',
      stats: DayStats(),
    );

void main() {
  testWidgets('a failed read does not claim the user has no recaps', (tester) async {
    await tester.pumpWidget(
      _wrap(
        DailySummariesList(
          fetchSummaries: ({int limit = 30, int offset = 0}) async =>
              (items: const <DailySummary>[], ok: false),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No daily recaps yet'), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);
  });

  testWidgets('an empty answer still shows the empty state', (tester) async {
    await tester.pumpWidget(
      _wrap(
        DailySummariesList(
          fetchSummaries: ({int limit = 30, int offset = 0}) async =>
              (items: const <DailySummary>[], ok: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No daily recaps yet'), findsOneWidget);
  });

  testWidgets('recaps that loaded are listed', (tester) async {
    await tester.pumpWidget(
      _wrap(
        DailySummariesList(
          fetchSummaries: ({int limit = 30, int offset = 0}) async => (items: [_summary()], ok: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No daily recaps yet'), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsNothing);
  });
}
