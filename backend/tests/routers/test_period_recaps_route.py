"""GET /v1/users/recaps/{period}: weekly and monthly recaps (#4468).

The route resolves the period in the user's timezone, reads the daily recaps for
it and the period before in one bounded query, reads the live open tasks, ranks
people from the period's conversations under one request budget, reports a cut
scan through the list-truncation header, and fails open (without people) if
that scan breaks.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi import HTTPException, Response

from database.conversation_scan import RECAP_PEOPLE_SCAN_CAP
from models.period_recap import PeriodRecapResponse
from routers import recaps as recaps_mod
from utils.observability.fallback import ALLOWED_COMPONENTS
from utils.other.list_budget import OMI_LIST_TRUNCATED_HEADER, ListReadBudget, ListReadBudgetExhausted

UID = 'u1'


def _summary(day: str, conversations: int, minutes: int):
    return {
        'id': f'sum-{day}',
        'date': day,
        'stats': {'total_conversations': conversations, 'total_duration_minutes': minutes},
    }


def _conversation(person_id: str, seconds: float):
    return {
        'id': f'c-{person_id}',
        'started_at': datetime(2026, 9, 30, 15, tzinfo=timezone.utc),
        'transcript_segments': [{'person_id': person_id, 'start': 0.0, 'end': seconds, 'text': 'hi'}],
    }


def _budget():
    return ListReadBudget(deadline_monotonic=time.monotonic() + 60)


@pytest.fixture
def deps(monkeypatch):
    calls = {'people_by_ids': [], 'budgets': []}
    summaries = MagicMock(
        return_value=[
            _summary('2026-10-01', 6, 120),
            _summary('2026-09-28', 3, 50),
            _summary('2026-09-24', 4, 90),
            _summary('2026-09-02', 2, 30),
        ]
    )

    def people_scan(uid, *, start_date, end_date, budget):
        calls['people_scan'] = (uid, start_date, end_date, budget)

        def rows():
            # Like iter_conversations: an exhausted budget ends the scan before any read.
            try:
                budget.check()
            except ListReadBudgetExhausted:
                return
            yield _conversation('p-sam', 300.0)
            yield _conversation('p-ana', 60.0)

        return rows()

    def action_items(uid, **kwargs):
        calls['action_items'] = (uid, kwargs)
        if kwargs['budget'].truncated:
            # Like get_action_items: no read once the request budget is spent.
            return []
        return [
            {
                'id': 'task-1',
                'description': 'Send revised numbers',
                'created_at': datetime(2026, 9, 29, 14, tzinfo=timezone.utc),
                'conversation_id': 'c1',
                'due_at': None,
                'completed': False,
            }
        ]

    def people_by_ids(uid, person_ids):
        calls['people_by_ids'].append(list(person_ids))
        names = {'p-sam': 'Sam', 'p-ana': 'Ana'}
        return [{'id': pid, 'name': names.get(pid, pid.upper())} for pid in person_ids]

    def budget_for(_request, *, route):
        budget = _budget()
        calls['budgets'].append((route, budget))
        return budget

    def no_full_people_read(_uid):
        raise AssertionError('the recap must not read every person')

    monkeypatch.setattr(recaps_mod.notification_db, 'get_user_time_zone', lambda _uid: 'America/New_York')
    monkeypatch.setattr(recaps_mod.daily_summaries_db, 'get_daily_summaries', summaries)
    monkeypatch.setattr(recaps_mod, 'recap_people_scan', people_scan)
    monkeypatch.setattr(recaps_mod.action_items_db, 'get_action_items', action_items)
    monkeypatch.setattr(recaps_mod.users_db, 'get_people', no_full_people_read)
    monkeypatch.setattr(recaps_mod.users_db, 'get_people_by_ids', people_by_ids)
    monkeypatch.setattr(recaps_mod, 'conversation_scan_budget', budget_for)
    monkeypatch.setattr(recaps_mod, 'local_today', lambda _tz: date(2026, 10, 4))
    return summaries, calls


def _get(period='week', day=None, response=None):
    return recaps_mod.get_period_recap(
        request=SimpleNamespace(state=SimpleNamespace()),
        response=response if response is not None else Response(),
        period=period,
        date=day,
        uid=UID,
    )


def test_week_recap_reads_both_periods_in_one_query_and_ranks_people(deps):
    summaries, calls = deps

    recap = _get('week', '2026-10-01')

    summaries.assert_called_once_with(UID, limit=124, offset=0, start_date='2026-09-21', end_date='2026-10-04')
    assert (recap.start_date, recap.end_date) == ('2026-09-28', '2026-10-04')
    assert recap.stats.total_conversations == 9
    # Today (Sunday) has no daily recap yet, so the week runs through Saturday.
    assert (recap.previous.start_date, recap.previous.end_date) == ('2026-09-21', '2026-09-26')
    assert recap.previous.total_conversations == 4
    assert recap.busiest_day.date == '2026-10-01'
    assert [(p.name, p.talk_minutes) for p in recap.top_people] == [('Sam', 5), ('Ana', 1)]
    [(route, budget)] = calls['budgets']
    assert route == 'period-recap'
    assert calls['people_scan'] == (
        UID,
        datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 5, 3, 59, 59, 999999, tzinfo=timezone.utc),
        budget,
    )


def test_month_recap_defaults_to_the_current_month_in_the_users_timezone(deps):
    summaries, _ = deps

    recap = _get('month')

    assert (recap.start_date, recap.end_date) == ('2026-10-01', '2026-10-31')
    assert summaries.call_args.kwargs['start_date'] == '2026-09-01'
    # October 4 has no daily recap yet: October 1-3 compares with September 1-3.
    assert (recap.previous.start_date, recap.previous.end_date) == ('2026-09-01', '2026-09-03')
    assert recap.previous.total_conversations == 2


@pytest.mark.parametrize('day', ['2026-10-05', '2026-13-01', 'yesterday', '0001-01-01', '1999-12-31'])
def test_future_or_malformed_dates_are_rejected(deps, day):
    with pytest.raises(HTTPException) as error:
        _get('week', day)

    assert error.value.status_code == 422


def test_unknown_period_is_rejected(deps):
    with pytest.raises(HTTPException) as error:
        _get('year')

    assert error.value.status_code == 422


def test_people_scan_failure_still_serves_the_recap_and_records_the_fallback(deps, monkeypatch, caplog):
    fallbacks = []

    def broken_scan(uid, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(recaps_mod, 'recap_people_scan', broken_scan)
    monkeypatch.setattr(recaps_mod, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    response = Response()
    with caplog.at_level(logging.WARNING, logger=recaps_mod.logger.name):
        recap = _get('week', '2026-10-01', response=response)

    assert recap.stats.total_conversations == 9
    assert recap.top_people == []
    # The recap is missing its people: the app shows the partial notice.
    assert response.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert [f['outcome'] for f in fallbacks] == ['degraded']
    # A component outside the closed enum collapses to 'other' on the dashboard.
    assert fallbacks[0]['component'] == 'daily_summary'
    assert fallbacks[0]['component'] in ALLOWED_COMPONENTS
    # record_fallback(log=logger) already logs; no second warning line.
    assert [r for r in caplog.records if r.name == recaps_mod.logger.name] == []


def test_a_degraded_read_keeps_its_cause_at_debug_level(deps, monkeypatch, caplog):
    # The fallback warning names no cause, so a programming error inside a read
    # would otherwise look like a routine outage. Its traceback stays at debug.
    def broken_scan(uid, **_kwargs):
        raise TypeError('unexpected keyword argument')

    def broken_tasks(uid, **_kwargs):
        raise KeyError('missing field')

    monkeypatch.setattr(recaps_mod, 'recap_people_scan', broken_scan)
    monkeypatch.setattr(recaps_mod.action_items_db, 'get_action_items', broken_tasks)
    monkeypatch.setattr(recaps_mod, 'record_fallback', lambda **kwargs: None)

    with caplog.at_level(logging.DEBUG, logger=recaps_mod.logger.name):
        _get('week', '2026-10-01', response=Response())

    records = [r for r in caplog.records if r.name == recaps_mod.logger.name]
    assert {r.levelno for r in records} == {logging.DEBUG}
    assert sorted(r.exc_info[0].__name__ for r in records) == ['KeyError', 'TypeError']


def test_a_failed_daily_recap_read_fails_the_request(deps, monkeypatch):
    # The daily recaps are the recap: without them every total would read zero,
    # so the failure reaches the app as an error it offers Try Again on.
    _, calls = deps
    fallbacks = []

    def broken_summaries(uid, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(recaps_mod.daily_summaries_db, 'get_daily_summaries', broken_summaries)
    monkeypatch.setattr(recaps_mod, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    with pytest.raises(RuntimeError, match='firestore unavailable'):
        _get('week', '2026-10-01')

    assert fallbacks == []
    assert 'action_items' not in calls and 'people_scan' not in calls


def test_the_earliest_supported_anchor_is_served(deps):
    recap = _get('month', '2000-01-01')

    assert (recap.start_date, recap.end_date) == ('2000-01-01', '2000-01-31')


def test_open_tasks_are_the_live_open_tasks_created_in_the_period(deps):
    _, calls = deps

    recap = _get('week', '2026-10-01')

    [(_, budget)] = calls['budgets']
    assert calls['action_items'] == (
        UID,
        {
            'completed': False,
            'start_date': datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc),
            'end_date': datetime(2026, 10, 5, 3, 59, 59, 999999, tzinfo=timezone.utc),
            'limit': recaps_mod.RECAP_TASK_READ_LIMIT,
            'budget': budget,
        },
    )
    assert [item.model_dump() for item in recap.open_action_items] == [
        {
            'id': 'task-1',
            'description': 'Send revised numbers',
            'date': '2026-09-29',
            'source_conversation_id': 'c1',
            'due_at': None,
        }
    ]


def test_locked_tasks_do_not_crowd_out_open_ones(deps, monkeypatch):
    # Newest first, as the task list orders them: ten locked tasks, then three open ones.
    tasks = [
        {
            'id': f'locked-{i}',
            'description': 'Locked task',
            'is_locked': True,
            'created_at': datetime(2026, 10, 3, 12, i, tzinfo=timezone.utc),
        }
        for i in range(10)
    ] + [
        {
            'id': f'open-{i}',
            'description': f'Open task {i}',
            'created_at': datetime(2026, 9, 29, 12, i, tzinfo=timezone.utc),
        }
        for i in range(3)
    ]
    monkeypatch.setattr(recaps_mod.action_items_db, 'get_action_items', lambda uid, *, limit, **_kwargs: tasks[:limit])

    recap = _get('week', '2026-10-01')

    assert [item.id for item in recap.open_action_items] == ['open-0', 'open-1', 'open-2']
    assert recaps_mod.RECAP_TASK_READ_LIMIT == 50


def test_a_failed_people_scan_keeps_the_tasks(deps, monkeypatch):
    def broken_scan(uid, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(recaps_mod, 'recap_people_scan', broken_scan)
    monkeypatch.setattr(recaps_mod, 'record_fallback', lambda **kwargs: None)

    recap = _get('week', '2026-10-01')

    assert [item.id for item in recap.open_action_items] == ['task-1']


def test_names_come_from_the_top_ranked_people_only(deps, monkeypatch):
    _, calls = deps
    crowd = [_conversation(f'p-{i:02d}', 100.0 + i) for i in range(20)]
    monkeypatch.setattr(recaps_mod, 'recap_people_scan', lambda uid, **_kwargs: iter(crowd))

    recap = _get('week', '2026-10-01')

    expected = [f'p-{i:02d}' for i in range(19, 4, -1)]
    assert calls['people_by_ids'] == [expected]
    assert [p.person_id for p in recap.top_people] == expected[:5]


def test_dismissed_people_are_left_out_like_the_people_list(deps, monkeypatch):
    # get_people_by_ids returns dismissed people on purpose; the recap lists people, so it drops them.
    def people_by_ids(_uid, _person_ids):
        return [{'id': 'p-sam', 'name': 'Sam', 'is_dismissed': True}, {'id': 'p-ana', 'name': 'Ana'}]

    monkeypatch.setattr(recaps_mod.users_db, 'get_people_by_ids', people_by_ids)

    recap = _get('week', '2026-10-01')

    assert [p.name for p in recap.top_people] == ['Ana']


def test_a_full_read_of_daily_recaps_drops_the_comparison(deps):
    summaries, _ = deps
    summaries.return_value = [_summary('2026-10-01', 1, 10)] * recaps_mod.RECAP_SUMMARY_READ_LIMIT

    recap = _get('week', '2026-10-01')

    assert recap.stats.total_conversations == 1
    assert recap.previous is None


def test_a_complete_recap_has_no_truncation_header(deps):
    response = Response()

    _get('week', '2026-10-01', response=response)

    assert OMI_LIST_TRUNCATED_HEADER not in response.headers


def test_a_people_scan_that_fills_its_cap_is_a_sample_not_a_truncation(deps, monkeypatch):
    # Like the People page, the cap is a documented sample: Try Again could
    # never clear a notice for it, so the response is not marked truncated.
    closed = []

    def full_scan(uid, **_kwargs):
        try:
            for i in range(RECAP_PEOPLE_SCAN_CAP + 5):
                yield _conversation(f'p-{i % 3}', 10.0)
        finally:
            closed.append(True)

    monkeypatch.setattr(recaps_mod, 'recap_people_scan', full_scan)
    response = Response()

    recap = _get('week', '2026-10-01', response=response)

    assert OMI_LIST_TRUNCATED_HEADER not in response.headers
    assert {p.person_id for p in recap.top_people} == {'p-0', 'p-1', 'p-2'}
    assert closed == [True]


def test_the_people_sample_is_documented_on_the_response():
    description = PeriodRecapResponse.model_fields['top_people'].description or ''

    assert f'up to {RECAP_PEOPLE_SCAN_CAP} conversations in the period, newest first' in description


def test_a_failed_task_read_still_serves_the_recap_marked_partial(deps, monkeypatch, caplog):
    fallbacks = []

    def broken_tasks(uid, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(recaps_mod.action_items_db, 'get_action_items', broken_tasks)
    monkeypatch.setattr(recaps_mod, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    response = Response()

    with caplog.at_level(logging.WARNING, logger=recaps_mod.logger.name):
        recap = _get('week', '2026-10-01', response=response)

    assert recap.stats.total_conversations == 9
    assert recap.open_action_items == []
    assert [p.name for p in recap.top_people] == ['Sam', 'Ana']
    assert fallbacks == [
        {
            'component': 'daily_summary',
            'from_mode': 'with_tasks',
            'to_mode': 'without_tasks',
            'reason': 'other',
            'outcome': 'degraded',
            'log': recaps_mod.logger,
        }
    ]
    assert response.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert [r for r in caplog.records if r.name == recaps_mod.logger.name] == []


def test_a_scan_cut_by_the_request_budget_is_reported_truncated(deps, monkeypatch):
    def cut_scan(uid, *, budget, **_kwargs):
        yield _conversation('p-sam', 300.0)
        budget.mark_exhausted('deadline')

    monkeypatch.setattr(recaps_mod, 'recap_people_scan', cut_scan)
    response = Response()

    recap = _get('week', '2026-10-01', response=response)

    assert response.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert [p.name for p in recap.top_people] == ['Sam']


def test_a_task_read_cut_by_the_request_budget_is_reported_truncated(deps, monkeypatch):
    def cut_tasks(uid, *, budget, **_kwargs):
        budget.mark_exhausted('documents')
        return []

    monkeypatch.setattr(recaps_mod.action_items_db, 'get_action_items', cut_tasks)
    response = Response()

    _get('week', '2026-10-01', response=response)

    assert response.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'


def test_the_route_policy_declares_the_byok_check_its_auth_dependency_runs():
    # get_current_user_uid validates BYOK headers whenever they are present, so
    # the manifest says so, as it does for the daily-summaries routes.
    [route] = [r for r in recaps_mod.router.routes if getattr(r, 'path', None) == '/v1/users/recaps/{period}']
    assert any(dep.call is recaps_mod.auth.get_current_user_uid for dep in route.dependant.dependencies)
    manifest_text = (Path(__file__).resolve().parents[2] / 'route_policy_manifest.yaml').read_text()
    manifest = yaml.load(manifest_text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
    [entry] = [
        e for e in manifest['routes'] if e.get('method') == 'GET' and e.get('path') == '/v1/users/recaps/{period}'
    ]

    assert entry['policy']['byok'] == 'validated_when_headers_present'
