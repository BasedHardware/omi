"""Weekly and monthly recaps (#4468) built from the daily recaps already stored.

A period recap is a deterministic roll-up: no LLM call, so it is cheap to open
any time. It totals the days, picks the busiest one, keeps the highlights,
decisions, open questions and open action items, compares with the previous
period, and ranks the people the user talked to most (#3808).
"""

from datetime import date, datetime, timezone

import pytest

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


def test_recap_keeps_highlights_decisions_questions_and_open_actions_with_their_day():
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
    assert recap['open_action_items'] == [
        {
            'date': '2026-09-28',
            'description': 'Send revised numbers',
            'priority': 'high',
            'source_conversation_id': 'c1',
        }
    ]


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

    assert recap['previous'] == {'total_conversations': 5, 'total_duration_minutes': 100}


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
