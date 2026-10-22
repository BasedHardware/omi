"""FREE_RETENTION_LOCK_DAYS: Free-plan conversations older than the window are retention locked.

Off by default: no row carries ``retention_locked`` and no detail read answers 402.
When on, only ``basic``-plan accounts are affected; paid plans (Stripe trials carry a
paid plan type) never are. Export/download routes are untouched by construction: the
lock lives in the list and detail handlers only.
"""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import routers.conversations as conv  # noqa: E402
import utils.free_plan_retention as retention  # noqa: E402
from models.conversation import Conversation  # noqa: E402
from models.users import PlanType  # noqa: E402

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _row(cid: str, age_days: int, *, now: datetime | None = None) -> dict:
    when = (now or datetime.now(timezone.utc)) - timedelta(days=age_days)
    return {
        'id': cid,
        'created_at': when,
        'started_at': when,
        'finished_at': when,
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': cid, 'overview': '', 'sections': [], 'action_items': [], 'events': []},
    }


def _plan(monkeypatch, plan):
    monkeypatch.setattr(
        retention.users_db,
        'get_user_valid_subscription',
        lambda uid, **_kw: None if plan is None else SimpleNamespace(plan=plan),
    )


# ── helper ────────────────────────────────────────────────────────────────────


def test_off_by_default_never_locks(monkeypatch):
    monkeypatch.delenv('FREE_RETENTION_LOCK_DAYS', raising=False)
    _plan(monkeypatch, PlanType.basic)
    rows = [_row('old', 400, now=NOW)]
    retention.annotate_retention_lock('uid', rows, now=NOW)
    assert 'retention_locked' not in rows[0]
    assert retention.retention_lock_days_for_user('uid') == 0


@pytest.mark.parametrize('plan', [PlanType.plus, PlanType.unlimited, PlanType.operator, PlanType.architect])
def test_paid_plans_are_never_locked(monkeypatch, plan):
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', '30')
    _plan(monkeypatch, plan)
    rows = [_row('old', 400, now=NOW)]
    retention.annotate_retention_lock('uid', rows, now=NOW)
    assert 'retention_locked' not in rows[0]


@pytest.mark.parametrize('plan', [PlanType.basic, None])
def test_free_rows_are_locked_past_the_window(monkeypatch, plan):
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', '30')
    _plan(monkeypatch, plan)
    rows = [_row('fresh', 1, now=NOW), _row('edge', 29, now=NOW), _row('old', 31, now=NOW), {'id': 'no-created-at'}]
    retention.annotate_retention_lock('uid', rows, now=NOW)
    assert [r['retention_locked'] for r in rows] == [False, False, True, False]


def test_created_at_accepts_iso_strings_and_naive_datetimes(monkeypatch):
    old = NOW - timedelta(days=45)
    assert retention.is_retention_locked({'created_at': old.isoformat()}, 30, now=NOW)
    assert retention.is_retention_locked({'created_at': old.replace(tzinfo=None)}, 30, now=NOW)
    assert not retention.is_retention_locked({'created_at': 'not-a-date'}, 30, now=NOW)


def test_unreadable_subscription_fails_open(monkeypatch):
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', '30')

    def boom(uid, **_kw):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(retention.users_db, 'get_user_valid_subscription', boom)
    assert retention.retention_lock_days_for_user('uid') == 0


# ── GET /v1/conversations ─────────────────────────────────────────────────────


def _list(monkeypatch, rows):
    monkeypatch.setattr(
        conv.conversations_db, 'get_conversations_without_photos', lambda uid, limit, offset, **kw: rows
    )
    monkeypatch.setattr(
        conv,
        'list_read_budget_for_request',
        lambda request, route: SimpleNamespace(truncated=False, observe=lambda outcome: None),
    )
    return conv.get_conversations(
        request=None,
        response=None,
        sources=None,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
        uid='uid',
    )


def test_list_stamps_retention_locked_for_free_accounts(monkeypatch):
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', '30')
    _plan(monkeypatch, PlanType.basic)
    result = _list(monkeypatch, [_row('fresh', 1), _row('old', 31)])
    assert [(r['id'], r['retention_locked']) for r in result] == [('fresh', False), ('old', True)]
    # Older clients that do not know the field still decode the row; the model defaults it.
    assert Conversation(**result[1]).retention_locked is True
    assert Conversation(**_row('plain', 1)).retention_locked is False


def test_list_is_unchanged_while_off(monkeypatch):
    monkeypatch.delenv('FREE_RETENTION_LOCK_DAYS', raising=False)
    _plan(monkeypatch, PlanType.basic)
    result = _list(monkeypatch, [_row('old', 400)])
    assert 'retention_locked' not in result[0]


# ── GET /v1/conversations/{id} ────────────────────────────────────────────────


def _detail(monkeypatch, row):
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid, **kw: row)
    monkeypatch.setattr(conv.conversations_db, 'is_visible_conversation', lambda c, include_discarded: True)
    return conv.get_conversation_by_id(
        row['id'], source=None, include_discarded=None, uid='uid', include_translations=False, translation_cursor=None
    )


def test_detail_answers_402_retention_locked_for_old_free_rows(monkeypatch):
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', '30')
    _plan(monkeypatch, PlanType.basic)
    with pytest.raises(HTTPException) as exc_info:
        _detail(monkeypatch, _row('old', 31))
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == {'error': 'retention_locked', 'days': 30}
    # A row inside the window reads normally, and the row is never rewritten.
    fresh = _row('fresh', 1)
    assert _detail(monkeypatch, fresh) is fresh
    assert 'retention_locked' not in fresh


def test_detail_reads_old_rows_for_paid_plans_and_while_off(monkeypatch):
    old = _row('old', 400)
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', '30')
    _plan(monkeypatch, PlanType.plus)
    assert _detail(monkeypatch, old) is old
    monkeypatch.delenv('FREE_RETENTION_LOCK_DAYS')
    _plan(monkeypatch, PlanType.basic)
    assert _detail(monkeypatch, old) is old
