"""Round-2 durable-teaching hardening contracts.

Read-budget projections reconcile each conversation's ledger at most once per
request; ledger admission bounds serialized document bytes so bookkeeping can
never abort a manual label; live teaching persists its connection's real
sample rate; a missing ledger lazily admits receipt-authorized legacy work
exactly once. Strict fake storage, synthetic audio, fake providers only.
"""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import timedelta
import json
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from google.cloud.firestore_v1._helpers import encode_dict
from google.cloud.firestore_v1.types import Document
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol
from database import conversations as db
from database import speaker_assignment_effects as assignment_effects
from database import speaker_learning_jobs as ledger
from database import users as users_db
from utils import speaker_learning_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestoreCollection,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
from tests.unit.test_speaker_learning_durable_jobs import (
    world,
    assign,
    jobs_map,
    the_job,
    advance,
    _segments,
    _fail_attempt,
    UID,
    CONV,
    NOW,
    CONV_PATH,
    LEDGER_PATH,
    PERSON_PATH,
)
from tests.unit.test_speaker_learning_pool import world as pool_world
from tests.unit import test_speaker_learning_pool as pool


def setup_people(world, monkeypatch, count=30):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(count)
    for i in range(count):
        world.store.rows[('users', UID, 'people', f'p{i}')] = dict(id=f'p{i}', name=f'Person {i}')
    del world.store.rows[('users', UID, 'people', 'p')]
    monkeypatch.setattr(users_db, 'db', world.store)
    reads = []
    original = StrictFirestoreDocument.get

    def counted_get(ref, *args, **kwargs):
        reads.append(ref.path)
        return original(ref, *args, **kwargs)

    def stream(collection):
        for path, row in world.store.rows.items():
            if path[:-1] == collection._path:
                reads.append(path)
                snap = StrictFirestoreSnapshot(row)
                snap.id = path[-1]
                yield snap

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted_get)
    monkeypatch.setattr(StrictFirestoreCollection, 'stream', stream)
    return reads


@pytest.mark.parametrize(
    'pending,retained,before,after',
    [(0, 0, 30, 30), (1, 1, 36, 36), (30, 30, 2820, 123), (0, 30, 1020, 63), (1, 30, 1080, 65)],
)
def test_get_people_reconciles_each_ledger_once(world, monkeypatch, pending, retained, before, after):
    reads = setup_people(world, monkeypatch)
    for i in range(retained):
        assign(person_id=f'p{i}', segment_ids=[f's{i}'])
    for i, job in enumerate(world.store.rows.get(LEDGER_PATH, {}).get('jobs', {}).values()):
        if i >= pending:
            ledger._transition_terminal(job, 'text_mismatch')
    reads.clear()
    people = users_db.get_people(UID)
    assert len(people) == 30
    print(f'READ_COUNT pending={pending} retained={retained} people=30 total={len(reads)}')
    assert len(reads) == after


def test_projection_cache_is_fresh_per_request(world, monkeypatch):
    setup_people(world, monkeypatch, count=1)
    assign(person_id='p0', segment_ids=['s0'])
    assert users_db.get_people(UID)[0]['voice_learning_state'] == 'pending'
    assign(person_id='p0', segment_ids=['s0'], use_for_speech_training=False)
    assert users_db.get_people(UID)[0]['voice_learning_state'] != 'pending'


def test_projection_cache_keys_by_conversation(world, monkeypatch):
    reads = setup_people(world, monkeypatch, count=3)
    world.store.rows[('users', UID, 'conversations', 'c2')] = dict(
        id='c2', status='completed', transcript_segments=_segments(3)
    )
    assign(person_id='p0', segment_ids=['s0'])
    assign(person_id='p2', segment_ids=['s1'])
    assign(cid='c2', person_id='p1', segment_ids=['s0'])
    reads.clear()
    people = {p['id']: p for p in users_db.get_people(UID)}
    assert all(people[pid]['voice_learning_state'] == 'pending' for pid in ('p0', 'p1', 'p2'))
    ledger_reads = [path for path in reads if path[:3] == ('users', UID, 'speaker_learning_jobs')]
    assert sorted(ledger_reads) == [
        ('users', UID, 'speaker_learning_jobs', CONV),
        ('users', UID, 'speaker_learning_jobs', 'c2'),
    ]


def test_failed_ledger_projection_preserves_person(world, monkeypatch):
    assign(person_id='p', segment_ids=['s0'])

    def boom(*args, **kwargs):
        raise RuntimeError('ledger read failed')

    monkeypatch.setattr(ledger, 'run_transactional', boom)
    person = deepcopy(world.store.rows[PERSON_PATH])
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['id'] == 'p' and projected['name'] == 'Sam'
    assert projected['voice_learning_state'] != 'pending'


def _encoded_size(document: dict) -> int:
    return len(Document.serialize(Document(fields=encode_dict(document))))


def _ledger_bytes(store):
    return _encoded_size({'jobs': jobs_map(store)})


def test_ledger_byte_budget_holds_across_repeated_real_labels(world):
    ids = [f'{i:03d}-' + 'x' * 252 for i in range(200)]
    segments = _segments(200)
    for item, sid in zip(segments, ids):
        item['id'] = sid
    world.store.rows[CONV_PATH]['transcript_segments'] = segments
    for _ in range(6):
        assign(person_id='p', speaker_id=0)
        assert _ledger_bytes(world.store) <= 256 * 1024
        assert len(jobs_map(world.store)) <= ledger.MAX_JOBS
    for transaction in world.store.transactions:
        for path, payload in transaction.sets:
            if path == LEDGER_PATH:
                assert _encoded_size(payload) <= 1024 * 1024
    assert ('person', 'capacity_exhausted') in world.events
    assert any(job['state'] == 'pending' for job in jobs_map(world.store).values())


def test_preseeded_oversized_ledger_is_pruned_on_next_label(world):
    jobs_doc = {}
    for i in range(8):
        seeded = ledger._new_job(
            CONV, 'person', 'p', 0, [f'k{i}-{j}-' + 'x' * 700 for j in range(60)], None, world.clock[0]
        )
        ledger._transition_terminal(seeded, 'stored')
        jobs_doc[f'pre-{i}'] = seeded
    world.store.rows[LEDGER_PATH] = {'jobs': jobs_doc}
    assert _ledger_bytes(world.store) > ledger.MAX_LEDGER_BYTES
    assign(person_id='p', segment_ids=['s0'])
    assert _ledger_bytes(world.store) <= ledger.MAX_LEDGER_BYTES
    assert any(job['state'] == 'pending' and job['segment_ids'] == ['s0'] for job in jobs_map(world.store).values())


def test_oversized_malformed_ledger_stays_bounded_without_failing_label(world):
    jobs_doc = {
        f'j{i}': dict(
            ledger._new_job(
                CONV,
                'person',
                f'px{i}',
                0,
                [f'z{i}-{j}-' + 'y' * 700 for j in range(60)],
                None,
                world.clock[0],
            )
        )
        for i in range(40)
    }
    world.store.rows[LEDGER_PATH] = {'jobs': jobs_doc}
    raw, _, _, _ = assign(person_id='p', segment_ids=['s0'])
    assert _ledger_bytes(world.store) <= ledger.MAX_LEDGER_BYTES
    assert len(jobs_map(world.store)) <= ledger.MAX_JOBS
    person = world.store.rows[PERSON_PATH]
    assert person['voice_learning_job']['conversation_id'] == CONV
    transaction = world.store.transactions[-1]
    total_writes = len(transaction.sets) + len(transaction.updates) + len(transaction.creates)
    assert total_writes < 500


def test_one_huge_candidate_commits_label_as_terminal_capacity(world):
    big_id = 'h' * (ledger.MAX_LEDGER_BYTES + 4096)
    segment = dict(_segments(1)[0], id=big_id)
    world.store.rows[CONV_PATH]['transcript_segments'] = [segment]
    raw, _, _, _ = assign(person_id='p', segment_ids=[big_id], use_for_speech_training=True)
    assert raw['_speaker_learning_queued'] is False
    assert ('person', 'queued') not in world.events
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'capacity_exhausted'
    assert job['segment_ids'] == []
    assert _ledger_bytes(world.store) <= ledger.MAX_LEDGER_BYTES
    assert any(s.get('person_id') == 'p' for s in raw['transcript_segments'])


def test_bookkeeping_failure_keeps_label_and_evidence(world, monkeypatch):
    def broken(*args, **kwargs):
        kwargs['updates']['p']['voice_learning_job'] = {'conversation_id': 'leak', 'job_id': 'leak'}
        kwargs['updates']['injected'] = {'voice_learning_job': {'conversation_id': 'x', 'job_id': 'y'}}
        raise RuntimeError('document size rejection')

    monkeypatch.setattr(assignment_effects.learning_jobs, 'prepare_assignment_jobs', broken)
    raw, _, _, _ = assign(person_id='p', segment_ids=['s0'])
    assert raw['_speaker_learning_queued'] is False
    assert any(s.get('person_id') == 'p' for s in raw['transcript_segments'])
    person = world.store.rows[PERSON_PATH]
    assert 'voice_learning_job' not in person
    assert 'updated_at' in person
    assert LEDGER_PATH not in world.store.rows


def test_ensure_job_persists_rate_on_new_job(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[LEDGER_PATH] = {'jobs': {}}
    job_id = ledger.ensure_job(
        UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=24000, firestore_client=world.store
    )
    assert jobs_map(world.store)[job_id]['sample_rate'] == 24000


def test_ensure_job_updates_pending_rate_without_resetting_attempts(world):
    assign(person_id='p', segment_ids=['s0'])
    job_id, job = the_job(world.store)
    assert 'sample_rate' not in job
    assert (
        ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=24000, firestore_client=world.store)
        is None
    )
    job = jobs_map(world.store)[job_id]
    assert job['sample_rate'] == 24000
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    job = jobs_map(world.store)[job_id]
    assert job['attempts'] == 1 and job['state'] == 'pending'
    expires_at = job['expires_at']
    assert (
        ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=8000, firestore_client=world.store)
        is None
    )
    job = jobs_map(world.store)[job_id]
    assert job['sample_rate'] == 8000 and job['attempts'] == 1 and job['expires_at'] == expires_at
    assert world.events.count(('person', 'queued')) == 1


@pytest.mark.parametrize('bad_rate', [True, 16000.0, '24000', 7999, 48001, -1])
def test_ensure_job_ignores_invalid_rates(world, bad_rate):
    assign(person_id='p', segment_ids=['s0'])
    job_id, _ = the_job(world.store)
    ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=bad_rate, firestore_client=world.store)
    assert 'sample_rate' not in jobs_map(world.store)[job_id]


def test_running_job_rate_is_not_rewritten(world):
    assign(person_id='p', segment_ids=['s0'])
    job_id, _ = the_job(world.store)
    ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=24000, firestore_client=world.store)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed['sample_rate'] == 24000
    ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=8000, firestore_client=world.store)
    assert jobs_map(world.store)[job_id]['sample_rate'] == 24000


def test_coordinator_cycle_and_restart_retry_preserve_rate(world):
    assign(person_id='p', segment_ids=['s0'])
    ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=24000, firestore_client=world.store)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_args.kwargs['sample_rate'] == 24000
    advance(world.clock, 31)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 2
    assert world.extract.await_args.kwargs['sample_rate'] == 24000


def test_live_24k_job_teaches_at_persisted_rate(pool_world, monkeypatch):
    rate = 24000
    pcm = b'\x01\x00' * (rate * 60)
    pool_world.store.rows[pool.CONV_PATH] = pool.conversation(
        [pool.seg('s0', 0, 12)], receipt=pool.receipt_segments(['s0'])
    )
    chunk = {
        'timestamp': pool.STARTED_AT,
        'path': f'fake/{pool.STARTED_AT}.bin',
        'span': {'start': pool.STARTED_AT, 'samples': rate * 60, 'sample_rate': rate},
    }
    monkeypatch.setattr(pool.storage, 'list_audio_chunks', lambda *a, **k: [chunk])
    monkeypatch.setattr(pool.storage, 'download_audio_chunks_and_merge', lambda *a, **k: pcm)

    def fake_chunks(*args, **kwargs):
        yield pool.STARTED_AT, pcm

    monkeypatch.setattr(pool.speaker_audio, 'iter_audio_chunk_pcm', fake_chunks)
    monkeypatch.setattr(jobs, 'extract_speaker_samples', pool.teaching.extract_speaker_samples)
    outcome = asyncio.run(
        jobs._execute_job(
            pool.UID,
            pool.CONV,
            dict(target='person', person_id=pool.PERSON, segment_ids=['s0'], sample_rate=rate),
        )
    )
    assert outcome == 'stored'
    legacy = asyncio.run(
        jobs._execute_job(pool.UID, pool.CONV, dict(target='person', person_id=pool.PERSON, segment_ids=['s0']))
    )
    assert legacy == 'uncovered_audio'


def test_pusher_speaker_request_forwards_live_sample_rate(monkeypatch):
    captured = []

    async def fake_learning(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(pusher, 'run_authorized_person_learning', fake_learning)
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setattr(pusher, 'SPEAKER_SAMPLE_PROCESS_INTERVAL', 0.01)
    monkeypatch.setattr(pusher, 'SPEAKER_SAMPLE_MIN_AGE', 0.0)
    frame = (
        struct.pack('<I', 105) + json.dumps({'person_id': 'p', 'conversation_id': 'c', 'segment_ids': ['s0']}).encode()
    )

    class SampleRequestSocket:
        def __init__(self):
            self.frames = deque([frame])
            self.client_state = WebSocketState.CONNECTED

        async def accept(self):
            return None

        async def close(self, code=1000, reason=None):
            self.client_state = WebSocketState.DISCONNECTED

        async def receive_bytes(self):
            if self.frames:
                return self.frames.popleft()
            raise WebSocketDisconnect(1000)

    asyncio.run(pusher._websocket_util_trigger(SampleRequestSocket(), 'uid', 24000))
    assert captured and captured[0].get('sample_rate') == 24000


def _drop_durable_markers(world):
    world.store.rows.pop(LEDGER_PATH, None)
    world.store.rows[PERSON_PATH].pop('voice_learning_job', None)


def test_missing_ledger_lazily_admits_authorized_legacy_work_once(world):
    assign(person_id='p', segment_ids=['s0'])
    _drop_durable_markers(world)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 1
    _, job = the_job(world.store)
    assert job['attempts'] == 1 and job['state'] == 'pending'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 1, 'backoff skips and the ledger marker blocks rescanning'


def test_legacy_admission_never_readmits_after_exhaustion(world):
    assign(person_id='p', segment_ids=['s0'])
    _drop_durable_markers(world)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    advance(world.clock, 3601)
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        _fail_attempt(world)
    job = the_job(world.store)[1]
    assert job['state'] == 'terminal' and job['last_outcome'] == 'exhausted'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 1


def test_existing_empty_ledger_never_bootstraps(world):
    assign(person_id='p', segment_ids=['s0'])
    _drop_durable_markers(world)
    world.store.rows[LEDGER_PATH] = {'jobs': {}}
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0
    assert jobs_map(world.store) == {}


def test_missing_ledger_marker_persists_without_candidates(world):
    _drop_durable_markers(world)
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert world.store.rows[LEDGER_PATH] == {'jobs': {}}
    before = deepcopy(world.store.rows[LEDGER_PATH])
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert world.store.rows[LEDGER_PATH] == before


def test_legacy_disabled_user_admits_nothing_but_marks(world):
    assign(person_id='p', segment_ids=['s0'])
    _drop_durable_markers(world)
    world.store.rows[('users', UID)]['save_other_voice_profiles'] = False
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0
    assert world.store.rows[LEDGER_PATH] == {'jobs': {}}


def test_legacy_opted_out_receipt_admits_nothing(world):
    assign(person_id='p', segment_ids=['s0'], use_for_speech_training=False)
    _drop_durable_markers(world)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0
    assert world.store.rows[LEDGER_PATH] == {'jobs': {}}


def test_legacy_ready_print_is_not_retaught(world):
    assign(person_id='p', segment_ids=['s0'])
    _drop_durable_markers(world)
    world.store.rows[PERSON_PATH].update(speech_samples=['a.wav'], speaker_embedding=[1.0], speech_samples_version=3)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0


@pytest.mark.parametrize('flag', ['deleted', 'is_locked', 'discarded'])
def test_legacy_source_lifecycle_never_extracts(world, flag):
    assign(person_id='p', segment_ids=['s0'])
    _drop_durable_markers(world)
    world.store.rows[CONV_PATH][flag] = True
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0


def test_legacy_admission_bounds_candidates(world):
    count = ledger.MAX_JOBS + 8
    segments = _segments(count)
    receipt = {'generation': 1, 'segments': {}}
    for i in range(count):
        pid = f'p{i}'
        segments[i]['person_id'] = pid
        receipt['segments'][f's{i}'] = {'person_id': pid, 'generation': 1, 'use_for_speech_training': True}
        world.store.rows[('users', UID, 'people', pid)] = dict(id=pid, name=f'Person {i}')
    world.store.rows[CONV_PATH]['transcript_segments'] = segments
    world.store.rows[CONV_PATH]['manual_speaker_assignments'] = receipt
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert len(jobs_map(world.store)) <= ledger.MAX_JOBS
    assert world.extract.await_count == jobs.VOICE_LEARNING_JOB_MAX_PER_PASS


def test_malformed_ledger_entry_never_aborts_the_label(world):
    world.store.rows[LEDGER_PATH] = {'jobs': {'bad': None}}
    raw, _, _, _ = assign(person_id='p', segment_ids=['s0'])
    assert any(s.get('person_id') == 'p' for s in raw['transcript_segments'])
    assert 'bad' not in jobs_map(world.store)
    assert _ledger_bytes(world.store) <= 256 * 1024


def test_ensure_job_updates_covered_prior_rate_across_receipt_bump(world):
    segments = _segments(3)
    segments[2]['speaker_id'] = 1
    world.store.rows[CONV_PATH]['transcript_segments'] = segments
    assign(person_id='p', segment_ids=['s0', 's1'])
    job_id, job = the_job(world.store)
    assign(is_user=True, segment_ids=['s2'], use_for_speech_training=True)
    assert len(jobs_map(world.store)) == 2
    assert (
        ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], sample_rate=24000, firestore_client=world.store)
        is None
    )
    job = jobs_map(world.store)[job_id]
    assert job['sample_rate'] == 24000 and job['attempts'] == 0
    assert world.events.count(('person', 'queued')) == 1


def test_targeted_claim_executes_only_the_requested_job(world):
    assign(person_id='p', segment_ids=['s0'])
    assign(is_user=True, segment_ids=['s1'], use_for_speech_training=True)
    outcome = asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0']))
    assert outcome == 'no_audio'
    assert world.extract.await_count == 1 and world.owner.await_count == 0
    by_target = {job['target']: job for job in jobs_map(world.store).values()}
    assert by_target['person']['attempts'] == 1
    assert by_target['owner']['attempts'] == 0 and by_target['owner']['state'] == 'pending'


def test_targeted_claim_prefers_newest_matching_job(world):
    assign(person_id='p', segment_ids=['s0', 's1'])
    assign(is_user=True, segment_ids=['s1'], use_for_speech_training=False)
    assign(person_id='p', segment_ids=['s0', 's1'])
    person_jobs = sorted(
        (job for job in jobs_map(world.store).values() if job['target'] == 'person'), key=ledger._job_created
    )
    assert len(person_jobs) >= 2
    outcome = asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0']))
    assert outcome == 'no_audio' and world.extract.await_count == 1
    refreshed = jobs_map(world.store)
    attempted = [job for job in refreshed.values() if job['target'] == 'person' and job['attempts'] == 1]
    assert len(attempted) == 1 and attempted[0]['generation'] == person_jobs[-1]['generation']


def test_repeat_immediate_call_never_consumes_older_duplicate(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    assign(person_id='p', segment_ids=['s0', 's1'])
    assign(is_user=True, segment_ids=['s2'], use_for_speech_training=False)
    assign(person_id='p', segment_ids=['s0', 's1'])
    assert asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0'])) == 'no_audio'
    assert asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0'])) == 'pending'
    assert world.extract.await_count == 1
    older = min((job for job in jobs_map(world.store).values() if job['target'] == 'person'), key=ledger._job_created)
    assert older['attempts'] == 0


@pytest.mark.parametrize('newest_state', ['running', 'backoff', 'terminal'])
def test_targeted_claim_never_falls_back_to_older_matching_job(world, newest_state):
    assign(person_id='p', segment_ids=['s0'])
    assign(is_user=True, segment_ids=['s1'], use_for_speech_training=False)
    assign(person_id='p', segment_ids=['s0'])
    person_jobs = sorted(
        (job for job in jobs_map(world.store).values() if job['target'] == 'person'), key=ledger._job_created
    )
    assert len(person_jobs) == 2
    newest = person_jobs[-1]
    if newest_state == 'running':
        newest['state'] = 'running'
        newest['lease_until'] = world.clock[0] + timedelta(minutes=5)
    elif newest_state == 'backoff':
        newest['next_attempt_at'] = world.clock[0] + timedelta(minutes=5)
    else:
        ledger._transition_terminal(newest, 'text_mismatch')
    claimed = ledger.claim_next_job(
        UID,
        CONV,
        assignment={'target': 'person', 'person_id': 'p', 'segment_ids': ['s0']},
        now=world.clock[0],
        firestore_client=world.store,
    )
    assert claimed is None
    assert person_jobs[0]['attempts'] == 0


def test_ensure_job_updates_newest_covered_prior_rate(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    assign(person_id='p', segment_ids=['s0', 's1', 's2'])
    older = ledger._new_job(CONV, 'person', 'p', 1, ['s0', 's1'], None, world.clock[0])
    newer = ledger._new_job(CONV, 'person', 'p', 1, ['s0', 's1', 's2'], None, world.clock[0] + timedelta(seconds=1))
    world.store.rows[LEDGER_PATH] = {'jobs': {'j-old': older, 'j-new': newer}}
    advance(world.clock, 2)
    outcome = asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0'], sample_rate=24000))
    assert outcome == 'no_audio'
    assert world.extract.await_args.kwargs['sample_rate'] == 24000
    refreshed = jobs_map(world.store)
    assert refreshed['j-new']['attempts'] == 1 and refreshed['j-new']['sample_rate'] == 24000
    assert refreshed['j-old']['attempts'] == 0 and 'sample_rate' not in refreshed['j-old']


def test_immediate_learning_run_respects_deadline(world, monkeypatch):
    assign(person_id='p', segment_ids=['s0'])

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    world.extract.side_effect = hang
    monkeypatch.setattr(jobs, 'VOICE_LEARNING_RETRY_DEADLINE_SECONDS', 0.2)
    outcome = asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0']))
    assert outcome == 'timeout'
    _, job = the_job(world.store)
    assert job['attempts'] == 1 and job['last_outcome'] == 'timeout' and job['state'] == 'pending'
    assert job['lease_token'] is None


def test_targeted_claim_in_backoff_never_duplicates_provider_work(world):
    assign(person_id='p', segment_ids=['s0'])
    assert asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0'])) == 'no_audio'
    assert asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0'])) == 'pending'
    assert world.extract.await_count == 1
    _, job = the_job(world.store)
    assert job['attempts'] == 1


def test_bookkeeping_failure_still_runs_the_direct_request(world, monkeypatch):
    assign(person_id='p', segment_ids=['s0'])

    def broken(*args, **kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(ledger, 'ensure_job', broken)
    outcome = asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0']))
    assert outcome == 'no_audio'
    assert world.extract.await_count == 1
    assert the_job(world.store)[1]['attempts'] == 0


def test_owner_bookkeeping_failure_preserves_contribution_retraction(world, monkeypatch):
    world.store.rows[('users', UID)]['speaker_embedding'] = [1.0, 0.0]
    world.store.rows[('users', UID)]['owner_voice_pooled_at'] = world.clock[0]
    world.store.rows[('users', UID)]['owner_voice_confirmations'] = [
        {'conversation_id': CONV, 'segment_ids': ['s1'], 'generation': 1, 'at': world.clock[0], 'embedding': [1.0, 0.0]}
    ]
    monkeypatch.setattr(
        assignment_effects.learning_jobs,
        'prepare_assignment_jobs',
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')),
    )
    raw, _, _, _ = assign(person_id='p', segment_ids=['s1'])
    assert any(s.get('person_id') == 'p' for s in raw['transcript_segments'])
    person = world.store.rows[PERSON_PATH]
    assert 'voice_learning_job' not in person
    assert world.store.rows[('users', UID)]['speaker_embedding'] is None
    assert world.store.rows[('users', UID)]['owner_voice_confirmations'] == []
