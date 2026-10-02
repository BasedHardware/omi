import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/widgets/device_tile.dart';

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
      // Not the model's default, so the row has to render this summary's emoji.
      dayEmoji: '🌙',
    );

void main() {
  testWidgets('a failed read does not claim the user has no recaps', (tester) async {
    await tester.pumpWidget(
      _wrap(
        DailySummariesList(
          fetchSummaries: ({int limit = 30, int offset = 0}) async => (items: const <DailySummary>[], ok: false),
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
          fetchSummaries: ({int limit = 30, int offset = 0}) async => (items: const <DailySummary>[], ok: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No daily recaps yet'), findsOneWidget);
  });

  testWidgets('recaps that loaded are listed', (tester) async {
    final summary = _summary();
    await tester.pumpWidget(
      _wrap(
        DailySummariesList(
          fetchSummaries: ({int limit = 30, int offset = 0}) async => (items: [summary], ok: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No daily recaps yet'), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsNothing);
    // A flat row like Home's: the day's emoji in a tile and a chevron, no card around it.
    expect(tester.widget<DeviceTile>(find.byType(DeviceTile)).emoji, summary.dayEmoji);
    expect(find.byIcon(Icons.chevron_right_rounded), findsOneWidget);
  });
}
