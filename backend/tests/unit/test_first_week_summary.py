"""First-week summary guarantee (SCA-4790): stamp, deadline, lane and counter.

Hermetic: no Firestore, no task client, no LLM.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import enrichment as enrichment_config  # noqa: E402
from config import summary_guarantee as guarantee  # noqa: E402
from database import users as users_db  # noqa: E402
from services import first_week_summary_closeout as closeout  # noqa: E402
from utils.conversations import summary_delivery  # noqa: E402
from utils.enrichment import age_gate, fresh_demotion  # noqa: E402

PAID = 1_790_000_000
HOUR = 3600


def _clear(monkeypatch):
    for name in (
        guarantee.FIRST_WEEK_ENABLED_ENV,
        guarantee.FIRST_WEEK_WINDOW_ENV,
        'ENRICHMENT_FIRST_WEEK_TASKS_QUEUE',
        'ENRICHMENT_FRESH_TASKS_QUEUE',
        'ENRICHMENT_TASKS_QUEUE',
        'ENRICHMENT_TASKS_HANDLER_URL',
        'ENRICHMENT_TASKS_OIDC_AUDIENCE',
        'ENRICHMENT_TASKS_INVOKER_SA',
        'ENRICHMENT_ROUTE',
        'ENRICHMENT_FRESH_DEMOTE_AFTER_MIN',
        'ENRICHMENT_MAX_AGE_HOURS',
    ):
        monkeypatch.delenv(name, raising=False)


# --- the window stamp ------------------------------------------------------


def test_stamp_is_absent_without_a_paid_start_or_outside_the_window(monkeypatch):
    _clear(monkeypatch)
    assert guarantee.first_week_stamp(None, PAID) is None
    assert guarantee.first_week_stamp(PAID, PAID - 1) is None
    assert guarantee.first_week_stamp(PAID, PAID + 7 * 24 * HOUR) is None


def test_stamp_covers_a_conversation_created_inside_the_paid_week(monkeypatch):
    _clear(monkeypatch)
    stamp = guarantee.first_week_stamp(PAID, PAID + 3 * 24 * HOUR, interval='monthly')
    assert stamp == {
        'policy_id': guarantee.FIRST_WEEK_POLICY_ID,
        'paid_since': PAID,
        'window_end_at': PAID + 7 * 24 * HOUR,
        'interval': 'monthly',
    }


def test_kill_switch_off_and_zero_hours_disable_the_stamp(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    assert guarantee.first_week_stamp(PAID, PAID + HOUR) is None
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setenv(guarantee.FIRST_WEEK_WINDOW_ENV, '0')
    assert guarantee.first_week_stamp(PAID, PAID + HOUR) is None


def test_window_is_stored_not_recomputed_from_age(monkeypatch):
    _clear(monkeypatch)
    row = {'first_week_summary': guarantee.first_week_stamp(PAID, PAID + HOUR)}
    assert guarantee.first_week_open(row, now=PAID + 6 * 24 * HOUR) is True
    assert guarantee.first_week_open(row, now=PAID + 7 * 24 * HOUR) is False
    # A config change after stamping does not move an in-flight window.
    monkeypatch.setenv(guarantee.FIRST_WEEK_WINDOW_ENV, '24')
    assert guarantee.first_week_open(row, now=PAID + 6 * 24 * HOUR) is True


def test_interval_comes_from_the_period_length_not_a_catalog():
    assert guarantee.first_week_interval(PAID, PAID + 30 * 24 * HOUR) == 'monthly'
    assert guarantee.first_week_interval(PAID, PAID + 365 * 24 * HOUR) == 'yearly'
    assert guarantee.first_week_interval(None, PAID) == 'unknown'


# --- the paid-start epoch --------------------------------------------------


def test_paid_since_is_set_once_on_a_free_to_paid_transition():
    stored = {'plan': 'basic', 'status': 'active'}
    incoming = {'plan': 'unlimited', 'status': 'active'}
    patch = users_db.paid_since_patch(stored, incoming, now=PAID)
    assert patch == {'paid_since': PAID}
    # The user-level epoch is authoritative and a renewal never moves it.
    assert users_db.paid_since_patch(stored, incoming, stored_user_paid_since=PAID, now=PAID + 99) == {
        'paid_since': PAID
    }
    # A legacy paid row without the epoch is never covered.
    assert users_db.paid_since_patch({'plan': 'unlimited', 'status': 'active'}, incoming, now=PAID) == {}


def test_paid_since_ignores_a_trial_that_was_never_charged():
    stored = {'plan': 'basic', 'status': 'active'}
    assert users_db.paid_since_patch(stored, {'plan': 'unlimited', 'status': 'trialing'}, now=PAID) == {}
    # A carried epoch from the caller is authoritative and never moved.
    assert users_db.paid_since_patch(stored, {'plan': 'unlimited', 'status': 'active', 'paid_since': 5}, now=PAID) == {
        'paid_since': 5
    }


# --- the deadline readers --------------------------------------------------


def _stamped_row(now=PAID + 30 * HOUR):
    return {'first_pending_at': PAID + 20 * HOUR, 'first_week_summary': guarantee.first_week_stamp(PAID, PAID)}


def test_age_gate_does_not_park_a_row_inside_its_stored_window(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    row = _stamped_row()
    assert age_gate.expired(row, row['first_pending_at'], now=PAID + 96 * HOUR) is False
    assert age_gate.expired(row, row['first_pending_at'], now=PAID + 7 * 24 * HOUR + 1) is True
    # Kill switch off restores today's gate exactly.
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    assert age_gate.expired(row, row['first_pending_at'], now=PAID + 96 * HOUR) is True


def test_demotion_skips_an_open_first_week_row_with_no_first_week_queue(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('ENRICHMENT_FRESH_DEMOTE_AFTER_MIN', '30')
    dispatch = {
        'queue': 'enrichment-fresh',
        'handler': 'https://worker/v2/enrichment/run',
        'audience': 'https://worker/v2/enrichment/run',
        'invoker_sa': 'sa@example.iam',
    }
    row = {
        'first_pending_at': PAID,
        'first_summary_policy': {'first_summary_enabled': True, 'first_summary_deadline_seconds': 60},
        'first_week_summary': guarantee.first_week_stamp(PAID, PAID),
        'dispatch': dispatch,
    }
    assert fresh_demotion.stale_fresh(row, now=PAID + HOUR) is False
    assert fresh_demotion.stale_fresh(row, now=PAID + 7 * 24 * HOUR) is True


def test_first_week_deadline_is_the_stored_window_end(monkeypatch):
    _clear(monkeypatch)
    row = _stamped_row()
    assert summary_delivery.first_week_deadline(row, row['first_pending_at']) == 7 * 24 * HOUR - 20 * HOUR
    unstated = {'first_summary_policy': {'first_summary_enabled': True, 'first_summary_deadline_seconds': 60}}
    assert summary_delivery.first_week_deadline(unstated, 0) == 60


# --- the lane --------------------------------------------------------------


def test_first_week_binding_uses_its_reserved_queue_and_falls_back(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE', 'enrichment-first-week')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://worker/v2/enrichment/run')
    assert enrichment_config.dispatch_binding(recent=False, first_week=True)['queue'] == 'enrichment-first-week'
    # Priority is its own admission gate: no 30-minute freshness clock needed.
    assert enrichment_config.dispatch_binding(recent=False, first_week=False)['queue'] == 'enrichment'
    monkeypatch.delenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE')
    assert enrichment_config.dispatch_binding(recent=True, first_week=True)['queue'] == 'enrichment-fresh'
    # Backfill keeps its own routing.
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_QUEUE', 'sync-backfill')
    assert enrichment_config.dispatch_binding(backfill=True, first_week=True)['queue'] == 'sync-backfill'


# --- the counter -----------------------------------------------------------


def test_closeout_classifies_summarized_failed_and_no_attempt():
    stamp = guarantee.first_week_stamp(PAID, PAID)
    base = {'first_week_summary': stamp, 'first_week_outcome': None}
    assert closeout.classify({**base, 'summary_output_present': True, 'summary_completed_at': PAID + HOUR}) == (
        'summarized',
        'unknown',
    )
    assert closeout.classify({**base, 'summary_empty_failures': 1})[0] == 'attempt_failed'
    assert closeout.classify({**base, 'summary_blocked_reason': 'blocked_byok'})[0] == 'attempt_failed'
    assert closeout.classify(base)[0] == 'no_attempt'


def test_closeout_counts_only_an_uncounted_row():
    stamp = guarantee.first_week_stamp(PAID, PAID)
    row = {'first_week_summary': stamp, 'first_week_outcome': None, 'summary_output_present': True}
    assert closeout.outcome_patch(row, now=PAID + 8 * 24 * HOUR) == {
        'first_week_outcome': 'summarized',
        'first_week_outcome_at': PAID + 8 * 24 * HOUR,
    }
    counted = {**row, 'first_week_outcome': 'no_attempt'}
    assert closeout.outcome_patch(counted, now=PAID + 9 * 24 * HOUR) is None


def test_closeout_is_a_no_op_when_the_guarantee_is_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    assert closeout.tick(now=PAID, client=None) == {'scanned': 0, 'closed': 0, 'errors': 0}


def test_a_summary_that_lands_after_the_close_is_not_backdated():
    stamp = guarantee.first_week_stamp(PAID, PAID)
    row = {
        'first_week_summary': stamp,
        'summary_output_present': True,
        'summary_completed_at': stamp['window_end_at'] + HOUR,
    }
    assert closeout.classify(row)[0] == 'no_attempt'
