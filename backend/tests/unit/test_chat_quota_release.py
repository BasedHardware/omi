"""Regression: a terminally failed chat turn must give the question back.

`record_chat_quota_question` charges before the provider call (fail-closed on
Firestore), and nothing used to release that charge when the stream then
failed — a retry cost a second question. `release_chat_quota_question` marks
the same idempotency event `released` and decrements the counter in one
transaction, so a retried failure path cannot double-refund and a release
against a never-recorded key is a no-op.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database.llm_usage as llm_usage_db
import database.user_usage as user_usage_db
from tests.unit.test_realtime_quota_counter import UID, _FrozenDatetime, _Store

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch) -> _Store:
    store = _Store()
    monkeypatch.setattr(llm_usage_db, 'datetime', _FrozenDatetime)
    monkeypatch.setattr(user_usage_db, 'datetime', _FrozenDatetime)
    # record/release fall back to the module-level client when none is passed.
    monkeypatch.setattr(llm_usage_db, 'db', store)
    return store


def _questions(store: _Store) -> int:
    return int(user_usage_db.get_monthly_chat_usage(UID, NOW, firestore_client=store)['questions'])


def test_failed_turn_releases_the_charged_question(store) -> None:
    key = 'v2_messages:msg-failed'
    assert llm_usage_db.record_chat_quota_question(UID, key, 'v2_messages')
    assert _questions(store) == 1

    assert llm_usage_db.release_chat_quota_question(UID, key)
    assert _questions(store) == 0


def test_release_is_idempotent_on_retry(store) -> None:
    key = 'v2_messages:msg-flaky'
    llm_usage_db.record_chat_quota_question(UID, key, 'v2_messages')
    assert llm_usage_db.release_chat_quota_question(UID, key)
    # A retried failure path releasing the same key must not double-refund.
    assert not llm_usage_db.release_chat_quota_question(UID, key)
    assert _questions(store) == 0


def test_release_never_recorded_is_a_noop(store) -> None:
    # Turn failed before the charge — nothing to give back, no negative count.
    assert not llm_usage_db.release_chat_quota_question(UID, 'v2_messages:ghost')
    assert _questions(store) == 0


def test_release_lands_in_the_recorded_plan_bucket(store) -> None:
    key = 'v2_messages:msg-plan'
    llm_usage_db.record_chat_quota_question(UID, key, 'v2_messages')
    llm_usage_db.release_chat_quota_question(UID, key)

    day = store.rows[('users', UID, 'llm_usage', '2026-09-02')]
    assert day['backend_chat']['quota_questions'] == 0
    assert day['plan_usage']['basic']['backend_chat']['quota_questions'] == 0
    # The release must not mint a phantom call on the bucket.
    assert day['plan_usage']['basic']['backend_chat'].get('call_count', 0) == 1
