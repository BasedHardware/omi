"""Durable speaker-learning ledger and coordinator contracts.

The assignment transaction commits a bounded per-conversation job ledger;
the coordinator claims jobs under leases and finishes them against the same
publication fences. Tests drive real transactions over synthetic storage with
an injected clock — no timers, no provider calls.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import conversations as db
from database import speaker_learning_jobs as ledger
from models.person_confidence import SOURCE_CARD
from utils import speaker_learning_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

UID = 'u'
CONV = 'c'
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
LEDGER_PATH = ('users', UID, 'speaker_learning_jobs', CONV)
CONV_PATH = ('users', UID, 'conversations', CONV)
PERSON_PATH = ('users', UID, 'people', 'p')


def _segments(count=2, person_id=None, is_user=False):
    return [
        dict(
            id=f's{i}',
            speaker='SPEAKER_00',
            speaker_id=0,
            text='Synthetic speech',
            start=i * 10.0,
            end=i * 10.0 + 8.0,
            is_user=is_user,
            person_id=person_id,
        )
        for i in range(count)
    ]


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    store.rows[CONV_PATH] = dict(id=CONV, status='completed', transcript_segments=_segments())
    store.rows[PERSON_PATH] = dict(id='p', name='Sam')
    store.rows[('users', UID)] = dict(uid=UID)
    clock = [datetime.now(timezone.utc) + timedelta(seconds=5)]
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(ledger, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(ledger, '_now', lambda: clock[0])
    events = []
    monkeypatch.setattr(ledger, 'record_speaker_learning_job_events', events.extend)
    # database.conversations imports the recorder from the ledger module at call time.
    extract = AsyncMock(return_value='no_audio')
    monkeypatch.setattr(jobs, 'extract_speaker_samples', extract)
    owner = AsyncMock(return_value='no_audio')
    monkeypatch.setitem(
        sys.modules,
        'utils.speaker_tag_prompts.service',
        SimpleNamespace(store_owner_voice_sample=owner),
    )
    return SimpleNamespace(store=store, clock=clock, events=events, extract=extract, owner=owner)


def assign(uid=UID, cid=CONV, **kwargs):
    return db.assign_conversation_speaker(uid, cid, **kwargs)


def jobs_map(store, cid=CONV):
    return dict((store.rows.get(('users', UID, 'speaker_learning_jobs', cid)) or {}).get('jobs') or {})


def the_job(store):
    found = jobs_map(store)
    assert len(found) == 1
    job_id, job = next(iter(found.items()))
    return job_id, job


def advance(clock, seconds):
    clock[0] = clock[0] + timedelta(seconds=seconds)


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_assignment_commits_durable_job_at_label_time(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    job_id, job = the_job(world.store)
    assert job['target'] == target and job['state'] == 'pending'
    assert job['attempts'] == 0 and job['segment_ids'] == ['s0']
    assert job['expires_at'] - job['created_at'] == ledger.JOB_LIFETIME
    if target == 'person':
        person = world.store.rows[PERSON_PATH]
        assert person['voice_learning_job'] == {'conversation_id': CONV, 'job_id': job_id}
    assert (target, 'queued') in world.events


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_coordinator_records_retryable_attempt_with_backoff(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    _, job = the_job(world.store)
    assert job['attempts'] == 1 and job['state'] == 'pending'
    assert job['last_outcome'] == 'no_audio'
    delay = (job['next_attempt_at'] - world.clock[0]).total_seconds()
    assert 0 < delay <= ledger.RETRY_DELAYS[0]
    worker = world.extract if target == 'person' else world.owner
    assert worker.await_count == 1


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_backoff_skips_then_audio_arrival_stores(world, target, monkeypatch):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    if target == 'person':

        async def decide(uid, person_id, cid, ids):
            return 'stored' if (world.store.rows.get(CONV_PATH) or {}).get('audio_files') else 'no_audio'

        world.extract.side_effect = decide
        worker = world.extract
    else:

        async def decide_owner(uid, cid, ids, **kwargs):
            return 'stored' if (world.store.rows.get(CONV_PATH) or {}).get('audio_files') else 'no_audio'

        world.owner.side_effect = decide_owner
        worker = world.owner
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert worker.await_count == 1, 'backoff must not consume attempts before next_attempt_at'
    _, job = the_job(world.store)
    assert job['attempts'] == 1
    world.store.rows[CONV_PATH]['audio_files'] = [{'name': 'a.bin'}]
    advance(world.clock, 60)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'stored'
    assert job['attempts'] == 2 and worker.await_count == 2


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_restart_runs_from_storage_without_local_state(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
        world.extract.return_value = 'stored'
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
        world.owner.return_value = 'stored'
    jobs._in_flight_retries.clear()
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'stored'


def test_owner_card_job_keeps_exact_subset_and_card_generation(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3, is_user=True)
    assign(
        is_user=True,
        speaker_id=0,
        use_for_speech_training=False,
        evidence_source=SOURCE_CARD,
        owner_segment_ids=['s0', 's2'],
    )
    _, job = the_job(world.store)
    assert job['target'] == 'owner' and job['card_generation'] == 1
    assert sorted(job['segment_ids']) == ['s0', 's2']


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_duplicate_ensure_and_delivery_do_not_duplicate_work(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    job_id, job = the_job(world.store)
    again = ledger.ensure_job(
        UID,
        CONV,
        person_id='p' if target == 'person' else None,
        segment_ids=['s0'],
        firestore_client=world.store,
    )
    assert again is None and len(jobs_map(world.store)) == 1
    provider = world.extract if target == 'person' else world.owner
    provider.return_value = 'stored'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert provider.await_count == 1
    assert the_job(world.store)[1]['state'] == 'terminal'


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_running_lease_blocks_duplicate_claim_and_stale_token_is_ignored(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    first = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert first and ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert (
        ledger.finish_job(
            UID, CONV, first['job_id'], 'stale-token', 'error', now=world.clock[0], firestore_client=world.store
        )
        is False
    )
    _, job = the_job(world.store)
    assert job['state'] == 'running'
    advance(world.clock, 121)
    reclaimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert reclaimed['job_id'] == first['job_id'] and reclaimed['attempts'] == 2
    assert reclaimed['lease_token'] != first['lease_token']
    assert (
        ledger.finish_job(
            UID, CONV, first['job_id'], first['lease_token'], 'error', now=world.clock[0], firestore_client=world.store
        )
        is False
    )


def test_crash_after_publication_is_recognized_stored(world):
    assign(person_id='p', segment_ids=['s0'])
    _publish_person(world)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed is None, 'reconcile must terminalize the already-published job'
    assert the_job(world.store)[1]['last_outcome'] == 'stored'


def test_relabel_supersedes_pending_job(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s0'])
    found = jobs_map(world.store)
    p_job = next(j for j in found.values() if j.get('person_id') == 'p')
    assert p_job['state'] == 'terminal' and p_job['last_outcome'] == 'superseded'
    q_job = next(j for j in found.values() if j.get('person_id') == 'q')
    assert q_job['state'] == 'pending'


def test_unrelated_label_bump_does_not_revoke_person_or_owner(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(4)
    assign(person_id='p', segment_ids=['s0'])
    assign(is_user=True, segment_ids=['s1'], use_for_speech_training=True)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s2'])
    found = jobs_map(world.store)
    live = [j for j in found.values() if j['state'] != 'terminal']
    targets = {j['target'] for j in live}
    assert 'person' in targets and 'owner' in targets


def test_owner_relabel_revokes_owner_job(world):
    assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s0'])
    found = jobs_map(world.store)
    owner_job = next(j for j in found.values() if j.get('target') == 'owner')
    assert owner_job['state'] == 'terminal' and owner_job['last_outcome'] == 'superseded'


@pytest.mark.parametrize('target', ['person', 'owner'])
@pytest.mark.parametrize('flag,outcome', [('deleted', 'deleted'), ('is_locked', 'locked'), ('discarded', 'discarded')])
def test_source_lifecycle_flags_terminal_without_extraction(world, flag, outcome, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    world.store.rows[CONV_PATH][flag] = True
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    job = the_job(world.store)[1]
    assert job['state'] == 'terminal' and job['last_outcome'] == outcome
    assert world.extract.await_count == 0 and world.owner.await_count == 0


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_missing_conversation_terminalizes_as_deleted(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    del world.store.rows[CONV_PATH]
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert the_job(world.store)[1]['last_outcome'] == 'deleted'


def test_five_retryable_failures_exhaust(world):
    assign(person_id='p', segment_ids=['s0'])
    for attempt in range(ledger.MAX_ATTEMPTS):
        claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
        assert claimed, f'attempt {attempt + 1} must be claimable'
        ledger.finish_job(
            UID,
            CONV,
            claimed['job_id'],
            claimed['lease_token'],
            'error',
            now=world.clock[0],
            firestore_client=world.store,
        )
        advance(world.clock, 3601)
    job = the_job(world.store)[1]
    assert job['state'] == 'terminal' and job['last_outcome'] == 'exhausted'
    assert job['attempts'] == ledger.MAX_ATTEMPTS


def test_seven_day_expiry_terminalizes(world):
    assign(person_id='p', segment_ids=['s0'])
    advance(world.clock, 8 * 24 * 3600)
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert the_job(world.store)[1]['last_outcome'] == 'exhausted'


def test_pass_bound_and_fairness_across_invocations(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(7)
    for i in range(7):
        world.store.rows[('users', UID, 'people', f'p{i}')] = dict(id=f'p{i}', name=f'p{i}')
        assign(person_id=f'p{i}', segment_ids=[f's{i}'])
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == jobs.VOICE_LEARNING_JOB_MAX_PER_PASS
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 7
    calls = [c.args[1] for c in world.extract.await_args_list]
    assert calls == [f'p{i}' for i in range(7)], 'oldest pending jobs run first across passes'


def _seed_authorized_jobs(world, count, *, terminal=0):
    """Seed valid pending jobs sharing person 'p''s authorized s0 contribution."""
    assign(person_id='p', segment_ids=['s0'])
    job_id, job = the_job(world.store)
    jobs_doc = {job_id: job}
    for i in range(count - 1):
        seeded = ledger._new_job(CONV, 'person', 'p', 1, ['s0'], None, world.clock[0] - timedelta(minutes=count - i))
        if i < terminal:
            ledger._transition_terminal(seeded, 'stored')
        jobs_doc[f'seeded-{i}'] = seeded
    world.store.rows[LEDGER_PATH] = {'jobs': jobs_doc}


def test_capacity_prunes_terminal_first(world):
    _seed_authorized_jobs(world, ledger.MAX_JOBS, terminal=4)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s1'])
    found = jobs_map(world.store)
    assert len(found) <= ledger.MAX_JOBS
    assert 'seeded-0' not in found, 'the oldest terminal entry prunes first'
    terminal = [j for j in found.values() if j['state'] == 'terminal']
    assert len(terminal) <= 3
    assert any(j['person_id'] == 'q' and j['state'] == 'pending' for j in found.values())


def test_capacity_terminalizes_oldest_active(world):
    _seed_authorized_jobs(world, ledger.MAX_JOBS)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s1'])
    found = jobs_map(world.store)
    assert len(found) == ledger.MAX_JOBS
    assert 'seeded-0' not in found, 'the oldest active job yields to the new admission'
    assert ('person', 'capacity_exhausted') in world.events
    assert any(j['state'] == 'pending' for j in found.values())


def test_segment_cap_records_terminal_segment_limit(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(ledger.MAX_SEGMENT_IDS + 1)
    ids = [f's{i}' for i in range(ledger.MAX_SEGMENT_IDS + 1)]
    assign(person_id='p', segment_ids=ids)
    job = the_job(world.store)[1]
    assert job['state'] == 'terminal' and job['last_outcome'] == 'segment_limit'
    assert len(job['segment_ids']) == ledger.MAX_SEGMENT_IDS
    assert world.extract.await_count == 0


def test_save_other_disabled_terminalizes_person_job(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[('users', UID)]['save_other_voice_profiles'] = False
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert the_job(world.store)[1]['last_outcome'] == 'disabled'


def test_save_other_disabled_queues_no_person_job(world):
    world.store.rows[('users', UID)]['save_other_voice_profiles'] = False
    assign(person_id='p', segment_ids=['s0'])
    assert jobs_map(world.store) == {}


def test_quality_failure_is_terminal_not_retried(world):
    assign(person_id='p', segment_ids=['s0'])
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'insufficient_speech',
        now=world.clock[0],
        firestore_client=world.store,
    )
    job = the_job(world.store)[1]
    assert job['state'] == 'terminal' and job['last_outcome'] == 'insufficient_speech'
    assert world.store.rows[PERSON_PATH]['voice_learning_state'] == 'needs_more_speech'


def test_terminal_job_never_requeues_on_duplicate_ensure(world):
    assign(person_id='p', segment_ids=['s0'])
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'text_mismatch',
        now=world.clock[0],
        firestore_client=world.store,
    )
    job_id, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'text_mismatch'
    attempts = job['attempts']
    assert ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], firestore_client=world.store) is None
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    _, job = the_job(world.store)
    assert job['attempts'] == attempts and world.extract.await_count == 0


def test_projector_pending_only_while_live_job(world):
    assign(person_id='p', segment_ids=['s0'])
    person = deepcopy(world.store.rows[PERSON_PATH])
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['voice_learning_state'] == 'pending'
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'contaminated',
        now=world.clock[0],
        firestore_client=world.store,
    )
    person = deepcopy(world.store.rows[PERSON_PATH])
    assert (
        ledger.project_person_learning(UID, person, firestore_client=world.store)['voice_learning_state'] == 'unknown'
    )


def test_projector_legacy_pending_without_pointer_is_unknown(world):
    person = {'id': 'p', 'voice_learning_state': 'pending', 'voice_needed_seconds': 42}
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['voice_learning_state'] == 'unknown' and projected['voice_needed_seconds'] is None


def test_projector_ready_print_stays_learned(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[PERSON_PATH].update(speech_samples=['a.wav'], speaker_embedding=[1.0], speech_samples_version=3)
    person = deepcopy(world.store.rows[PERSON_PATH])
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['voice_learning_state'] == 'learned'


def test_projector_ready_print_under_disabled_settings_is_disabled(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[PERSON_PATH].update(speech_samples=['a.wav'], speaker_embedding=[1.0], speech_samples_version=3)
    world.store.rows[('users', UID)]['save_other_voice_profiles'] = False
    person = deepcopy(world.store.rows[PERSON_PATH])
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['voice_learning_state'] == 'disabled'


def test_projector_pointer_to_another_person_is_not_pending(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    person = deepcopy(world.store.rows[('users', UID, 'people', 'q')])
    job_id, _ = the_job(world.store)
    person['voice_learning_job'] = {'conversation_id': CONV, 'job_id': job_id}
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['voice_learning_state'] != 'pending'


def test_stale_worker_cannot_overwrite_newer_pointer(world):
    assign(person_id='p', segment_ids=['s0'])
    job_id, _ = the_job(world.store)
    world.store.rows[PERSON_PATH]['voice_learning_job'] = {'conversation_id': CONV, 'job_id': 'newer'}
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'stored',
        now=world.clock[0],
        firestore_client=world.store,
    )
    person = world.store.rows[PERSON_PATH]
    assert person['voice_learning_job']['job_id'] == 'newer'
    assert 'voice_learning_state' not in person or person['voice_learning_state'] != 'learned'


def test_ensure_job_for_legacy_live_request(world):
    assign(person_id='p', segment_ids=['s0'], use_for_speech_training=True)
    world.store.rows[LEDGER_PATH] = {'jobs': {}}
    job_id = ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], firestore_client=world.store)
    assert job_id and the_job(world.store)[1]['state'] == 'pending'


def test_manual_teaching_is_not_subscription_gated(world, monkeypatch):
    monkeypatch.setattr(
        'utils.speaker_permissions.users_db.get_user_valid_subscription',
        lambda uid, **kwargs: (_ for _ in ()).throw(AssertionError('no plan check on manual teaching')),
    )
    assign(person_id='p', segment_ids=['s0'])
    assert the_job(world.store)[1]['state'] == 'pending'


def _publish_person(world, *, person_id='p', ids=('s0',), generation=1, embedding=(1.0,)):
    _, job = the_job(world.store)
    world.store.rows[('users', UID, 'people', person_id)].update(
        speech_samples=['a.wav'],
        speech_sample_transcripts=['synthetic'],
        speech_samples_version=3,
        speaker_embedding=list(embedding),
        speech_sample_source={
            'conversation_id': CONV,
            'segment_ids': list(ids),
            'generation': generation,
            'stored_at': job['created_at'] + timedelta(seconds=1),
        },
    )


def _fail_attempt(world, outcome='error'):
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed, 'attempt must be claimable'
    applied = ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        outcome,
        now=world.clock[0],
        firestore_client=world.store,
    )
    advance(world.clock, 3601)
    return claimed, applied


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_fifth_attempt_success_stores(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
        worker = world.extract
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
        worker = world.owner
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        claimed, applied = _fail_attempt(world)
        assert applied
    worker.return_value = 'stored'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert worker.await_count == 1
    _, job = the_job(world.store)
    assert job['attempts'] == ledger.MAX_ATTEMPTS
    assert job['state'] == 'terminal' and job['last_outcome'] == 'stored'
    assert world.events.count((target, 'stored')) == 1


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_fifth_attempt_failure_is_exhausted(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
        worker = world.extract
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
        worker = world.owner
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        _fail_attempt(world)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert worker.await_count == 1
    _, job = the_job(world.store)
    assert job['attempts'] == ledger.MAX_ATTEMPTS
    assert job['state'] == 'terminal' and job['last_outcome'] == 'exhausted'
    assert world.events.count((target, 'exhausted')) == 1


def test_fifth_attempt_running_lease_stays_pending_for_projector(world):
    assign(person_id='p', segment_ids=['s0'])
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        _fail_attempt(world)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed
    _, job = the_job(world.store)
    assert job['state'] == 'running' and job['attempts'] == ledger.MAX_ATTEMPTS
    person = deepcopy(world.store.rows[PERSON_PATH])
    projected = ledger.project_person_learning(UID, person, firestore_client=world.store)
    assert projected['voice_learning_state'] == 'pending'
    applied = ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'stored',
        now=world.clock[0],
        firestore_client=world.store,
    )
    assert applied is True
    assert the_job(world.store)[1]['last_outcome'] == 'stored'


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_fifth_attempt_running_lease_is_not_terminalized(world, target):
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        _fail_attempt(world)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    _, job = the_job(world.store)
    assert job['state'] == 'running' and job['attempts'] == ledger.MAX_ATTEMPTS
    applied = ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'error',
        now=world.clock[0],
        firestore_client=world.store,
    )
    assert applied is True
    assert the_job(world.store)[1]['last_outcome'] == 'exhausted'


def test_expired_running_lease_with_publication_reconciles_stored(world):
    assign(person_id='p', segment_ids=['s0'])
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    _publish_person(world)
    advance(world.clock, 121)
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'stored'
    assert (
        ledger.finish_job(
            UID,
            CONV,
            claimed['job_id'],
            claimed['lease_token'],
            'error',
            now=world.clock[0],
            firestore_client=world.store,
        )
        is False
    )


def test_expired_running_lease_without_publication_is_exhausted(world):
    assign(person_id='p', segment_ids=['s0'])
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        _fail_attempt(world)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    advance(world.clock, 121)
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'exhausted'


def test_person_optout_after_publication_supersedes(world):
    assign(person_id='p', segment_ids=['s0'], use_for_speech_training=True)
    _publish_person(world)
    assign(person_id='p', segment_ids=['s0'], use_for_speech_training=False)
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'superseded'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0


def test_publication_before_current_label_is_not_accepted(world):
    assign(person_id='p', segment_ids=['s0'], use_for_speech_training=True)
    _, job = the_job(world.store)
    world.store.rows[PERSON_PATH].update(
        speech_samples=['a.wav'],
        speech_sample_transcripts=['synthetic'],
        speech_samples_version=3,
        speaker_embedding=[1.0],
        speech_sample_source={
            'conversation_id': CONV,
            'segment_ids': ['s0'],
            'generation': 0,
            'stored_at': job['created_at'] - timedelta(seconds=1),
        },
    )
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 1


def test_overlapping_foreign_source_is_not_accepted(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[PERSON_PATH].update(
        speech_samples=['a.wav'],
        speech_sample_transcripts=['synthetic'],
        speech_samples_version=3,
        speaker_embedding=[1.0],
        speech_sample_source={
            'conversation_id': CONV,
            'segment_ids': ['s0', 's9'],
            'generation': 1,
            'stored_at': datetime.now(timezone.utc),
        },
    )
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 1


def test_owner_stale_generation_confirmation_is_not_stored(world):
    assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    _, job = the_job(world.store)
    world.store.rows[('users', UID)].update(
        speaker_embedding=[1.0, 0.5],
        owner_voice_confirmations=[
            {
                'embedding': [1.0],
                'conversation_id': CONV,
                'segment_ids': ['s0'],
                'generation': 0,
                'at': job['created_at'] + timedelta(seconds=1),
            }
        ],
    )
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.owner.await_count == 1


def test_owner_old_confirmation_is_not_stored(world):
    assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    _, job = the_job(world.store)
    world.store.rows[('users', UID)].update(
        speaker_embedding=[1.0, 0.5],
        owner_voice_confirmations=[
            {
                'embedding': [1.0],
                'conversation_id': CONV,
                'segment_ids': ['s0'],
                'generation': job['generation'],
                'at': job['created_at'] - timedelta(seconds=1),
            }
        ],
    )
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.owner.await_count == 1


def test_owner_card_optout_revokes_job(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(2, is_user=True)
    assign(
        is_user=True,
        speaker_id=0,
        use_for_speech_training=False,
        evidence_source=SOURCE_CARD,
        owner_segment_ids=['s0', 's1'],
    )
    _, job = the_job(world.store)
    assert job['target'] == 'owner' and job['state'] == 'pending'
    assign(
        is_user=False,
        speaker_id=0,
        use_for_speech_training=False,
        rejection={'kind': 'not_me', 'person_id': None},
    )
    found = jobs_map(world.store)
    card_job = next(j for j in found.values() if j.get('card_generation') is not None)
    assert card_job['state'] == 'terminal' and card_job['last_outcome'] == 'superseded'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.owner.await_count == 0


def test_segment_limit_admission_emits_event(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(ledger.MAX_SEGMENT_IDS + 1)
    ids = [f's{i}' for i in range(ledger.MAX_SEGMENT_IDS + 1)]
    assign(person_id='p', segment_ids=ids)
    assert ('person', 'segment_limit') in world.events
    assert ('person', 'queued') not in world.events


def test_ensure_segment_limit_emits_event(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(ledger.MAX_SEGMENT_IDS + 1)
    ids = [f's{i}' for i in range(ledger.MAX_SEGMENT_IDS + 1)]
    assign(person_id='p', segment_ids=ids)
    world.events.clear()
    world.store.rows[LEDGER_PATH] = {'jobs': {}}
    ledger.ensure_job(UID, CONV, person_id='p', segment_ids=ids, firestore_client=world.store)
    assert ('person', 'segment_limit') in world.events


def test_retried_event_fires_on_actual_retry_claim(world):
    assign(person_id='p', segment_ids=['s0'])
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'no_audio',
        now=world.clock[0],
        firestore_client=world.store,
    )
    advance(world.clock, 31)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed['attempts'] == 2
    assert ('person', 'retried') in world.events
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'no_audio',
        now=world.clock[0],
        firestore_client=world.store,
    )
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'no_audio',
        now=world.clock[0],
        firestore_client=world.store,
    )
    assert world.events.count(('person', 'retried')) == 1


def test_no_retried_event_on_first_attempt(world):
    assign(person_id='p', segment_ids=['s0'])
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed['attempts'] == 1
    assert ('person', 'retried') not in world.events


def test_unknown_provider_outcome_normalizes_to_error(world):
    assign(person_id='p', segment_ids=['s0'])
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'arbitrary provider detail string',
        now=world.clock[0],
        firestore_client=world.store,
    )
    _, job = the_job(world.store)
    assert job['last_outcome'] == 'error'


def test_assignment_reports_durable_admission(world):
    raw, _, _, _ = assign(person_id='p', segment_ids=['s0'], use_for_speech_training=True)
    assert raw['_speaker_learning_queued'] is True
    raw2, _, _, _ = assign(person_id='p', segment_ids=['s1'], use_for_speech_training=False)
    assert raw2['_speaker_learning_queued'] is False


def test_discarded_assignment_admits_terminal_job(world):
    world.store.rows[CONV_PATH]['discarded'] = True
    raw, _, _, _ = assign(person_id='p', segment_ids=['s0'], use_for_speech_training=True)
    assert raw['_speaker_learning_queued'] is False
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'discarded'
    assert ('person', 'queued') not in world.events
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0


def test_transaction_retry_resets_results(world, monkeypatch):
    assign(person_id='p', segment_ids=['s0'])

    def twice(client, fn):
        fn(client.transaction())
        fn(client.transaction())

    monkeypatch.setattr(ledger, 'run_transactional', twice)
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    assert ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], firestore_client=world.store) is None
    advance(world.clock, 121)
    monkeypatch.undo()
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert claimed
    monkeypatch.setattr(ledger, 'run_transactional', twice)
    assert (
        ledger.finish_job(
            UID,
            CONV,
            claimed['job_id'],
            claimed['lease_token'],
            'stored',
            now=world.clock[0],
            firestore_client=world.store,
        )
        is False
    )


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_duplicate_ensure_after_unrelated_receipt_bump_keeps_one_job(world, target):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    job_id, job = the_job(world.store)
    assert job['target'] == target and job['state'] == 'pending'
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s1'])
    world.events.clear()
    assert (
        ledger.ensure_job(
            UID,
            CONV,
            person_id='p' if target == 'person' else None,
            segment_ids=['s0'],
            firestore_client=world.store,
        )
        is None
    )
    found = jobs_map(world.store)
    same = [
        j
        for j in found.values()
        if j.get('target') == target and j.get('person_id') == ('p' if target == 'person' else None)
    ]
    assert len(same) == 1 and same[0]['attempts'] == job['attempts']
    assert (target, 'queued') not in world.events


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_duplicate_ensure_after_unrelated_bump_never_requeues_terminal(world, target):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    if target == 'person':
        assign(person_id='p', segment_ids=['s0'])
    else:
        assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    claimed = ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store)
    assert ledger.finish_job(
        UID,
        CONV,
        claimed['job_id'],
        claimed['lease_token'],
        'text_mismatch',
        now=world.clock[0],
        firestore_client=world.store,
    )
    job_id, job = the_job(world.store)
    assert job['last_outcome'] == 'text_mismatch'
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s1'])
    assert (
        ledger.ensure_job(
            UID,
            CONV,
            person_id='p' if target == 'person' else None,
            segment_ids=['s0'],
            firestore_client=world.store,
        )
        is None
    )
    found = jobs_map(world.store)
    same = [
        j
        for j in found.values()
        if j.get('target') == target and j.get('person_id') == ('p' if target == 'person' else None)
    ]
    assert len(same) == 1 and same[0]['attempts'] == job['attempts'] and same[0]['state'] == 'terminal'
    world.extract.reset_mock()
    world.owner.reset_mock()
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    if target == 'owner':
        assert world.owner.await_count == 0
    else:
        assert all(call.args[1] != 'p' for call in world.extract.await_args_list)


def test_ensure_subset_of_assignment_ids_matches_existing_job(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    assign(person_id='p', segment_ids=['s0', 's1'])
    job_id, job = the_job(world.store)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s2'])
    assert ledger.ensure_job(UID, CONV, person_id='p', segment_ids=['s0'], firestore_client=world.store) is None
    found = jobs_map(world.store)
    p_jobs = [j for j in found.values() if j.get('person_id') == 'p']
    assert len(p_jobs) == 1 and p_jobs[0]['segment_ids'] == ['s0', 's1']


def test_reconsent_after_relabel_creates_distinct_new_job(world):
    assign(person_id='p', segment_ids=['s0'])
    old_id, _ = the_job(world.store)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s0'])
    assign(person_id='p', segment_ids=['s0'])
    found = jobs_map(world.store)
    p_jobs = {jid: j for jid, j in found.items() if j.get('person_id') == 'p'}
    assert len(p_jobs) == 2 and old_id in p_jobs
    assert p_jobs[old_id]['state'] == 'terminal' and p_jobs[old_id]['last_outcome'] == 'superseded'
    new = [jid for jid in p_jobs if jid != old_id]
    assert len(new) == 1 and p_jobs[new[0]]['state'] == 'pending' and p_jobs[new[0]]['generation'] == 3


def test_projector_without_pointer_never_reads_client():
    class Exploding:
        def collection(self, *args, **kwargs):
            raise AssertionError('pointer-less person must not trigger a client read')

    person = {'id': 'p', 'name': 'Sam', 'voice_learning_state': 'pending'}
    assert (
        ledger.project_person_learning(UID, person, firestore_client=Exploding())['voice_learning_state'] == 'unknown'
    )
    ready = dict(person, speaker_embedding=[1.0], speech_samples=['a.wav'], speech_samples_version=3)
    assert ledger.project_person_learning(UID, ready, firestore_client=Exploding())['voice_learning_state'] == 'learned'
    disabled = dict(person, voice_learning_state='disabled')
    assert (
        ledger.project_person_learning(UID, disabled, firestore_client=Exploding())['voice_learning_state']
        == 'disabled'
    )


def test_projector_live_pointer_under_disabled_settings_is_disabled(world):
    assign(person_id='p', segment_ids=['s0'])
    world.store.rows[('users', UID)]['save_other_voice_profiles'] = False
    projected = ledger.project_person_learning(UID, world.store.rows[PERSON_PATH], firestore_client=world.store)
    assert projected['voice_learning_state'] == 'disabled'


def test_projector_mismatched_fresh_pointer_does_not_project_stale_ledger(world):
    assign(person_id='p', segment_ids=['s0'])
    stale = dict(world.store.rows[PERSON_PATH])
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    assign(person_id='p', segment_ids=['s1'])
    projected = ledger.project_person_learning(UID, stale, firestore_client=world.store)
    assert projected['voice_learning_job']['job_id'] != stale['voice_learning_job']['job_id']
    assert projected['voice_learning_state'] == 'unknown'


def test_owner_crash_after_publication_is_recognized_stored(world):
    assign(is_user=True, segment_ids=['s0'], use_for_speech_training=True)
    _, job = the_job(world.store)
    world.store.rows[('users', UID)].update(
        speaker_embedding=[1.0, 0.5],
        owner_voice_confirmations=[
            {
                'embedding': [1.0],
                'conversation_id': CONV,
                'segment_ids': ['s0'],
                'generation': job['generation'],
                'at': job['created_at'] + timedelta(seconds=1),
            }
        ],
    )
    assert ledger.claim_next_job(UID, CONV, now=world.clock[0], firestore_client=world.store) is None
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'stored'


def test_later_owner_optout_supersedes_card_job(world):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(2, is_user=True)
    assign(
        is_user=True,
        speaker_id=0,
        use_for_speech_training=False,
        evidence_source=SOURCE_CARD,
        owner_segment_ids=['s0'],
    )
    _, job = the_job(world.store)
    assert job['state'] == 'pending' and job['card_generation'] == 1
    assign(is_user=True, speaker_id=0, use_for_speech_training=False)
    _, job = the_job(world.store)
    assert job['state'] == 'terminal' and job['last_outcome'] == 'superseded'
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.owner.await_count == 0


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_ensure_after_partial_relabel_supersession_admits_new_job(world, target):
    world.store.rows[CONV_PATH]['transcript_segments'] = _segments(3)
    if target == 'person':
        assign(person_id='p', segment_ids=['s0', 's1'])
    else:
        assign(is_user=True, segment_ids=['s0', 's1'], use_for_speech_training=True)
    old_id, _ = the_job(world.store)
    world.store.rows[('users', UID, 'people', 'q')] = dict(id='q', name='Quinn')
    assign(person_id='q', segment_ids=['s1'])
    assert jobs_map(world.store)[old_id]['last_outcome'] == 'superseded'
    new_id = ledger.ensure_job(
        UID,
        CONV,
        person_id='p' if target == 'person' else None,
        segment_ids=['s0'],
        firestore_client=world.store,
    )
    assert new_id is not None and new_id != old_id
    found = jobs_map(world.store)
    assert found[new_id]['generation'] == 2 and found[new_id]['segment_ids'] == ['s0']
    assert found[old_id]['state'] == 'terminal' and found[old_id]['last_outcome'] == 'superseded'


def test_sync_v1_route_schedules_learning_retries_after_audio_finalize():
    source = (Path(__file__).resolve().parents[2] / 'routers' / 'sync.py').read_text(encoding='utf-8')
    fn_start = source.index('async def sync_local_files(')
    fn_end = source.index('@router.post(  # v2 async sync-local-files', fn_start)
    fn_body = source[fn_start:fn_end]
    assert fn_body.index('_finalize_sync_audio_files') < fn_body.index('schedule_person_voice_learning_retries')


def test_pipeline_schedules_learning_retries_outside_private_cloud_gate():
    """Reprocessed conversations must trigger durable teaching even without fresh audio."""
    source = (Path(__file__).resolve().parents[2] / 'utils' / 'sync' / 'pipeline.py').read_text(encoding='utf-8')
    start = source.index('async def _run_full_pipeline_background_async')
    end = source.find('\nasync def ', start + 1)
    body = source[start : end if end != -1 else len(source)]
    idx = body.index('schedule_person_voice_learning_retries')
    indent = idx - (body.rindex('\n', 0, idx) + 1)
    gate = body.index('if private_cloud_sync_enabled:', body.index('_finalize_sync_audio_files') - 400)
    gate_indent = gate - (body.rindex('\n', 0, gate) + 1)
    assert indent == gate_indent, 'retry scheduling must not sit inside the private-cloud audio gate'
