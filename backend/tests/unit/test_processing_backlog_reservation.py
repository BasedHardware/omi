"""Atomic excluded-reservation refunds and real worker/store composition, no cloud IO."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from database.legal_holds import DestructiveOperationInProgress, LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION

import pytest

from database import processing_backlog as store
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils import processing_backlog_worker as worker

UID = 'synthetic-owner'
PERIOD = '2026-10'
NOW = datetime(2026, 10, 19, tzinfo=timezone.utc).timestamp()
SUMMARY = ('users', UID, 'processing_backlog', 'current')


def source_path(kind, identity='excluded', uid=UID):
    return ('users', uid, 'stt_cap_holds' if kind == 'audio' else store.COLLECTION, identity)


@pytest.fixture
def reservation(monkeypatch):
    monkeypatch.setattr(store.time, 'time', lambda: NOW)
    monkeypatch.setattr(store, '_request_memo', lambda: SimpleNamespace(forget_request_reads=lambda uid: None))

    def build(kind='audio', remaining=7):
        reserved = {'kind': kind, 'id': 'excluded', 'units': 3, 'at': 20}
        choice = {
            'state': 'processing',
            'period': PERIOD,
            'token': 'choice',
            'lease': 'owner',
            'lease_until': NOW + 1800,
            'remaining': remaining,
            'reserved': reserved,
            'cutoff': NOW,
        }
        source = (
            worker.cap_hold.hold_manifest({'metadata': 'encrypted-sync', 'name': 'excluded'}, 3, NOW - 10, 20)
            if kind == 'audio'
            else {'units': 3, 'started_at': 20, 'queued_at': NOW - 10}
        )
        client = StrictFirestore({SUMMARY: choice, source_path(kind): source})
        monkeypatch.setattr(store, 'get_firestore_client', lambda: client)

        def release(**kwargs):
            return store.release_undispatched_reservation(
                UID,
                'choice',
                'owner',
                PERIOD,
                reserved,
                audio_manifest=deepcopy(source) if kind == 'audio' else None,
                **kwargs,
            )

        return SimpleNamespace(
            client=client,
            choice=client.rows[SUMMARY],
            source=client.rows[source_path(kind)],
            proof=deepcopy(source),
            reserved=reserved,
            release=release,
        )

    return build


@pytest.mark.parametrize('kind', ['audio', 'text'])
@pytest.mark.parametrize('remaining', [7, None])
def test_transaction_refunds_only_chosen_estimate_once(reservation, kind, remaining):
    h = reservation(kind, remaining)
    before = deepcopy(h.source)
    expected = {'reserved': {}, 'remaining': None if remaining is None else 10, 'scope_skipped': True}
    assert h.release() == expected
    assert h.release() is None  # Same debit cannot be refunded twice, including after restart.
    assert h.choice['remaining'] == expected['remaining'] and h.source == before
    assert len(h.client.transactions[0].updates) == 1
    assert h.client.transactions[0].updates[0][0] == SUMMARY
    assert not any('usage' in '/'.join(path) for path in h.client.rows)


def test_refunded_exclusion_cannot_finish_choice_on_stale_local_failure(reservation):
    h = reservation()
    assert h.release() is not None
    assert not store.finish(UID, 'choice', 'owner', PERIOD)
    assert h.choice['state'] == 'processing' and h.choice['scope_skipped'] is False
    assert h.choice['cursor_audio'] is None and h.choice['cursor_text'] is None


@pytest.mark.parametrize(
    'field,value',
    [
        ('state', 'waiting_choice'),
        ('token', 'new-choice'),
        ('lease', 'other-worker'),
        ('lease', None),
        ('lease_until', NOW),
        ('period', '2026-09'),
        ('reserved', {'id': 'different'}),
        ('remaining', -1),
        ('remaining', float('nan')),
    ],
)
def test_wrong_choice_ownership_period_or_debit_retains_reservation(reservation, field, value):
    h = reservation()
    h.choice[field] = value
    before = deepcopy(h.choice)
    assert h.release() is None
    assert h.choice['reserved'] == before['reserved']
    assert not any(tx.updates for tx in h.client.transactions)


@pytest.mark.parametrize('kind', ['audio', 'text'])
def test_missing_source_or_owner_never_refunds(reservation, kind):
    h = reservation(kind)
    h.client.rows.pop(source_path(kind))
    assert h.release() is None
    assert store.release_undispatched_reservation('other-owner', 'choice', 'owner', PERIOD, h.reserved) is None
    assert h.choice['remaining'] == 7 and h.choice['reserved'] == h.reserved


@pytest.mark.parametrize(
    'updates',
    [
        {'piece_receipts': {'p': {'state': 'dispatched'}}},
        {'piece_receipts': {'p': {'state': 'dispatched', 'provider_result': 'encrypted'}}},
        {'piece_receipts': {'p': {'state': 'failed_reconciliation'}}},
        {'piece_ingests': {'p': {'state': 'transcribed'}}},
        {'processed_paths': ['p']},
        {'finalized_paths': ['p']},
        {'finalized': True},
        {'settled': True},
        {'failed_reconciliation': True},
        {'retain_audio': True},
        {'lease_until': NOW + 1, 'lease_token': 'active'},
        {'lease_until': 0, 'lease_token': 'expired-unknown'},
        {'lease_token': ''},
        {'lease_token': None},
        {'lease_token': '', 'piece_plan': {}},
        {'piece_plan': {}},
        {'piece_plan': None},
        {'piece_plan': {'piece': {'seconds': 3}}},
        {'next_attempt_at': NOW},
        {'next_attempt_at': None},
        {'state': 'completed'},
        {'state': 'staging'},
        {'state': 'sealing'},
    ],
)
def test_audio_intents_receipts_or_claim_history_retain_even_with_matching_proof(reservation, updates):
    h = reservation()
    h.source.update(updates)
    result = store.release_undispatched_reservation(
        UID, 'choice', 'owner', PERIOD, h.reserved, audio_manifest=deepcopy(h.source)
    )
    assert result is None and h.choice['remaining'] == 7 and h.choice['reserved'] == h.reserved


@pytest.mark.parametrize('field', ['lease_until', 'next_attempt_at'])
def test_legacy_audio_without_lease_proof_retains(reservation, field):
    h = reservation()
    h.source.pop(field)
    assert (
        store.release_undispatched_reservation(
            UID, 'choice', 'owner', PERIOD, h.reserved, audio_manifest=deepcopy(h.source)
        )
        is None
    )


@pytest.mark.parametrize('claim', [{'run_lease': 'expired', 'run_lease_until': 0}, {'run_lease_until': NOW + 1}])
def test_any_text_claim_history_retains(reservation, claim):
    h = reservation('text')
    h.source.update(claim)
    assert h.release() is None and h.choice['remaining'] == 7


@pytest.mark.parametrize('field', ['started_at', 'queued_at', 'units'])
def test_legacy_incomplete_text_shape_retains(reservation, field):
    h = reservation('text')
    h.source.pop(field)
    assert h.release() is None and h.choice['remaining'] == 7


@pytest.mark.parametrize('units', [None, '3', True, -1, float('nan'), float('inf')])
def test_malformed_debit_never_refunds_or_clears_reservation(reservation, units):
    h = reservation()
    h.reserved['units'] = units
    h.choice['reserved']['units'] = units
    assert h.release() is None and h.choice['remaining'] == 7 and h.choice['reserved']
    assert not any(tx.updates for tx in h.client.transactions)


def test_missing_chosen_remaining_does_not_assume_unlimited(reservation):
    h = reservation()
    h.choice.pop('remaining')
    assert h.release() is None and h.choice['reserved'] == h.reserved


def test_manifest_changed_since_decrypt_invalidates_refund(reservation):
    h = reservation()
    h.source['metadata'] = 'different-origin'
    assert h.release() is None
    h.source['metadata'] = h.proof['metadata']
    h.source['piece_receipts'] = {'p': {'state': 'dispatched'}}
    assert h.release() is None


def test_transaction_rechecks_calendar_month_not_only_callers_period(reservation, monkeypatch):
    h = reservation()
    later = datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()
    h.choice['lease_until'] = later + 1800
    monkeypatch.setattr(store.time, 'time', lambda: later)
    assert h.release() is None and h.choice['remaining'] == 7


@pytest.mark.parametrize(
    'authority,payload',
    [
        (('account_deletions', UID), {'wipe_status': 'pending'}),
        (
            ('legal_hold_deletion_gates', UID),
            {
                'schema_version': LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
                'uid': UID,
                'state': 'running',
                'kind': 'account_deletion',
                'token': 'wipe',
                'started_at': datetime.now(timezone.utc),
            },
        ),
    ],
)
def test_refund_reads_actual_privacy_fence_in_same_transaction(reservation, authority, payload):
    h = reservation()
    h.client.rows[authority] = payload
    with pytest.raises(DestructiveOperationInProgress):
        h.release()
    assert h.choice['reserved'] == h.reserved and h.choice['remaining'] == 7
    assert not any(tx.updates for tx in h.client.transactions)


@pytest.fixture
def worker_reservation(reservation, monkeypatch):
    def build(kind='audio', remaining=7):
        h = reservation(kind, remaining)
        h.choice['lease_until'] = 0
        live = worker.cap_hold.hold_manifest({'metadata': 'encrypted-live', 'name': 'live'}, 2, NOW - 10, 10)
        h.client.rows[source_path('audio', 'live')] = live
        monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
        monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
        monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:' + UID)
        monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
        monkeypatch.setattr(worker.funded_processing, 'period_id', lambda: PERIOD)
        monkeypatch.setattr(worker.funded_processing, 'allowance', lambda uid: SimpleNamespace(managed=True))
        monkeypatch.setattr(worker.funded_processing, 'capacity', lambda _: (100, 100))
        monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
        monkeypatch.setattr(store, 'read', lambda uid: deepcopy(h.client.rows[SUMMARY]))
        monkeypatch.setattr(
            worker.cap_hold, 'holds', lambda uid: h.client.collection('users').document(uid).collection('stt_cap_holds')
        )
        monkeypatch.setattr(
            worker.cap_hold,
            'metadata',
            lambda uid, row: {'origin': 'live' if row['metadata'] == 'encrypted-live' else 'sync'},
        )
        monkeypatch.setattr(worker, 'recording_units_per_hour', lambda _: 3600)
        # Integration lane 6: no open cap-hold batch reservations in these scenarios.
        monkeypatch.setattr(worker.cap_hold_reservations, 'open_units', lambda *args, **kwargs: 0.0)

        async def blocking(executor, function, *args, **kwargs):
            return function(*args, **kwargs)

        monkeypatch.setattr(worker, 'run_blocking', blocking)

        def page(uid, queue, cursor):
            h.pages.append(queue)
            result = []
            for path, row in h.client.rows.items():
                if path[:-1] != source_path(queue)[:-1] or row.get('state') == 'purged':
                    continue
                field = 'listed_at' if queue == 'audio' else 'started_at'
                if cursor and row[field] >= cursor['at']:
                    continue
                result.append((queue, SimpleNamespace(id=path[-1], to_dict=lambda row=row: deepcopy(row))))
            return result

        h.pages = []
        monkeypatch.setattr(worker, '_page', page)

        async def recover(uid, snap):
            row = snap.to_dict()
            assert row['metadata'] == 'encrypted-live', 'excluded reservation dispatched'
            h.client.rows[source_path('audio', row['name'])]['state'] = 'purged'
            return True

        h.provider = AsyncMock(side_effect=recover)
        monkeypatch.setattr(worker.cap_hold_recovery, 'recover_selected', h.provider)
        return h

    return build


@pytest.mark.parametrize('kind', ['audio', 'text'])
@pytest.mark.parametrize('remaining', [7, None])
async def test_reserved_excluded_item_refunds_then_processes_live_and_survives_restart(
    worker_reservation, kind, remaining
):
    h = worker_reservation(kind, remaining)
    await worker.run(UID, continuation=True)
    expected = None if remaining is None else 8  # 7 + refunded 3 - selected live 2.
    assert h.choice['remaining'] == expected and h.choice['reserved'] == {}
    assert h.choice['state'] == 'processing' and h.choice['cursor_audio'] is None
    assert source_path(kind) in h.client.rows and h.provider.await_count == 1
    await worker.run(UID, continuation=True)
    assert h.choice['remaining'] == expected and h.provider.await_count == 1
    assert h.choice['state'] == 'processing'  # Excluded source remains eligible for later widening.


async def test_lost_refund_response_restarts_without_double_refund_or_finishing(worker_reservation, monkeypatch):
    h = worker_reservation()
    release = store.release_undispatched_reservation

    def lost(*args, **kwargs):
        assert release(*args, **kwargs) is not None
        raise OSError('synthetic lost commit response')

    monkeypatch.setattr(store, 'release_undispatched_reservation', lost)
    await worker.run(UID, continuation=True)
    assert h.choice['remaining'] == 10 and h.choice['reserved'] == {} and h.choice['scope_skipped']
    assert not h.pages and h.choice['state'] == 'processing'
    monkeypatch.setattr(store, 'release_undispatched_reservation', release)
    await worker.run(UID, continuation=True)
    assert h.choice['remaining'] == 8 and h.provider.await_count == 1


@pytest.mark.parametrize(
    'kind,updates',
    [
        ('audio', {'piece_receipts': {'p': {'state': 'dispatched'}}}),
        ('audio', {'lease_until': NOW + 1800, 'lease_token': 'another-worker'}),
        ('audio', {'metadata': 'unknown'}),
        ('text', {'run_lease': 'expired', 'run_lease_until': 0}),
    ],
)
async def test_ambiguous_or_claimed_excluded_reservation_blocks_without_provider_or_refund(
    worker_reservation, monkeypatch, kind, updates
):
    h = worker_reservation(kind)
    h.source.update(updates)
    if updates.get('metadata') == 'unknown':
        # Unreadable provenance is covered separately; this is an explicit unknown lane.
        monkeypatch.setattr(worker.cap_hold, 'metadata', Mock(return_value={'origin': 'unknown'}))
    await worker.run(UID, continuation=True)
    assert h.choice['remaining'] == 7 and h.choice['reserved'] == h.reserved
    assert not h.pages and h.provider.await_count == 0 and h.choice['state'] == 'processing'


@pytest.mark.parametrize('failure', ['manifest', 'metadata', 'transaction'])
async def test_read_failures_preserve_reservation_and_choice(worker_reservation, monkeypatch, failure):
    h = worker_reservation()
    if failure == 'metadata':
        monkeypatch.setattr(worker.cap_hold, 'metadata', Mock(side_effect=OSError('synthetic storage error')))
    else:
        real_get = StrictFirestoreDocument.get
        calls = []

        def get(ref, transaction=None, **kwargs):
            if ref.path == source_path('audio'):
                calls.append(transaction)
                if failure == 'manifest' or transaction is not None:
                    raise OSError('synthetic hold read error')
            return real_get(ref, transaction=transaction, **kwargs)

        monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    await worker.run(UID, continuation=True)
    assert h.choice['remaining'] == 7 and h.choice['reserved'] == h.reserved
    assert not h.pages and h.provider.await_count == 0 and h.choice['state'] == 'processing'


def accepted_upgrade(h, *, remaining=50, cutoff=NOW + 20):
    return store.start(
        UID, period=PERIOD, remaining=remaining, cutoff=cutoff, request_key='synthetic-payment-upgrade', automatic=True
    )


@pytest.mark.parametrize('kind', ['audio', 'text'])
@pytest.mark.parametrize('remaining', [50, None])
def test_actual_accepted_upgrade_wins_over_scope_skip_only_after_reservation_clears(reservation, kind, remaining):
    h = reservation(kind)
    h.choice.update(scope_skipped=True, cursor_audio={'at': 20, 'id': 'excluded'})
    intent = accepted_upgrade(h, remaining=remaining)
    assert intent['token'] == 'choice' and intent['pending_upgrade']['remaining'] == remaining
    assert not store.finish(UID, 'choice', 'owner', PERIOD)  # An actual reservation still owns the debit.
    assert h.choice['reserved'] == h.reserved and h.choice['pending_upgrade']
    assert h.release() is not None
    assert store.finish(UID, 'choice', 'owner', PERIOD)
    token = h.choice['token']
    assert token != 'choice' and h.choice['state'] == 'processing'
    assert h.choice['remaining'] == remaining and h.choice['cutoff'] == NOW + 20
    assert h.choice['reserved'] == {} and h.choice['scope_skipped'] is False
    assert h.choice['cursor_audio'] is None and h.choice['cursor_text'] is None
    assert h.choice['pending_upgrade'] == {} and h.choice['lease_until'] == 0
    assert not store.checkpoint(UID, 'choice', 'owner', {'remaining': 0})
    # Replaying payment intent cannot extend this new token a second time.
    accepted_upgrade(h, remaining=1)
    assert h.choice['token'] == token and h.choice['remaining'] == remaining and not h.choice['pending_upgrade']


@pytest.mark.parametrize(
    'pending_period,calendar', [('2026-09', NOW), (PERIOD, datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())]
)
def test_scope_skip_cannot_consume_wrong_month_upgrade(reservation, monkeypatch, pending_period, calendar):
    h = reservation()
    accepted_upgrade(h)
    assert h.release() is not None
    h.choice['pending_upgrade']['period'] = pending_period
    h.choice['lease_until'] = calendar + 1800
    monkeypatch.setattr(store.time, 'time', lambda: calendar)
    assert not store.finish(UID, 'choice', 'owner', PERIOD)
    assert h.choice['token'] == 'choice' and h.choice['remaining'] == 10
    assert h.choice['state'] == 'processing' and h.choice['cursor_audio'] is None
    assert h.choice['scope_skipped'] is False and h.choice['pending_upgrade']['period'] == pending_period


def add_new_live_hold(h):
    h.client.rows[source_path('audio', 'new-live')] = worker.cap_hold.hold_manifest(
        {'metadata': 'encrypted-live', 'name': 'new-live'}, 2, NOW + 10, 30
    )


def refund_count(h):
    return sum(
        patch.get('scope_skipped') is True and patch.get('reserved') == {} and patch.get('remaining') == 10
        for tx in h.client.transactions
        for path, patch in tx.updates
        if path == SUMMARY
    )


@pytest.mark.parametrize('kind', ['audio', 'text'])
@pytest.mark.parametrize('remaining', [50, None])
async def test_worker_refunds_exclusion_consumes_actual_upgrade_and_processes_new_live(
    worker_reservation, monkeypatch, kind, remaining
):
    h = worker_reservation(kind)
    excluded = deepcopy(h.source)
    add_new_live_hold(h)
    monkeypatch.setattr(store.time, 'time', lambda: NOW + 20)
    accepted_upgrade(h, remaining=remaining)
    await worker.run(UID, continuation=True)
    token = h.choice['token']
    assert token != 'choice' and h.choice['remaining'] == remaining and h.choice['cutoff'] == NOW + 20
    assert not h.choice['pending_upgrade'] and h.choice['scope_skipped'] is False
    assert h.choice['cursor_audio'] is None and h.choice['cursor_text'] is None
    assert h.provider.await_count == 1 and refund_count(h) == 1
    assert h.client.rows[source_path('audio', 'new-live')]['state'] == 'held'  # Old cutoff excluded it.
    await worker.run(UID, continuation=True)
    expected = None if remaining is None else remaining - 2
    assert h.choice['token'] == token and h.choice['remaining'] == expected and h.choice['state'] == 'processing'
    assert h.provider.await_count == 2 and h.source == excluded
    await worker.run(UID, continuation=True)
    assert h.choice['remaining'] == expected and h.provider.await_count == 2 and refund_count(h) == 1


async def test_lost_refund_response_preserves_pending_upgrade_and_new_live_progress(worker_reservation, monkeypatch):
    h = worker_reservation()
    add_new_live_hold(h)
    monkeypatch.setattr(store.time, 'time', lambda: NOW + 20)
    accepted_upgrade(h)
    release = store.release_undispatched_reservation

    def lost(*args, **kwargs):
        assert release(*args, **kwargs) is not None
        raise OSError('synthetic lost refund response')

    monkeypatch.setattr(store, 'release_undispatched_reservation', lost)
    await worker.run(UID, continuation=True)
    assert h.choice['token'] == 'choice' and h.choice['remaining'] == 10 and h.choice['scope_skipped']
    assert h.choice['pending_upgrade']['remaining'] == 50 and not h.pages
    monkeypatch.setattr(store, 'release_undispatched_reservation', release)
    await worker.run(UID, continuation=True)
    token = h.choice['token']
    assert token != 'choice' and h.choice['remaining'] == 50 and h.provider.await_count == 1
    await worker.run(UID, continuation=True)
    assert h.choice['token'] == token and h.choice['remaining'] == 48
    assert h.provider.await_count == 2 and refund_count(h) == 1


@pytest.mark.parametrize(
    'kind,updates',
    [
        ('audio', {'piece_receipts': {'p': {'state': 'dispatched'}}}),
        ('text', {'run_lease': 'other-worker', 'run_lease_until': NOW + 1800}),
    ],
)
async def test_actual_paid_or_claimed_reservation_blocks_pending_upgrade(worker_reservation, kind, updates):
    h = worker_reservation(kind)
    accepted_upgrade(h)
    h.source.update(updates)
    await worker.run(UID, continuation=True)
    assert h.choice['token'] == 'choice' and h.choice['remaining'] == 7 and h.choice['reserved'] == h.reserved
    assert h.choice['pending_upgrade']['remaining'] == 50 and not h.pages and h.provider.await_count == 0


@pytest.mark.parametrize('planned', [False, True])
def test_real_claim_checkpoint_release_history_never_refunds(reservation, monkeypatch, planned):
    h = reservation()
    hold = worker.cap_hold
    monkeypatch.setattr(hold, 'get_firestore_client', lambda: h.client)
    monkeypatch.setattr(
        hold, 'external_write_fence', lambda uid: store.external_write_fence(uid, firestore_client=h.client)
    )
    monkeypatch.setattr(hold, 'ensure_summary', lambda uid: {})
    monkeypatch.setattr(hold, 'forget_request_reads', lambda uid: None)
    ref = h.client.collection('users').document(UID).collection('stt_cap_holds').document('excluded')
    claimed = hold.claim(UID, ref, NOW)
    assert claimed is not None
    if planned:
        assert hold.checkpoint(UID, ref, claimed['lease_token'], {'piece_plan': {}})
    hold.release(UID, ref, claimed['lease_token'])
    released = deepcopy(h.source)
    assert released['lease_token'] == '' and released['lease_until'] == 0 and released['next_attempt_at'] == NOW
    assert ('piece_plan' in released) is planned
    assert (
        store.release_undispatched_reservation(UID, 'choice', 'owner', PERIOD, h.reserved, audio_manifest=released)
        is None
    )
    assert h.choice['remaining'] == 7 and h.choice['reserved'] == h.reserved
    assert h.source == released and not h.client.transactions[-1].updates
    assert not any('usage' in '/'.join(path) for path in h.client.rows)
