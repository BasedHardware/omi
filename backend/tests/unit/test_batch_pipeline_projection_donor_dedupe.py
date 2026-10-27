"""Batch publication reaches the shared donor contract and post-commit observation."""

from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database import conversations as db
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_donor_live_dedupe import WORDS, bridge_lines, rows
from utils.batch_pipeline import projection
from utils.batch_pipeline.audio import audio_unit, with_context
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import owner_key
from utils.sync import recording_lineage, recording_session_target


@pytest.fixture
def batch_projection(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setattr(db, 'index_sync_assignment', lambda *a: None)
    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', lambda *a, **kw: ())
    client = StrictFirestore()
    live, donor = rows()
    # The donor contains both a retimed repeat and novel speech.
    donor['transcript_segments'].append(
        dict(start=12, end=16, text='Novel donor speech must survive consolidation.', speaker_id=0, is_user=False)
    )
    donor['finished_at'] = donor['started_at'] + timedelta(seconds=16)
    db.assign_sync_conversation('u', donor, firestore_client=client)
    client.rows[('users', 'u', 'conversations', 'live')] = live
    client.rows[('users', 'u')] = {'data_protection_level': 'standard'}
    binding = ProjectionBinding(
        'u',
        'job',
        'content',
        ('segment',),
        client_device_id='pendant',
        target_conversation_id='live',
        privacy_generation=0,
    )
    work = WorkItem(
        'segment',
        'u',
        1020,
        'gs://synthetic/audio#1',
        10,
        Priority.FRESH,
        privacy_generation=0,
        requires_compute_admission=True,
    )
    namespace = 'batch_pipeline_test_donor'
    result = {'outcome': 'success', 'result_uri': 'gs://synthetic/result#1'}
    client.rows[(f'{namespace}_jobs', work.segment_id)] = {
        **asdict(work),
        'projection_binding': asdict(binding),
        'result': result,
        'policy_parts': {'projection': ProjectionPolicy().to_dict()},
    }
    client.rows[(f'{namespace}_results', work.segment_id)] = {
        'protocol_version': 1,
        'segment_id': work.segment_id,
        'owner_key': owner_key('u'),
        'capture_at': work.capture_at,
        'previous_segment_id': None,
        'result': result,
        'projection_state': 'pending',
    }
    client.rows[(f'{namespace}_owners', owner_key('u'))] = {}
    ledger = sync_content_ledger_ref(client, 'u', binding.content_id)
    client.rows[ledger.path] = {
        'dispatch_protocol': 'batch_v1',
        'status': 'processing',
        'job_id': binding.job_id,
        'batch_pipeline': {'protocol_version': 1, 'namespace': namespace, 'segment_ids': ['segment']},
    }
    payload = {
        'audio_seconds': 10,
        'speech_seconds': 4,
        'speech_spans': [{'start': 0, 'end': 4}],
        'words': [{'word': 'Fresh projected speech is also preserved.', 'timestamp': [0, 4]}],
        'diarization': {'turns': [{'start': 0, 'end': 4, 'speaker': 'SPEAKER_00'}]},
    }
    context = {
        'owner_id': 'u',
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': work.segment_id,
        'capture_at': work.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': binding.target_conversation_id,
        'recording_session_id': 'synthetic-origin',
        'audio_start_seconds': 1000,
        'audio_end_seconds': 1030,
        'filenames': ['f.opus'],
        'capture_evidence_claims': {
            'f.opus': {
                'capture_root': '12345678-1234-4234-8234-123456789abc',
                'clock_epoch': 0,
                'source_frame_start': 0,
                'frame_count': 100,
                'rate_hz': 16000,
                'channel': 'mono',
                'codec': 'opus',
            }
        },
    }

    # Only metadata discovery is injected; resolve_context, its S1/cohort gates,
    # build_incoming, assignment and ProjectionSession persistence stay real.
    def targets(ids, *args):
        args[-1].update({ids[0]: 'bound'})
        return {ids[0]: 'live'}

    planned = Mock(side_effect=targets)
    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', planned)
    monkeypatch.setattr(recording_session_target, 'resolve_recording_session_sync_target', lambda *a, **kw: 'live')
    projector = projection.Projector(
        SimpleNamespace(client=client, namespace=namespace),
        Mock(return_value=payload),
        fetch_audio=lambda _: with_context(audio_unit(1020, b'\0\0').wav, context),
        clock=lambda: 2000,
    )
    # External audio/enrichment/client completion is outside content transfer.
    monkeypatch.setattr(projector, 'finish_part', Mock())
    monkeypatch.setattr(projector, '_finish', lambda *a, **kw: None)
    markers = []
    assign = db.assign_sync_conversation

    def observed_assignment(uid, incoming, **kwargs):
        markers.append(incoming.get('_sync_lineage_eligible', False))
        return assign(uid, incoming, **kwargs)

    monkeypatch.setattr(db, 'assign_sync_conversation', observed_assignment)
    return SimpleNamespace(**locals())


@pytest.mark.parametrize('gate', ['on', 'no_s1', 'dedupe_off', 'lineage_off', 'not_allowlisted'])
def test_batch_entrypoint_dedupes_donor_and_observes_committed_transfer(batch_projection, monkeypatch, caplog, gate):
    lane = batch_projection
    if gate == 'no_s1':
        lane.context.pop('capture_evidence_claims')
    elif gate == 'dedupe_off':
        monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'false')
    elif gate == 'lineage_off':
        monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'false')
    elif gate == 'not_allowlisted':
        monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'other')
    active = gate in {'on', 'no_s1'}
    # A bridge line must never precede the transaction commit boundary.
    new_transaction = lane.client.transaction
    transaction = new_transaction()
    commit = transaction._commit

    def checked_commit():
        assert not bridge_lines(caplog)
        commit()

    monkeypatch.setattr(transaction, '_commit', checked_commit)
    monkeypatch.setattr(lane.client, 'transaction', lambda: transaction)
    with caplog.at_level(logging.INFO):
        lane.projector.project('segment')
    assert lane.markers == [gate in {'on', 'dedupe_off'}]
    assert lane.planned.call_count == int(gate in {'on', 'dedupe_off'})
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    segments = db.decode_transcript_segments_verified(
        'u', stored['transcript_segments'], stored.get('transcript_segments_compressed', False)
    )
    assert sum(s['text'] == WORDS for s in segments) == (1 if active else 2)
    assert sum(s['text'] == 'Novel donor speech must survive consolidation.' for s in segments) == 1
    assert sum(s['text'] == 'Fresh projected speech is also preserved.' for s in segments) == 1
    assert len(bridge_lines(caplog)) == int(active)
    if active:
        assert 'outcome=bridge_clear' in bridge_lines(caplog)[0]
        assert 'operation=assignment' in bridge_lines(caplog)[0]
        assert 'lexical_proof_count_bucket=1' in bridge_lines(caplog)[0]
    assert lane.client.rows[('users', 'u', 'conversations', 'donor')]['sync_merged_into'] == 'live'
    entry = lane.client.rows[(f'{lane.namespace}_results', 'segment')]
    assert entry['projection']['conversation_id'] == 'live'
    before = deepcopy(stored)
    monkeypatch.setattr(lane.client, 'transaction', new_transaction)
    # StrictFirestore enforces ordering but does not evaluate ArrayUnion.
    # Materialize this known output union before testing the receipt replay.
    lane.client.rows[(f'{lane.namespace}_jobs', 'segment')]['conversation_ids'] = ['live']
    entry['conversation_ids'] = ['live']
    with caplog.at_level(logging.INFO):
        lane.projector.project('segment')
    assert lane.client.rows[('users', 'u', 'conversations', 'live')] == before
    assert len(bridge_lines(caplog)) == int(active)


@pytest.mark.parametrize('gate', ['allowlist', 'percent', 'disabled', 'outside'])
def test_batch_admission_switches_still_bound_projection_cohort(monkeypatch, gate):
    from database.batch_pipeline_intake import AdmissionDisabled, admit
    from tests.unit.test_batch_pipeline_intake import proposal
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false' if gate == 'disabled' else 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100' if gate == 'percent' else '0')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner' if gate == 'allowlist' else '')
    store = MemoryStore()
    works, binding = proposal()
    if gate in {'disabled', 'outside'}:
        with pytest.raises(AdmissionDisabled):
            admit(store, works, binding, 0, namespace='batch_pipeline_test_donor')
        assert not store.rows
    else:
        assert admit(store, works, binding, 0, namespace='batch_pipeline_test_donor')['outcome'] == 'batch'
        assert store.rows['jobs', 'segment']['projection_binding'] == asdict(binding)


def test_record_projection_replacement_rolls_over_before_staging_oversized_live_write(batch_projection, monkeypatch):
    from dataclasses import replace
    from utils.sync import assignment

    lane = batch_projection
    binding = replace(lane.binding, record_origin=True, native_record=True)
    lane.client.rows[(f'{lane.namespace}_jobs', 'segment')]['projection_binding'] = asdict(binding)
    live = lane.client.rows[('users', 'u', 'conversations', 'live')]
    live.update(
        record_lane_owner='batch_live_v1',
        status='completed',
        private_cloud_sync_enabled=True,
        structured={'overview': 'x' * 20000},
    )
    lane.client.rows[('users', 'u')]['private_cloud_sync_enabled'] = True
    for index, segment in enumerate(live['transcript_segments']):
        segment['id'] = f'live-{index}'
    before = deepcopy(live)
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 6000)
    lane.projector.project('segment')
    receipt = lane.client.rows[(f'{lane.namespace}_results', 'segment')]['projection']
    assert receipt['conversation_id'] != 'live'
    assert lane.client.rows[('users', 'u', 'conversations', 'live')] == before
    assert all(
        path != ('users', 'u', 'conversations', 'live') for tx in lane.client.transactions for path, _ in tx.updates
    )
    stored = lane.client.rows[('users', 'u', 'conversations', receipt['conversation_id'])]
    segments = db.decode_transcript_segments_verified(
        'u', stored['transcript_segments'], stored.get('transcript_segments_compressed', False)
    )
    assert any(s['text'] == 'Fresh projected speech is also preserved.' for s in segments)
