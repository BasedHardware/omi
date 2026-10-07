// Recaps: the weekly and monthly recap page (PeriodRecapPage) with a full week, an empty month and
// a failed load.
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/recaps.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/pages/conversations/period_recap_page.dart';

import '../harness.dart';

wire.GeneratedPeriodRecapResponse _week() => wire.GeneratedPeriodRecapResponse.fromJson({
      'period': 'week',
      'start_date': '2026-09-28',
      'end_date': '2026-10-04',
      'days_recorded': 5,
      'stats': {
        'total_conversations': 23,
        'total_duration_minutes': 312,
        'action_items_created': 9,
        'memories_created': 14,
      },
      'previous': {
        'start_date': '2026-09-21',
        'end_date': '2026-09-27',
        'total_conversations': 17,
        'total_duration_minutes': 240,
      },
      'busiest_day': {'date': '2026-10-01', 'total_conversations': 7, 'total_duration_minutes': 104},
      'top_people': [
        {'person_id': 'p-sam', 'name': 'Sam Rivera', 'conversations': 6, 'talk_minutes': 48},
        {'person_id': 'p-priya', 'name': 'Priya Shah', 'conversations': 4, 'talk_minutes': 31},
        {'person_id': 'p-alex', 'name': 'Alex Kim', 'conversations': 2, 'talk_minutes': 12},
      ],
      // No emoji: flutter-tester has no emoji font, so they would render as empty boxes.
      'highlights': [
        {'date': '2026-09-28', 'topic': 'Vendor quote', 'emoji': '', 'summary': 'Agreed to sign the revised quote.'},
        {'date': '2026-09-30', 'topic': 'Launch plan', 'emoji': '', 'summary': 'Beta moves to the second week.'},
        {'date': '2026-10-02', 'topic': 'Team offsite', 'emoji': '', 'summary': 'Shortlisted two venues.'},
      ],
      'decisions': [
        {'date': '2026-09-30', 'decision': 'Move the beta to the second week of October'},
        {'date': '2026-10-02', 'decision': 'Hold the offsite in March'},
      ],
      'open_questions': [
        {'date': '2026-10-01', 'question': 'Who owns the launch budget?'},
      ],
      'open_action_items': [
        {'id': 'task-1', 'date': '2026-09-28', 'description': 'Send the signed quote to finance'},
        {'id': 'task-2', 'date': '2026-10-02', 'description': 'Book a call with both venues'},
      ],
    });

wire.GeneratedPeriodRecapResponse _emptyMonth() => wire.GeneratedPeriodRecapResponse.fromJson({
      'period': 'month',
      'start_date': '2026-10-01',
      'end_date': '2026-10-31',
      'days_recorded': 0,
      'stats': {
        'total_conversations': 0,
        'total_duration_minutes': 0,
        'action_items_created': 0,
        'memories_created': 0,
      },
    });

final recapsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'recaps-week',
    title: 'Weekly recap: totals against last week, busiest day, people, highlights, decisions, open tasks',
    page: 'lib/pages/conversations/period_recap_page.dart (PeriodRecapPage)',
    state: 'An injected loader returns a five-day week with three people, three highlights and two open tasks',
    run: (a) async {
      await a.pump(PeriodRecapPage(load: (period) async => ApiSuccess(_week())), scaffold: false);
      expect(find.text('Sam Rivera'), findsOneWidget);
      await a.scrollSeries('Open Recaps on This Week and scroll through the week');
    },
  ),
  AuditScenario(
    id: 'recaps-month-empty',
    title: 'Monthly recap with nothing recorded',
    page: 'lib/pages/conversations/period_recap_page.dart (PeriodRecapPage)',
    state: 'An injected loader returns a month with no recorded days, people or open tasks',
    run: (a) async {
      await a.pump(
        PeriodRecapPage(initialPeriod: RecapPeriod.month, load: (period) async => ApiSuccess(_emptyMonth())),
        scaffold: false,
      );
      await a.shot('Open Recaps on This Month with nothing recorded');
    },
  ),
  AuditScenario(
    id: 'recaps-error',
    title: 'Recap that failed to load, with Try Again',
    page: 'lib/pages/conversations/period_recap_page.dart (PeriodRecapPage)',
    state: 'An injected loader fails with a server error',
    run: (a) async {
      await a.pump(
        PeriodRecapPage(load: (period) async => const ApiFailure(ApiProblem(ApiProblemKind.server))),
        scaffold: false,
      );
      await a.shot('A failed recap load shows an error with Try Again, never an empty recap');
    },
  ),
];
