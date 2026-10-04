import 'dart:async';

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

wire.GeneratedPeriodRecapResponse _recap(
  String period, {
  int conversations = 12,
  int days = 4,
  List<Map<String, dynamic>>? highlights,
}) =>
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
      'highlights': highlights ??
          [
            {'date': '2026-09-28', 'topic': 'Vendor quote', 'emoji': '💼', 'summary': 'Agreed to sign this week.'},
          ],
      'decisions': [
        {'date': '2026-09-28', 'decision': 'Move the offsite to March'},
      ],
      'open_questions': [
        {'date': '2026-09-29', 'question': 'Who owns the budget?'},
      ],
      'open_action_items': [
        {'id': 'task-1', 'date': '2026-09-28', 'description': 'Send revised numbers'},
      ],
      'top_people': [
        {'person_id': 'p-sam', 'name': 'Sam', 'conversations': 4, 'talk_minutes': 25},
      ],
      'previous': {
        'start_date': '2026-09-21',
        'end_date': '2026-09-27',
        'total_conversations': 9,
        'total_duration_minutes': 80,
      },
    });

/// The overview's conversation total, matched inside its own row: a bare number could be any row's value.
Finder _conversationsTotal(String count) =>
    find.descendant(of: find.widgetWithText(OmiSettingsRow, 'Conversations'), matching: find.text(count));

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
    expect(_conversationsTotal('12'), findsOneWidget);
    expect(find.text('Previous: 9'), findsOneWidget);
    // Lengths in rows are compact (ux-contract §8): 95 min, 80 min before, 25 min with Sam.
    expect(find.text('1h 35m'), findsOneWidget);
    expect(find.text('Previous: 1h 20m'), findsOneWidget);
    expect(find.text('25m'), findsOneWidget);
    expect(find.text('Busiest day'), findsOneWidget);
    expect(find.text('Sam'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('💼 Vendor quote'), 200);
    expect(find.text('💼 Vendor quote'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Send revised numbers'), 200);
    expect(find.text('Move the offsite to March'), findsOneWidget);
    expect(find.text('Who owns the budget?'), findsOneWidget);
    // The open tasks are titled apart from the overview's count of tasks created.
    expect(find.text('Open Tasks'), findsOneWidget);
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
    expect(_conversationsTotal('40'), findsOneWidget);
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

  testWidgets('every failed load offers Try Again, whatever the cause', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async {
            calls++;
            return calls == 1
                ? const ApiFailure(ApiProblem(ApiProblemKind.unprocessable))
                : ApiSuccess(_recap(period.name));
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

  testWidgets('a late answer to an earlier request never replaces the newer one', (tester) async {
    final pending = <Completer<ApiResult<wire.GeneratedPeriodRecapResponse>>>[];
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) {
            final completer = Completer<ApiResult<wire.GeneratedPeriodRecapResponse>>();
            pending.add(completer);
            return completer.future;
          },
        ),
      ),
    );
    await tester.pump();

    // Week -> Month -> Week, before any answer arrives.
    await tester.tap(find.text('This Month'));
    await tester.pump();
    await tester.tap(find.text('This Week'));
    await tester.pump();
    expect(pending, hasLength(3));

    pending[2].complete(ApiSuccess(_recap('week', conversations: 33)));
    await tester.pumpAndSettle();
    pending[1].complete(ApiSuccess(_recap('month', conversations: 40)));
    pending[0].complete(ApiSuccess(_recap('week', conversations: 11)));
    await tester.pumpAndSettle();

    expect(_conversationsTotal('33'), findsOneWidget);
    expect(_conversationsTotal('11'), findsNothing);
    expect(_conversationsTotal('40'), findsNothing);
  });

  testWidgets('a cut-short recap says so above what it has, and Try Again reloads', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async {
            calls++;
            return ApiSuccess(_recap(period.name), truncated: calls == 1);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(OmiPartialNotice), findsOneWidget);
    // The people read so far are kept, below the fold under the notice.
    expect(find.text('Sam', skipOffstage: false), findsOneWidget);
    expect(
      tester.getTopLeft(find.byType(OmiPartialNotice)).dy,
      lessThan(tester.getTopLeft(find.text('Conversations')).dy),
    );

    await tester.tap(find.byKey(const ValueKey('search_partial_retry')));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.byType(OmiPartialNotice), findsNothing);
    expect(find.text('Sam', skipOffstage: false), findsOneWidget);
  });

  testWidgets('pulling down refreshes the recap and keeps it on screen meanwhile', (tester) async {
    final pending = <Completer<ApiResult<wire.GeneratedPeriodRecapResponse>>>[];
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) {
            final completer = Completer<ApiResult<wire.GeneratedPeriodRecapResponse>>();
            pending.add(completer);
            return completer.future;
          },
        ),
      ),
    );
    pending.single.complete(ApiSuccess(_recap('week', conversations: 12)));
    await tester.pumpAndSettle();

    await tester.fling(find.text('Conversations'), const Offset(0, 400), 1000);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1)); // the overscroll settles
    await tester.pump(const Duration(seconds: 1)); // the indicator arms and calls onRefresh

    expect(pending, hasLength(2));
    expect(find.byType(OmiLoadingState), findsNothing);
    expect(_conversationsTotal('12'), findsOneWidget);

    pending.last.complete(ApiSuccess(_recap('week', conversations: 21)));
    await tester.pumpAndSettle();

    expect(_conversationsTotal('21'), findsOneWidget);
  });

  testWidgets('pulling down on an empty recap refreshes it too', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async {
            calls++;
            return ApiSuccess(
              wire.GeneratedPeriodRecapResponse.fromJson({
                'period': period.name,
                'start_date': '2026-09-28',
                'end_date': '2026-10-04',
                'days_recorded': 0,
              }),
            );
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.fling(find.byType(OmiEmptyState), const Offset(0, 400), 1000);
    await tester.pumpAndSettle();

    expect(calls, 2);
  });

  testWidgets('pulling down on a failed load retries it', (tester) async {
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

    await tester.fling(find.byType(OmiErrorState), const Offset(0, 400), 1000);
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('Sam'), findsOneWidget);
  });

  testWidgets('the recap groups sit inside the page margins with room between them', (tester) async {
    await tester.pumpWidget(_app(PeriodRecapPage(load: (period) async => ApiSuccess(_recap(period.name)))));
    await tester.pumpAndSettle();

    // Like the settings pages: a margin on both sides, and a gap before each further group.
    final width = tester.getSize(find.byType(PeriodRecapPage)).width;
    final overview = tester.getRect(find.byType(OmiSettingsGroup).at(0));
    final people = tester.getRect(find.byType(OmiSettingsGroup).at(1));
    expect((overview.left, overview.right), (OmiSpacing.md, width - OmiSpacing.md));
    expect((people.left, people.right), (OmiSpacing.md, width - OmiSpacing.md));
    expect(people.top - overview.bottom, OmiSpacing.xxl);
  });

  testWidgets('a highlight without a topic is titled by its summary', (tester) async {
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async => ApiSuccess(
            _recap(
              period.name,
              highlights: [
                {'date': '2026-09-29', 'summary': 'Talked through the roadmap.'},
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final row = find.byWidgetPredicate((w) => w is OmiSettingsRow && w.title == 'Talked through the roadmap.');
    await tester.scrollUntilVisible(row, 200);
    expect(row, findsOneWidget);
    expect(tester.widget<OmiSettingsRow>(row).subtitle, isNull);
    expect(find.byWidgetPredicate((w) => w is OmiSettingsRow && w.title.trim().isEmpty), findsNothing);
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

  testWidgets('open tasks show even before the period has a daily recap', (tester) async {
    await tester.pumpWidget(
      _app(
        PeriodRecapPage(
          load: (period) async => ApiSuccess(
            wire.GeneratedPeriodRecapResponse.fromJson({
              'period': period.name,
              'start_date': '2026-09-28',
              'end_date': '2026-10-04',
              'days_recorded': 0,
              'open_action_items': [
                {'id': 'task-1', 'date': '2026-09-28', 'description': 'Send revised numbers'},
              ],
            }),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(OmiEmptyState), findsNothing);
    await tester.scrollUntilVisible(find.text('Send revised numbers'), 200);
    expect(find.text('Send revised numbers'), findsOneWidget);
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
