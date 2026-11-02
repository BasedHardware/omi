"""Capture age and bounded redrive through real projection, assignment and receipts."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database import conversations
from database.batch_pipeline_projection_release import ProjectionReleaseStore, release_page
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_owner_chain_projection import (
    BURST,
    SUCCESS_PAYLOAD,
    ResultLog,
    patch_conversation_assignment,
    projector_for,
)
from utils.batch_pipeline import projection
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason as Reason


@pytest.mark.parametrize(
    'subtype', [Reason.RECORD_TARGET_MISSING, Reason.RECORD_FINALIZE_PENDING, Reason.LIVE_TARGET_NOT_PERSISTED]
)
@pytest.mark.parametrize('age,held', [(120, False), (6 * 3600 - 1, False), (6 * 3600, True), (8 * 3600, True)])
def test_backfill_age_gate_uses_capture_end_in_real_owner_walk(monkeypatch, subtype, age, held):
    log = ResultLog()
    log.commit(BURST, 'capture', 'unit', ['unit'], record=True, fresh_capture=False, outcome='success')
    job = log.jobs['unit']
    now = job['capture_at'] + job['duration_seconds'] + age
    patch_conversation_assignment(monkeypatch, subtype, fail_first_n=10**6)
    projector = projector_for(log, lambda *_: dict(SUCCESS_PAYLOAD))
    projector.clock = lambda: now
    projector.project_owner(BURST)
    row = log.results['unit']
    assert row['projection_state'] == ('quarantine_held' if held else 'pending')
    if held:
        assert log.jobs['unit']['recovery_state'] == 'held'
    else:
        assert row['projection_blocked_since'] == now
        assert not row.get('projection')
        # Repeated attempts do not turn a recent capture into old content.
        projector.project_owner(BURST)
        assert row['projection_state'] == 'pending'
    assert job['audio_uri'] and row['result']['result_uri']


@pytest.mark.parametrize(
    'reason', [Reason.RECORD_TARGET_DISCARDED, Reason.LINEAGE_OWNERSHIP_AMBIGUOUS, Reason.RECORD_PRIVACY_CHANGED]
)
def test_terminal_conflicts_hold_even_on_recent_capture(reason):
    assert projection.quarantines_assignment_conflict(
        SyncAssignmentConflict('synthetic', subtype=reason),
        {'fresh_capture': False, 'capture_at': 100, 'duration_seconds': 1},
        now=120,
    )


@pytest.mark.parametrize(
    'capture,duration',
    [(None, 1), (True, 1), (1, None), (1, True), (float('nan'), 1), (1, float('inf')), (-1, 1), (1, 0)],
)
def test_unknown_capture_age_keeps_the_bounded_retry(capture, duration):
    assert not projection.quarantines_assignment_conflict(
        SyncAssignmentConflict('synthetic', subtype=Reason.RECORD_FINALIZE_PENDING),
        {'fresh_capture': False, 'capture_at': capture, 'duration_seconds': duration},
        now=100000,
    )


@pytest.fixture
def real_projection(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setattr(conversations, 'index_sync_assignment', lambda *a: None)
    monkeypatch.setattr(conversations, 'find_sync_live_overlap_candidates', lambda *a, **k: ())
    client = StrictFirestore()
    namespace = 'batch_pipeline_hold_test'
    binding = ProjectionBinding(
        'synthetic-owner',
        'job',
        'content',
        ('unit',),
        record_origin=True,
        target_conversation_id='target',
        data_protection_level='standard',
    )
    work = WorkItem('unit', binding.owner_id, 1000, 'gs://synthetic/audio', 10, Priority.DEEP, privacy_generation=0)
    result = {'outcome': 'success', 'result_uri': 'gs://synthetic/result'}
    job = {
        **asdict(work),
        'projection_binding': asdict(binding),
        'result': result,
        'fresh_capture': False,
        'policy_parts': {'projection': ProjectionPolicy().to_dict()},
    }
    entry = {
        'protocol_version': 1,
        'segment_id': 'unit',
        'owner_key': owner_key(binding.owner_id),
        'capture_at': 1000,
        'previous_segment_id': None,
        'committed_at': 1001,
        'projection_state': 'pending',
        'result': result,
    }
    client.rows[('users', binding.owner_id)] = {'data_protection_level': 'standard'}
    client.rows[(namespace + '_jobs', 'unit')] = job
    client.rows[(namespace + '_results', 'unit')] = entry
    client.rows[(namespace + '_owners', owner_key(binding.owner_id))] = {}
    ledger = sync_content_ledger_ref(client, binding.owner_id, binding.content_id)
    client.rows[ledger.path] = {
        'dispatch_protocol': 'batch_v1',
        'status': 'processing',
        'job_id': binding.job_id,
        'batch_pipeline': {'protocol_version': 1, 'namespace': namespace, 'segment_ids': ['unit']},
    }
    payload = {**deepcopy(SUCCESS_PAYLOAD), 'audio_seconds': 10}
    projector = projection.Projector(
        SimpleNamespace(client=client, namespace=namespace), Mock(return_value=payload), clock=lambda: 30000
    )
    target_key = ('users', binding.owner_id, 'conversations', 'target')
    target = {
        'id': 'target',
        'record_lane_owner': 'batch_sync_v1',
        'status': 'completed',
        'source': 'omi',
        'started_at': datetime.fromtimestamp(1000, timezone.utc),
        'finished_at': datetime.fromtimestamp(1010, timezone.utc),
        'transcript_segments': [],
        'data_protection_level': 'standard',
    }

    transaction = client.transaction

    def next_transaction(*args, **kwargs):
        # Known output union only; StrictFirestore deliberately does not model
        # transforms. Preserve its strict read-before-write checks unchanged.
        for table in ('jobs', 'results'):
            row = client.rows[(namespace + '_' + table, 'unit')]
            if row.get('conversation_ids') is not None:
                row['conversation_ids'] = ['target']
        return transaction(*args, **kwargs)

    monkeypatch.setattr(client, 'transaction', next_transaction)

    def assign():
        current_job, current_entry, current_binding = projector.store.read('unit')
        projector._assign('unit', current_job, current_entry, current_binding, finish=False)

    return SimpleNamespace(**locals())


def test_landed_target_releases_projects_once_and_renews_episode_budget(real_projection):
    lane = real_projection
    lane.assign()  # old missing target: hold through the real assignment path
    row = lane.client.rows[(lane.namespace + '_results', 'unit')]
    assert row['projection_state'] == 'quarantine_held'
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    release = ProjectionReleaseStore(lane.projector.store)
    assert release.release('unit', 30001)
    assert not release.release('unit', 30002)
    lane.assign()
    projected = deepcopy(lane.client.rows[lane.target_key])
    assert (
        len(
            conversations.decode_transcript_segments_verified(
                lane.binding.owner_id,
                projected['transcript_segments'],
                bool(projected.get('transcript_segments_compressed')),
            )
        )
        == 1
    )
    assert row['projection_release_attempts'] == 0
    assert row['projection_redriven_at'] == 30001
    lane.assign()  # real transaction receipt replay
    assert lane.client.rows[lane.target_key] == projected
    assert lane.client.rows[(lane.namespace + '_jobs', 'unit')]['audio_uri'] == lane.work.audio_uri
    assert row['result'] == lane.result


def test_recent_missing_target_retries_then_assigns_when_writer_lands(real_projection):
    lane = real_projection
    lane.projector.clock = lambda: 1130
    with pytest.raises(SyncAssignmentConflict) as raised:
        lane.assign()
    job, row, binding = lane.projector.store.read('unit')
    assert not lane.projector.resolve_failing_head('unit', job, row, binding, raised.value)
    row = lane.client.rows[(lane.namespace + '_results', 'unit')]
    assert row['projection_state'] == 'pending'
    assert row['projection_blocked_since'] == 1130
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    lane.assign()
    assert row['projection']['state'] == 'persisted'
    assert not lane.client.rows[(lane.namespace + '_jobs', 'unit')].get('recovery_state')


def test_kill_switch_off_still_drains_versioned_released_rows(real_projection, monkeypatch):
    lane = real_projection
    lane.assign()
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    assert ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
    row = lane.client.rows[(lane.namespace + '_results', 'unit')]
    assert row['protocol_version'] == 2 and row['projection_release_version'] == 1
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    lane.assign()
    assert row['projection']['state'] == 'persisted'


def test_unknown_release_protocol_cannot_assign(real_projection):
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    lane = real_projection
    lane.assign()
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    assert ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
    lane.client.rows[(lane.namespace + '_results', 'unit')]['projection_release_version'] = 2
    with pytest.raises(ProjectionBlocked):
        lane.assign()
    assert lane.client.rows[lane.target_key] == lane.target


@pytest.mark.parametrize('intent', ['speech_redrive', 'terminal_disposition', 'silence_disposition'])
def test_release_leaves_open_operator_intents_untouched(real_projection, intent):
    lane = real_projection
    lane.assign()
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    lane.client.rows[(lane.namespace + '_jobs', 'unit')][intent] = {'state': 'prepared'}
    before = deepcopy(lane.client.rows)
    assert not ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
    assert lane.client.rows == before


@pytest.mark.parametrize('fence', ['generation', 'explicit_off', 'deleted', 'custom_stt'])
def test_redrive_rechecks_generation_deletion_and_explicit_off(real_projection, fence):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked, PRIVACY_COLLECTION
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    lane = real_projection
    lane.assign()
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    assert ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
    if fence == 'generation':
        lane.client.rows[(PRIVACY_COLLECTION, owner_key(lane.binding.owner_id))] = {'generation': 1}
    elif fence == 'explicit_off':
        lane.client.rows[lane.target_key].update(record_lane_owner='batch_live_v1', private_cloud_sync_enabled=False)
    elif fence == 'deleted':
        lane.client.rows[lane.target_key]['deleted'] = True
    else:
        lane.client.rows[lane.target_key]['uses_custom_stt'] = True
    target = deepcopy(lane.client.rows[lane.target_key])
    try:
        lane.assign()
    except (BatchPrivacyBlocked, ProjectionBlocked):
        pass
    assert lane.client.rows[lane.target_key] == target
    assert not target['transcript_segments']
    assert lane.client.rows[(lane.namespace + '_results', 'unit')]['result'] == lane.result


def test_conflict_log_and_counter_accept_only_closed_values(monkeypatch, caplog):
    from utils.batch_pipeline import correctness_metrics, projection_hold_policy

    monkeypatch.setenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'true')
    before = correctness_metrics.CONFLICT_HOLDS.labels('other')._value.get()
    error = SyncAssignmentConflict('private-message', subtype='private-subtype')
    with caplog.at_level('INFO', logger=projection_hold_policy.__name__):
        projection_hold_policy.log_conflict_hold(error)
    assert correctness_metrics.CONFLICT_HOLDS.labels('other')._value.get() == before + 1
    assert 'conflict_subtype=other' in caplog.text
    assert 'private-' not in caplog.text


def test_release_then_discard_race_cannot_write_and_repeated_release_is_bounded(real_projection):
    lane = real_projection
    lane.assign()
    release = ProjectionReleaseStore(lane.projector.store)
    for attempt in range(3):
        lane.client.rows[lane.target_key] = deepcopy(lane.target)
        assert release.release('unit', 31000 + attempt)
        lane.client.rows[lane.target_key]['discarded'] = True
        before = deepcopy(lane.client.rows[lane.target_key])
        lane.assign()
        assert lane.client.rows[lane.target_key] == before
        assert not release.release('unit', 32000 + attempt)
    lane.client.rows[lane.target_key]['discarded'] = False
    assert not release.release('unit', 33000)
    assert lane.client.rows[(lane.namespace + '_results', 'unit')]['projection_release_attempts'] == 3


def test_landed_ordinary_target_is_releasable_without_record_route(real_projection):
    lane = real_projection
    lane.assign()
    binding = replace(lane.binding, record_origin=False)
    lane.client.rows[(lane.namespace + '_jobs', 'unit')]['projection_binding'] = asdict(binding)
    target = deepcopy(lane.target)
    target.pop('record_lane_owner')
    lane.client.rows[lane.target_key] = target
    assert ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
    lane.assign()
    projected = deepcopy(lane.client.rows[lane.target_key])
    assert (
        len(
            conversations.decode_transcript_segments_verified(
                lane.binding.owner_id,
                projected['transcript_segments'],
                bool(projected.get('transcript_segments_compressed')),
            )
        )
        == 1
    )
    lane.assign()
    assert lane.client.rows[lane.target_key] == projected


def test_release_scan_resumes_after_last_examined_row_at_time_bound(monkeypatch):
    import database.batch_pipeline_projection_release as release

    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['first', 'second', 'third'])
    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', lambda *a: False)
    monkeypatch.setattr(release.time, 'monotonic', lambda: 10)
    counts, cursor = release_page(Mock(), limit=3, after_id=None, now=100, deadline=9)
    assert counts['examined'] == 1
    assert cursor == 'first'


def test_multipart_release_preserves_committed_suffix_and_rebuilds_summary(real_projection, monkeypatch):
    lane = real_projection
    binding = replace(lane.binding, record_origin=False)
    job = lane.client.rows[(lane.namespace + '_jobs', 'unit')]
    job.update(projection_binding=asdict(binding), duration_seconds=200)
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    payload = {
        'audio_seconds': 200,
        'speech_seconds': 2,
        'speech_spans': [{'start': 0, 'end': 1}, {'start': 150, 'end': 151}],
        'words': [{'word': 'First.', 'timestamp': [0, 1]}, {'word': 'Second.', 'timestamp': [150, 151]}],
        'diarization': {'turns': [{'start': 0, 'end': 200, 'speaker': 'a'}]},
    }
    lane.projector.load_result = lambda *_: deepcopy(payload)
    real = conversations.assign_sync_conversation
    attempts = []

    def miss_once(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise SyncAssignmentConflict('synthetic', subtype=Reason.RECORD_TARGET_MISSING)
        return real(*args, **kwargs)

    monkeypatch.setattr(conversations, 'assign_sync_conversation', miss_once)
    lane.assign()
    lane.projector.store.ready('unit', binding, 30000, part_index=1, policy=ProjectionPolicy())
    row = lane.client.rows[(lane.namespace + '_results', 'unit')]
    suffix = deepcopy(row['projection_parts']['1'])
    assert row['projection_state'] == 'quarantine_held'
    assert ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
    assert row['projection_parts'] == {'1': suffix}
    lane.assign()
    assert row['projection']['state'] == 'persisted'
    assert row['projection']['speech_seconds'] == 2
    assert row['projection_release_attempts'] == 0
    assert row['projection_parts']['1'] == suffix
    # Ordinary assignment may split speech groups separated by >120 seconds
    # into separate conversations; the release must preserve that policy.
    segments = []
    for key, projected in lane.client.rows.items():
        if len(key) == 4 and key[:3] == lane.target_key[:3] and not projected.get('deleted'):
            segments.extend(
                conversations.decode_transcript_segments_verified(
                    lane.binding.owner_id,
                    projected['transcript_segments'],
                    bool(projected.get('transcript_segments_compressed')),
                )
            )
    assert sorted(segment['text'] for segment in segments) == ['First.', 'Second.']
    assert len(attempts) == 3  # rejected first, assigned suffix, then only repaired first
    before = deepcopy(lane.client.rows)
    lane.assign()
    assert lane.client.rows == before


def test_explicit_off_restores_first_failure_strike_and_old_release_eligibility(monkeypatch, real_projection):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    assert projection.quarantines_assignment_conflict(
        SyncAssignmentConflict('synthetic', subtype=Reason.RECORD_FINALIZE_PENDING),
        {'fresh_capture': False, 'capture_at': 100, 'duration_seconds': 1},
        now=120,
    )
    lane = real_projection
    lane.assign()
    lane.client.rows[lane.target_key] = deepcopy(lane.target)
    lane.client.rows[(lane.namespace + '_results', 'unit')]['projection_redriven_at'] = 20000
    assert not ProjectionReleaseStore(lane.projector.store).release('unit', 30001)
