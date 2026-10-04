import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/recaps.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/period_recap_page.dart';
import 'package:omi/ui/ui.dart';

wire.GeneratedPeriodRecapResponse _recap(String period, {int conversations = 12, int days = 4}) =>
    wire.GeneratedPeriodRecapResponse.fromJson({
      'period': period,
      'start_date': period == 'week' ? '2026-09-28' : '2026-10-01',
      'end_date': period == 'week' ? '2026-10-04' : '2026-10-31',
      'days_recorded': days,
      'stats': {
        'total_conversations': conversations,
        'total_duration_minutes': 95,
        'action_items_created': 3,
        'memories_created': 7,
      },
      'busiest_day': {'date': '2026-10-01', 'total_conversations': 6, 'total_duration_minutes': 60},
      'highlights': [
        {'date': '2026-09-28', 'topic': 'Vendor quote', 'emoji': '💼', 'summary': 'Agreed to sign this week.'},
      ],
      'decisions': [
        {'date': '2026-09-28', 'decision': 'Move the offsite to March'},
      ],
      'open_questions': [
        {'date': '2026-09-29', 'question': 'Who owns the budget?'},
      ],
      'open_action_items': [
        {'date': '2026-09-28', 'description': 'Send revised numbers'},
      ],
      'top_people': [
        {'person_id': 'p-sam', 'name': 'Sam', 'conversations': 4, 'talk_minutes': 25},
      ],
      'previous': {'total_conversations': 9, 'total_duration_minutes': 80},
    });

Widget _app(Widget home) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

void main() {
  testWidgets('the week recap shows totals, the trend, the busiest day, people and the week\'s threads',
      (tester) async {
    await tester.pumpWidget(_app(PeriodRecapPage(load: (period) async => ApiSuccess(_recap(period.name)))));
    await tester.pumpAndSettle();

    expect(find.byType(OmiBackButton), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('Previous: 9'), findsOneWidget);
    expect(find.text('Busiest day'), findsOneWidget);
    expect(find.text('Sam'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('💼 Vendor quote'), 200);
    expect(find.text('💼 Vendor quote'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Send revised numbers'), 200);
    expect(find.text('Move the offsite to March'), findsOneWidget);
    expect(find.text('Who owns the budget?'), findsOneWidget);
  });

  testWidgets('switching to This Month loads the month recap', (tester) async {
    final requested = <RecapPeriod>[];
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async {
            requested.add(period);
            return ApiSuccess(_recap(period.name, conversations: period == RecapPeriod.month ? 40 : 12));
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('This Month'));
    await tester.pumpAndSettle();

    expect(requested, [RecapPeriod.week, RecapPeriod.month]);
    expect(find.text('40'), findsOneWidget);
  });

  testWidgets('a failed load offers Try Again, which reloads', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async {
            calls++;
            return calls == 1 ? const ApiFailure(ApiProblem(ApiProblemKind.server)) : ApiSuccess(_recap(period.name));
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(OmiErrorState), findsOneWidget);
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('Sam'), findsOneWidget);
  });

  testWidgets('a period with nothing recorded says so instead of showing zeros', (tester) async {
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async => ApiSuccess(
            wire.GeneratedPeriodRecapResponse.fromJson({
              'period': period.name,
              'start_date': '2026-09-28',
              'end_date': '2026-10-04',
              'days_recorded': 0,
            }),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(OmiEmptyState), findsOneWidget);
    expect(find.text('Nothing recorded in this period yet'), findsOneWidget);
  });

  testWidgets('Daily Recaps opens the weekly and monthly recaps', (tester) async {
    await tester.pumpWidget(
      _app(
        DailyRecapsPage(
          fetchSummaries: ({int limit = 20, int offset = 0}) async => (items: const <DailySummary>[], ok: true),
          loadPeriodRecap: (period) async => ApiSuccess(_recap(period.name)),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Recaps'));
    await tester.pumpAndSettle();

    expect(find.byType(PeriodRecapPage), findsOneWidget);
    expect(find.text('Sam'), findsOneWidget);
  });
}
