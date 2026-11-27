"""Forced first-week attempt at close (SCA-4806): Option A discriminator.

Hermetic: no Firestore, no task client, no LLM. The fake models document reads
with a field mask plus transaction set, the two operations this path uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import summary_guarantee as guarantee  # noqa: E402
from database import first_week_queries  # noqa: E402
from services import first_week_forced_close as forced  # noqa: E402
from utils.enrichment import outbox  # noqa: E402

PAID = 1_790_000_000
HOUR = 3600
WINDOW_END = PAID + 7 * 24 * HOUR


class Snapshot:
    def __init__(self, data: dict | None, reference=None):
        self._data = dict(data or {})
        self.exists = data is not None
        self.reference = reference

    def to_dict(self) -> dict:
        return dict(self._data)


class Ref:
    def __init__(self, client, path: str, data: dict | None = None):
        self.client = client
        self.path = path
        self.data = dict(data or {})
        self.reads = 0

    def collection(self, name: str):
        return Collection(self.client, f'{self.path}/{name}')

    def get(self, transaction=None, *, field_paths=None):
        self.reads += 1
        data = self.client.rows.get(self.path)
        if data is None:
            return Snapshot(None, self)
        if field_paths is not None:
            data = {field: data[field] for field in field_paths if field in data}
        return Snapshot(data, self)


class Transaction:
    def __init__(self, client):
        self.client = client
        self.writes: list[tuple[str, dict]] = []

    def set(self, ref, data, merge=False):
        self.writes.append((ref.path, dict(data)))
        ref.data.update(data)


class Collection:
    def __init__(self, client, path: str):
        self.client = client
        self.path = path

    def document(self, doc_id: str):
        return Ref(self.client, f'{self.path}/{doc_id}')


class Client:
    def __init__(self, rows: dict[str, dict] | None = None):
        self.rows = {path: dict(data) for path, data in (rows or {}).items()}
        self.transaction_writes: list[str] = []

    def collection(self, path: str):
        return Collection(self, path)

    def transaction(self):
        return Transaction(self)


@pytest.fixture(autouse=True)
def lane_env(monkeypatch):
    for name in (
        guarantee.FIRST_WEEK_ENABLED_ENV,
        guarantee.FIRST_WEEK_WINDOW_ENV,
        guarantee.FIRST_WEEK_FORCED_CLOSE_ENV,
        guarantee.FIRST_WEEK_CLOSE_RESERVE_ENV,
        guarantee.FIRST_WEEK_FORCED_LIMIT_ENV,
        'ENRICHMENT_ROUTE',
        'ENRICHMENT_TASKS_QUEUE',
        'ENRICHMENT_FIRST_WEEK_TASKS_QUEUE',
        'ENRICHMENT_TASKS_HANDLER_URL',
        'ENRICHMENT_TASKS_OIDC_AUDIENCE',
        'ENRICHMENT_TASKS_INVOKER_SA',
        'ENRICHMENT_MAX_AGE_HOURS',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE', 'enrichment-first-week')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://worker.example/v2/enrichment/run')
    monkeypatch.setenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', 'https://worker.example/v2/enrichment/run')
    monkeypatch.setenv('ENRICHMENT_TASKS_INVOKER_SA', 'worker@example.iam.gserviceaccount.com')
    monkeypatch.setattr(forced.firestore, 'transactional', lambda fn: fn)


CONVERSATION_PATH = 'users/uid/conversations/cid'


def _stamp(*, end: int = WINDOW_END) -> dict:
    return {
        'policy_id': guarantee.FIRST_WEEK_POLICY_ID,
        'paid_since': PAID,
        'window_end_at': end,
        'interval': 'monthly',
    }


def _conversation(**extra) -> dict:
    return {
        'status': 'completed',
        'data_protection_level': 'standard',
        'first_week_summary': _stamp(),
        'first_week_outcome': None,
        'processing_deferred': True,
        'terminal_no_derived_effects': True,
        **extra,
    }


def _parked_row(**extra) -> dict:
    row = {
        'uid': 'uid',
        'conversation_id': 'cid',
        'document_id': outbox.key('uid', 'cid'),
        'dormant': True,
        'age_gate_parked': True,
        'deferred_reason': 'age_gate_72h',
        'deferred_since': PAID + HOUR,
        'lease_until': 0,
        'task_token': 'token',
        'due_at': None,
        'dispatch': {
            'queue': 'enrichment',
            'handler': 'https://worker.example/v2/enrichment/run',
            'audience': 'https://worker.example/v2/enrichment/run',
            'invoker_sa': 'worker@example.iam.gserviceaccount.com',
        },
    }
    row.update(extra)
    return row


def _open_row(**extra) -> dict:
    row = _parked_row(dormant=False, age_gate_parked=False, deferred_reason=None)
    row.update(extra)
    return row


def _store(conversation: dict | None, row: dict | None):
    rows = {CONVERSATION_PATH: conversation if conversation is not None else None}
    if row is not None:
        rows[f'{outbox.COLLECTION}/{outbox.key("uid", "cid")}'] = row
    return Client({path: data for path, data in rows.items() if data is not None})


def _force(client, wakes=None, now=WINDOW_END - 2 * HOUR):
    ref = client.collection('users').document('uid').collection('conversations').document('cid')
    sent = wakes if wakes is not None else []

    def wake(row):
        sent.append(dict(row))

    disposition, pending = forced.force_one(ref, now=now, client=client, wake=wake)
    return disposition, pending, sent


# --- the forceable classes -------------------------------------------------


def test_forces_a_budget_row_parked_at_the_age_gate():
    client = _store(_conversation(), _parked_row())
    disposition, pending, sent = _force(client)
    assert disposition == 'forced'
    assert pending['age_gate_parked'] is False
    assert pending['deferred_reason'] is None
    assert pending['dormant'] is False
    assert pending['due_at'] == WINDOW_END - 2 * HOUR
    assert pending['dispatch']['queue'] == 'enrichment-first-week'
    assert pending['first_week_forced_policy'] == forced.FORCED_POLICY_ID
    assert pending['first_week_forced_at'] == WINDOW_END - 2 * HOUR
    assert sent and sent[0]['task_token'] == pending['task_token']
    assert pending['task_token'] != 'token'


def test_forces_an_open_row_only_when_the_budget_refusal_is_stored():
    """Post-PR1 a budget row is not age-gate parked; the budget marker is what admits it."""
    client = _store(_conversation(), _open_row())
    disposition, pending, _sent = _force(client)
    assert disposition == 'forced'
    assert pending['dispatch']['queue'] == 'enrichment-first-week'


def test_an_open_row_without_a_budget_refusal_is_the_late_class_and_is_never_forced():
    conversation = _conversation(processing_deferred=False, terminal_no_derived_effects=False)
    client = _store(conversation, _open_row())
    disposition, pending, sent = _force(client)
    assert disposition == 'row_open'
    assert pending is None and sent == []


def test_a_leased_row_is_in_flight_and_is_never_touched():
    client = _store(_conversation(), _parked_row(lease_until=WINDOW_END))
    disposition, pending, sent = _force(client)
    assert disposition == 'leased'
    assert pending is None and sent == []


def test_a_row_already_forced_is_not_forced_again():
    client = _store(_conversation(), _parked_row(first_week_forced_at=PAID + HOUR))
    assert _force(client)[0] == 'already_forced'


def test_no_obligation_row_is_out_of_scope():
    client = _store(_conversation(), None)
    assert _force(client)[0] == 'no_obligation_row'


def test_a_custody_hold_is_not_a_capacity_park():
    row = _parked_row(age_gate_parked=False, deferred_reason='merge_blocked')
    client = _store(_conversation(), row)
    assert _force(client)[0] == 'custody_hold'


# --- the never-force classes ----------------------------------------------


@pytest.mark.parametrize(
    'change, reason',
    (
        ({'data_protection_level': 'private'}, 'privacy'),
        ({'processing_state': 'local_pending'}, 'local_only'),
        ({'client_processing': {'state': 'ready'}}, 'local_only'),
        ({'deleted': True}, 'lifecycle'),
        ({'discarded': True}, 'lifecycle'),
        ({'status': 'failed'}, 'lifecycle'),
        ({'user_title': 'mine'}, 'manual'),
        ({'summary_blocked_reason': 'empty_output_exhausted'}, 'attempt_failed'),
        ({'summary_empty_failures': 2}, 'attempt_failed'),
        ({'summary_blocked_reason': 'content_below_floor'}, 'content_below_floor'),
        ({'finalization_engine': 'go', 'finalization_owner_epoch': 2}, 'generation_owned'),
        ({'summary_output_present': True}, 'already_summarized'),
        ({'deferred': True}, 'deferred_out_of_scope'),
    ),
)
def test_never_force_classes(change, reason):
    client = _store(_conversation(**change), _parked_row())
    assert _force(client)[0] == reason


def test_a_closed_window_or_counted_outcome_is_not_forced():
    closed = _conversation(**{'first_week_summary': _stamp(end=PAID)})
    assert _force(_store(closed, _parked_row()), now=PAID + HOUR)[0] == 'window_closed'
    counted = _conversation(first_week_outcome='no_attempt')
    assert _force(_store(counted, _parked_row()))[0] == 'already_closed'


def test_an_unbound_dispatch_is_skipped_rather_than_woken(monkeypatch):
    monkeypatch.delenv('ENRICHMENT_TASKS_HANDLER_URL', raising=False)
    client = _store(_conversation(), _parked_row(dispatch=None))
    disposition, pending, sent = _force(client)
    assert disposition == 'unbound'
    assert pending is None and sent == []


def test_a_wake_failure_leaves_durable_due_debt():
    client = _store(_conversation(), _parked_row())

    def wake(_row):
        raise RuntimeError('tasks unavailable')

    ref = client.collection('users').document('uid').collection('conversations').document('cid')
    disposition, pending = forced.force_one(ref, now=WINDOW_END - HOUR, client=client, wake=wake)
    assert disposition == 'wake_error'
    assert pending['due_at'] == WINDOW_END - HOUR
    assert pending['dormant'] is False


# --- the phase -------------------------------------------------------------


class PageSnapshot:
    def __init__(self, reference):
        self.reference = reference


def _page(client, count):
    refs = []
    for index in range(count):
        path = f'users/uid/conversations/cid{index}'
        client.rows[path] = _conversation()
        client.rows[f'{outbox.COLLECTION}/{outbox.key("uid", f"cid{index}")}'] = _parked_row(
            conversation_id=f'cid{index}'
        )
        refs.append(PageSnapshot(Ref(client, path)))
    return refs


def test_the_flag_ships_off_and_skips_the_query(monkeypatch):
    called = []
    monkeypatch.setattr(
        first_week_queries, 'approaching_first_week_conversations', lambda **_kwargs: called.append(True) or []
    )
    counts = forced.tick(now=PAID, client=Client())
    assert counts['disabled'] == 1
    assert called == []


def test_zero_reserve_disables_the_phase(monkeypatch):
    monkeypatch.setenv(guarantee.FIRST_WEEK_FORCED_CLOSE_ENV, 'true')
    monkeypatch.setenv(guarantee.FIRST_WEEK_CLOSE_RESERVE_ENV, '0')
    counts = forced.tick(now=PAID, client=Client())
    assert counts['disabled'] == 1


def test_tick_admits_at_most_the_per_tick_limit(monkeypatch):
    monkeypatch.setenv(guarantee.FIRST_WEEK_FORCED_CLOSE_ENV, 'true')
    monkeypatch.setenv(guarantee.FIRST_WEEK_FORCED_LIMIT_ENV, '4')
    client = Client()
    page = _page(client, 10)
    monkeypatch.setattr(first_week_queries, 'approaching_first_week_conversations', lambda **_kwargs: page)
    sent = []
    counts = forced.tick(now=WINDOW_END - HOUR, client=client, wake=sent.append)
    assert counts['forced'] == 4
    assert counts['skipped'] == 0
    assert len(sent) == 4


def test_a_query_error_fails_only_this_phase(monkeypatch):
    monkeypatch.setenv(guarantee.FIRST_WEEK_FORCED_CLOSE_ENV, 'true')

    def broken(**_kwargs):
        raise RuntimeError('index missing')

    monkeypatch.setattr(first_week_queries, 'approaching_first_week_conversations', broken)
    counts = forced.tick(now=PAID, client=Client())
    assert counts == {'examined': 0, 'forced': 0, 'skipped': 0, 'errors': 1, 'disabled': 0}


def test_tick_skips_a_row_that_is_already_in_a_lane(monkeypatch):
    monkeypatch.setenv(guarantee.FIRST_WEEK_FORCED_CLOSE_ENV, 'true')
    client = Client()
    path = 'users/uid/conversations/cid0'
    client.rows[path] = _conversation(processing_deferred=False, terminal_no_derived_effects=False)
    client.rows[f'{outbox.COLLECTION}/{outbox.key("uid", "cid0")}'] = _open_row(conversation_id='cid0')
    page = [PageSnapshot(Ref(client, path))]
    monkeypatch.setattr(first_week_queries, 'approaching_first_week_conversations', lambda **_kwargs: page)
    counts = forced.tick(now=WINDOW_END - HOUR, client=client, wake=lambda _row: None)
    assert counts['forced'] == 0
    assert counts['skipped'] == 1
