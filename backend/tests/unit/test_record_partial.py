"""Real barriers, staging, admission and worker; all identities/audio synthetic."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import wave

import pytest

from config.record_audio import record_identity, require_record_audio_barrier
from config.policy import BatchUnitPolicy
from database.record_audio import seal_record_audio, set_record_upload_pending, renew_record_token_lease
from database.record_partial import finish_partial, PAYER_REFUSALS
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_intake import admit
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from tests.unit.test_batch_pipeline_worker import setup_worker
from utils.batch_pipeline import live, record_partial, record_producer_proof
from utils.batch_pipeline import record_seal_cluster_repair as cluster, record_seal_repair as repair
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.record_partial_audio import missing_units, union
from utils.batch_pipeline.source_audio import MAGIC, materialize
from utils.batch_pipeline.live_projection import replace_record
from utils.batch_pipeline.record_seal_nojob import registration
from diarizer.batch_pipeline_models import decode_pcm16_wav

ROW = ('users', 'synthetic', 'conversations', 'record')
FLAGS = {'K_SERVICE': 'synthetic-role', 'BATCH_PIPELINE_PERCENT': '5', 'BATCH_LIVE_STT_RETIRE_PERCENT': '0'}
NOW = 4000


@pytest.fixture
def source(monkeypatch):
    from utils.executors import sync_executor

    original_run_blocking = record_partial.run_blocking

    async def run_blocking(executor, fn, *args, **kwargs):
        # Partial source collection also downloads retained objects; it must
        # not borrow the coordinator pool when admission concurrency grows.
        assert executor is not sync_executor
        return await original_run_blocking(executor, fn, *args, **kwargs)

    monkeypatch.setattr(record_partial, 'run_blocking', run_blocking)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-batch-bucket')
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: NOW)
    row = {
        'id': 'record',
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'private_cloud_sync_enabled': True,
        'source': 'omi',
        'language': 'en',
        'data_protection_level': 'standard',
        'started_at': datetime.fromtimestamp(100, timezone.utc),
        'finished_at': datetime.fromtimestamp(110, timezone.utc),
        'transcript_segments': [],
        'structured': {},
        'record_upload_revision': 0,
    }
    client = StrictFirestore({ROW: row, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    proof = {
        'namespace': 'prod-omi-backend',
        'captured_at': NOW - 1,
        'pods': {},
        'resource_version': 'synthetic',
        'file_sha256': 'synthetic',
    }
    return store, client, proof


def finish(source, **kwargs):
    store, _, proof = source
    return finish_partial(
        store,
        '/'.join(ROW),
        reason='tail_lagging',
        proof=proof,
        now=NOW,
        register=lambda tx, uid, cid, row: registration(tx, uid, cid, row, FLAGS),
        **kwargs,
    )


def pending(source):
    return source[0].run(lambda tx: tx.get('jobs', record_identity('synthetic', 'record')[1]))


def test_partial_is_distinct_from_complete_and_api_exposes_it(source):
    from models.conversation import Conversation

    assert finish(source) == 'partial_finished'
    row = source[1].rows[ROW]
    assert row['record_audio_closed'] is False
    require_record_audio_barrier(row)
    assert row['record_audio_partial']['reason'] == 'tail_lagging'
    model = Conversation(**{**row, 'created_at': row['started_at']})
    assert model.model_dump()['record_audio_partial']['reason'] == 'tail_lagging'
    assert pending(source)['state'] == 'record_pending'
    assert pending(source)['partial_reason'] == 'tail_lagging'
    assert finish(source) == 'already_partial'
    assert repair.seal_refusal(pending(source), row) == 'already_partial'


@pytest.mark.parametrize('age', [1799, 1800])
def test_exact_30_minute_boundary(source, age):
    source[1].rows[ROW]['finished_at'] = datetime.fromtimestamp(NOW - age, timezone.utc)
    assert finish(source) == ('not_aged' if age < 1800 else 'partial_finished')


@pytest.mark.parametrize(
    'change',
    [
        {'deleted': True},
        {'discarded': True},
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'data_protection_level': 'e2ee'},
    ],
)
def test_privacy_and_payer_fences(source, change):
    source[1].rows[ROW].update(change)
    assert finish(source) == 'privacy_refused'
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


def test_deletion_marker_in_real_privacy_fence(source):
    source[1].rows[('users', 'synthetic', 'deleted_conversations', 'record')] = {'deleted': True}
    assert finish(source) == 'privacy_refused'
    assert 'record_audio_partial' not in source[1].rows[ROW]


@pytest.mark.parametrize('identity', [True, {'pod': 'alive', 'process_started_at': 100}])
def test_live_and_unproven_producers_never_expire_by_age(source, identity):
    source[1].rows[ROW]['record_upload_sessions'] = {'producer': identity}
    source[2]['pods'] = {'alive': 100}
    assert finish(source) == 'upload_pending'
    assert not source[1].rows[ROW].get('record_audio_partial')


def test_dead_producer_requires_existing_fresh_death_proof(source):
    source[1].rows[ROW]['record_upload_sessions'] = {'producer': {'pod': 'gone', 'process_started_at': 100}}
    assert finish(source) == 'partial_finished'
    assert source[1].rows[ROW]['record_upload_sessions'] == {}


def test_partial_requires_fresh_inventory_even_without_tokens(source):
    source[2]['captured_at'] = NOW - 301
    assert finish(source) == 'state_changed'
    assert not source[1].rows[ROW].get('record_audio_partial')


def test_malformed_partial_version_never_opens_the_barrier(source):
    assert finish(source) == 'partial_finished'
    source[1].rows[ROW]['record_audio_partial']['version'] = True
    with pytest.raises(ValueError, match='barrier'):
        require_record_audio_barrier(source[1].rows[ROW])


def test_producer_finishing_between_check_and_apply_is_not_raced(source):
    source[1].rows[ROW]['record_upload_sessions'] = {'producer': {'pod': 'alive', 'process_started_at': 100}}
    source[2]['pods'] = {'alive': 100}
    assert finish(source) == 'upload_pending'
    set_record_upload_pending('synthetic', 'record', 'producer', False, firestore_client=source[1])
    assert seal_record_audio('synthetic', 'record', firestore_client=source[1]) is None
    assert finish(source) == 'already_closed'
    assert not source[1].rows[ROW].get('record_audio_partial')


def test_late_producer_cannot_promote_partial_to_complete(source):
    assert finish(source) == 'partial_finished'
    set_record_upload_pending('synthetic', 'record', 'late', True, firestore_client=source[1])
    with pytest.raises(ValueError, match='barrier'):
        require_record_audio_barrier(source[1].rows[ROW])
    set_record_upload_pending('synthetic', 'record', 'late', False, firestore_client=source[1])
    assert seal_record_audio('synthetic', 'record', firestore_client=source[1]) is None
    assert not source[1].rows[ROW]['record_audio_closed']
    assert finish(source) == 'partial_finished'
    require_record_audio_barrier(source[1].rows[ROW])


def test_late_refresh_keeps_the_original_closed_metric_reason(source):
    assert (
        finish_partial(
            source[0],
            '/'.join(ROW),
            reason='budget_limit',
            proof=source[2],
            now=NOW,
            register=lambda tx, uid, cid, row: registration(tx, uid, cid, row, FLAGS),
        )
        == 'partial_finished'
    )
    set_record_upload_pending('synthetic', 'record', 'late', True, firestore_client=source[1])
    set_record_upload_pending('synthetic', 'record', 'late', False, firestore_client=source[1])
    details = {}
    assert (
        cluster.repair_one(
            source[0],
            None,
            None,
            '/'.join(ROW),
            flags=FLAGS,
            inventory=lambda: source[2],
            budget=SweepBudget(240),
            reason_out=details,
        )
        == 'partial_finished'
    )
    assert details['partial_reason'] == 'budget_limit'
    assert pending(source)['partial_reason'] == 'budget_limit'


def test_kill_switch_off_does_not_finish_or_admit(source, monkeypatch):
    monkeypatch.setenv('RECORD_AUDIO_PARTIAL_ENABLED', 'false')
    assert finish(source) == 'disabled'
    assert not source[1].transactions
    monkeypatch.delenv('RECORD_AUDIO_PARTIAL_ENABLED')
    assert finish(source) == 'partial_finished'
    monkeypatch.setenv('RECORD_AUDIO_PARTIAL_ENABLED', 'false')
    with pytest.raises(ValueError, match='barrier'):
        require_record_audio_barrier(source[1].rows[ROW])


@pytest.mark.parametrize('private', ['A' * 28, 'person@example.invalid', 'users/private/conversations/private'])
def test_rerun_metric_and_log_discard_arbitrary_identifiers(private, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger=record_partial.__name__):
        record_partial.event(private)
        record_partial.record_failure(ValueError(private))
    assert private not in caplog.text
    assert 'outcome=state_changed' in caplog.text
    assert all(
        private not in sample.labels.values() for metric in record_partial.RERUNS.collect() for sample in metric.samples
    )


def test_only_actual_reference_frames_become_coverage_and_gap_fill_is_sliced():
    ref = {'start_frame': 0, 'frames': 16000, 'offset_frame': 0}
    initial, coverage = missing_units([(100, 3, [ref, {**ref, 'start_frame': 32000}])], [])
    assert coverage == [{'start': 1600000, 'end': 1616000}, {'start': 1632000, 'end': 1648000}]
    late, updated = missing_units([(100, 3, [{**ref, 'frames': 48000}])], coverage)
    assert late[0][:2] == (101, 1)
    assert late[0][2][0]['offset_frame'] == 16000
    assert updated == [{'start': 1600000, 'end': 1648000}]
    assert missing_units([(100, 3, [{**ref, 'frames': 48000}])], updated)[0] == []


def test_user_edit_before_partial_fill_survives_even_inside_enclosing_span(source):
    row = deepcopy(source[1].rows[ROW])
    row['has_transcript_corrections'] = True
    row['transcript_segments'] = [
        {'id': 'edited', 'text': 'User wording', 'start': 0, 'end': 1, 'speaker_id': 0, 'is_user': False}
    ]
    incoming = {
        'started_at': row['started_at'],
        'transcript_segments': [
            {
                'id': 'new',
                'text': 'Late speech',
                'start': 1,
                'end': 2,
                'speaker_id': 0,
                'is_user': False,
                'speaker': 'SPEAKER_00',
                'speaker_id_scope': 'final:batch:late',
            }
        ],
    }
    result, _ = replace_record(row, incoming, {'start': 100, 'end': 102, 'preserve_existing': True})
    assert [(s['id'], s['text']) for s in result['transcript_segments']] == [
        ('edited', 'User wording'),
        ('new', 'Late speech'),
    ]


@pytest.mark.parametrize('text', ['Existing transcript from another path', 'An edit without correction metadata'])
async def test_initial_partial_fills_only_empty_spans(source, audio, text):
    audio.add(100)
    old = {'id': 'existing', 'text': text, 'start': 0, 'end': 1, 'speaker_id': 0, 'is_user': False}
    source[1].rows[ROW]['transcript_segments'] = [old]
    assert finish(source) == 'partial_finished'
    await audio.drain()
    await audio.drain()
    bindings = [row['projection_binding'] for row in source[1].rows.values() if row.get('projection_binding')]
    assert len(bindings) == 1 and bindings[0]['partial_record'] is True
    row = source[1].rows[ROW]
    segment = {'speaker_id': 0, 'speaker': 'SPEAKER_00', 'speaker_id_scope': 'final:batch:initial', 'is_user': False}
    incoming = {
        'started_at': row['started_at'],
        'transcript_segments': [
            {**segment, 'id': 'overlap', 'text': 'Worse ASR', 'start': 0, 'end': 0.5},
            {**segment, 'id': 'straddle', 'text': 'Ambiguous split', 'start': 0.5, 'end': 1.5},
            {**segment, 'id': 'gap', 'text': 'New speech', 'start': 1, 'end': 2},
        ],
    }
    result, added = replace_record(row, incoming, {'start': 100, 'end': 102, 'preserve_existing': True})
    assert result['transcript_segments'][0] == old
    assert [s['id'] for s in result['transcript_segments']] == ['existing', 'gap']
    assert [s['id'] for s in added] == ['gap']


@pytest.mark.parametrize(
    'ambiguous', [{'start': 0, 'end': 0}, {'audio_alignment': 'unplaced'}, {'audio_alignment': 'unknown'}]
)
def test_partial_keeps_text_when_existing_alignment_is_ambiguous(source, ambiguous):
    row = deepcopy(source[1].rows[ROW])
    old = {'id': 'old', 'text': 'Keep', 'start': 0, 'end': 1, 'speaker_id': 0, 'is_user': False, **ambiguous}
    row['transcript_segments'] = [old]
    incoming = {
        'started_at': row['started_at'],
        'transcript_segments': [
            {'id': 'new', 'text': 'Guess', 'start': 1, 'end': 2, 'speaker_id': 0, 'is_user': False}
        ],
    }
    result, added = replace_record(row, incoming, {'start': 100, 'end': 102, 'preserve_existing': True})
    assert result['transcript_segments'] == [old]
    assert added == []


@pytest.mark.parametrize(
    'invalid',
    [
        {'start': 0, 'end': 1},  # Valid locally, but negative after the clock shift.
        {'start': 2, 'end': 2},
        {'start': 2, 'end': float('inf')},
        {'start': 2, 'end': 3, 'audio_alignment': 'unplaced'},
        {'start': 2, 'end': 3, 'audio_alignment': 'unknown'},
    ],
)
def test_initial_partial_rejects_invalid_alignment_on_both_clocks(source, invalid):
    row = deepcopy(source[1].rows[ROW])
    segment = {'speaker_id': 0, 'speaker': 'SPEAKER_00', 'is_user': False}
    incoming = {
        'started_at': datetime.fromtimestamp(99, timezone.utc),
        'transcript_segments': [
            {**segment, 'id': 'invalid', 'text': 'Cannot place', **invalid},
            {**segment, 'id': 'valid', 'text': 'Placed speech', 'start': 1, 'end': 2},
        ],
    }
    result, added = replace_record(row, incoming, {'start': 99, 'end': 102, 'preserve_existing': True})
    assert [s['id'] for s in result['transcript_segments']] == ['valid']
    assert [(s['start'], s['end']) for s in added] == [(0, 1)]
    assert row['transcript_segments'] == []
    assert incoming['transcript_segments'][0] == {**segment, 'id': 'invalid', 'text': 'Cannot place', **invalid}


@pytest.mark.parametrize('state', ['record_pending', 'partial_retired'])
def test_real_repair_skips_unchanged_partial_inventory_but_rearms_upload_revision(source, state):
    assert finish(source) == 'partial_finished'
    job_id = record_identity('synthetic', 'record')[1]
    job = pending(source)
    job.update(state=state, partial_run={'retired_at': NOW, 'coverage': [{'start': 1600000, 'end': 1616000}]})
    source[0].run(lambda tx: tx.put('jobs', job_id, job))
    before = deepcopy(source[1].rows)
    inventory = Mock(return_value=source[2])

    def sweep():
        return cluster.repair_one(
            source[0],
            object(),
            object(),
            '/'.join(ROW),
            flags=FLAGS,
            inventory=inventory,
            budget=SweepBudget(240),
        )

    # One day's five-minute repair attempts, using the real per-row repair path.
    for _ in range(288):
        assert sweep() == 'already_partial'
    inventory.assert_not_called()
    assert source[1].rows == before
    set_record_upload_pending('synthetic', 'record', 'late', True, firestore_client=source[1])
    set_record_upload_pending('synthetic', 'record', 'late', False, firestore_client=source[1])
    assert sweep() == 'partial_finished'
    assert inventory.call_count == 1
    assert pending(source)['state'] == 'record_pending'
    assert 'retired_at' not in pending(source)['partial_run']
    assert pending(source)['partial_run']['coverage'] == job['partial_run']['coverage']
    assert source[1].rows[ROW]['record_audio_closed'] is False
    assert source[1].rows[ROW]['transcript_segments'] == before[ROW]['transcript_segments']
    for _ in range(288):
        assert sweep() == 'already_partial'
    assert inventory.call_count == 1


def set_byok(source):
    job = pending(source)
    policy = replace(
        BatchUnitPolicy.from_dict(job['policy']), stt_route='provider', provider_reason='byok', provider_service='byok'
    )
    source[0].run(lambda tx: tx.put('jobs', job['segment_id'], {**job, 'policy': policy.to_dict()}))


def test_initial_partial_refuses_and_counts_recorded_byok(source):
    assert live.register_recording('synthetic', source[1].rows[ROW], store=source[0], now=NOW, server_flags=FLAGS)
    set_byok(source)
    before = PAYER_REFUSALS._value.get()
    assert finish(source) == 'byok_refused'
    assert PAYER_REFUSALS._value.get() == before + 1
    assert not source[1].rows[ROW].get('record_audio_partial')


@pytest.mark.parametrize('stage', ['plan', 'intake', 'late'])
@pytest.mark.parametrize('refusal', ['byok', 'discarded'])
async def test_continuation_refuses_before_storage_reads(source, audio, monkeypatch, stage, refusal):
    assert finish(source) == 'partial_finished'
    if stage != 'plan':
        if stage == 'intake':
            audio.add(100)
        await audio.drain()
    if refusal == 'byok':
        set_byok(source)
    else:
        source[1].rows[ROW]['discarded'] = True

    def forbidden(*args, **kwargs):
        pytest.fail('refused continuation read audio or plan')

    monkeypatch.setattr(record_partial, 'list_audio_chunks', forbidden)
    monkeypatch.setattr(audio.artifacts, 'load_record_plan', forbidden)
    monkeypatch.setattr(audio.artifacts, 'stage_audio', forbidden)
    phase = 'late' if stage == 'late' else 'initial'
    before = record_partial.RERUNS.labels(phase=phase, outcome=refusal + '_refused')._value.get()
    await audio.drain(now=NOW + 3600)
    assert record_partial.RERUNS.labels(phase=phase, outcome=refusal + '_refused')._value.get() == before + 1
    assert len([row for row in source[1].rows.values() if row.get('projection_binding')]) == 0


@pytest.mark.parametrize('refusal', ['byok', 'discarded'])
async def test_continuation_intake_rechecks_after_staging_race(source, audio, monkeypatch, refusal):
    audio.add(100)
    assert finish(source) == 'partial_finished'
    await audio.drain()
    original = audio.artifacts.stage_audio

    def racing(item, body):
        uri = original(item, body)
        if refusal == 'byok':
            set_byok(source)
        else:
            source[1].rows[ROW]['discarded'] = True
        return uri

    monkeypatch.setattr(audio.artifacts, 'stage_audio', racing)
    with pytest.raises(ValueError, match='partial BYOK excluded|target unavailable'):
        await audio.drain()
    assert not any(row.get('projection_binding') for row in source[1].rows.values())


@pytest.mark.parametrize('refusal', ['byok', 'discarded'])
async def test_continuation_rechecks_after_listing_before_reading_audio(source, audio, monkeypatch, refusal):
    audio.add(100)
    assert finish(source) == 'partial_finished'

    def racing(*args, **kwargs):
        if refusal == 'byok':
            set_byok(source)
        else:
            source[1].rows[ROW]['discarded'] = True
        return list(audio.chunks)

    def forbidden(*args, **kwargs):
        pytest.fail('row changed during listing; retained audio must not be read')

    monkeypatch.setattr(record_partial, 'list_audio_chunks', racing)
    monkeypatch.setattr(live, 'retained_record_units', forbidden)
    await audio.drain()
    assert not pending(source).get('partial_run')


async def test_completed_coordinator_polls_hourly_and_retires_after_24h_without_deleting(source, audio, monkeypatch):
    audio.add(100)
    assert finish(source) == 'partial_finished'
    calls = []
    monkeypatch.setattr(record_partial, 'list_audio_chunks', lambda *a, **k: calls.append(1) or list(audio.chunks))
    await audio.drain()
    await audio.drain()
    content = record_partial.page_content(pending(source)['partial_run'])
    source[0].run(lambda tx: tx.put('content', 'synthetic/' + content, {'status': 'completed'}))
    await audio.drain()
    assert pending(source)['available_at'] == NOW + 3600
    await audio.drain(now=NOW + 3599)
    assert len(calls) == 1
    for hour in range(1, 24):
        await audio.drain(now=NOW + hour * 3600)
        assert pending(source)['available_at'] == NOW + (hour + 1) * 3600
        assert pending(source)['state'] == 'record_pending'
    before = record_partial.RERUNS.labels(phase='late', outcome='retired')._value.get()
    artifacts_before = deepcopy(audio.artifacts.client.objects)
    await audio.drain(now=NOW + 86400)
    assert len(calls) == 25
    assert pending(source)['state'] == 'partial_retired'
    assert record_partial.RERUNS.labels(phase='late', outcome='retired')._value.get() == before + 1
    assert audio.artifacts.client.objects == artifacts_before
    assert source[1].rows[ROW]['record_audio_partial']
    assert source[1].rows[ROW]['record_audio_closed'] is False
    audio.add(101)  # Unsignalled storage-only arrivals cannot restart polling.
    await audio.drain(now=NOW + 90000)
    assert len(calls) == 25
    # Ordinary repair does not restart polling without a new upload revision.
    assert finish(source) == 'already_partial'
    assert pending(source)['state'] == 'partial_retired'
    set_record_upload_pending('synthetic', 'record', 'late', True, firestore_client=source[1])
    set_record_upload_pending('synthetic', 'record', 'late', False, firestore_client=source[1])
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: NOW + 90000)
    source[2]['captured_at'] = NOW + 89999
    assert (
        cluster.repair_one(
            source[0],
            audio.artifacts.client,
            audio.artifacts,
            '/'.join(ROW),
            flags=FLAGS,
            inventory=lambda: source[2],
            budget=SweepBudget(240),
        )
        == 'partial_finished'
    )
    assert pending(source)['state'] == 'record_pending'
    assert 'retired_at' not in pending(source)['partial_run']
    await audio.drain(now=NOW + 90000)
    assert len(calls) == 26
    assert pending(source)['state'] == 'record_pending'
    assert pending(source)['partial_run']['generation'] == 2
    await audio.drain(now=NOW + 90000)
    assert sorted(row['capture_at'] for row in source[1].rows.values() if row.get('projection_binding')) == [100, 101]


async def test_inventory_change_resets_retirement_window(source, audio):
    assert finish(source) == 'partial_finished'
    await audio.drain()
    audio.add(100)
    await audio.drain(now=NOW + 23 * 3600)
    run = pending(source)['partial_run']
    assert run['generation'] == 2 and not run['complete']
    assert run['inventory_changed_at'] == NOW + 23 * 3600
    await audio.drain(now=NOW + 25 * 3600)
    assert pending(source)['state'] == 'record_pending'


async def test_hourly_poll_claim_fences_stale_scheduler_snapshots_before_listing(source, audio, monkeypatch):
    assert finish(source) == 'partial_finished'
    await audio.drain()
    snapshot = pending(source)
    calls = []

    def listed(*args, **kwargs):
        assert pending(source)['partial_run']['next_inventory_at'] == NOW + 7200
        calls.append(1)
        return []

    monkeypatch.setattr(record_partial, 'list_audio_chunks', listed)
    for _ in range(2):
        await record_partial.drain_partial(
            source[0],
            snapshot,
            source[1].rows[ROW],
            audio.artifacts.client,
            audio.artifacts,
            live.retained_record_units,
            now=NOW + 3600,
        )
    assert len(calls) == 1


@pytest.mark.parametrize('listing_error', [False, True])
async def test_live_drainer_never_overwrites_hourly_inventory_schedule(source, audio, monkeypatch, listing_error):
    assert finish(source) == 'partial_finished'
    await audio.drain()
    monkeypatch.setattr(live.time, 'time', lambda: NOW + 3600)
    monkeypatch.setattr(source[0], 'due', lambda *args: [pending(source)['segment_id']])
    if listing_error:

        def unavailable(*args, **kwargs):
            raise RuntimeError('synthetic listing error')

        monkeypatch.setattr(record_partial, 'list_audio_chunks', unavailable)
    await live.drain_recordings(source[0])
    assert pending(source)['available_at'] == NOW + 7200


def test_late_object_filling_4100_holes_reapplies_worker_reference_bound():
    origin, frames = 1600000, 9000
    pcm = b'\x01\x00' * frames
    ref = {
        'start_frame': 0,
        'frames': frames,
        'offset_frame': 0,
        'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
        'bucket': 'retained',
        'path': 'chunks/synthetic/record/late',
        'generation': 1,
    }
    coverage = [[origin + 2 * i, origin + 2 * i + 1] for i in range(4100)]
    units, covered = missing_units([(100, frames / 16000, [ref])], coverage)
    assert len(units) == 17
    assert max(len(refs) for _, _, refs in units) <= 256
    assert sum(r['frames'] for _, _, refs in units for r in refs) == frames - 4100
    assert covered == [{'start': origin, 'end': origin + frames}]
    recognized_frames = 0
    downloads = []
    for start, duration, refs in units:
        item = SimpleNamespace(
            owner_id='synthetic', conversation_id='record', capture_at=start, duration_seconds=duration
        )
        body = (
            MAGIC
            + json.dumps(
                {
                    'owner_id': item.owner_id,
                    'conversation_id': item.conversation_id,
                    'capture_at': start,
                    'references': refs,
                    'context': {},
                }
            ).encode()
        )
        wav = materialize(body, item, lambda reference: downloads.append(reference['generation']) or pcm)
        with wave.open(io.BytesIO(wav), 'rb') as stream:
            recognized_frames += stream.readframes(stream.getnframes()).count(b'\x01\x00')
    assert recognized_frames == frames - 4100
    assert len(downloads) == len(units)  # One pinned source read per bounded unit, not per hole.


@pytest.mark.parametrize('change', [{'generation': 2}, {'path': 'chunks/synthetic/record/other'}, {'bucket': 'other'}])
def test_source_reuse_never_crosses_a_pinned_identity(change):
    pcm = b'\x01\x00' * 2
    ref = {
        'bucket': 'retained',
        'path': 'chunks/synthetic/record/late',
        'generation': 1,
        'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
        'start_frame': 0,
        'offset_frame': 0,
        'frames': 1,
    }
    item = SimpleNamespace(owner_id='synthetic', conversation_id='record', capture_at=100, duration_seconds=2 / 16000)
    refs = [ref, {**ref, **change, 'start_frame': 1, 'offset_frame': 1}]
    body = (
        MAGIC
        + json.dumps(
            {
                'owner_id': item.owner_id,
                'conversation_id': item.conversation_id,
                'capture_at': 100,
                'references': refs,
                'context': {},
            }
        ).encode()
    )
    calls = []
    materialize(body, item, lambda source: calls.append(source) or pcm)
    assert len(calls) == 2


@pytest.fixture
def audio(source, monkeypatch):
    store, client, _ = source
    chunks, pcm = [], {}

    class Storage(ObjectClient):
        def blob(self, name, generation=None):
            if not name.startswith('chunks/'):
                return super().blob(name, generation)
            body = pcm[name]

            class Raw:
                size = len(body)
                metadata = {}

                def reload(self, **kwargs):
                    assert generation == kwargs['if_generation_match'] == 1

                def download_as_bytes(self, **kwargs):
                    assert generation == kwargs['if_generation_match'] == 1
                    return body

            return Raw()

    storage = Storage()
    artifacts = create_artifact_store(store, storage, 'synthetic-batch-bucket', b'x' * 32)
    monkeypatch.setattr(record_partial, 'list_audio_chunks', lambda *args, **kwargs: list(chunks))
    monkeypatch.setattr(live, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(live, 'create_artifact_store', lambda *args: artifacts)

    def enqueue(tx, item, now, *, policy):
        # Queue ordering is covered by the scheduler's own emulator contract.
        # Keep the actual intake/privacy/staging transaction under StrictFirestore.
        if tx.get('jobs', item.segment_id):
            return False
        tx.put(
            'jobs',
            item.segment_id,
            {
                **asdict(item),
                'state': 'ready',
                'policy': policy.to_dict(),
                'owner_key': record_partial.owner_key(item.owner_id),
                'merge_pending': True,
            },
        )
        return True

    from utils.batch_pipeline import record_provider

    def admit_with_queue_seam(*args, **kwargs):
        kwargs.setdefault('enqueue', enqueue)
        return admit(*args, **kwargs)

    monkeypatch.setattr(record_provider, 'admit', admit_with_queue_seam)

    def add(start, frames=16000):
        name = f'chunks/synthetic/record/{len(chunks)}.pcm'
        chunks.append({'path': name, 'generation': 1, 'timestamp': start})
        pcm[name] = b'\x01\x00' * frames

    async def drain(now=NOW):
        return await live.admit_recording(
            store, pending(source), now=now, provider_outbox_factory=lambda: environment.outbox
        )

    environment = SimpleNamespace(add=add, drain=drain, chunks=chunks, pcm=pcm, artifacts=artifacts, outbox=None)
    return environment


async def test_real_staging_admission_worker_late_audio_and_serial_receipts(source, audio):
    audio.add(100)
    assert finish(source) == 'partial_finished'
    await audio.drain()  # durable immutable plan
    await audio.drain()  # real admission, normal scheduler job
    store = source[0]
    run = pending(source)['partial_run']
    content = record_partial.page_content(run)
    jobs = [
        row
        for (path, row) in source[1].rows.items()
        if path[0] == 'batch_pipeline_dev_jobs' and not row.get('partial_coordinator')
    ]
    assert len(jobs) == 1
    item = live.WorkItem(**{key: jobs[0][key] for key in live.WorkItem.__dataclass_fields__ if key in jobs[0]})
    wav = audio.artifacts.fetch_audio(item)
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        assert stream.readframes(stream.getnframes()) == audio.pcm[audio.chunks[0]['path']]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: decode_pcm16_wav(audio.artifacts.fetch_audio(work))
    )
    assert worker.process_batch([item])[0].segment_id == item.segment_id
    assert saved[item.segment_id]['words'] and not failures
    before = len(jobs)
    await audio.drain()  # ledger owns the in-flight page, no duplicate enqueue
    assert len([p for p in source[1].rows if p[0] == 'batch_pipeline_dev_jobs']) == before + 1
    store.run(lambda tx: tx.put('content', 'synthetic/' + content, {'status': 'completed'}))
    await audio.drain()
    assert pending(source)['partial_run']['complete']
    assert source[1].rows[ROW]['record_audio_partial']['applied_generation'] == 1
    audio.add(101)
    await audio.drain(now=NOW + 3600)
    await audio.drain(now=NOW + 3600)
    later = pending(source)['partial_run']
    assert later['generation'] == 2
    new_content = record_partial.page_content(later)
    new_jobs = [
        row
        for path, row in source[1].rows.items()
        if path[0] == 'batch_pipeline_dev_jobs'
        and (row.get('projection_binding') or {}).get('content_id') == new_content
    ]
    assert len(new_jobs) == 1
    assert new_jobs[0]['capture_at'] == 101 and new_jobs[0]['duration_seconds'] == 1
    assert new_jobs[0]['projection_binding']['partial_record']
    assert not source[1].rows[ROW]['record_audio_closed']


@pytest.mark.parametrize('language', ['en', 'und'])
async def test_auto_partial_freezes_audio_proof_without_changing_custody(source, audio, monkeypatch, language):
    from diarizer.batch_pipeline_models import stt_language
    from utils.batch_pipeline import record_language
    from utils.batch_pipeline.audio import read_context

    row = source[1].rows[ROW]
    row.update(
        language='multi',
        client_platform='ios',
        external_data={'server_batch_only': True},
        has_content=True,
        server_batch_audio_start=100,
        server_batch_audio_end=110,
    )
    audio.add(100)
    assert finish(source) == 'partial_finished'
    proof = {
        'stt_language': language,
        'stt_language_evidence': 'audio_lid' if language == 'en' else 'unavailable',
        'stt_language_confidence': 0.99 if language == 'en' else 0.0,
    }
    classify = AsyncMock(return_value=proof)
    monkeypatch.setattr(record_language, 'classify_wav', classify)
    monkeypatch.setattr(
        record_language, 'ServingLanguageProbeGuard', lambda *a, **k: SimpleNamespace(raise_if_denied=lambda: None)
    )
    await audio.drain()
    await audio.drain()
    jobs = [
        job
        for path, job in source[1].rows.items()
        if path[0] == 'batch_pipeline_dev_jobs' and not job.get('partial_coordinator')
    ]
    assert len(jobs) == 1 and classify.call_count == 1
    intakes = [
        intake
        for path, intake in source[1].rows.items()
        if path[0] == 'batch_pipeline_dev_intakes' and intake.get('record_partial_parent')
    ]
    assert len(intakes) == 1
    assert intakes[0]['language_receipts'][jobs[0]['segment_id']] == {
        'version': 1,
        'language': language,
        'evidence': 'audio_lid' if language == 'en' else 'unavailable',
    }
    work = live.WorkItem(**{key: jobs[0][key] for key in live.WorkItem.__dataclass_fields__ if key in jobs[0]})
    context = read_context(audio.artifacts.fetch_audio(work))
    assert stt_language(context, duration_seconds=1) == language
    assert context['conversation_id'] == 'record'
    assert len(audio.chunks) == 1 and audio.pcm[audio.chunks[0]['path']]
    assert pending(source)['state'] == 'record_pending'


async def test_over_cap_rows_use_real_worker_bounds_and_two_pages(source, audio):
    for i in range(129):
        audio.add(100 + 40 * i, frames=16)
    assert finish(source) == 'partial_finished'
    await audio.drain()
    assert pending(source)['partial_run']['units'] == 129
    await audio.drain()
    run = pending(source)['partial_run']
    store = source[0]
    content = record_partial.page_content(run)
    store.run(lambda tx: tx.put('content', 'synthetic/' + content, {'status': 'completed'}))
    await audio.drain()
    assert pending(source)['partial_run']['page'] == 1
    await audio.drain()
    groups = {}
    for path, row in source[1].rows.items():
        binding = row.get('projection_binding') or {}
        if binding:
            groups[binding['content_id']] = len(binding['segment_ids'])
    assert sorted(groups.values()) == [1, 128]


def test_more_than_4096_references_split_without_weakening_complete_proof(source, audio):
    for i in range(4097):
        audio.add(100 + i / 16000, frames=1)
    with pytest.raises(ValueError, match='reference budget'):
        list(live.retained_record_units('synthetic', 'record', audio.chunks, audio.artifacts.client, b'x' * 32))
    units = list(
        live.retained_record_units('synthetic', 'record', audio.chunks, audio.artifacts.client, b'x' * 32, partial=True)
    )
    assert sum(len(refs) for _, _, refs in units) == 4097
    assert max(len(refs) for _, _, refs in units) <= 256


@pytest.mark.parametrize('preview,enabled', [(False, True), (True, True), (False, False)])
def test_real_repair_composes_partial_after_tail_refusal(source, audio, monkeypatch, preview, enabled):
    audio.add(100)
    monkeypatch.setenv('RECORD_AUDIO_PARTIAL_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *args, **kwargs: list(audio.chunks))
    details = {}
    result = cluster.repair_one(
        source[0],
        audio.artifacts.client,
        audio.artifacts,
        '/'.join(ROW),
        flags=FLAGS,
        inventory=lambda: source[2],
        budget=SweepBudget(240),
        mode='plan' if preview else 'apply',
        reason_out=details,
    )
    assert result == ('proof_refused' if not enabled else 'partial_eligible' if preview else 'partial_finished')
    assert bool(source[1].rows[ROW].get('record_audio_partial')) == (enabled and not preview)
    assert audio.pcm[audio.chunks[0]['path']] == b'\x01\x00' * 16000


async def test_producer_starts_during_staging_prevents_intake_commit(source, audio, monkeypatch):
    audio.add(100)
    assert finish(source) == 'partial_finished'
    await audio.drain()
    original = audio.artifacts.stage_audio

    def racing(item, body):
        uri = original(item, body)
        set_record_upload_pending('synthetic', 'record', 'late', True, firestore_client=source[1])
        return uri

    monkeypatch.setattr(audio.artifacts, 'stage_audio', racing)
    with pytest.raises(ValueError, match='barrier'):
        await audio.drain()
    assert len([path for path in source[1].rows if path[0] == 'batch_pipeline_dev_jobs']) == 1


async def test_deletion_during_partial_plan_read_returns_no_plaintext(source, audio):
    audio.add(100)
    assert finish(source) == 'partial_finished'
    await audio.drain()
    audio.artifacts.client.after_download = lambda: source[1].rows.__setitem__(
        ('users', 'synthetic', 'deleted_conversations', 'record'), {'deleted': True}
    )
    with pytest.raises(BatchPrivacyBlocked):
        await audio.drain()
    assert len([path for path in source[1].rows if path[0] == 'batch_pipeline_dev_jobs']) == 1


@pytest.mark.parametrize('language', ['ca', 'sw'])
async def test_unsupported_partial_uses_durable_modulate_outbox_after_rollback(source, audio, monkeypatch, language):
    from utils.batch_pipeline import record_provider
    from utils.batch_pipeline.audio import read_context

    row = source[1].rows[ROW]
    row.update(
        language=language,
        external_data={'server_batch_only': True},
        has_content=True,
        server_batch_audio_start=100,
        server_batch_audio_end=110,
    )
    audio.add(100)
    assert finish(source) == 'partial_finished'
    monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', '')
    from database.outbox_provider_stt import FirestoreProviderSttOutbox

    wakes = Mock()
    outbox = FirestoreProviderSttOutbox(client=source[1], collection='synthetic_provider_outbox', create_wake=wakes)
    audio.outbox = outbox
    await audio.drain()
    await audio.drain()
    jobs = [
        job
        for path, job in source[1].rows.items()
        if path[0] == 'batch_pipeline_dev_jobs' and not job.get('partial_coordinator')
    ]
    assert len(jobs) == 1
    job = jobs[0]
    assert job['state'] == 'provider_pending'
    assert job['stt_route']['language'] == language
    assert job['stt_route']['provider_service'] == 'modulate'
    assert job['policy']['provider_service'] == 'modulate'
    assert job['policy']['batch_enabled']
    assert not job['requires_compute_admission']
    assert job['projection_binding']['native_record'] and job['projection_binding']['partial_record']
    rows = [value for path, value in source[1].rows.items() if path[0] == 'synthetic_provider_outbox']
    assert len(rows) == 1 and rows[0]['segment_id'] == job['segment_id']
    wakes.assert_called_once()
    work = live.WorkItem(**{key: job[key] for key in live.WorkItem.__dataclass_fields__ if key in job})
    context = read_context(audio.artifacts.fetch_audio(work))
    assert context['stt_language'] == language and context['stt_language_evidence'] == 'declared'
    assert len(audio.chunks) == 1 and audio.pcm[audio.chunks[0]['path']]
    assert not any(path[0] in {'batch_pipeline_dev_queues', 'batch_pipeline_dev_control'} for path in source[1].rows)


@pytest.mark.parametrize(
    'mode,expected', [('off', 'upload_pending'), ('shadow', 'upload_pending'), ('serve', 'partial_finished')]
)
def test_lease_dead_partial_exit_and_hourly_coordinator(source, monkeypatch, mode, expected):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    source[1].rows[ROW]['record_upload_sessions'] = {
        's': {
            'pod': 'live',
            'process_started_at': 100,
            'last_signal_at': 100,
            'lease_expires_at': 3700,
            'signal_source': 'frames',
        }
    }
    source[2]['pods']['live'] = 1  # Scoped inventory proves this original pusher is still live.
    assert finish(source) == expected
    row = source[1].rows[ROW]
    assert not row.get('record_audio_closed')
    if expected == 'partial_finished':
        assert not row['record_upload_sessions']
        assert pending(source)['partial_coordinator']
        assert pending(source)['available_at'] == NOW
        assert row['record_audio_partial']['reason'] == 'tail_lagging'


def test_renewal_before_partial_transaction_keeps_live_uploader_fenced(source, monkeypatch):

    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    source[1].rows[ROW]['record_upload_sessions'] = {
        's': {
            'pod': 'live',
            'process_started_at': 100,
            'last_signal_at': 100,
            'lease_expires_at': 3700,
            'signal_source': 'frames',
        }
    }
    renew_record_token_lease('synthetic', 'record', source='frames', session='s', firestore_client=source[1])
    assert finish(source) == 'upload_pending'


@pytest.mark.parametrize('accepted', [False, True])
async def test_custody_fence_old_partial_pass_then_bytes_land_is_rerun(source, audio, monkeypatch, accepted):
    from database import record_custody_append as custody

    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    audio.add(100)
    assert finish(source) == 'partial_finished'
    await audio.drain()  # Old-audio plan exists before the upload starts.
    revision = source[1].rows[ROW].get('record_upload_revision', 0)
    assert custody.begin('synthetic', 'record', 'custody:interleaving', firestore_client=source[1])
    assert source[1].rows[ROW].get('record_upload_revision', 0) == revision
    assert finish(source) == 'upload_pending'
    with pytest.raises(ValueError, match='barrier'):
        await audio.drain()  # No old-audio pass may commit through the fence.
    audio.add(105)  # The late bytes now land durably.
    if not accepted:
        from utils.batch_pipeline.record_lease_append import wake_partial

        wake_partial(source[0], 'synthetic', 'record', NOW)
    custody.finish('synthetic', 'record', 'custody:interleaving', accepted=accepted, firestore_client=source[1])
    assert source[1].rows[ROW].get('record_upload_revision', 0) == revision + accepted
    # An incomplete old plan may finish its old page, but the new revision and
    # changed inventory schedule a subsequent generation containing these bytes.
    assert pending(source)['partial_run']['next_inventory_at'] == NOW
    assert not source[1].rows[ROW]['record_upload_sessions']
    await audio.drain()
    run = pending(source)['partial_run']
    assert run['generation'] == 2
    plan = audio.artifacts.load_record_plan(record_partial.seed_for(pending(source)), run['plan_uri'])
    assert any(ref['path'] == audio.chunks[-1]['path'] for _, _, refs in plan['units'] for ref in refs)


@pytest.mark.parametrize('writer', ['renew', 'begin'])
@pytest.mark.parametrize('status', ['completed', 'processing', 'recording'])
async def test_frames_fill_interior_gap_after_complete_seal_and_schedule_real_work(
    source, audio, monkeypatch, writer, status
):
    from database.batch_pipeline_record_lease_recovery import recovery_segment

    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    audio.add(100)
    audio.add(109)  # Old retained tail already reaches finished_at.
    assert finish(source) == 'partial_finished'
    original = pending(source)
    original.update(state='committed', partial_coordinator=False)
    source[0].run(lambda tx: tx.put('jobs', original['segment_id'], original))
    source[1].rows[ROW].update(
        record_audio_closed=True, record_audio_partial=None, record_upload_sessions={}, status=status
    )
    revision = source[1].rows[ROW].get('record_upload_revision', 0)
    barrier = None
    if writer == 'begin':
        from database import record_audio
        from utils import pusher_record_barrier

        monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: source[1])
        monkeypatch.setattr(
            pusher_record_barrier, 'producer_identity', lambda: {'pod': 'resumed-pusher', 'process_started_at': 100}
        )
        barrier = pusher_record_barrier.PusherRecordBarrier('synthetic')
        await barrier.begin_recording('record')
        assert barrier.upload_sessions['record'] in source[1].rows[ROW]['record_upload_sessions']
    else:
        assert renew_record_token_lease(
            'synthetic',
            'record',
            source='frames',
            session='resumed',
            producer={'pod': 'resumed-pusher', 'process_started_at': 100},
            firestore_client=source[1],
        )
    audio.add(105)  # Interior audio, not a missing tail.
    # The obligation exists before any older job changes the conversation's
    # status. Normal continuation can wait for finalization/publication.
    recovery = source[0].run(lambda tx: tx.get('jobs', recovery_segment('synthetic', 'record')))
    assert recovery['partial_coordinator']
    source[1].rows[ROW]['status'] = 'completed'
    interior_pcm = audio.pcm[audio.chunks[-1]['path']]
    audio.chunks.sort(key=lambda chunk: chunk['timestamp'])
    assert source[1].rows[ROW]['record_upload_revision'] == revision + 1
    assert not source[1].rows[ROW]['record_audio_closed']
    if barrier is not None:
        assert await barrier.finish_recording('record')
    else:
        set_record_upload_pending('synthetic', 'record', 'resumed', False, firestore_client=source[1])
        assert seal_record_audio('synthetic', 'record', firestore_client=source[1]) is None
    segment = recovery_segment('synthetic', 'record')
    await live.admit_recording(source[0], source[0].run(lambda tx: tx.get('jobs', segment)), now=NOW)
    await live.admit_recording(source[0], source[0].run(lambda tx: tx.get('jobs', segment)), now=NOW)
    jobs = [
        row
        for path, row in source[1].rows.items()
        if path[0] == 'batch_pipeline_dev_jobs' and row.get('projection_binding', {}).get('partial_record')
    ]
    interior = next(row for row in jobs if row['capture_at'] <= 105 < row['capture_at'] + row['duration_seconds'])
    item = live.WorkItem(**{key: interior[key] for key in live.WorkItem.__dataclass_fields__ if key in interior})
    wav = audio.artifacts.fetch_audio(item)
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        stream.setpos(round((105 - interior['capture_at']) * 16000))
        assert stream.readframes(16000) == interior_pcm
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: decode_pcm16_wav(audio.artifacts.fetch_audio(work))
    )
    assert worker.process_batch([item])[0].segment_id == item.segment_id
    assert saved[item.segment_id]['words'] and not failures
    assert source[0].run(lambda tx: tx.get('jobs', original['segment_id'])) == original


def test_crashed_post_seal_producer_has_partial_finish_exit_on_recovery_coordinator(source, monkeypatch):
    from database.batch_pipeline_record_lease_recovery import recovery_segment

    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    assert finish(source) == 'partial_finished'
    original = pending(source)
    original.update(state='committed', partial_coordinator=False)
    source[0].run(lambda tx: tx.put('jobs', original['segment_id'], original))
    source[1].rows[ROW].update(record_audio_closed=True, record_audio_partial=None, record_upload_sessions={})
    renew_record_token_lease(
        'synthetic',
        'record',
        source='frames',
        session='crashed',
        producer={'pod': 'resumed', 'process_started_at': 100},
        firestore_client=source[1],
    )
    now = NOW + 3601
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: now)
    proof = {**source[2], 'captured_at': now}
    assert (
        finish_partial(source[0], '/'.join(ROW), reason='tail_lagging', proof=proof, now=now, retry_aged=True)
        == 'partial_finished'
    )
    assert not source[1].rows[ROW]['record_upload_sessions']
    recovery = source[0].run(lambda tx: tx.get('jobs', recovery_segment('synthetic', 'record')))
    assert recovery['state'] == 'record_pending' and recovery['partial_coordinator']
    assert source[0].run(lambda tx: tx.get('jobs', original['segment_id'])) == original


@pytest.mark.parametrize('old_state', ['record_pending', 'committed'])
def test_post_seal_recovery_preserves_old_work_and_waits_for_full_publication(source, monkeypatch, old_state):
    from database.batch_pipeline_record_lease_recovery import recovery_segment
    from database.record_partial import continuation_refusal

    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    assert finish(source) == 'partial_finished'
    original = pending(source)
    original.update(state=old_state, partial_coordinator=False)
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')  # A later ramp cannot replace the stored policy.
    source[0].run(lambda tx: tx.put('jobs', original['segment_id'], original))
    source[1].rows[ROW].update(record_audio_closed=True, record_audio_partial=None, record_upload_sessions={})
    renew_record_token_lease(
        'synthetic',
        'record',
        source='frames',
        session='resumed',
        producer={'pod': 'resumed', 'process_started_at': 100},
        firestore_client=source[1],
    )
    if old_state == 'record_pending':
        assert pending(source)['policy'] == original['policy']
        assert not pending(source)['partial_coordinator']
        assert not source[0].run(lambda tx: tx.get('jobs', recovery_segment('synthetic', 'record')))
        return
    recovery = source[0].run(lambda tx: tx.get('jobs', recovery_segment('synthetic', 'record')))
    assert recovery['policy'] == original['policy']
    content = original['record_content_id']
    source[0].run(lambda tx: tx.put('intakes', 'bp_' + content, {'segment_ids': [original['segment_id']]}))
    source[0].run(lambda tx: tx.put('content', 'synthetic/' + content, {'status': 'processing'}))
    assert continuation_refusal(source[0], recovery) == 'state_changed'
    source[0].run(lambda tx: tx.put('content', 'synthetic/' + content, {'status': 'completed'}))
    assert continuation_refusal(source[0], recovery) is None
    assert pending(source) == original
