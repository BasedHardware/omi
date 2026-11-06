"""Synthetic ghost hints: release/expiry gaps and the repair's active follow-up.

Loopback Firestore only, using the existing projection lane's anonymous client.
The strict xfails assert the desired automatic exit, so a selector fix must turn
them into passing regressions rather than silently preserving today's gap.
"""

from copy import deepcopy
from dataclasses import asdict

import pytest

from config.batch_pipeline import HELD_DEAD_LETTER_SECONDS
from database.batch_pipeline_projection_release import (
    RELEASE_PAGE,
    RELEASE_TICK_SECONDS,
    ProjectionReleaseStore,
    expired_page_ids,
    release_scan_pass,
)
from database.batch_pipeline_store import projection_page
from scripts.reconcile_batch_projection_ghost_holds import reconcile
from tests.integration.test_batch_pipeline_projection_firestore import lane
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key

pytestmark = pytest.mark.integration
NOW = 10000.0
GHOSTS = ('a-ghost-none', 'b-ghost-recovered')
RESTORABLE, MISSING, PRIVACY = 'c-real-restorable', 'd-real-missing', 'e-privacy'


@pytest.fixture
def holds(lane, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED', 'true')
    projection = lane.projector.store
    for segment in (*GHOSTS, RESTORABLE, MISSING, PRIVACY):
        binding = ProjectionBinding(
            lane.uid,
            f'job-{segment}',
            f'content-{segment}',
            (segment,),
            target_conversation_id=f'target-{segment}',
            record_origin=True,
            data_protection_level='standard',
        )
        if segment != MISSING:
            lane.user.collection('conversations').document(binding.target_conversation_id).set(
                {'status': 'completed', 'record_lane_owner': 'batch_sync_v1'}
            )
        ghost = segment in GHOSTS
        projection.ref('jobs', segment).set(
            {
                'owner_id': lane.uid,
                'state': 'committed',
                'projection_binding': asdict(binding),
                'recovery_state': (None if segment == GHOSTS[0] else 'recovered') if ghost else 'held',
                'audio_uri': 'gs://synthetic/retained-audio#1',
            }
        )
        projection.ref('results', segment).set(
            {
                'segment_id': segment,
                'owner_key': owner_key(lane.uid),
                'committed_at': 1.0,
                'projection_state': 'quarantine_held',
                'protocol_version': 2,
                'payload': {'words': ['synthetic retained output']},
                'projection': (
                    {'state': 'ready'}
                    if ghost
                    else {
                        'state': 'quarantined',
                        'disposition': 'ambiguous_generation',
                        'quarantine_reason': 'conversation_missing' if segment == MISSING else 'record_conflict',
                        'held_speech_seconds': 3.0,
                    }
                ),
                **(
                    {
                        'projection_privacy_refusal': {
                            'version': 1,
                            'reason': 'recording_privacy_changed',
                            'held_at': 1.0,
                        }
                    }
                    if segment == PRIVACY
                    else {}
                ),
            }
        )
    return lane


def snapshot(lane, kind):
    return {doc.id: doc.to_dict() for doc in lane.client.collection(f'{lane.store.namespace}_{kind}').stream()}


def scan(lane, now):
    counts, _ = release_scan_pass(lane.projector.store, limit=RELEASE_PAGE, after_id=None, now=now)
    if counts['error']:
        pytest.fail(f'release scan had {counts["error"]} errors; this is not the expected selector gap')
    return counts


def test_real_hold_releases_missing_target_waits_then_expires_privacy_is_fenced(holds):
    projection = holds.projector.store
    before = snapshot(holds, 'results')
    privacy_job = projection.ref('jobs', PRIVACY).get().to_dict()
    release = ProjectionReleaseStore(projection)
    assert release.release(RESTORABLE, NOW)
    released = projection.ref('results', RESTORABLE).get().to_dict()
    assert released['projection_state'] == 'pending' and released['projection'] == {}
    assert projection.ref('jobs', RESTORABLE).get().to_dict()['recovery_state'] is None
    assert released['payload'] == before[RESTORABLE]['payload']
    assert not release.release(MISSING, NOW) and not release.expired
    waiting = projection.ref('results', MISSING).get().to_dict()
    deadline = NOW + HELD_DEAD_LETTER_SECONDS
    assert waiting == {**before[MISSING], 'held_deadline_at': deadline}
    assert not release.release(MISSING, deadline - 1) and not release.expired
    assert projection.ref('results', MISSING).get().to_dict() == waiting
    assert not release.release(MISSING, deadline) and release.expired
    assert projection.ref('results', MISSING).get().to_dict() == {
        **waiting,
        'held_expired_at': deadline,
        'held_expired_reason': 'held_expired',
    }
    assert not release.release(MISSING, deadline + 1) and not release.expired
    assert MISSING in expired_page_ids(holds.client, holds.store.namespace, RELEASE_PAGE, None)
    assert not release.release(PRIVACY, NOW)
    assert not release.release(PRIVACY, deadline)
    assert projection.ref('results', PRIVACY).get().to_dict() == before[PRIVACY]
    assert projection.ref('jobs', PRIVACY).get().to_dict() == privacy_job


@pytest.mark.parametrize('segment', GHOSTS, ids=['recovery-none', 'recovery-recovered'])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason='GAP ghost_hold_release_ineligible: ready receipts with recovery none/recovered fail release gates',
)
def test_gap_ghost_hold_release_ineligible(holds, segment):
    scan(holds, NOW)
    # Desired automatic ready-hint repair; current main leaves the ghost held.
    assert holds.projector.store.ref('results', segment).get().to_dict()['projection_state'] in {
        'ready',
        'pending',
        'completed',
    }


@pytest.mark.parametrize('segment', GHOSTS, ids=['recovery-none', 'recovery-recovered'])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason='GAP ghost_hold_expiry_ineligible: receipt/job gates precede deadline stamping and held expiry',
)
def test_gap_ghost_hold_expiry_ineligible(holds, segment):
    scan(holds, NOW)
    scan(holds, NOW + HELD_DEAD_LETTER_SECONDS)
    entry = holds.projector.store.ref('results', segment).get().to_dict()
    # Aged ghosts need an automatic exit, whether repaired or dead-lettered.
    assert (
        entry['projection_state'] in {'ready', 'pending', 'completed'}
        or entry.get('held_expired_reason') == 'held_expired'
    )


def test_reconcile_only_repairs_ghost_hints_and_is_idempotent(holds):
    before_results, before_jobs = snapshot(holds, 'results'), snapshot(holds, 'jobs')
    dry = reconcile(holds.client, holds.store.namespace, batch_size=1)
    assert dry == dict(scanned=5, matched=2, updated=0, conflicts=0, errors=0, deadline_reached=0)
    assert snapshot(holds, 'results') == before_results
    applied = reconcile(holds.client, holds.store.namespace, apply=True, batch_size=1)
    assert applied == {**dry, 'updated': 2}
    assert snapshot(holds, 'results') == {
        segment: {**row, **({'projection_state': 'ready'} if segment in GHOSTS else {})}
        for segment, row in before_results.items()
    }
    assert snapshot(holds, 'jobs') == before_jobs
    assert set(projection_page(holds.client, holds.store.namespace, states=('ready',))[0]) == set(GHOSTS)
    assert reconcile(holds.client, holds.store.namespace, apply=True, batch_size=1) == {
        **dry,
        'scanned': 3,
        'matched': 0,
    }


@pytest.mark.parametrize('recovery_state', [None, 'recovered'], ids=['recovery-none', 'recovery-recovered'])
def test_repaired_ready_hint_completes_ledger_and_publishes_without_reassignment(lane, monkeypatch, recovery_state):
    batch = lane.seed()
    lane.finish(batch)
    segment = batch.ids[0]

    def crash_before_completion(*args, **kwargs):
        raise RuntimeError('synthetic stop after ready receipt')

    with monkeypatch.context() as patch:
        patch.setattr(lane.projector, 'complete_content', crash_before_completion)
        with pytest.raises(RuntimeError, match='synthetic stop after ready receipt'):
            lane.projector.project(segment)
    ref = lane.projector.store.ref('results', segment)
    ready = deepcopy(ref.get().to_dict())
    assert ready['projection']['state'] == 'ready'
    ref.update({'projection_state': 'quarantine_held'})
    lane.projector.store.ref('jobs', segment).update({'recovery_state': recovery_state})
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.published
    assert projection_page(lane.client, lane.store.namespace, states=('ready',))[0] == []
    loads, tasks = list(lane.loads), list(lane.tasks)
    assert reconcile(lane.client, lane.store.namespace, apply=True)['updated'] == 1
    assert ref.get().to_dict() == ready
    assert projection_page(lane.client, lane.store.namespace, states=('ready',))[0] == [segment]
    # Drive the ordinary ready-receipt replay path, including the real ledger,
    # accounting and acknowledgement transactions. Only external publication
    # and enqueue are captured by the established emulator lane fixture.
    result = lane.projector.project(segment)
    assert result is not None and result['updated_memories']
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert lane.projector.status(lane.uid, batch.binding.content_id)['status'] == 'completed'
    assert lane.published == [result]
    assert ref.get().to_dict()['projection_state'] == 'completed'
    assert lane.loads == loads and lane.tasks == tasks
    accounting = lane.projector.store.prepare_accounting(batch.binding, NOW)
    assert accounting['completed'] and not accounting['updates']
    assert lane.projector.project(segment) == result
    assert lane.loads == loads and lane.tasks == tasks
    assert lane.published == [result]


@pytest.mark.skip(
    reason='Rows examined in a 5s tick depend on emulator RPC latency and host load; page 128 is a cap, not throughput'
)
def test_release_scan_throughput_5s_page128():
    assert RELEASE_TICK_SECONDS == 5.0 and RELEASE_PAGE == 128
