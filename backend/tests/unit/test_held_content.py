"""At-cap contract: retries, period reset, stale races, legacy capability, and entitlement safety."""

from datetime import datetime, timedelta, timezone

import pytest

from config.held_content import budget_period, capture_state, current_choice
from database import budget_choice
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import held_content_flags


@pytest.fixture(autouse=True)
def choice_clock(monkeypatch):
    monkeypatch.setattr(budget_choice, 'budget_period', lambda: '2026-10')


def test_flags_default_off_and_explicit_capability(monkeypatch):
    monkeypatch.delenv('HELD_CONTENT_ENABLED', raising=False)
    assert not held_content_flags.capable('1')
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    assert held_content_flags.capable('1')
    for capability in [None, '', '0', '2', 'true']:
        assert not held_content_flags.capable(capability)


@pytest.mark.parametrize('value', ['false', '', '1', 'on', 'malformed'])
def test_malformed_flags_do_not_enable(monkeypatch, value):
    monkeypatch.setenv('HELD_CONTENT_ENABLED', value)
    assert not held_content_flags.enabled()


def test_budget_period_uses_utc_month():
    assert budget_period(datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)) == '2026-12'
    assert budget_period(datetime(2027, 1, 1, tzinfo=timezone.utc)) == '2027-01'
    # Local dates on either side of midnight must still use the UTC month.
    assert budget_period(datetime(2026, 11, 1, 0, 30, tzinfo=timezone(timedelta(hours=7)))) == '2026-10'
    assert budget_period(datetime(2026, 10, 31, 23, 30, tzinfo=timezone(timedelta(hours=-7)))) == '2026-11'


@pytest.mark.parametrize('choice', [None, {'choice': 'upgrade'}, {'choice': 'on_device'}])
def test_recovery_requires_managed_allowance(choice):
    assert capture_state(managed=True, exhausted=False, choice=choice) == 'managed'
    assert capture_state(managed=False, exhausted=False, choice=choice) == 'unavailable'


def test_at_cap_states_and_upgrade_is_not_entitlement():
    assert capture_state(managed=False, exhausted=True, choice=None) == 'held_pending_choice'
    assert capture_state(managed=False, exhausted=True, choice={'choice': 'upgrade'}) == 'held_pending_choice'
    assert capture_state(managed=False, exhausted=True, choice={'choice': 'on_device'}) == 'on_device'


def test_transactional_choice_is_idempotent_and_bounded(monkeypatch):
    db = StrictFirestore()
    expected = {'period': '2026-10', 'choice': 'on_device', 'dont_ask_again': True}
    for _ in range(2):
        assert budget_choice.set_choice('test-user', '2026-10', 'on_device', True, firestore_client=db) == expected
    assert len(db.rows) == 1
    assert len(db.transactions[0].sets) == 1
    assert len(db.transactions[1].sets) == 0
    assert budget_choice.get_choice('test-user', '2026-10', firestore_client=db) == expected
    assert budget_choice.get_choice('test-user', '2026-11', firestore_client=db) is None
    monkeypatch.setattr(budget_choice, 'budget_period', lambda: '2026-11')
    assert (
        budget_choice.set_choice('test-user', '2026-11', 'upgrade', False, firestore_client=db)['choice'] == 'upgrade'
    )
    assert len(db.rows) == 1


def test_conflicting_retry_cannot_overwrite_first_choice():
    db = StrictFirestore()
    budget_choice.set_choice('test-user', '2026-10', 'on_device', True, firestore_client=db)
    with pytest.raises(budget_choice.BudgetChoiceConflict):
        budget_choice.set_choice('test-user', '2026-10', 'upgrade', False, firestore_client=db)
    assert budget_choice.get_choice('test-user', '2026-10', firestore_client=db)['choice'] == 'on_device'


def test_newer_stored_period_rejects_when_request_month_equals_clock():
    db = StrictFirestore()
    path = ('users', 'test-user', 'budget_choice', 'current')
    stored = {'period': '2026-11', 'choice': 'upgrade', 'dont_ask_again': False}
    db.rows[path] = dict(stored)
    with pytest.raises(budget_choice.BudgetChoiceConflict, match='budget_period_changed'):
        budget_choice.set_choice('test-user', '2026-10', 'on_device', True, firestore_client=db)
    assert db.rows[path] == stored
    assert all(not tx.sets for tx in db.transactions)


def test_two_transaction_attempts_cross_the_month_change(monkeypatch):
    from google.api_core.exceptions import Aborted

    db = StrictFirestore()
    ref = db.collection('users').document('test-user').collection('budget_choice').document('current')
    tx = db.transaction()
    tx._max_attempts = 2
    staged = []

    def commit():
        if not staged:
            staged.append([path for path, _payload in tx.sets])
            for path, _payload in list(tx.sets):
                db.rows.pop(path, None)
            tx.sets.clear()
            tx.has_written = False
            monkeypatch.setattr(budget_choice, 'budget_period', lambda: '2026-11')
            raise Aborted('synthetic contention')

    monkeypatch.setattr(tx, '_commit', commit)
    with pytest.raises(budget_choice.BudgetChoiceConflict, match='budget_period_changed'):
        budget_choice._store(tx, ref, '2026-10', 'on_device', False)
    assert staged == [[ref.path]]
    assert not db.rows
    assert not tx.sets


def test_delayed_previous_period_cannot_overwrite_reset_choice(monkeypatch):
    monkeypatch.setattr(budget_choice, 'budget_period', lambda: '2026-11')
    db = StrictFirestore()
    budget_choice.set_choice('test-user', '2026-11', 'upgrade', False, firestore_client=db)
    with pytest.raises(budget_choice.BudgetChoiceConflict):
        budget_choice.set_choice('test-user', '2026-10', 'on_device', True, firestore_client=db)
    assert budget_choice.get_choice('test-user', '2026-11', firestore_client=db)['choice'] == 'upgrade'


@pytest.mark.parametrize(
    'record', [None, {}, {'period': '2026-10', 'choice': 'bad'}, {'period': '2026-09', 'choice': 'upgrade'}]
)
def test_missing_corrupt_and_expired_choice_does_not_suppress_prompt(record):
    assert current_choice(record, '2026-10') is None


@pytest.mark.parametrize('choice,dont_ask', [('managed', False), ('on_device', 'true')])
def test_invalid_choice_does_not_write(choice, dont_ask):
    db = StrictFirestore()
    with pytest.raises(ValueError):
        budget_choice.set_choice('test-user', '2026-10', choice, dont_ask, firestore_client=db)
    assert not db.rows


@pytest.mark.parametrize('period', ['2026-09', '2026-11'])
def test_choice_transaction_rejects_noncurrent_month_without_writing(period):
    db = StrictFirestore()
    with pytest.raises(budget_choice.BudgetChoiceConflict, match='budget_period_changed'):
        budget_choice.set_choice('test-user', period, 'upgrade', False, firestore_client=db)
    assert not db.rows
    assert all(not tx.sets for tx in db.transactions)


def test_transaction_attempt_rechecks_month_after_its_read(monkeypatch):
    db = StrictFirestore()
    ref = db.collection('users').document('test-user').collection('budget_choice').document('current')
    get = ref.get

    def read_then_rollover(*args, **kwargs):
        result = get(*args, **kwargs)
        monkeypatch.setattr(budget_choice, 'budget_period', lambda: '2026-11')
        return result

    monkeypatch.setattr(ref, 'get', read_then_rollover)
    with pytest.raises(budget_choice.BudgetChoiceConflict, match='budget_period_changed'):
        budget_choice._store(db.transaction(), ref, '2026-10', 'on_device', False)
    assert not db.rows
