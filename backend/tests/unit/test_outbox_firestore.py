"""FirestoreEnrichmentOutbox state machine on the in-memory row store (contract (b)).

The emulator conformance suite (lane 12, ``tests/integration/test_outbox_conformance.py``) proves Firestore
persistence; this file pins the row semantics and their compatibility with ``mark``/``run``.
"""

from unittest.mock import Mock

import pytest

from database.outbox import Claim, Outcome
from database.outbox_firestore import ENRICHMENT_OUTBOX as outbox, firestore_outbox
from database.outbox import OutboxKind
from tests.unit.test_sync_reprocess_coalesce import state, sweep_query  # noqa: F401
from utils.enrichment import custody
from utils.enrichment import outbox as reprocess

KEY = reprocess.key('u', 'c')
PAYLOAD = {'conversation_id': 'c', 'language': 'en'}


@pytest.fixture
def rows(state, monkeypatch):  # noqa: F811
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: False)
    return state


def _enqueue(available_at, *, now=0.0, **kwargs):
    return outbox.enqueue(KEY, 'u', PAYLOAD, available_at, now=now, **kwargs)


def _claim(rows, *, now=1000.0, lease=120.0):
    claimed = outbox.claim_key(KEY, rows[0][KEY]['task_token'], lease, now=now)
    assert isinstance(claimed, Claim), claimed
    return claimed


def test_enqueue_writes_a_mark_compatible_row_and_wakes_after_commit(rows):
    state_rows, tasks = rows
    result = _enqueue(600.0, policy_id='p1')
    row = state_rows[KEY]
    assert result.row_id == KEY and not result.coalesced and result.wake_token == row['task_token']
    assert row['due_at'] == 600.0 and row['policy_id'] == 'p1' and row['uid'] == 'u'
    assert tasks[-1]['task_token'] == row['task_token']  # non-transactional enqueue wakes itself
    # The same row is claimable by today's run(): row compatibility (invariant 7).
    assert reprocess.run(KEY, row['task_token'], lambda *_: None, now=601) == 'processed'
    assert KEY not in state_rows


def test_enqueue_coalesces_with_min_and_max_rules(rows):
    state_rows, _tasks = rows
    _enqueue(600.0)
    assert _enqueue(900.0, coalesce='max').coalesced
    assert state_rows[KEY]['due_at'] == 900.0 and state_rows[KEY]['version'] == 2
    assert _enqueue(300.0, coalesce='min').coalesced
    assert state_rows[KEY]['due_at'] == 300.0 and state_rows[KEY]['version'] == 3
    assert len(state_rows) == 1


def test_enqueue_rejects_a_foreign_dedupe_key(rows):
    with pytest.raises(ValueError):
        outbox.enqueue(reprocess.key('u', 'other'), 'u', PAYLOAD, 1.0, now=0.0)


def test_claim_key_fences_stale_wakes_busy_leases_and_not_due_rows(rows):
    state_rows, tasks = rows
    _enqueue(600.0)
    token = state_rows[KEY]['task_token']
    assert outbox.claim_key(KEY, 'f' * 32, 120, now=700) is Outcome.STALE
    deferred = outbox.claim_key(KEY, token, 120, now=10)
    assert deferred is Outcome.DEFERRED
    assert state_rows[KEY]['task_token'] != token and tasks[-1]['task_token'] == state_rows[KEY]['task_token']
    assert outbox.claim_key(KEY, token, 120, now=700) is Outcome.STALE  # the old wake is now stale
    claim = _claim(rows, now=700)
    assert claim.owner_id == 'u' and claim.attempt == 1 and claim.payload['conversation_id'] == 'c'
    assert outbox.claim_key(KEY, claim.wake_token, 120, now=701) is Outcome.BUSY


def test_privacy_fence_discards_before_claim(rows, monkeypatch):
    _enqueue(1.0)
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: True)
    assert outbox.claim_key(KEY, rows[0][KEY]['task_token'], 120, now=10) is Outcome.DISCARDED


def test_lease_token_fences_every_later_call(rows):
    state_rows, _tasks = rows
    _enqueue(1.0)
    first = _claim(rows, now=10, lease=120)
    assert outbox.heartbeat(first, 120, now=100)
    assert state_rows[KEY]['lease_until'] == 220
    assert not outbox.heartbeat(first, 120, now=221)  # expired leases are not renewed
    second = _claim(rows, now=300)
    assert second.lease_token != first.lease_token and second.attempt == 2
    assert not outbox.ack(first, 'processed', now=301)
    assert not outbox.release(first, 'locked', now=301)
    assert outbox.defer(first, 900, 'policy_defer', now=301) is None
    assert outbox.ack(second, 'processed', now=302)


def test_ack_retires_or_rearms_by_version(rows):
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    _enqueue(50.0, now=20)  # an append during processing bumps the version
    assert outbox.ack(claim, 'processed', now=30)
    assert state_rows[KEY]['lease_until'] == 0 and state_rows[KEY]['task_token'] != claim.wake_token
    assert tasks[-1]['task_token'] == state_rows[KEY]['task_token']
    again = _claim(rows, now=60)
    assert outbox.ack(again, 'processed', now=61)
    assert KEY not in state_rows


def test_a_wake_token_rotated_under_a_live_lease_does_not_strand_the_holder(rows):
    """M1 L09-3: a producer (mark_update / mark_effects) may rotate task_token mid-lease; invariant 1 fences
    on lease_token only, so the live holder still records its summary and settles."""
    state_rows, _tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    state_rows[KEY]['task_token'] = 'e' * 32  # mark_effects merges a new token and keeps the lease
    assert outbox.heartbeat(claim, 120, now=20)
    assert outbox.record_summary(claim)
    assert outbox.ack(claim, 'processed', now=21)
    assert state_rows[KEY]['dormant'] and state_rows[KEY]['summary_seen']


def test_release_after_a_rotation_rearms_under_a_fresh_wake(rows):
    """The queue retries the released (now stale) task, and the rotated wake may have been answered BUSY."""
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    state_rows[KEY]['task_token'] = 'e' * 32
    assert outbox.release(claim, 'dependency', now=20)
    fresh = state_rows[KEY]['task_token']
    assert fresh not in ('e' * 32, claim.wake_token) and tasks[-1]['task_token'] == fresh
    assert state_rows[KEY]['lease_until'] == 0 and state_rows[KEY]['owner'] is None


def test_release_without_a_rotation_keeps_the_wake_for_the_queue_retry(rows):
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    woken = len(tasks)
    assert outbox.release(claim, 'dependency', now=20)
    assert state_rows[KEY]['task_token'] == claim.wake_token and len(tasks) == woken


def test_record_summary_keeps_a_dormant_receipt(rows):
    state_rows, _tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    assert outbox.record_summary(claim)
    assert outbox.ack(claim, 'processed', now=11)
    receipt = state_rows[KEY]
    assert receipt['dormant'] and receipt['summary_seen'] and receipt['uid'] is None
    assert 'summary_seen_by' not in receipt


def test_defer_mints_a_new_wake_and_release_keeps_it(rows):
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    token = outbox.defer(claim, 500.0, 'open_live_target', now=11)
    assert token and token != claim.wake_token and tasks[-1]['task_token'] == token
    assert state_rows[KEY]['deferred_reason'] == 'open_live_target' and state_rows[KEY]['due_at'] == 500.0
    claim = _claim(rows, now=600)
    assert outbox.release(claim, 'locked', now=601)
    assert state_rows[KEY]['lease_until'] == 0 and state_rows[KEY]['task_token'] == claim.wake_token
    assert isinstance(outbox.claim_key(KEY, claim.wake_token, 120, now=602), Claim)  # the queue retry claims


def test_transactional_enqueue_defers_the_wake_to_the_caller(rows, monkeypatch):
    state_rows, tasks = rows
    written = {}

    class Snapshot:
        exists = False

        def to_dict(self):
            return None

    class Ref:
        def get(self, transaction):
            return Snapshot()

    class Collection:
        def document(self, _document_id):
            return Ref()

    class Client:
        def collection(self, _name):
            return Collection()

    class Transaction:
        def set(self, _ref, value):
            written['row'] = value

    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: Client())
    before = len(tasks)
    result = _enqueue(1.0, tx=Transaction())
    assert written['row']['summary_lane'] == 'batch' and result.wake_token == written['row']['task_token']
    assert len(tasks) == before  # no task before the caller commits
    state_rows[KEY] = written['row']  # the caller's commit

    class Stored:
        exists = True

        def to_dict(self):
            return dict(state_rows[KEY])

    Ref.get = lambda self, transaction=None: Stored()
    outbox.wake(KEY, result.wake_token)
    outbox.wake(KEY, 'f' * 32)  # a superseded token never wakes
    assert len(tasks) == before + 1 and tasks[-1]['task_token'] == result.wake_token


def test_sweep_discards_privacy_fenced_rows_instead_of_rewaking(rows, monkeypatch, sweep_query):  # noqa: F811
    _enqueue(1.0)
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: True)
    counts = outbox.sweep(now=10_000)
    assert counts.discarded == 1 and counts.rewoken == 0


def test_selector_serves_only_the_built_kinds():
    assert firestore_outbox(OutboxKind.ENRICHMENT) is outbox
    with pytest.raises(NotImplementedError):
        firestore_outbox(OutboxKind.CAP_HOLD_REDRIVE)  # reserved; provider_stt is lane 8's


def test_pull_claims_due_rows_by_their_stored_wake(rows, monkeypatch):
    state_rows, _tasks = rows
    _enqueue(1.0)
    monkeypatch.setattr(reprocess, 'due_rows', lambda **_: [(key, dict(row)) for key, row in state_rows.items()])
    claims = outbox.claim(5, 120, now=10)
    assert [claim.row_id for claim in claims] == [KEY]
    assert outbox.claim(5, 120, now=11) == []  # the leased row answers BUSY, not a second claim


def test_outbox_for_selects_the_firestore_enrichment_outbox():
    from database.outbox import outbox_for

    assert outbox_for(OutboxKind.ENRICHMENT) is outbox


def test_not_due_deferral_is_not_a_processing_attempt(rows):
    _enqueue(600.0)
    assert outbox.claim_key(KEY, rows[0][KEY]['task_token'], 120, now=10) is Outcome.DEFERRED
    assert not rows[0][KEY].get('claim_attempts')
    assert _claim(rows, now=700).attempt == 1


def test_conformance_factory_uses_the_injected_privacy_check_and_wake(rows, monkeypatch):
    from database.outbox_firestore import FirestoreOutbox

    # Contract (b) seams, as testing/store_fixtures.py injects them: privacy_blocked(owner_id, payload) and
    # create_wake(row_id, wake_token, available_at). The injected creator stands in for the queue binding.
    wakes, blocked = [], set()
    injected = FirestoreOutbox(
        OutboxKind.ENRICHMENT,
        privacy_blocked=lambda owner_id, payload: (owner_id, payload['conversation_id']) in blocked,
        create_wake=lambda row_id, token, at: wakes.append((row_id, token, at)),
    )
    monkeypatch.setattr(custody, 'discard_blocked', Mock(side_effect=AssertionError('default fence used')))
    result = injected.enqueue(KEY, 'u', PAYLOAD, 1.0, now=0.0)
    assert [(row_id, token) for row_id, token, _ in wakes] == [(KEY, result.wake_token)]
    blocked.add(('u', PAYLOAD['conversation_id']))
    assert injected.claim_key(KEY, result.wake_token, 120, now=10) is Outcome.DISCARDED
    assert injected.claim_key(KEY, result.wake_token, 120, now=11) is Outcome.STALE  # the row was discarded
    assert injected.claim_key('not-a-row', result.wake_token, 120, now=12) is Outcome.STALE
    with pytest.raises(NotImplementedError):
        FirestoreOutbox(OutboxKind.CAP_HOLD_REDRIVE)


def test_enqueue_snapshots_the_first_summary_policy_once(rows):
    state_rows, _tasks = rows
    _enqueue(600.0, snapshot_summary=True)
    snapshot = state_rows[KEY]['first_summary_policy']
    assert snapshot is not None and state_rows[KEY]['first_summary_policy_source'] == 'creation'
    _enqueue(900.0, snapshot_summary=True)  # a coalesced append keeps the admitted decision
    assert state_rows[KEY]['first_summary_policy'] == snapshot
    assert state_rows[KEY]['first_summary_policy_source'] == 'creation'


def test_claim_stamps_a_fallback_snapshot_on_a_batch_row_without_one(rows):
    state_rows, _tasks = rows
    _enqueue(1.0)
    state_rows[KEY]['summary_lane'] = 'batch'
    state_rows[KEY].pop('first_summary_policy', None)
    claim = _claim(rows, now=10)
    assert state_rows[KEY]['first_summary_policy_source'] == 'fallback'
    assert claim.payload['first_summary_policy'] == state_rows[KEY]['first_summary_policy']
