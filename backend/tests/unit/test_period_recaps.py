"""Weekly and monthly recaps (#4468) built from the daily recaps already stored.

A period recap is a deterministic roll-up: no LLM call, so it is cheap to open
any time. It totals the days, picks the busiest one, keeps the highlights,
decisions, open questions and open action items, compares with the previous
period, and ranks the people the user talked to most (#3808).
"""

from datetime import date, datetime, timezone

import pytest

from models.period_recap import PeriodRecapResponse
from utils import period_recaps as pr


def _day(day: str, *, conversations=0, minutes=0, actions=0, memories=0, **fields):
    return {
        'id': f'sum-{day}',
        'date': day,
        'stats': {
            'total_conversations': conversations,
            'total_duration_minutes': minutes,
            'action_items_created': actions,
            'memories_created': memories,
        },
        **fields,
    }


WEEK = [
    _day(
        '2026-09-28',
        conversations=3,
        minutes=50,
        actions=2,
        memories=4,
        highlights=[
            {
                'topic': 'Vendor quote',
                'emoji': '💼',
                'summary': 'Agreed to sign this week.',
                'conversation_ids': ['c1'],
            },
            {'topic': 'Gym', 'emoji': '🏋️', 'summary': 'Leg day.', 'conversation_ids': ['c2']},
            {'topic': 'Third', 'emoji': '•', 'summary': 'Dropped: at most two per day.', 'conversation_ids': []},
        ],
        decisions_made=[{'decision': 'Move the offsite to March', 'conversation_id': 'c1'}],
        unresolved_questions=[{'question': 'Who owns the budget?', 'conversation_id': 'c1'}],
        action_items=[
            {'description': 'Send revised numbers', 'priority': 'high', 'source_conversation_id': 'c1'},
            {'description': 'Book flights', 'completed': True},
        ],
    ),
    _day('2026-10-01', conversations=6, minutes=120, actions=1, memories=2),
    _day('2026-10-04', conversations=1, minutes=10),
    # Outside the week: never counted.
    _day('2026-10-05', conversations=99, minutes=999),
]


def test_week_runs_monday_to_sunday_around_the_anchor():
    assert pr.period_bounds('week', date(2026, 10, 1)) == (date(2026, 9, 28), date(2026, 10, 4))
    assert pr.period_bounds('week', date(2026, 9, 28)) == (date(2026, 9, 28), date(2026, 10, 4))
    assert pr.period_bounds('week', date(2026, 10, 4)) == (date(2026, 9, 28), date(2026, 10, 4))


def test_month_covers_the_calendar_month_including_leap_february():
    assert pr.period_bounds('month', date(2026, 10, 17)) == (date(2026, 10, 1), date(2026, 10, 31))
    assert pr.period_bounds('month', date(2028, 2, 3)) == (date(2028, 2, 1), date(2028, 2, 29))


def test_previous_period_is_the_one_just_before():
    assert pr.previous_period_bounds('week', date(2026, 9, 28)) == (date(2026, 9, 21), date(2026, 9, 27))
    assert pr.previous_period_bounds('month', date(2026, 3, 1)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert pr.previous_period_bounds('month', date(2026, 1, 1)) == (date(2025, 12, 1), date(2025, 12, 31))


def test_unknown_period_is_rejected():
    with pytest.raises(ValueError):
        pr.period_bounds('year', date(2026, 10, 1))


def test_recap_totals_days_and_finds_the_busiest_one():
    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), WEEK)

    assert recap['period'] == 'week'
    assert (recap['start_date'], recap['end_date']) == ('2026-09-28', '2026-10-04')
    assert recap['days_recorded'] == 3
    assert recap['stats'] == {
        'total_conversations': 10,
        'total_duration_minutes': 180,
        'action_items_created': 3,
        'memories_created': 6,
    }
    assert recap['busiest_day'] == {
        'date': '2026-10-01',
        'summary_id': 'sum-2026-10-01',
        'total_conversations': 6,
        'total_duration_minutes': 120,
    }


def test_recap_keeps_highlights_decisions_and_questions_with_their_day():
    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), WEEK)

    assert [(h['date'], h['topic']) for h in recap['highlights']] == [
        ('2026-09-28', 'Vendor quote'),
        ('2026-09-28', 'Gym'),
    ]
    assert recap['decisions'] == [
        {'date': '2026-09-28', 'decision': 'Move the offsite to March', 'conversation_id': 'c1'}
    ]
    assert recap['open_questions'] == [
        {'date': '2026-09-28', 'question': 'Who owns the budget?', 'conversation_id': 'c1'}
    ]


def test_open_tasks_come_from_the_live_task_list_not_the_daily_snapshots():
    # A daily recap copies each task's `completed` flag when it is generated, so
    # a task finished later still reads as open there. The live list is the truth.
    live = [
        {
            'id': 'task-2',
            'description': 'Book the venue',
            'created_at': datetime(2026, 10, 2, 2, 30, tzinfo=timezone.utc),  # Oct 1 in New York
            'conversation_id': 'c9',
            'due_at': datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc),
            'completed': False,
        },
        {'id': 'task-blank', 'description': '   ', 'created_at': datetime(2026, 9, 29, 12, tzinfo=timezone.utc)},
        {
            'id': 'task-1',
            'description': 'Send revised numbers',
            'created_at': datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc),
            'conversation_id': None,
            'due_at': None,
            'completed': False,
        },
    ]

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), WEEK, action_items=live, time_zone='America/New_York'
    )

    assert recap['open_action_items'] == [
        {
            'id': 'task-2',
            'description': 'Book the venue',
            'date': '2026-10-01',
            'source_conversation_id': 'c9',
            'due_at': '2026-10-03T17:00:00+00:00',
        },
        {
            'id': 'task-1',
            'description': 'Send revised numbers',
            'date': '2026-09-28',
            'source_conversation_id': None,
            'due_at': None,
        },
    ]


def test_a_locked_task_is_never_shown_in_full():
    # Locked tasks are paywalled: the task list truncates them and the chat tools
    # drop them. The recap leaves them out rather than leak the description.
    secret = 'Renegotiate the supplier contract ' + 'x' * 166
    live = [
        {
            'id': 'task-locked',
            'description': secret,
            'is_locked': True,
            'created_at': datetime(2026, 9, 29, 15, tzinfo=timezone.utc),
        },
        {
            'id': 'task-open',
            'description': 'Book flights',
            'created_at': datetime(2026, 9, 30, 15, tzinfo=timezone.utc),
        },
    ]
    assert len(secret) == 200

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), WEEK, action_items=live)

    assert [item['id'] for item in recap['open_action_items']] == ['task-open']
    assert all(secret not in item['description'] for item in recap['open_action_items'])


def test_a_non_string_conversation_id_is_dropped_not_served():
    days = [
        _day(
            '2026-09-29',
            conversations=1,
            decisions_made=[{'decision': 'Ship it', 'conversation_id': 42}],
            unresolved_questions=[{'question': 'Who signs?', 'conversation_id': {'id': 'c1'}}],
        )
    ]
    live = [
        {
            'id': 'task-1',
            'description': 'Book flights',
            'conversation_id': ['c1'],
            'created_at': datetime(2026, 9, 30, 15, tzinfo=timezone.utc),
        }
    ]

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), days, action_items=live)

    assert recap['decisions'][0]['conversation_id'] is None
    assert recap['open_questions'][0]['conversation_id'] is None
    assert recap['open_action_items'][0]['source_conversation_id'] is None
    PeriodRecapResponse(**recap)


def test_a_non_string_daily_recap_id_leaves_the_busiest_day_unlinked():
    days = [_day('2026-09-29', conversations=1, id=7)]

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), days)

    assert recap['busiest_day']['summary_id'] is None
    PeriodRecapResponse(**recap)


def test_open_tasks_are_capped_after_locked_ones_are_dropped():
    live = [
        {
            'id': f'locked-{i}',
            'description': 'Locked',
            'is_locked': True,
            'created_at': datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
        }
        for i in range(3)
    ] + [
        {'id': f'open-{i}', 'description': f'Open {i}', 'created_at': datetime(2026, 9, 30, 12, tzinfo=timezone.utc)}
        for i in range(12)
    ]

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), [], action_items=live)

    assert [item['id'] for item in recap['open_action_items']] == [f'open-{i}' for i in range(pr.MAX_RECAP_ITEMS)]


def test_the_daily_recaps_task_snapshots_are_ignored():
    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), WEEK)

    assert recap['open_action_items'] == []


def test_lists_are_capped_and_malformed_entries_skipped():
    noisy = [
        _day(
            f'2026-10-{day:02d}',
            conversations=1,
            decisions_made=[{'decision': f'decision {day}-{i}'} for i in range(3)] + [{'decision': ''}, 'junk'],
            highlights=[{'topic': None, 'summary': None}],
            stats='not-a-dict',
        )
        for day in range(1, 32)
    ]

    recap = pr.build_period_recap('month', date(2026, 10, 1), date(2026, 10, 31), noisy)

    assert len(recap['decisions']) == pr.MAX_RECAP_ITEMS
    assert recap['decisions'][0]['decision'] == 'decision 1-0'
    assert recap['highlights'] == []
    assert recap['stats']['total_conversations'] == 0
    assert recap['days_recorded'] == 31


def test_previous_period_totals_give_the_trend():
    previous = [_day('2026-09-22', conversations=4, minutes=90), _day('2026-09-25', conversations=1, minutes=10)]

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), WEEK, previous_summaries=previous)

    assert recap['previous'] == {
        'start_date': '2026-09-21',
        'end_date': '2026-09-27',
        'total_conversations': 5,
        'total_duration_minutes': 100,
    }


def test_an_in_progress_period_compares_with_the_same_days_of_the_previous_one():
    assert pr.comparable_previous_bounds('week', date(2026, 9, 28), date(2026, 10, 4), date(2026, 10, 1)) == (
        date(2026, 9, 21),
        date(2026, 9, 24),
    )
    assert pr.comparable_previous_bounds('month', date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 4)) == (
        date(2026, 9, 1),
        date(2026, 9, 4),
    )
    # Never past the previous period's own end (March 30 vs a 28-day February).
    assert pr.comparable_previous_bounds('month', date(2026, 3, 1), date(2026, 3, 31), date(2026, 3, 30)) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )


def test_a_finished_period_compares_with_the_whole_previous_one():
    assert pr.comparable_previous_bounds('week', date(2026, 9, 21), date(2026, 9, 27), date(2026, 10, 1)) == (
        date(2026, 9, 14),
        date(2026, 9, 20),
    )
    assert pr.comparable_previous_bounds('month', date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 4)) == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )


def test_previous_totals_only_count_the_comparable_days():
    previous = [_day('2026-09-22', conversations=4, minutes=90), _day('2026-09-25', conversations=1, minutes=10)]

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), WEEK, previous_summaries=previous, today=date(2026, 10, 1)
    )

    assert recap['previous'] == {
        'start_date': '2026-09-21',
        'end_date': '2026-09-24',
        'total_conversations': 4,
        'total_duration_minutes': 90,
    }


def test_a_monday_without_its_daily_recap_has_nothing_to_compare_yet():
    # Today's daily recap is written in the evening, so on a Monday morning the
    # week has no comparable day yet.
    previous = [_day('2026-09-21', conversations=4, minutes=90)]

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), [], previous_summaries=previous, today=date(2026, 9, 28)
    )

    assert recap['previous'] is None


def test_mid_week_without_todays_recap_compares_through_yesterday():
    week = [_day('2026-09-28', conversations=3, minutes=50), _day('2026-10-01', conversations=6, minutes=120)]
    previous = [_day('2026-09-22', conversations=4, minutes=90), _day('2026-09-25', conversations=1, minutes=10)]

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), week, previous_summaries=previous, today=date(2026, 10, 2)
    )

    assert recap['previous'] == {
        'start_date': '2026-09-21',
        'end_date': '2026-09-24',
        'total_conversations': 4,
        'total_duration_minutes': 90,
    }


def test_mid_week_with_todays_recap_compares_through_today():
    week = [_day('2026-09-28', conversations=3, minutes=50), _day('2026-10-02', conversations=6, minutes=120)]
    previous = [_day('2026-09-22', conversations=4, minutes=90), _day('2026-09-25', conversations=1, minutes=10)]

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), week, previous_summaries=previous, today=date(2026, 10, 2)
    )

    assert (recap['previous']['end_date'], recap['previous']['total_conversations']) == ('2026-09-25', 5)


def test_a_past_period_compares_with_the_whole_previous_one():
    previous = [_day('2026-09-21', conversations=4, minutes=90), _day('2026-09-27', conversations=1, minutes=10)]

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), [], previous_summaries=previous, today=date(2026, 10, 10)
    )

    assert recap['previous'] == {
        'start_date': '2026-09-21',
        'end_date': '2026-09-27',
        'total_conversations': 5,
        'total_duration_minutes': 100,
    }


def test_the_last_day_with_its_recap_compares_with_the_whole_previous_month():
    # February 28 with its recap is the whole of February: compare with all of
    # January, as tomorrow will, not January 1-28.
    february = [_day('2026-02-28', conversations=1, minutes=10)]
    january = [_day('2026-01-28', conversations=2, minutes=20), _day('2026-01-31', conversations=3, minutes=30)]

    recap = pr.build_period_recap(
        'month', date(2026, 2, 1), date(2026, 2, 28), february, previous_summaries=january, today=date(2026, 2, 28)
    )

    assert recap['previous'] == {
        'start_date': '2026-01-01',
        'end_date': '2026-01-31',
        'total_conversations': 5,
        'total_duration_minutes': 50,
    }


def test_a_30_day_month_on_its_last_day_compares_with_all_of_a_31_day_one():
    # April 30 is 29 days after April 1, but March has 31: the last day with its
    # recap compares with all of March, not March 1-30.
    april = [_day('2026-04-30', conversations=1, minutes=10)]
    march = [_day('2026-03-30', conversations=2, minutes=20), _day('2026-03-31', conversations=3, minutes=30)]

    recap = pr.build_period_recap(
        'month', date(2026, 4, 1), date(2026, 4, 30), april, previous_summaries=march, today=date(2026, 4, 30)
    )

    assert (recap['previous']['end_date'], recap['previous']['total_conversations']) == ('2026-03-31', 5)


def test_a_weeks_last_day_counts_only_once_its_recap_exists():
    previous = [_day('2026-09-26', conversations=2, minutes=20), _day('2026-09-27', conversations=3, minutes=30)]
    saturday = [_day('2026-10-03', conversations=1, minutes=10)]
    sunday = saturday + [_day('2026-10-04', conversations=1, minutes=10)]

    def compared(days):
        recap = pr.build_period_recap(
            'week', date(2026, 9, 28), date(2026, 10, 4), days, previous_summaries=previous, today=date(2026, 10, 4)
        )
        return recap['previous']['end_date'], recap['previous']['total_conversations']

    assert compared(saturday) == ('2026-09-26', 2)
    assert compared(sunday) == ('2026-09-27', 5)


def test_the_busiest_day_tie_goes_to_the_earliest_date():
    days = [_day('2026-09-29', conversations=3, minutes=60), _day('2026-10-02', conversations=3, minutes=60)]

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), list(reversed(days)))

    assert recap['busiest_day']['date'] == '2026-09-29'


def test_a_non_canonical_stored_date_is_rejected():
    # date.fromisoformat accepts the basic format '20261001' on Python 3.11;
    # only the canonical YYYY-MM-DD form is a stored recap date.
    days = [_day('20261001', conversations=5, minutes=50), _day('2026-10-02', conversations=1, minutes=10)]

    recap = pr.build_period_recap('month', date(2026, 10, 1), date(2026, 10, 31), days)

    assert recap['days_recorded'] == 1
    assert recap['stats']['total_conversations'] == 1


def test_people_are_ranked_by_talk_time_and_unnamed_people_are_left_out():
    stats = {
        'p-sam': {'conversation_count': 4, 'talk_seconds': 1500.0},
        'p-ana': {'conversation_count': 9, 'talk_seconds': 600.0},
        'p-gone': {'conversation_count': 20, 'talk_seconds': 9000.0},
        'p-lee': {'conversation_count': 1, 'talk_seconds': 30.0},
    }
    names = {'p-sam': 'Sam', 'p-ana': 'Ana', 'p-lee': 'Lee'}

    recap = pr.build_period_recap(
        'week', date(2026, 9, 28), date(2026, 10, 4), WEEK, people_stats=stats, people_names=names
    )

    assert recap['top_people'] == [
        {'person_id': 'p-sam', 'name': 'Sam', 'conversations': 4, 'talk_minutes': 25},
        {'person_id': 'p-ana', 'name': 'Ana', 'conversations': 9, 'talk_minutes': 10},
        {'person_id': 'p-lee', 'name': 'Lee', 'conversations': 1, 'talk_minutes': 1},
    ]


def test_people_rank_is_talk_time_then_conversations_then_id():
    stats = {
        'p-b': {'conversation_count': 2, 'talk_seconds': 60.0},
        'p-a': {'conversation_count': 2, 'talk_seconds': 60.0},
        'p-c': {'conversation_count': 5, 'talk_seconds': 60.0},
        'p-d': {'conversation_count': 1, 'talk_seconds': 900.0},
        'p-e': {'conversation_count': 1},
    }

    assert pr.rank_people(stats) == ['p-d', 'p-c', 'p-a', 'p-b', 'p-e']
    assert pr.rank_people({}) == []


def test_empty_period_is_a_valid_recap():
    recap = pr.build_period_recap('month', date(2026, 11, 1), date(2026, 11, 30), [])

    assert recap['days_recorded'] == 0
    assert recap['busiest_day'] is None
    assert recap['stats']['total_conversations'] == 0
    assert recap['highlights'] == recap['top_people'] == []
    assert recap['previous'] is None


def test_local_period_bounds_become_utc_instants_in_the_users_timezone():
    start, end = pr.period_utc_bounds(date(2026, 9, 28), date(2026, 10, 4), 'America/New_York')

    assert start == datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 5, 3, 59, 59, 999999, tzinfo=timezone.utc)


def test_a_malformed_stored_date_is_skipped_not_a_crash():
    # '2026-10-0x' sorts between '2026-10-01' and '2026-10-31' as a string, so a
    # string-bounds check alone lets it reach date.fromisoformat (busiest day).
    days = [
        _day('2026-10-02', conversations=2, minutes=20),
        _day('2026-10-0x', conversations=9, minutes=900),
        _day('2026-10-1', conversations=9, minutes=900),
        {'date': None, 'stats': {'total_conversations': 9}},
    ]

    recap = pr.build_period_recap('month', date(2026, 10, 1), date(2026, 10, 31), days)

    assert recap['days_recorded'] == 1
    assert recap['busiest_day']['date'] == '2026-10-02'
    assert recap['stats']['total_conversations'] == 2


def _busy_month(entries_per_day=3, busiest='2026-10-31'):
    return [
        _day(
            f'2026-10-{day:02d}',
            conversations=1,
            minutes=500 if f'2026-10-{day:02d}' == busiest else 10,
            highlights=[{'topic': f'topic {day}-{i}', 'summary': 's'} for i in range(entries_per_day)],
            decisions_made=[{'decision': f'decision {day}-{i}'} for i in range(entries_per_day)],
            unresolved_questions=[{'question': f'question {day}-{i}'} for i in range(entries_per_day)],
        )
        for day in range(1, 32)
    ]


def test_month_lists_spread_across_the_period_instead_of_its_first_days():
    recap = pr.build_period_recap('month', date(2026, 10, 1), date(2026, 10, 31), _busy_month())

    for key in ('highlights', 'decisions', 'open_questions'):
        dates = [item['date'] for item in recap[key]]
        assert len(dates) == pr.MAX_RECAP_ITEMS, key
        assert dates == sorted(dates), key
        assert '2026-10-31' in dates, key
        assert max(dates.count(day) for day in dates) <= pr.MAX_HIGHLIGHTS_PER_DAY, key
    # Busiest day first, then the rest by date: one entry each before any day gets a second.
    assert [h['date'] for h in recap['highlights']] == [f'2026-10-{day:02d}' for day in range(1, 10)] + ['2026-10-31']


def test_few_days_fill_the_cap_by_depth_and_keep_each_days_order():
    days = [
        _day(
            day,
            conversations=1,
            minutes=minutes,
            highlights=[{'topic': f'{day} h{i}'} for i in range(5)],
            decisions_made=[{'decision': f'{day} d{i}'} for i in range(5)],
        )
        for day, minutes in (('2026-10-01', 10), ('2026-10-02', 30), ('2026-10-03', 20))
    ]

    recap = pr.build_period_recap('month', date(2026, 10, 1), date(2026, 10, 31), days)

    # Highlights stop at two per day.
    assert [h['topic'] for h in recap['highlights']] == [
        '2026-10-01 h0',
        '2026-10-01 h1',
        '2026-10-02 h0',
        '2026-10-02 h1',
        '2026-10-03 h0',
        '2026-10-03 h1',
    ]
    # Decisions go three deep everywhere, and the busiest day (Oct 2) gets the tenth.
    assert [d['decision'] for d in recap['decisions']] == [
        '2026-10-01 d0',
        '2026-10-01 d1',
        '2026-10-01 d2',
        '2026-10-02 d0',
        '2026-10-02 d1',
        '2026-10-02 d2',
        '2026-10-02 d3',
        '2026-10-03 d0',
        '2026-10-03 d1',
        '2026-10-03 d2',
    ]


def test_a_regenerated_daily_recap_replaces_the_older_copy_of_that_date():
    days = [
        {
            **_day('2026-10-01', conversations=6, minutes=120),
            'created_at': datetime(2026, 10, 2, 1, tzinfo=timezone.utc),
        },
        {**_day('2026-10-01', conversations=9, minutes=900)},  # no created_at: oldest
        {**_day('2026-10-01', conversations=2, minutes=20), 'created_at': '2026-10-03T08:00:00+00:00'},
        {**_day('2026-10-01', conversations=7, minutes=70), 'created_at': 'not-a-date'},
    ]

    recap = pr.build_period_recap('week', date(2026, 9, 28), date(2026, 10, 4), days)

    assert recap['days_recorded'] == 1
    assert recap['stats']['total_conversations'] == 2
    assert recap['busiest_day']['total_duration_minutes'] == 20
