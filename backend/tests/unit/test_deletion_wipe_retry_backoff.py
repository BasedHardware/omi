"""A ``failed`` account-deletion wipe backs off instead of being re-selected every tick.

``get_pending_deletion_wipes`` age-filters every status it returns except ``failed``, which its
docstring called "always actionable". A wipe that fails for a persistent reason — the missing
Cloud Tasks queue in #11680, or any dependency that is down — is therefore re-selected by every
reconciler tick on every pod, forever: one claim transaction and one error log per pod per 300s
against a record that cannot make progress, while the user who asked for deletion was told
``{"status": "ok"}``.

The delay backs off per recorded attempt and saturates. It never gives up: an accepted deletion
stays actionable, and a record that predates the counter or the timestamp stays immediately
actionable rather than becoming permanently stuck.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.users as users


def _doc(doc_id, data):
    d = MagicMock()
    d.exists = True
    d.id = doc_id
    d.to_dict.return_value = data
    return d


class _Query:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        return _Query(self._docs[:n])

    def stream(self):
        return iter(self._docs)


class _Collection:
    def __init__(self, by_status, doc_ref):
        self._by_status = by_status
        self._doc_ref = doc_ref

    def where(self, field, op, value):
        assert (field, op) == ('wipe_status', '==')
        return _Query(self._by_status.get(value, []))

    def document(self, _uid):
        return self._doc_ref


def _patch_db(monkeypatch, by_status=None, doc_ref=None):
    collection = _Collection(by_status or {}, doc_ref or MagicMock())
    fake = MagicMock()
    fake.collection.return_value = collection
    monkeypatch.setattr(users, 'db', fake)


def _failed(uid, *, minutes_ago, attempts=None):
    data = {
        'wipe_status': 'failed',
        'wipe_failed_at': datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    }
    if attempts is not None:
        data['wipe_attempts'] = attempts
    return _doc(uid, data)


def _uids(rows):
    return [row['uid'] for row in rows]


def test_backoff_doubles_per_attempt_and_saturates():
    assert users.deletion_wipe_retry_delay(1) == timedelta(0)
    assert users.deletion_wipe_retry_delay(2) == timedelta(minutes=5)
    assert users.deletion_wipe_retry_delay(3) == timedelta(minutes=10)
    assert users.deletion_wipe_retry_delay(4) == timedelta(minutes=20)
    assert users.deletion_wipe_retry_delay(50) == users.DELETION_WIPE_RETRY_MAX_DELAY


def test_first_failure_is_retried_on_the_next_tick(monkeypatch):
    # A transient error must cost nothing: one failure, no wait.
    _patch_db(monkeypatch, {'failed': [_failed('uid1', minutes_ago=0, attempts=1)]})
    assert _uids(users.get_pending_deletion_wipes()) == ['uid1']


def test_repeatedly_failing_wipe_is_not_reselected_inside_its_window(monkeypatch):
    # Three attempts -> 10 minutes; it failed one minute ago.
    _patch_db(monkeypatch, {'failed': [_failed('uid1', minutes_ago=1, attempts=3)]})
    assert users.get_pending_deletion_wipes() == []


def test_repeatedly_failing_wipe_returns_once_the_window_elapses(monkeypatch):
    _patch_db(monkeypatch, {'failed': [_failed('uid1', minutes_ago=30, attempts=3)]})
    assert _uids(users.get_pending_deletion_wipes()) == ['uid1']


def test_a_poisoned_record_never_shadows_a_ready_one(monkeypatch):
    # The old code took the first page of failed docs; a page full of backed-off
    # records must not starve one whose window has elapsed.
    _patch_db(
        monkeypatch,
        {
            'failed': [
                _failed('poisoned', minutes_ago=1, attempts=40),
                _failed('ready', minutes_ago=1, attempts=1),
            ]
        },
    )
    assert _uids(users.get_pending_deletion_wipes()) == ['ready']


def test_record_written_before_the_counter_existed_stays_actionable(monkeypatch):
    # Legacy principal: no wipe_attempts field. Counted as a first attempt, not as
    # an unknown that gets skipped.
    _patch_db(monkeypatch, {'failed': [_failed('legacy', minutes_ago=0)]})
    assert _uids(users.get_pending_deletion_wipes()) == ['legacy']


def test_record_without_a_failure_timestamp_stays_actionable(monkeypatch):
    # A missing timestamp must never be a reason to stop retrying a wipe the user
    # has already been told was accepted.
    _patch_db(monkeypatch, {'failed': [_doc('no_ts', {'wipe_status': 'failed', 'wipe_attempts': 9})]})
    assert _uids(users.get_pending_deletion_wipes()) == ['no_ts']


def test_marking_a_wipe_failed_counts_the_attempt(monkeypatch):
    doc_ref = MagicMock()
    _patch_db(monkeypatch, doc_ref=doc_ref)

    users.mark_user_deletion_wipe_failed('uid1')

    payload, kwargs = doc_ref.set.call_args[0][0], doc_ref.set.call_args[1]
    assert kwargs == {'merge': True}
    assert payload['wipe_status'] == 'failed'
    # An Increment, not a read-modify-write: two pods failing the same wipe both count.
    assert isinstance(payload['wipe_attempts'], users.firestore.Increment)
