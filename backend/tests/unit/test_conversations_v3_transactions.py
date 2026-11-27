"""Strict read-before-write contracts using synthetic document boundaries."""

from database import conversations_v3_leases as leases
from database.firestore_transaction_retry import FirestoreContentionExhausted

from database import conversations_v3_processing as writers

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import importlib
from unittest.mock import AsyncMock, Mock

import pytest
from google.api_core.exceptions import Aborted
from google.cloud import firestore


from config.record_wal_duplicate import (
    MERGE_PLAN_FIELD,
    MERGE_TARGET_FIELD,
    RETAINED_DONORS_FIELD,
    SETTLED_FIELD,
    has_retained_custody,
)
from database import batch_pipeline_purge, conversation_batch_purge_jobs as purge_jobs, legal_holds
from database import conversations_v3 as store
from database.account_deletion_marker import ACCOUNT_DELETION_COLLECTION
from utils import cloud_tasks
from utils.other import storage
from utils.conversations.v3 import bind_request_log_trace, metrics, service, summary
from utils.conversations import (
    lifecycle,
)  # noqa: F401 -- the commit path's import graph is paid at collection, not in a test's CPU budget
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot

AT = datetime.now(timezone.utc)
R = ('users', 'synthetic', 'conversations', 'r')
# Captured before any test patches it: the hold-race test runs the real canonical helper.
REAL_DELETE_PRIVACY_AUDIO = storage.delete_privacy_conversation_audio
L = ('users', 'synthetic', 'conversation_v3_leases', 'builder')


@pytest.fixture(scope='module', autouse=True)
def lifecycle_owner_import():
    # Exercise real lifecycle transactions below, but load their owner during
    # file setup, as the call-phase CPU guard requires for shared imports.
    return importlib.import_module('utils.conversations.lifecycle')


@pytest.fixture
def strict(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)

    def transactional(body):
        def run(tx, *args, **kwargs):
            with client.lock:
                return body(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda s: (s.to_dict() or {}).get('_test_revision', 1)),
        raising=False,
    )
    monkeypatch.setattr(store, 'encrypt', lambda value, uid: value)
    monkeypatch.setattr(store.conversations, '_prepare_conversation_for_write', lambda row, *a, **kw: deepcopy(row))
    return client


@pytest.fixture(scope='module', autouse=True)
def speaker_evidence_import():
    # Hydration's real lazy dependency is setup work; import failures still
    # fail this suite and its cost stays inside the whole-file wall limit.
    return importlib.import_module('utils.speakers.evidence')


def test_two_workers_get_one_lease(strict):
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: leases.acquire('synthetic', 'builder', firestore_client=strict), range(2)))
    assert sum(token is not None for token in tokens) == 1


def test_expired_worker_cannot_release_successor(strict):
    old = leases.acquire('synthetic', 'builder', now=AT - timedelta(hours=1), firestore_client=strict)
    new = leases.acquire('synthetic', 'builder', now=AT, firestore_client=strict)
    leases.release('synthetic', 'builder', old, firestore_client=strict)
    assert strict.rows[L]['token'] == new


@pytest.mark.parametrize('mode', ['default', 'off'])
@pytest.mark.parametrize('wipe_status', [None, 'cancelled', 'billing_failed', 'pending'])
def test_atomic_projection_and_claim(strict, monkeypatch, mode, wipe_status):
    monkeypatch.delenv('CONVERSATIONS_V3_BATCH_COMMIT_READS', raising=False)
    if mode == 'off':
        monkeypatch.setenv('CONVERSATIONS_V3_BATCH_COMMIT_READS', 'off')
    batch_get = Mock(wraps=strict.get_all)
    monkeypatch.setattr(strict, 'get_all', batch_get)
    recording = {'recording': True, 'v3_pending': True}
    strict.rows[R] = recording.copy()
    if wipe_status is not None:
        strict.rows[(ACCOUNT_DELETION_COLLECTION, 'synthetic')] = {'wipe_status': wipe_status}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    source = {'id': 'r', 'recording': True, '_v3_revision': 1}
    row = {
        'id': 'c',
        'status': 'processing',
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': ['r'],
        'transcript_segments': [],
        'structured': {},
    }
    card = R[:-1] + ('c',)
    if wipe_status == 'pending':
        with pytest.raises(store.Conflict, match='^account_deletion$'):
            store.commit_projection('synthetic', token, {'r': source}, {}, [row], [], firestore_client=strict)
        assert strict.rows[R] == recording
        assert card not in strict.rows
        return

    store.commit_projection('synthetic', token, {'r': source}, {}, [row], [], firestore_client=strict)
    if mode == 'default':
        assert batch_get.call_count == 3  # inputs, tombstone, and new target
        assert all(call.kwargs['transaction'] is strict.transactions[-1] for call in batch_get.call_args_list)
    else:
        batch_get.assert_not_called()
    assert strict.rows[R]['v3_pending'] is False
    assert strict.rows[R]['claims'] == [{'conversation_id': 'c', 'start': AT, 'end': AT}]
    assert strict.rows[card]['id'] == 'c'


@pytest.mark.parametrize('missing', [False, True])
def test_projection_reads_unordered_chunks_and_prefers_existing_row(strict, monkeypatch, missing):
    monkeypatch.delenv('CONVERSATIONS_V3_BATCH_COMMIT_READS', raising=False)
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    existing = {'r': {'_v3_revision': 1}}
    for index in range(100):
        cid = f'c{index}'
        existing[cid] = {'_v3_revision': 1}
        if not (missing and index == 99):
            strict.rows[(*R[:-1], cid)] = {'_test_revision': 1}
    batch_get = Mock(wraps=strict.get_all)
    monkeypatch.setattr(strict, 'get_all', batch_get)

    def commit():
        return store.commit_projection(
            'synthetic', token, {'r': {'_v3_revision': 2}}, existing, [], [], firestore_client=strict
        )

    if missing:
        with pytest.raises(store.Conflict, match='source_changed'):
            commit()
    else:
        assert commit() == set()
    assert strict.rows[R]['v3_pending'] is missing
    assert [len(call.args[0]) for call in batch_get.call_args_list] == [100, 1]
    assert all(call.kwargs['transaction'] is strict.transactions[-1] for call in batch_get.call_args_list)


def test_projection_defers_full_row_replacement_of_settled_wal(strict):
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'status': 'completed', 'started_at': AT, 'finished_at': AT, 'v3_recording_ids': []}
    strict.rows[path] = {**row, SETTLED_FIELD: True}
    existing = {**strict.rows[path], '_v3_revision': 1}
    before = deepcopy(strict.rows)
    with pytest.raises(store.Conflict, match='source_changed'):
        store.commit_projection('synthetic', token, {}, {'c': existing}, [row], [], firestore_client=strict)
    assert strict.rows == before


def test_new_speech_preserves_pending_on_conflict(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True, '_test_revision': 2}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    with pytest.raises(store.Conflict, match='source_changed'):
        store.commit_projection('synthetic', token, {'r': {'_v3_revision': 1}}, {}, [], [], firestore_client=strict)
    assert strict.rows[R]['v3_pending'] is True


@pytest.mark.parametrize('claims,left', [(0, 0), (1, 0), (2, 1)])
def test_delete_claims_zero_one_two(strict, claims, left):
    row = {
        'id': 'c',
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=1),
    }
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c')] = {'conversation_id': 'c'}
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [
            {'conversation_id': cid, 'start': AT + timedelta(minutes=i * 2), 'end': AT + timedelta(minutes=i * 2 + 1)}
            for i, cid in enumerate(['c', 'neighbour'][:claims])
        ],
    }
    store.release_claims('synthetic', row, firestore_client=strict)
    assert len(strict.rows[R]['claims']) == left
    assert strict.rows[R]['v3_audio_purge_pending'] is (left == 0)
    store.release_claims('synthetic', row, firestore_client=strict)
    assert len(strict.rows[R]['deleted_spans']) == 1


def test_pending_recording_audio_is_retained(strict):
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'v3_pending': True,
        'claims': [],
        'v3_audio_purge_pending': True,
    }
    assert not store.claim_audio_purge('synthetic', 'r', firestore_client=strict)
    assert not strict.rows[R].get('deleted')


def test_purge_closes_recording_owner_before_storage_delete(strict):
    strict.rows[R] = {'recording': True, 'status': 'completed', 'claims': [], 'v3_audio_purge_pending': True}
    assert store.claim_audio_purge('synthetic', 'r', firestore_client=strict)
    assert strict.rows[R]['deleted'] is True
    assert ('users', 'synthetic', 'deleted_conversations', 'r') in strict.rows


def test_delete_subtracts_surviving_claim_from_merged_window(strict):
    row = {
        'id': 'c',
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=3),
    }
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c')] = {'conversation_id': 'c'}
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [
            {'conversation_id': 'c', 'start': AT, 'end': AT + timedelta(minutes=3)},
            {'conversation_id': 'neighbour', 'start': AT + timedelta(minutes=1), 'end': AT + timedelta(minutes=2)},
        ],
    }
    store.release_claims('synthetic', row, firestore_client=strict)
    assert [(s['start'], s['end']) for s in strict.rows[R]['deleted_spans']] == [
        (AT, AT + timedelta(minutes=1)),
        (AT + timedelta(minutes=2), AT + timedelta(minutes=3)),
    ]
    assert strict.rows[R]['v3_audio_purge_pending'] is False


def test_merge_claim_transfer_is_idempotent_and_preserves_gaps(strict):
    sources = [{'id': 'a', 'v3_recording_ids': ['r']}, {'id': 'c', 'v3_recording_ids': ['r']}]
    target = {'id': 'merged', 'started_at': AT, 'finished_at': AT + timedelta(minutes=3)}
    strict.rows[('users', 'synthetic', 'conversations', 'merged')] = target
    strict.rows[R] = {
        'recording': True,
        'claims': [
            {'conversation_id': cid, 'start': AT + timedelta(minutes=i), 'end': AT + timedelta(minutes=i + 1)}
            for i, cid in enumerate(['a', 'neighbour', 'c'])
        ],
    }
    store.transfer_claims('synthetic', sources, target, firestore_client=strict)
    claims = strict.rows[R]['claims']
    assert [c['conversation_id'] for c in claims].count('merged') == 2
    assert [c['conversation_id'] for c in claims].count('neighbour') == 1
    store.transfer_claims('synthetic', sources, target, firestore_client=strict)
    assert strict.rows[R]['claims'] == claims


@pytest.mark.asyncio
async def test_two_concurrent_reconciles_publish_one_copy(strict, monkeypatch):
    import asyncio
    import json
    from utils.conversations.v3 import service

    start = AT - timedelta(hours=1)
    strict.rows[R] = {
        'id': 'r',
        'recording': True,
        'v3_pending': True,
        'status': 'completed',
        'source': 'omi',
        'started_at': start,
        'finished_at': start + timedelta(seconds=20),
        'data_protection_level': 'standard',
        'transcript_segments': [{'text': 'Synthetic planning speech', 'start': 0, 'end': 20, 'is_user': True}],
    }
    source = {**deepcopy(strict.rows[R]), '_v3_revision': 1}
    entered, resume = asyncio.Event(), asyncio.Event()
    original_load = store.load
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.clear_terminal_pending:
            return None
        if fn is original_load:
            entered.set()
            await resume.wait()
            return {'r': source}, {}, []
        return fn(*args, **kwargs)

    async def no_processing(uid):
        return None

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', no_processing)
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    calls = []

    def outline(uid, messages):
        calls.append(uid)
        return json.dumps(
            {
                'conversations': [
                    {
                        'first_line': 1,
                        'kind': 'conversation',
                        'title': 'Planning',
                        'line': 'You planned a visit.',
                        'emoji': '🌳',
                        'people': [],
                        'sections': [],
                    }
                ]
            }
        )

    monkeypatch.setattr(service.models, 'outline', outline)
    first = asyncio.create_task(service.reconcile('synthetic'))
    await entered.wait()
    assert await service.reconcile('synthetic') == 'busy'
    resume.set()
    assert await first == 'committed'
    copies = [r for path, r in strict.rows.items() if path[2] == 'conversations' and r.get('v3_derived')]
    assert len(copies) == 1 and len(strict.rows[R]['claims']) == 1
    assert calls == ['synthetic']


def test_delete_during_capture_rearms_purge_at_settlement(strict, monkeypatch):
    row = {'id': 'c', 'v3_derived': True, 'v3_recording_ids': ['r'], 'started_at': AT, 'finished_at': AT}
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c')] = {'conversation_id': 'c'}
    strict.rows[R] = {
        'id': 'r',
        'recording': True,
        'status': 'in_progress',
        'v3_pending': True,
        'claims': [{'conversation_id': 'c', 'start': AT, 'end': AT}],
    }
    store.release_claims('synthetic', row, firestore_client=strict)
    assert strict.rows[R]['v3_audio_purge_pending'] is False
    strict.rows[R]['status'] = 'completed'
    source = {**strict.rows[R], '_v3_revision': 1}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection('synthetic', token, {'r': source}, {}, [], [], firestore_client=strict)
    assert strict.rows[R]['v3_audio_purge_pending'] is True
    erased = []
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(legal_holds, 'account_deletion_firestore_client', lambda firestore_client=None: strict)
    monkeypatch.setattr(storage, 'delete_privacy_conversation_audio', lambda *a: erased.append(a))
    monkeypatch.setattr(
        service.conversations_db, 'update_conversation', lambda uid, cid, patch: strict.rows[R].update(patch)
    )
    service.purge_audio('synthetic', 'r')
    assert erased == [('synthetic', 'r')]
    assert strict.rows[R]['v3_audio_erased'] is True
    assert strict.rows[R]['v3_audio_purge_pending'] is False


CUSTODY = {
    SETTLED_FIELD: True,
    RETAINED_DONORS_FIELD: ['donor'],
    MERGE_TARGET_FIELD: 'successor',
    MERGE_PLAN_FIELD: {'r': {'keep': True, 'inherited': []}},
}
OBLIGATION = ('conversation_batch_purge_jobs', purge_jobs.job_id('synthetic', 'r'))


def _live(row):
    return {k: v for k, v in row.items() if v is not firestore.DELETE_FIELD}


def test_custody_clear_deletes_exactly_the_present_custody_fields():
    everything = {field: 'x' for field in store.AUDIO_PURGE_CUSTODY_FIELDS} | {'status': 'completed', 'other': 1}
    assert store._custody_clear(everything) == dict.fromkeys(store.AUDIO_PURGE_CUSTODY_FIELDS, firestore.DELETE_FIELD)
    assert store._custody_clear({MERGE_TARGET_FIELD: 'successor', 'status': 'completed'}) == {
        MERGE_TARGET_FIELD: firestore.DELETE_FIELD
    }
    assert store._custody_clear({'status': 'completed'}) == {}


def _purge_count(outcome):
    return metrics.AUDIO_PURGES.labels(outcome)._value.get()


def _row(cid):
    return ('users', 'synthetic', 'conversations', cid)


def _tombstone(cid):
    return ('users', 'synthetic', 'deleted_conversations', cid)


def _assert_audio_gate_held(uid):
    # Every blob deletion runs inside the sweep's one audio-deletion gate.
    legal_holds.current_destructive_operation_token(uid, kind=service.AUDIO_GATE_KIND)


@pytest.fixture
def purge_world(strict, monkeypatch):
    """The sweep's purge with storage and the batch-intake purge recorded in call order.

    The legal-hold preflight and the account gate are the real ones, on the strict client.
    """
    calls = []
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(legal_holds, 'account_deletion_firestore_client', lambda firestore_client=None: strict)
    monkeypatch.setattr(cloud_tasks, 'is_conversation_batch_purge_dispatch_configured', lambda: False)

    def erase(uid, cid, **kw):
        _assert_audio_gate_held(uid)
        calls.append(('erase', cid, kw))

    def prefixes(uid, cid):
        _assert_audio_gate_held(uid)
        calls.append(('prefixes', cid))

    monkeypatch.setattr(storage, 'delete_privacy_conversation_audio', erase)
    monkeypatch.setattr(storage, 'delete_conversation_audio_files', prefixes)

    def purge_batch_owner(uid, **kw):
        # The batch purge's own precondition: the owner's deletion intent exists.
        assert _tombstone(kw['conversation_id']) in strict.rows
        calls.append(('intakes', kw['conversation_id']))

    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge_batch_owner)
    monkeypatch.setattr(
        service.conversations_db, 'update_conversation', lambda uid, cid, patch: strict.rows[_row(cid)].update(patch)
    )
    return calls


@pytest.mark.parametrize('field', list(CUSTODY))
def test_purge_invalidates_custody_and_erases_intakes_before_audio(strict, purge_world, field):
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [],
        'v3_audio_purge_pending': True,
        field: CUSTODY[field],
    }
    before = _purge_count('custody_invalidated')
    service.purge_audio('synthetic', 'r')
    row = _live(strict.rows[R])
    assert field not in row and not has_retained_custody(row)
    assert row['deleted'] is True and row['v3_audio_erased'] is True and row['v3_audio_purge_pending'] is False
    if field == RETAINED_DONORS_FIELD:
        assert purge_world == [
            ('intakes', 'r'),
            ('intakes', 'donor'),
            ('erase', 'r', {'source_ids': ['donor']}),
            ('prefixes', 'donor'),
        ]
        assert row[store.AUDIO_PURGE_DONORS_FIELD] == []
    else:
        assert purge_world == [('intakes', 'r'), ('erase', 'r', {})]
    assert _purge_count('custody_invalidated') == before + 1
    # The intake purge reads the tombstone the claim wrote with the custody clear.
    assert ('users', 'synthetic', 'deleted_conversations', 'r') in strict.rows


def test_purge_without_custody_is_unchanged(strict, purge_world):
    strict.rows[R] = {'recording': True, 'status': 'completed', 'claims': [], 'v3_audio_purge_pending': True}
    before = _purge_count('custody_invalidated')
    claim = store.claim_audio_purge('synthetic', 'r', firestore_client=strict)
    assert claim == store.AudioPurgeClaim()
    # No obligation read and no marker: the claim's reads and writes are as before.
    assert strict.rows[R] == {
        'recording': True,
        'status': 'completed',
        'claims': [],
        'v3_audio_purge_pending': True,
        'deleted': True,
        'v3_audio_erased': True,
    }
    service.purge_audio('synthetic', 'r')
    assert purge_world == [('erase', 'r', {})]
    assert OBLIGATION not in strict.rows
    assert _purge_count('custody_invalidated') == before


def test_intake_purge_failure_keeps_audio_and_retries_the_purge(strict, purge_world, monkeypatch):
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [],
        'v3_audio_purge_pending': True,
        SETTLED_FIELD: True,
    }

    def unavailable(uid, **kw):
        purge_world.append(('intakes_failed', kw['conversation_id']))
        raise RuntimeError('synthetic data plane outage')

    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', unavailable)
    with pytest.raises(RuntimeError):
        service.purge_audio('synthetic', 'r')
    assert purge_world == [('intakes_failed', 'r')]
    row = _live(strict.rows[R])
    assert row['v3_audio_purge_pending'] is True and SETTLED_FIELD not in row
    # Custody is already gone, so the durable marker is what keeps the intakes owed on retry.
    assert row[store.AUDIO_PURGE_INTAKES_FIELD] == 'inline'
    monkeypatch.setattr(
        batch_pipeline_purge, 'purge_batch_owner', lambda uid, **kw: purge_world.append(('intakes', 'r'))
    )
    service.purge_audio('synthetic', 'r')
    assert purge_world == [('intakes_failed', 'r'), ('intakes', 'r'), ('erase', 'r', {})]
    assert strict.rows[R]['v3_audio_purge_pending'] is False


def test_sweep_retries_a_failed_intake_purge_without_erasing(strict, purge_world, monkeypatch):
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [],
        'v3_audio_purge_pending': True,
        MERGE_TARGET_FIELD: 'successor',
    }
    monkeypatch.setattr(
        batch_pipeline_purge, 'purge_batch_owner', Mock(side_effect=RuntimeError('synthetic data plane outage'))
    )
    before = _purge_count('intakes_failed')
    with pytest.raises(RuntimeError):
        service.purge_audio('synthetic', 'r')
    assert _purge_count('intakes_failed') == before + 1
    assert not [call for call in purge_world if call[0] == 'erase']


def test_dispatched_intake_purge_waits_for_its_obligation(strict, purge_world, monkeypatch):
    monkeypatch.setattr(cloud_tasks, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [],
        'v3_audio_purge_pending': True,
        RETAINED_DONORS_FIELD: ['donor'],
    }
    with pytest.raises(service.AudioPurgeIntakesPending):
        service.purge_audio('synthetic', 'r')
    # Obligation, tombstone and custody clear are one commit; the blobs wait.
    assert strict.rows[OBLIGATION]['conversation_id'] == 'r'
    assert _live(strict.rows[R])[store.AUDIO_PURGE_INTAKES_FIELD] == 'armed'
    assert purge_world == []
    with pytest.raises(service.AudioPurgeIntakesPending):
        service.purge_audio('synthetic', 'r')
    assert purge_world == []
    donor_obligation = ('conversation_batch_purge_jobs', purge_jobs.job_id('synthetic', 'donor'))
    # The donor owes its own obligation, behind its own tombstone.
    assert strict.rows[donor_obligation]['conversation_id'] == 'donor' and _tombstone('donor') in strict.rows
    del strict.rows[OBLIGATION]  # the obligation's owning run removes it after its last phase
    with pytest.raises(service.AudioPurgeIntakesPending):
        service.purge_audio('synthetic', 'r')
    del strict.rows[donor_obligation]
    service.purge_audio('synthetic', 'r')
    # Custody is gone, but the donors it retained are still owed with this recording's erase.
    assert RETAINED_DONORS_FIELD not in _live(strict.rows[R])
    assert purge_world == [('erase', 'r', {'source_ids': ['donor']}), ('prefixes', 'donor')]
    assert strict.rows[R]['v3_audio_purge_pending'] is False


PENDING = {'recording': True, 'status': 'completed', 'claims': [], 'v3_audio_purge_pending': True}


def _hold():
    legal_holds.place_legal_hold('synthetic', issuer='admin', active=True, firestore_client=legal_holds_client())


def legal_holds_client():
    return legal_holds.account_deletion_firestore_client()


def test_held_purge_deletes_nothing_and_stays_owed(strict, purge_world):
    strict.rows[R] = {**PENDING, SETTLED_FIELD: True, RETAINED_DONORS_FIELD: ['donor']}
    _hold()
    before = _purge_count('held')
    with pytest.raises(legal_holds.LegalHoldActive):
        service.purge_audio('synthetic', 'r')
    assert purge_world == []
    assert _purge_count('held') == before + 1
    # The hold is checked before the claim: custody and the row are untouched, the purge stays owed.
    assert strict.rows[R] == {**PENDING, SETTLED_FIELD: True, RETAINED_DONORS_FIELD: ['donor']}
    assert _tombstone('r') not in strict.rows and _tombstone('donor') not in strict.rows


def test_hold_placed_after_the_claim_stops_the_inline_purge_at_the_gate(strict, purge_world, monkeypatch):
    strict.rows[R] = {**PENDING, SETTLED_FIELD: True}
    claim = store.claim_audio_purge

    def claim_then_hold(*args, **kwargs):
        result = claim(*args, **kwargs)
        _hold()
        return result

    monkeypatch.setattr(store, 'claim_audio_purge', claim_then_hold)
    before = _purge_count('held')
    with pytest.raises(legal_holds.LegalHoldActive):
        service.purge_audio('synthetic', 'r')
    # The account gate re-checks the hold before the first deletion: no WAL, no intakes, no blobs.
    assert purge_world == []
    assert _purge_count('held') == before + 1
    row = _live(strict.rows[R])
    assert row['v3_audio_purge_pending'] is True and row[store.AUDIO_PURGE_INTAKES_FIELD] == 'inline'


def _merge_target_world(strict):
    strict.rows[R] = {
        **PENDING,
        SETTLED_FIELD: True,
        RETAINED_DONORS_FIELD: ['d1', 'd2'],
        'sync_merged_from': ['d1', 'd2'],
    }
    for donor in ('d1', 'd2'):
        strict.rows[_row(donor)] = {
            'deleted': True,
            SETTLED_FIELD: True,
            MERGE_TARGET_FIELD: 'r',
            'sync_merged_into': 'r',
        }


def test_merge_target_erases_every_donor_before_completing(strict, purge_world):
    _merge_target_world(strict)
    service.purge_audio('synthetic', 'r')
    assert purge_world == [
        ('intakes', 'r'),
        ('intakes', 'd1'),
        ('intakes', 'd2'),
        ('erase', 'r', {'source_ids': ['d1', 'd2']}),
        ('prefixes', 'd1'),
        ('prefixes', 'd2'),
    ]
    for donor in ('d1', 'd2'):
        assert _tombstone(donor) in strict.rows
        assert not has_retained_custody(_live(strict.rows[_row(donor)]))
    row = _live(strict.rows[R])
    assert row['v3_audio_purge_pending'] is False and row[store.AUDIO_PURGE_DONORS_FIELD] == []


@pytest.mark.parametrize('step', ['intakes', 'prefixes'])
def test_partial_donor_erasure_retries_without_completing(strict, purge_world, monkeypatch, step):
    _merge_target_world(strict)
    real = {'intakes': batch_pipeline_purge.purge_batch_owner, 'prefixes': storage.delete_conversation_audio_files}
    failed = []

    def flaky(uid, *args, **kwargs):
        cid = kwargs.get('conversation_id') or args[0]
        if cid == 'd2' and not failed:
            failed.append(cid)
            raise RuntimeError('synthetic outage')
        return real[step](uid, *args, **kwargs)

    if step == 'intakes':
        monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', flaky)
    else:
        monkeypatch.setattr(storage, 'delete_conversation_audio_files', flaky)
    with pytest.raises(RuntimeError):
        service.purge_audio('synthetic', 'r')
    row = _live(strict.rows[R])
    assert row['v3_audio_purge_pending'] is True and row[store.AUDIO_PURGE_DONORS_FIELD] == ['d1', 'd2']
    if step == 'intakes':
        assert not [call for call in purge_world if call[0] in {'erase', 'prefixes'}]
    first = list(purge_world)
    service.purge_audio('synthetic', 'r')
    # The retry repeats every idempotent step for both donors, then completes.
    assert purge_world[len(first) :] == [
        ('intakes', 'r'),
        ('intakes', 'd1'),
        ('intakes', 'd2'),
        ('erase', 'r', {'source_ids': ['d1', 'd2']}),
        ('prefixes', 'd1'),
        ('prefixes', 'd2'),
    ]
    row = _live(strict.rows[R])
    assert row['v3_audio_purge_pending'] is False and row[store.AUDIO_PURGE_DONORS_FIELD] == []


def test_blob_delete_failure_keeps_the_purge_pending_for_the_next_sweep(strict, purge_world, monkeypatch):
    strict.rows[R] = {**PENDING, SETTLED_FIELD: True}

    def unavailable(uid, cid, **kw):
        raise RuntimeError('synthetic storage outage')

    monkeypatch.setattr(storage, 'delete_privacy_conversation_audio', unavailable)
    before = _purge_count('erased')
    with pytest.raises(RuntimeError):
        service.purge_audio('synthetic', 'r')
    assert strict.rows[R]['v3_audio_purge_pending'] is True and _purge_count('erased') == before
    monkeypatch.setattr(
        storage, 'delete_privacy_conversation_audio', lambda uid, cid, **kw: purge_world.append(('erase', cid, kw))
    )
    service.purge_audio('synthetic', 'r')
    assert purge_world == [('intakes', 'r'), ('intakes', 'r'), ('erase', 'r', {})]
    assert strict.rows[R]['v3_audio_purge_pending'] is False and _purge_count('erased') == before + 1


def test_erased_donor_leaves_its_successor_lineage(strict, purge_world):
    successor = _row('successor')
    strict.rows[successor] = {RETAINED_DONORS_FIELD: ['other', 'r'], 'sync_merged_from': ['other', 'r']}
    strict.rows[R] = {**PENDING, 'deleted': True, SETTLED_FIELD: True, MERGE_TARGET_FIELD: 'successor'}
    service.purge_audio('synthetic', 'r')
    assert strict.rows[successor] == {RETAINED_DONORS_FIELD: ['other'], 'sync_merged_from': ['other']}
    assert purge_world == [('intakes', 'r'), ('erase', 'r', {})]


def _gate_row():
    return (
        legal_holds_client().document(f'{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/synthetic').get().to_dict()
    )


def test_no_hold_lands_between_canonical_and_prefix_deletes(strict, purge_world, monkeypatch):
    """The race the point preflight left open: a hold placed after the canonical packs go.

    The real canonical helper runs; its nested audio gate reuses the sweep's. A hold attempted
    between the canonical delete and the raw and donor prefix deletes is refused by the gate
    (place_legal_hold raises while a destructive gate runs), so it cannot be active for them.
    """
    _merge_target_world(strict)
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'synthetic-canonical')
    monkeypatch.setattr(storage, 'get_canonical_audio_bucket', lambda: 'canonical')
    refused = []

    def delete_packs(bucket, uid, cid):
        _assert_audio_gate_held(uid)
        purge_world.append(('packs', cid))
        if not refused:
            with pytest.raises(legal_holds.DestructiveOperationInProgress) as error:
                _hold()
            refused.append(error.value)

    monkeypatch.setattr(storage.audio_packs, 'delete_conversation', delete_packs)
    monkeypatch.setattr(storage, 'delete_privacy_conversation_audio', REAL_DELETE_PRIVACY_AUDIO)
    acquired = []
    real_acquire = legal_holds.acquire_destructive_operation

    def acquire(uid, *, kind, **kwargs):
        acquired.append(kind)
        return real_acquire(uid, kind=kind, **kwargs)

    monkeypatch.setattr(legal_holds, 'acquire_destructive_operation', acquire)
    service.purge_audio('synthetic', 'r')
    assert refused
    # The canonical step did not take a gate of its own: one intake gate, one audio gate.
    assert acquired == [purge_jobs.GATE_KIND, service.AUDIO_GATE_KIND]
    assert sorted(call for call in purge_world if call[0] == 'packs') == [
        ('packs', 'd1'),
        ('packs', 'd2'),
        ('packs', 'r'),
    ]
    assert [call for call in purge_world if call[0] == 'prefixes'] == [
        ('prefixes', 'r'),
        ('prefixes', 'd1'),
        ('prefixes', 'd2'),
    ]
    assert legal_holds.read_legal_hold('synthetic', firestore_client=legal_holds_client()) is None
    assert _gate_row()['state'] == 'completed' and _gate_row()['kind'] == service.AUDIO_GATE_KIND
    assert strict.rows[R]['v3_audio_purge_pending'] is False


def test_hold_landing_after_the_intake_purge_stops_every_blob_delete(strict, purge_world, monkeypatch):
    """A hold placed in the only window no gate covers, after the intake gate releases.

    The audio gate's acquisition reads it transactionally: no canonical, raw or donor
    prefix delete runs, the row stays owed with its donors, and the purge counts as held.
    """
    _merge_target_world(strict)
    real_gate = legal_holds.destructive_operation_gate

    @contextmanager
    def gate_then_hold(uid, *, kind, **kwargs):
        with real_gate(uid, kind=kind, **kwargs) as token:
            yield token
        if kind == purge_jobs.GATE_KIND:
            _hold()

    monkeypatch.setattr(legal_holds, 'destructive_operation_gate', gate_then_hold)
    before = _purge_count('held')
    with pytest.raises(legal_holds.LegalHoldActive):
        service.purge_audio('synthetic', 'r')
    assert purge_world == [('intakes', 'r'), ('intakes', 'd1'), ('intakes', 'd2')]
    assert _purge_count('held') == before + 1
    row = _live(strict.rows[R])
    assert row['v3_audio_purge_pending'] is True and row[store.AUDIO_PURGE_DONORS_FIELD] == ['d1', 'd2']
    # The refused acquisition never wrote the audio gate: the last row is the intake gate's receipt.
    assert _gate_row()['kind'] == purge_jobs.GATE_KIND and _gate_row()['state'] == 'completed'


def test_moved_donor_is_not_erased_with_its_former_target(strict, purge_world):
    """A retained donor whose current merge target names another conversation is that target's custody."""
    moved = {'deleted': True, SETTLED_FIELD: True, MERGE_TARGET_FIELD: 'other', 'sync_merged_into': 'other'}
    strict.rows[R] = {**PENDING, SETTLED_FIELD: True, RETAINED_DONORS_FIELD: ['d1', 'moved']}
    strict.rows[_row('d1')] = {'deleted': True, SETTLED_FIELD: True, MERGE_TARGET_FIELD: 'r'}
    strict.rows[_row('moved')] = dict(moved)
    service.purge_audio('synthetic', 'r')
    assert purge_world == [
        ('intakes', 'r'),
        ('intakes', 'd1'),
        ('erase', 'r', {'source_ids': ['d1']}),
        ('prefixes', 'd1'),
    ]
    # No tombstone, no custody clear, no intake purge and no prefix delete for the moved donor.
    assert _tombstone('moved') not in strict.rows and strict.rows[_row('moved')] == moved
    assert _tombstone('d1') in strict.rows and not has_retained_custody(_live(strict.rows[_row('d1')]))


@pytest.mark.parametrize('state', ['deleted', 'is_locked'])
def test_terminal_processing_settles_pending(strict, state):
    cid = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[cid] = {'id': 'c', state: True, 'v3_process_pending': True}
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    writers.settle_processing('synthetic', 'c', token, None, None, skipped=True, firestore_client=strict)
    assert strict.rows[cid]['v3_process_pending'] is False
    assert strict.rows[cid]['tile_state'] == 'done'
    assert 'summary_covers_through' not in strict.rows[cid]


def test_paid_processing_and_outline_retries_are_content_bounded(strict):
    cid = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'transcript_segments': [{'text': 'synthetic content'}]}
    strict.rows[cid] = dict(row, v3_process_pending=True)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert not writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert strict.rows[cid]['v3_process_pending'] is False
    row['transcript_segments'].append({'text': 'changed content'})
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    builder = leases.acquire('synthetic', 'builder', firestore_client=strict)
    assert store.outline_attempt('synthetic', builder, 'fp', firestore_client=strict)
    assert store.outline_attempt('synthetic', builder, 'fp', firestore_client=strict)
    assert not store.outline_attempt('synthetic', builder, 'fp', firestore_client=strict)
    assert store.outline_attempt('synthetic', builder, 'new-fp', firestore_client=strict)


def test_projection_allows_transcript_offload(strict, monkeypatch):
    calls = []
    monkeypatch.setattr(
        store.conversations, '_prepare_conversation_for_write', lambda row, *a, **kw: calls.append(kw) or dict(row)
    )
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection(
        'synthetic', token, {}, {}, [{'id': 'c', 'status': 'completed'}], [], firestore_client=strict
    )
    assert calls[0]['allow_offload'] is True


@pytest.mark.parametrize('abort_second_batch', [False, True])
def test_projection_partitions_bytes_and_keeps_pending_until_last_batch(
    strict, monkeypatch, caplog, abort_second_batch
):
    strict.rows[R] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    original = store.firestore.transactional
    observations = []

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            if abort_second_batch and len(observations) == 1:
                raise Aborted('cross-transaction contention')
            result = wrapped(tx, *args)
            observations.append(strict.rows[R]['v3_pending'])
            return result

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'started_at': AT,
            'finished_at': AT,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * 60000}],
        }
        for i in range(128)
    ]

    def commit():
        store.commit_projection(
            'synthetic', token, {'r': {**strict.rows[R], '_v3_revision': 1}}, {}, rows, [], firestore_client=strict
        )

    if abort_second_batch:
        trace_id = 'a' * 32
        with bind_request_log_trace({b'x-cloud-trace-context': (trace_id + '/42').encode()}):
            with pytest.raises(FirestoreContentionExhausted):
                commit()
        assert observations == [True]
        assert strict.rows[R]['v3_pending'] is True
        assert 0 < len(strict.rows[R]['claims']) < len(rows)
        assert f'stage=projection_commit outcome=contention trace_id={trace_id}' in caplog.text
        return

    commit()
    assert len(observations) >= 4
    assert all(observations[:-1]) and observations[-1] is False
    assert len(strict.rows[R]['claims']) == 128


def test_terminal_failure_metric_failure_does_not_stop_later_projection_batches(strict, monkeypatch):
    strict.rows[R] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'v3_process_failed': True,
            'v3_process_failure_reason': 'processing',
            'started_at': AT,
            'finished_at': AT,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * 60000}],
        }
        for i in range(128)
    ]
    terminal_failure = Mock(side_effect=OSError('metrics unavailable'))
    monkeypatch.setattr(metrics, 'terminal_failure', terminal_failure)

    store.commit_projection(
        'synthetic', token, {'r': {**strict.rows[R], '_v3_revision': 1}}, {}, rows, [], firestore_client=strict
    )

    assert terminal_failure.call_count == len(rows)
    assert all(('users', 'synthetic', 'conversations', row['id']) in strict.rows for row in rows)
    assert strict.rows[R]['v3_pending'] is False


def test_multi_batch_backfill_conversion_is_not_its_own_race_and_keeps_an_obligation(strict, monkeypatch):
    # A backfill donor is a plain conversation until the first batch hides it as a recording.
    strict.rows[R] = {'id': 'r', 'status': 'completed', 'structured': {'title': 'Old notes'}}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    original = store.firestore.transactional
    observations = []

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            result = wrapped(tx, *args)
            observations.append((strict.rows[R].get('recording'), strict.rows[R].get('v3_pending')))
            return result

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'started_at': AT,
            'finished_at': AT,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * 60000}],
        }
        for i in range(128)
    ]
    donor = {
        **strict.rows[R],
        'recording': True,
        '_v3_derive': True,
        '_v3_revision': 1,
        '_v3_backfill_run': 'run-1',
        '_v3_backfill_prior': {},
    }
    store.commit_projection('synthetic', token, {'r': donor}, {}, rows, [], firestore_client=strict)
    assert len(observations) >= 4
    # Hidden as a recording from the first batch, with a durable obligation until the last one lands.
    assert all(recording is True and pending is True for recording, pending in observations[:-1])
    assert observations[-1] == (True, False)
    assert len(strict.rows[R]['claims']) == 128
    # Non-destructive: the legacy notes stay, and the donor names its run and its prior state for undo.
    assert strict.rows[R]['structured'] == {'title': 'Old notes'}
    assert strict.rows[R]['v3_backfill_run'] == 'run-1' and strict.rows[R]['v3_backfill_prior'] == {}
    assert strict.rows[R]['v3_audio_purge_pending'] is False


def test_metadata_revision_change_does_not_rebill_unchanged_content(strict, monkeypatch):
    cid = ('users', 'synthetic', 'conversations', 'c')
    original = {'id': 'c', 'transcript_segments': [{'text': 'same real content'}], 'sync_content_revision': 1}
    strict.rows[cid] = dict(original, v3_process_pending=True, sync_content_revision=2)
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: snap.to_dict())
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    writers.settle_processing(
        'synthetic', 'c', token, 1, AT, content_hash=writers.processing_hash(original), firestore_client=strict
    )
    assert strict.rows[cid]['v3_process_pending'] is False
    strict.rows[cid]['transcript_segments'] = [{'text': 'actually changed content'}]
    with pytest.raises(store.Conflict, match='processing_source_changed'):
        writers.settle_processing(
            'synthetic', 'c', token, 1, AT, content_hash=writers.processing_hash(original), firestore_client=strict
        )


@pytest.mark.asyncio
async def test_summary_holder_stores_before_releasing_lease_and_detail_sees_result(strict, monkeypatch):
    from utils.conversations.v3 import summary

    cid = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'created_at': AT, 'started_at': AT, 'finished_at': AT, 'structured': {'title': 'Stable'}}
    strict.rows[cid] = row
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: snap.to_dict())

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(
        summary,
        'write',
        lambda *a: {'title': 'Stable', 'sections': [{'heading': 'Plan', 'body_markdown': 'Full notes.'}]},
    )
    original = writers.store_summary

    def persist(*args):
        assert leases.acquire('synthetic', 'summary-c', firestore_client=strict) is None
        return original(*args)

    monkeypatch.setattr(writers, 'store_summary', persist)
    token = await summary.prepare('synthetic', row)
    frames = [frame async for frame in summary.stream('synthetic', row, token=token)]
    assert frames[-1].startswith('done: ')
    assert strict.rows[cid]['structured']['sections'][0]['body_markdown'] == 'Full notes.'
    assert strict.rows[cid]['summary_covers_through'] == AT
    assert leases.acquire('synthetic', 'summary-c', firestore_client=strict) is not None


def test_on_open_projection_keeps_background_pending_obligation(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True, 'v3_pending_since': AT}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection(
        'synthetic',
        token,
        {'r': {**strict.rows[R], '_v3_revision': 1}},
        {},
        [],
        [],
        clear_pending=False,
        firestore_client=strict,
    )
    assert strict.rows[R]['v3_pending'] is True and strict.rows[R]['v3_pending_since'] == AT


def test_exhausted_retry_budget_is_failed_and_retryable(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'transcript_segments': [{'text': 'real speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for _ in range(2):
        assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    outcome = writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert outcome is writers.TERMINAL and not outcome
    failed = strict.rows[path]
    assert failed['tile_state'] == 'failed' and failed['status'] == 'completed'
    assert failed['summary_retryable'] and failed['v3_process_failed']
    assert writers.begin_processing('synthetic', row, token, force=True, firestore_client=strict)
    assert strict.rows[path]['tile_state'] == 'writing'
    assert strict.rows[path]['v3_process_attempts'] == 1


def test_attempts_exhausted_metric_failure_keeps_committed_terminal_state(strict, monkeypatch):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'transcript_segments': [{'text': 'real speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for _ in range(2):
        assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    terminal_failure = Mock(side_effect=OSError('metrics unavailable'))
    monkeypatch.setattr(metrics, 'terminal_failure', terminal_failure)

    outcome = writers.begin_processing('synthetic', row, token, firestore_client=strict)

    assert outcome is writers.TERMINAL
    terminal_failure.assert_called_once_with('attempts_exhausted')
    assert strict.rows[path]['tile_state'] == 'failed'
    assert strict.rows[path]['v3_process_failed'] is True


def test_successful_pass_resets_the_attempt_budget(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'transcript_segments': [{'text': 'unchanged speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for _ in range(3):
        assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
        writers.settle_processing('synthetic', 'c', token, None, AT, notes=True, firestore_client=strict)
    settled = strict.rows[path]
    assert settled['tile_state'] == 'done' and not settled['v3_process_failed']
    assert settled['v3_process_attempts'] == 0


def test_attempt_budget_counts_consecutive_failures_not_total_attempts(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'transcript_segments': [{'text': 'unchanged speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for outcome in ('failed', 'settled', 'failed', 'settled'):
        assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
        if outcome == 'failed':
            writers.fail_processing('synthetic', 'c', token, None, firestore_client=strict)
        else:
            writers.settle_processing('synthetic', 'c', token, None, AT, notes=True, firestore_client=strict)
    assert strict.rows[path]['tile_state'] == 'done' and not strict.rows[path]['v3_process_failed']


def test_two_consecutive_failures_still_reach_the_terminal_outcome(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'transcript_segments': [{'text': 'real speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for _ in range(2):
        assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
        writers.fail_processing('synthetic', 'c', token, None, firestore_client=strict)
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict) is writers.TERMINAL
    failed = strict.rows[path]
    assert failed['tile_state'] == 'failed' and failed['status'] == 'completed'
    assert failed['summary_retryable'] and failed['v3_process_failed']
    assert failed['v3_process_failure_reason'] == 'attempts_exhausted'


def test_failure_never_replaces_a_locked_presentation(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[path] = {'id': 'c', 'is_locked': True, 'tile_state': 'writing'}
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert not writers.fail_processing('synthetic', 'c', token, None, firestore_client=strict)
    assert strict.rows[path]['is_locked'] and strict.rows[path]['tile_state'] != 'failed'


def test_multiple_open_rows_are_rejected_before_any_batch_or_codec_write(strict, monkeypatch):
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    monkeypatch.setattr(
        store.conversations,
        '_prepare_conversation_for_write',
        lambda *a, **kw: pytest.fail('codec/offload ran before global open check'),
    )
    rows = [{'id': cid, 'status': 'in_progress', 'padding': 'x' * 2100000} for cid in ['a', 'b']]
    with pytest.raises(store.Conflict, match='multiple_open'):
        store.commit_projection('synthetic', token, {}, {}, rows, [], firestore_client=strict)
    assert not any(p[2] == 'conversations' for p in strict.rows)


def test_terminal_failure_counter_counts_committed_transitions_once(strict):
    from utils.conversations.v3 import metrics

    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'sync_content_revision': 1, 'transcript_segments': [{'text': 'speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    before = metrics.TERMINAL_FAILURES.labels('processing')._value.get()
    assert writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)
    assert not writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)
    assert metrics.TERMINAL_FAILURES.labels('processing')._value.get() == before + 1


def test_settlement_metric_failure_keeps_committed_processing_state(strict, monkeypatch):
    path = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[path] = {'id': 'c', 'v3_derived': True, 'status': 'completed', 'v3_process_pending': True}
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    counter = writers.summary_delivery.SETTLED_UNSUMMARIZED.labels('live', 'no_notes')
    inc = Mock(side_effect=OSError('metrics unavailable'))
    monkeypatch.setattr(counter, 'inc', inc)

    armed = writers.settle_processing('synthetic', 'c', token, None, AT, notes=False, firestore_client=strict)

    inc.assert_called_once()
    assert armed is False
    assert strict.rows[path]['v3_process_pending'] is False
    assert strict.rows[path]['tile_state'] == 'done'


def test_terminal_processing_metrics_failure_keeps_committed_failure(strict, monkeypatch):
    path = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[path] = {
        'id': 'c',
        'v3_derived': True,
        'sync_content_revision': 1,
        'transcript_segments': [{'text': 'speech'}],
    }
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    counter = writers.summary_delivery.SETTLED_UNSUMMARIZED.labels('live', 'failed')
    terminal_failure = Mock(side_effect=OSError('metrics unavailable'))
    unsummarized = Mock(side_effect=OSError('metrics unavailable'))
    monkeypatch.setattr(metrics, 'terminal_failure', terminal_failure)
    monkeypatch.setattr(counter, 'inc', unsummarized)

    changed = writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)

    terminal_failure.assert_called_once_with('processing')
    unsummarized.assert_called_once()
    assert changed is True
    assert strict.rows[path]['v3_process_failed'] is True
    assert strict.rows[path]['status'] == 'completed'


def test_locked_refinement_commits_redirect_and_transferred_claims_together(strict, monkeypatch):
    monkeypatch.setattr(store, 'merge_donors_have_tasks', lambda *a, **kw: False)
    older, later = R[:-1] + ('older',), R[:-1] + ('later',)
    end = AT + timedelta(seconds=30)
    midpoint = AT + timedelta(seconds=10)
    old_claims = [
        {'conversation_id': 'older', 'start': AT, 'end': midpoint},
        {'conversation_id': 'later', 'start': midpoint, 'end': end},
    ]
    strict.rows[R] = {'recording': True, 'claims': old_claims, 'v3_pending': True}
    strict.rows[older] = {'id': 'older', 'status': 'completed', 'v3_derived': True}
    strict.rows[later] = {'id': 'later', 'status': 'completed', 'v3_derived': True, 'sync_content_revision': 3}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    source = {'id': 'r', **strict.rows[R], '_v3_revision': 1}
    existing = {path[-1]: {**strict.rows[path], '_v3_revision': 1} for path in (older, later)}
    survivor = {
        **existing['older'],
        'started_at': AT,
        'finished_at': end,
        'v3_recording_ids': ['r'],
        '_v3_absorbed': ['later'],
        '_v3_claims': {'r': [{'start': AT, 'end': midpoint}, {'start': midpoint, 'end': end}]},
    }
    strict.rows[later]['_test_revision'] = 2
    with pytest.raises(store.Conflict, match='source_changed'):
        store.commit_projection('synthetic', token, {'r': source}, existing, [survivor], [], firestore_client=strict)
    assert strict.rows[R]['claims'] == old_claims
    assert 'deleted' not in strict.rows[later]

    existing['later']['_v3_revision'] = 2
    tombstone = ('users', 'synthetic', 'deleted_conversations', 'later')
    strict.rows[tombstone] = {'conversation_id': 'later'}
    with pytest.raises(store.Conflict, match='target_deleted'):
        store.commit_projection('synthetic', token, {'r': source}, existing, [survivor], [], firestore_client=strict)
    assert strict.rows[R]['claims'] == old_claims
    del strict.rows[tombstone]

    monkeypatch.setattr(store, 'merge_donors_have_tasks', lambda *a, **kw: True)
    with pytest.raises(store.Conflict, match='source_changed'):
        store.commit_projection('synthetic', token, {'r': source}, existing, [survivor], [], firestore_client=strict)
    assert strict.rows[R]['claims'] == old_claims
    assert 'deleted' not in strict.rows[later]
    monkeypatch.setattr(store, 'merge_donors_have_tasks', lambda *a, **kw: False)

    store.commit_projection('synthetic', token, {'r': source}, existing, [survivor], [], firestore_client=strict)
    assert strict.rows[older]['finished_at'] == end
    assert '_v3_absorbed' not in strict.rows[older]
    assert strict.rows[later]['deleted'] and strict.rows[later]['home_hidden']
    assert strict.rows[later]['sync_merged_into'] == strict.rows[later]['v3_claims_transferred_to'] == 'older'
    assert strict.rows[later]['sync_content_revision'] == 4
    assert strict.rows[R]['claims'] == [{**claim, 'conversation_id': 'older'} for claim in old_claims]


def test_full_builder_prunes_stale_provisional_lease_ids(strict):
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    strict.rows[L]['unlocked_ids'] = ['settled', 'live', 'missing']
    live, settled = R[:-1] + ('live',), R[:-1] + ('settled',)
    strict.rows[live] = {'id': 'live', 'v3_unlocked': True, 'status': 'processing'}
    strict.rows[settled] = {'id': 'settled', 'v3_unlocked': False, 'status': 'completed'}
    existing = {path[-1]: {**strict.rows[path], '_v3_revision': 1} for path in (live, settled)}
    new = {'id': 'new', 'v3_unlocked': True, 'status': 'in_progress'}
    store.commit_projection('synthetic', token, {}, existing, [new], [], firestore_client=strict)
    assert strict.rows[L]['unlocked_ids'] == ['new']
    assert strict.rows[live]['v3_unlocked']


@pytest.mark.parametrize('wipe_status', ['cancelled', 'billing_failed', 'pending'])
def test_summary_commit_respects_account_deletion_marker(strict, wipe_status):
    card = R[:-1] + ('card',)
    original = {'id': 'card', 'status': 'processing', 'v3_derived': True}
    strict.rows[card] = original.copy()
    strict.rows[(ACCOUNT_DELETION_COLLECTION, 'synthetic')] = {'wipe_status': wipe_status}
    token = leases.acquire('synthetic', 'summary-card', firestore_client=strict)
    structured = {'title': 'Synthetic'}

    if wipe_status == 'pending':
        with pytest.raises(store.Conflict, match='^account_deletion$'):
            writers.store_summary('synthetic', 'card', token, 1, structured, AT, firestore_client=strict)
        assert strict.rows[card] == original
        return

    writers.store_summary('synthetic', 'card', token, 1, structured, AT, firestore_client=strict)
    assert strict.rows[card]['structured'] == structured
    assert strict.rows[card]['summary_covers_through'] == AT


@pytest.mark.parametrize('already_open_locked', [False, True])
def test_on_open_summary_commit_finalizes_provisional_snapshot(strict, already_open_locked):
    card = R[:-1] + ('card',)
    strict.rows[card] = {
        'id': 'card',
        'v3_derived': True,
        'v3_unlocked': not already_open_locked,
        'v3_open_locked': already_open_locked,
        'v3_process_pending': already_open_locked,
        'status': 'processing' if already_open_locked else 'in_progress',
        'finished_at': AT,
    }
    token = leases.acquire('synthetic', 'summary-card', firestore_client=strict)
    writers.store_summary('synthetic', 'card', token, 1, {'title': 'Synthetic'}, AT, firestore_client=strict)
    row = strict.rows[card]
    assert row['status'] == 'completed' and row['v3_open_locked'] and not row['v3_unlocked']
    assert row['summary_covers_through'] == AT and row['v3_process_pending']


@pytest.mark.asyncio
async def test_open_notes_failure_keeps_an_older_preview_live(strict, monkeypatch):
    card = R[:-1] + ('card',)
    row = {
        'id': 'card',
        'v3_derived': True,
        'v3_unlocked': True,
        'status': 'processing',
        'tile_state': 'live',
        'finished_at': AT,
        'transcript_segments': [{'text': 'word ' * 300}],
    }
    strict.rows[card] = row
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: snap.to_dict())
    monkeypatch.setattr(writers, 'fail_processing', lambda *a, **kw: pytest.fail('unlocked card marked terminal'))

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def fail(*args):
        raise RuntimeError('synthetic model failure')

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'write', fail)
    token = await summary.prepare('synthetic', row)
    frames = [frame async for frame in summary.stream('synthetic', row, token=token)]
    assert frames[-1].startswith('error: ')
    assert strict.rows[card]['tile_state'] == 'live'


def test_preview_deadline_keeps_a_durable_sweep_obligation_until_lock(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True, 'v3_pending_since': AT}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    raw = {'id': 'r', **strict.rows[R], '_v3_revision': 1}
    preview = {
        'id': 'preview',
        'status': 'in_progress',
        'v3_unlocked': True,
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': ['r'],
        '_v3_preview_due_at': AT + timedelta(minutes=30),
    }
    store.commit_projection('synthetic', token, {'r': raw}, {}, [preview], [], firestore_client=strict)
    assert strict.rows[R]['v3_pending'] is True
    assert strict.rows[R]['v3_pending_since'] == AT + timedelta(minutes=30)

    prior = {**strict.rows[R[:-1] + ('preview',)], '_v3_revision': 1}
    settled = {**prior, 'status': 'processing', 'v3_unlocked': False, 'v3_process_pending': True}
    store.commit_projection(
        'synthetic',
        token,
        {'r': {**strict.rows[R], '_v3_revision': 1}},
        {'preview': prior},
        [settled],
        [],
        firestore_client=strict,
    )
    assert strict.rows[R]['v3_pending'] is False
    assert strict.rows[R]['v3_pending_since'] is None


@pytest.mark.parametrize('already_pending', [False, True])
def test_scoped_preview_commit_sets_wake_without_delaying_pending_speech(strict, already_pending):
    strict.rows[R] = {
        'recording': True,
        'v3_pending': already_pending,
        'v3_pending_since': AT if already_pending else None,
    }
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    raw = {'id': 'r', **strict.rows[R], '_v3_revision': 1}
    due = AT + timedelta(minutes=30)
    preview = {
        'id': 'preview',
        'status': 'processing',
        'v3_unlocked': True,
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': ['r'],
        '_v3_preview_due_at': due,
    }

    store.commit_projection(
        'synthetic', token, {'r': raw}, {}, [preview], [], clear_pending=False, firestore_client=strict
    )

    assert strict.rows[R]['v3_pending'] is True
    assert strict.rows[R]['v3_pending_since'] == (AT if already_pending else due)


@pytest.mark.parametrize('engine', ['pending', 'go'])
def test_processing_writers_refuse_foreign_snapshot(strict, monkeypatch, engine):
    uid, cid = 'synthetic', 'c'
    path = ('users', uid, 'conversations', cid)
    prior = {'id': cid, 'status': 'processing', 'sync_content_revision': 1, 'v3_process_pending': True}
    stored = {
        **prior,
        'finalization_engine': engine,
        'finalization_owner_epoch': 1,
        'v3_backfill_process_pending': True,
    }
    strict.rows[path] = stored.copy()
    token = leases.acquire(uid, 'summary-c', firestore_client=strict)
    monkeypatch.setattr(store.conversations, 'db', strict)

    assert not writers.begin_processing(uid, prior, token, firestore_client=strict)
    assert not writers.fail_processing(uid, cid, token, 1, firestore_client=strict)
    assert not writers.settle_processing(uid, cid, token, 1, AT, notes=True, firestore_client=strict)
    assert (
        writers.settle_backfill_processing(uid, cid, failed=True, max_attempts=1, firestore_client=strict) == 'absent'
    )
    with pytest.raises(service.Conflict, match='summary_source_changed'):
        writers.store_summary(uid, cid, token, 1, {'title': 'Synthetic'}, AT, firestore_client=strict)
    assert not lifecycle.complete(uid, cid)
    assert strict.rows[path] == stored


@pytest.fixture
def created_delivery(monkeypatch):
    # Load the integration graph in fixture setup. This test exercises the
    # drain's ownership check before any lease or integration work.
    created = importlib.import_module('utils.conversations.v3.created')
    deliver = AsyncMock()
    monkeypatch.setattr(created, 'deliver', deliver)
    return deliver


@pytest.mark.asyncio
async def test_queued_processing_skips_foreign_candidate_before_lease(monkeypatch, created_delivery):
    async def run_inline(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    pending = Mock(return_value=[{'id': 'c', 'finalization_engine': 'go', 'finalization_owner_epoch': 1}])
    acquire = Mock(side_effect=AssertionError('foreign row acquired a processing lease'))
    monkeypatch.setattr(service, 'run_blocking', run_inline)
    monkeypatch.setattr(service, 'pending_processing', pending)
    monkeypatch.setattr(leases, 'acquire', acquire)

    await service.drain_processing('synthetic')
    pending.assert_called_once_with('synthetic')
    acquire.assert_not_called()
    created_delivery.assert_awaited_once_with('synthetic')


@pytest.mark.parametrize(
    'change',
    [
        {'record_upload_revision': 8, 'record_audio_closed': False},
        {'record_sealed_at': AT.timestamp() + 1},
        {'record_upload_sessions': {'producer': True}},
        {'record_audio_partial': {'generation': 1}},
    ],
)
def test_native_notes_recheck_source_custody_during_the_write(strict, change, monkeypatch):
    from database import conversations_v3_fence as fence
    from tests.unit.test_conversations_v3_engine import native_ready_fields
    from utils.conversations.v3 import policy

    source = {'id': 'r', 'recording': True, 'started_at': AT - timedelta(seconds=20), **native_ready_fields(AT)}
    strict.rows[R] = source
    binding = policy.native_manual_binding(source)
    assert binding
    path = ('users', 'synthetic', 'conversations', 'native-derived')
    derived = {
        'id': path[-1],
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'manual_end': True,
        'v3_native_manual_binding': binding,
        'sync_content_revision': 3,
        'status': 'processing',
        'transcript_segments': [{'text': 'Synthetic notes input'}],
    }
    strict.rows[path] = derived
    from utils.conversations.v3 import triggers

    wakes = []

    def wake(uid, source_id, revision, *, rearm):
        assert strict.rows[R]['v3_pending'] is True
        wakes.append((uid, source_id, revision, rearm))

    monkeypatch.setattr(triggers, 'wake_native_manual_ready', wake)
    token = leases.acquire('synthetic', 'summary-' + path[-1], firestore_client=strict)
    assert writers.begin_processing('synthetic', derived, token, firestore_client=strict)
    with fence.writer('synthetic', path[-1], token, native_binding=binding):
        assert fence.permits(strict.transaction(), strict, 'synthetic', path[-1], strict.rows[path])
        # The builder has not updated the derived row; only the raw custody facts moved.
        strict.rows[R].update(change)
        with pytest.raises(store.Conflict, match='summary_source_changed'):
            writers.store_summary(
                'synthetic', path[-1], token, 1, {'overview': 'Stale content'}, AT, firestore_client=strict
            )
        assert strict.rows[R]['v3_pending'] is True  # The refusal is raised after the rearm transaction commits.
        pending_since = strict.rows[R]['v3_pending_since']
        assert not fence.permits(strict.transaction(), strict, 'synthetic', path[-1], strict.rows[path])
        assert not writers.begin_processing('synthetic', derived, token, firestore_client=strict)
        assert strict.rows[R]['v3_pending_since'] == pending_since
        with pytest.raises(store.Conflict, match='processing_source_changed'):
            writers.settle_processing('synthetic', path[-1], token, 3, AT, notes=True, firestore_client=strict)
    assert not strict.rows[path].get('structured')
    assert not strict.rows[path].get('v3_notes_written')
    assert wakes == [('synthetic', 'r', 7, True)]


@pytest.mark.parametrize('change', [{'deleted': True}, {'is_locked': True}, {'recording': False}])
def test_stale_native_proof_does_not_rearm_an_ineligible_source(strict, change):
    from database import conversations_v3_fence as fence
    from tests.unit.test_conversations_v3_engine import native_ready_fields
    from utils.conversations.v3 import policy

    source = {'id': 'r', 'recording': True, 'started_at': AT - timedelta(seconds=20), **native_ready_fields(AT)}
    binding = policy.native_manual_binding(source)
    strict.rows[R] = {**source, **change}
    tx = strict.transaction()
    assert not fence.permits_native_source(
        tx, strict, 'synthetic', {'v3_recording_ids': ['r'], 'v3_native_manual_binding': binding}
    )
    assert not tx.has_written
    assert 'v3_pending' not in strict.rows[R]


@pytest.mark.parametrize('change', [{'deleted': True}, {'is_locked': True}, {'recording': False}])
def test_stale_native_ineligible_source_settles_pending_tile(strict, change, monkeypatch):
    from tests.unit.test_conversations_v3_engine import native_ready_fields
    from utils.conversations.v3 import policy, triggers

    source = {'id': 'r', 'recording': True, 'started_at': AT - timedelta(seconds=20), **native_ready_fields(AT)}
    strict.rows[R] = source
    path = ('users', 'synthetic', 'conversations', 'native-derived')
    derived = {
        'id': path[-1],
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'v3_native_manual_binding': policy.native_manual_binding(source),
        'manual_end': True,
        'status': 'in_progress',
        'sync_content_revision': 3,
        'transcript_segments': [{'text': 'Synthetic notes input'}],
    }
    strict.rows[path] = derived
    token = leases.acquire('synthetic', 'summary-' + path[-1], firestore_client=strict)
    assert writers.begin_processing('synthetic', derived, token, firestore_client=strict)
    strict.rows[R].update(change)
    source_before = dict(strict.rows[R])
    monkeypatch.setattr(triggers, 'wake_native_manual_ready', lambda *a, **kw: pytest.fail('unexpected task'))
    with pytest.raises(store.Conflict, match='summary_source_changed'):
        writers.store_summary(
            'synthetic', path[-1], token, 1, {'overview': 'Stale content'}, AT, firestore_client=strict
        )
    settled = strict.rows[path]
    assert strict.rows[R] == source_before
    assert settled['status'] == 'completed'
    assert settled['tile_state'] == 'failed'
    assert settled['v3_process_pending'] is False
    assert settled['sync_content_revision'] == 4
    assert not settled.get('v3_native_manual_binding')
    assert not settled.get('structured')


def test_open_takes_preemptible_outline_lease_and_old_provider_cannot_publish(strict):
    uid, key, fingerprint = 'synthetic', 'builder', 'synthetic-revision'
    token = leases.acquire(uid, key, firestore_client=strict)
    assert store.outline_attempt(uid, token, fingerprint, preemptible=True, firestore_client=strict)
    assert leases.acquire(uid, key, firestore_client=strict) is None
    foreground = leases.acquire(uid, key, promote_llm=True, firestore_client=strict)
    assert foreground and foreground != token
    with pytest.raises(store.Conflict, match='lease_lost'):
        leases.mark_llm_preemptible(uid, key, token, False, firestore_client=strict)
    with pytest.raises(store.Conflict, match='lease_lost'):
        store.save_outline(uid, token, fingerprint, [], firestore_client=strict)
    assert store.outline_attempt(uid, foreground, fingerprint, firestore_client=strict)
    assert store.outline_attempt(uid, foreground, fingerprint, firestore_client=strict)
    assert not store.outline_attempt(uid, foreground, fingerprint, firestore_client=strict)
    assert leases.acquire(uid, key, promote_llm=True, firestore_client=strict) is None


def test_open_can_promote_summary_only_until_background_result_returns(strict):
    uid, key = 'synthetic', 'summary-conversation'
    token = leases.acquire(uid, key, firestore_client=strict)
    assert leases.acquire(uid, key, promote_llm=True, firestore_client=strict) is None
    leases.mark_llm_preemptible(uid, key, token, True, firestore_client=strict)
    leases.mark_llm_preemptible(uid, key, token, False, firestore_client=strict)
    assert leases.acquire(uid, key, promote_llm=True, firestore_client=strict) is None
    leases.mark_llm_preemptible(uid, key, token, True, firestore_client=strict)
    assert leases.acquire(uid, key, promote_llm=True, firestore_client=strict) is not None
    with pytest.raises(store.Conflict, match='lease_lost'):
        leases.mark_llm_preemptible(uid, key, token, False, firestore_client=strict)


@pytest.mark.asyncio
async def test_preempted_notes_pass_refunds_only_its_attempt(strict, monkeypatch):
    monkeypatch.setenv('OMI_V3_SUMMARY_FIRST_OPEN_GATING', 'true')
    from utils.conversations.v3 import models

    uid, cid = 'synthetic', 'conversation'
    key = 'summary-' + cid
    path = ('users', uid, 'conversations', cid)
    row = {'id': cid, 'status': 'processing', 'v3_process_pending': True}
    row['v3_process_fingerprint'] = writers.processing_hash(row)
    row['v3_process_attempts'] = 1
    strict.rows[path] = row.copy()
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: strict)
    token = leases.acquire(uid, key)
    assert writers.begin_processing(uid, row, token, firestore_client=strict)
    assert strict.rows[path]['v3_process_attempts'] == 2
    with models.notes_mode(uid, background_lease=(cid, token, datetime.now(timezone.utc))):
        with pytest.raises(store.Conflict, match='lease_lost'):
            async with models.summary_model_attempt():
                foreground = writers.acquire_open_summary(uid, cid)
                assert foreground and foreground != token
                assert writers.acquire_open_summary(uid, cid) is None

    assert strict.rows[path]['v3_process_attempts'] == 1
    assert strict.rows[path]['v3_process_pending'] is True
    leases.release(uid, key, foreground)
    token = leases.acquire(uid, key)
    assert writers.begin_processing(uid, row, token, firestore_client=strict)


@pytest.mark.asyncio
async def test_notes_drain_reloads_foreground_coverage_after_acquiring_lease(monkeypatch, created_delivery):
    scanned = {'id': 'c', 'v3_process_pending': True}
    written = {**scanned, 'summary_covers_through': AT, 'finished_at': AT, 'structured': {'title': 'On open'}}
    monkeypatch.setattr(service, 'pending_processing', lambda _: [scanned])
    monkeypatch.setattr(service, '_load_processing_row', lambda *_: written)
    monkeypatch.setattr(leases, 'acquire', lambda *_: 'token')
    monkeypatch.setattr(leases, 'release', lambda *_: None)
    process = AsyncMock()
    monkeypatch.setattr(service, '_process_leased', process)
    await service.drain_processing('synthetic')
    process.assert_awaited_once_with('synthetic', written, 'token')


@pytest.mark.asyncio
async def test_outline_takeover_after_attempt_claim_skips_provider_dispatch(strict, monkeypatch):
    from utils.conversations.v3 import models

    uid, key = 'synthetic', 'builder'
    token = leases.acquire(uid, key, firestore_client=strict)
    real_attempt = store.outline_attempt
    calls = []

    def claim(*args, **kwargs):
        assert real_attempt(*args, **kwargs, firestore_client=strict)
        assert leases.acquire(uid, key, promote_llm=True, firestore_client=strict)

    def promote_after_claim(*args, **kwargs):
        claim(*args, **kwargs)
        return True

    class Model:
        async def ainvoke(self, *_args, **_kwargs):
            calls.append('dispatch')

    monkeypatch.setattr(leases, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'outline_attempt', promote_after_claim)
    monkeypatch.setattr(models, 'require_current_generated_compute', lambda *a, **kw: None)
    monkeypatch.setattr(models, 'get_or_create_omi_gateway_llm', lambda *a, **kw: Model())
    group = {'finished': True, 'manual_end': False, 'end': datetime.now(timezone.utc)}
    with pytest.raises(store.Conflict, match='lease_lost'):
        await service._derive_outline(
            uid,
            key,
            token,
            group,
            [],
            'fingerprint',
            {},
            cohesion=False,
            silence_gap=timedelta(minutes=5),
            preview_key=None,
            flex_owner_deadline=service.time.monotonic() + 90,
        )
    assert not calls


def _processed(basis):
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value('omi_conversation_processed_seconds_count', {'lane': 'live', 'basis': basis}) or 0


def _unsummarized(reason):
    from prometheus_client import REGISTRY

    labels = {'lane': 'live', 'reason': reason}
    return REGISTRY.get_sample_value('omi_conversation_settled_unsummarized_total', labels) or 0


def _retried(strict, monkeypatch):
    """Run each transaction body twice: the first attempt aborts before commit, as a Firestore retry does."""

    def transactional(body):
        def run(tx, *args, **kwargs):
            with strict.lock:
                saved = deepcopy(strict.rows)
                body(strict.transaction(), *args, **kwargs)
                strict.rows.clear()
                strict.rows.update(saved)
                return body(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)


@pytest.fixture
def live_lane(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_ENABLED', raising=False)
    monkeypatch.delenv('CONVERSATION_TERMINAL_FAMILY_MODE', raising=False)


def test_first_notes_settle_observes_both_bases_once_across_a_retry(strict, monkeypatch, live_lane):
    path = ('users', 'synthetic', 'conversations', 'c')
    finished = datetime.now(timezone.utc) - timedelta(minutes=5)
    row = {'id': 'c', 'v3_derived': True, 'finished_at': finished, 'transcript_segments': [{'text': 'speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    _retried(strict, monkeypatch)
    before = _processed('finished'), _processed('end_or_sync')
    writers.settle_processing('synthetic', 'c', token, None, AT, notes=True, firestore_client=strict)
    assert (_processed('finished'), _processed('end_or_sync')) == (before[0] + 1, before[1] + 1)
    assert strict.rows[path]['v3_notes_written']
    # A late rewrite of a row that already has notes is not a first summary.
    assert writers.begin_processing('synthetic', row, token, force=True, firestore_client=strict)
    writers.settle_processing('synthetic', 'c', token, None, AT, notes=True, firestore_client=strict)
    assert _processed('finished') == before[0] + 1


def test_a_settle_without_notes_counts_the_unsummarized_denominator(strict, live_lane):
    path = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[path] = {'id': 'c', 'v3_derived': True, 'status': 'completed', 'v3_process_pending': True}
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    before = _unsummarized('no_notes'), _processed('finished')
    writers.settle_processing('synthetic', 'c', token, None, AT, notes=False, firestore_client=strict)
    assert _unsummarized('no_notes') == before[0] + 1 and _processed('finished') == before[1]


def test_open_notes_commit_observes_once_and_stamps_the_settle(strict, live_lane):
    card = R[:-1] + ('card',)
    strict.rows[card] = {
        'id': 'card',
        'v3_derived': True,
        'v3_unlocked': True,
        'status': 'in_progress',
        'finished_at': AT - timedelta(minutes=2),
    }
    token = leases.acquire('synthetic', 'summary-card', firestore_client=strict)
    before = _processed('finished')
    writers.store_summary('synthetic', 'card', token, 1, {'title': 'Synthetic'}, AT, firestore_client=strict)
    stamped = strict.rows[card]['terminal_family_at']
    assert strict.rows[card]['status'] == 'completed' and isinstance(stamped, datetime)
    assert _processed('finished') == before + 1
    writers.store_summary('synthetic', 'card', token, 1, {'title': 'Synthetic'}, AT, firestore_client=strict)
    assert _processed('finished') == before + 1 and strict.rows[card]['terminal_family_at'] == stamped


def test_failed_processing_stamps_once_and_counts_once(strict, live_lane):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'status': 'processing', 'sync_content_revision': 1}
    strict.rows[path] = dict(row, transcript_segments=[{'text': 'speech'}])
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    before = _unsummarized('failed')
    assert writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)
    stamped = strict.rows[path]['terminal_family_at']
    assert strict.rows[path]['status'] == 'completed' and 'terminal_family' not in strict.rows[path]
    assert not writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)
    assert strict.rows[path]['terminal_family_at'] == stamped
    assert _unsummarized('failed') == before + 1


@pytest.mark.parametrize('prior', [None, 'processing', 'completed'])
def test_projection_stamps_only_rows_it_moves_onto_completed(strict, prior, live_lane):
    cid_path = ('users', 'synthetic', 'conversations', 'c')
    existing = {}
    if prior is not None:
        stored = {'id': 'c', 'status': prior, **({'terminal_family_at': AT} if prior == 'completed' else {})}
        strict.rows[cid_path] = stored
        existing = {'c': {**stored, '_v3_revision': 1}}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    row = {
        **(existing.get('c') or {}),
        **writers.failure_patch(reason='outline'),
        'id': 'c',
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': [],
        'transcript_segments': [],
        'structured': {},
    }
    store.commit_projection('synthetic', token, {}, existing, [row], [], firestore_client=strict)
    written = strict.rows[cid_path]['terminal_family_at']
    assert written == AT if prior == 'completed' else written != AT
