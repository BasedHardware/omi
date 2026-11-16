"""Exact bytes, zero paid redispatch, privacy and single-owner transactions."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import BatchUnitPolicy, ProjectionPolicy
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_source_projection import project_alias
from database import batch_pipeline_source_reuse as reuse
from database.batch_pipeline_staging import artifact_id
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import source_reuse
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding, Priority
from utils.batch_pipeline.scheduler import owner_key
from utils.capture.batch_coverage import decode_for_intake

UID = 'synthetic-owner'
NS = 'batch_pipeline_test_sources'
KEY = 'a' * 64
SOURCE = hashlib.sha256(b'canonical').hexdigest()
COPY = hashlib.sha256(b'alias').hexdigest()
NOW = 1750000200.0


def raw_file(tmp_path, *, at=1750000100, sample=1, seconds=1, name='one'):
    directory = tmp_path / name
    directory.mkdir(exist_ok=True)
    path = directory / f'audio_omi_pcm16_16000_{at}.bin'
    body = struct.pack('<h', sample) * round(16000 * seconds)
    path.write_bytes(
        b''.join(struct.pack('<I', len(body[i : i + 32000])) + body[i : i + 32000] for i in range(0, len(body), 32000))
    )
    return str(path)


def decoded(paths, *, device='device', epoch=None, maximum=3600):
    return list(
        decode_for_intake(paths, maximum, UID, {'client_device_id': device, 'clock_epoch': epoch}, decoder=decode_units)
    )


@pytest.fixture(autouse=True)
def local(monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'synthetic-source-secret')
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.delenv('BATCH_SOURCE_REUSE_ENABLED', raising=False)


def test_same_file_in_different_bundles_keeps_source_identity_and_new_tail(tmp_path):
    first = decoded([raw_file(tmp_path, name='a')])[0]
    later = decoded([raw_file(tmp_path, name='b'), raw_file(tmp_path, at=1750000101, name='tail', sample=2)])
    assert len(later) == 2
    assert first.source_reuse_key == later[0].source_reuse_key
    assert first.source_reuse_key != later[1].source_reuse_key
    assert [u.duration_seconds for u in later] == [1, 1]


def test_exact_negative_gap_copy_inside_one_bundle_is_decoded_once(tmp_path):
    units = decoded([raw_file(tmp_path, name='a'), raw_file(tmp_path, name='b')])
    assert len(units) == 1 and units[0].duration_seconds == 1


@pytest.mark.parametrize('changed', ['bytes', 'device', 'epoch', 'clock26', 'touching', 'gap'])
def test_time_or_repeated_speech_is_never_identity(changed, tmp_path):
    original = decoded([raw_file(tmp_path, name='a')])[0]
    kwargs = {'device': 'other'} if changed == 'device' else {'epoch': 1} if changed == 'epoch' else {}
    stamp = 1750000100 + {'clock26': 26, 'touching': 1, 'gap': 50}.get(changed, 0)
    copy = decoded([raw_file(tmp_path, name='b', at=stamp, sample=2 if changed == 'bytes' else 1)], **kwargs)[0]
    assert original.source_reuse_key != copy.source_reuse_key


def test_exact_silence_reuses_only_same_original_file(tmp_path):
    one = decoded([raw_file(tmp_path, name='a', sample=0)])[0]
    same = decoded([raw_file(tmp_path, name='b', sample=0)])[0]
    other = decoded([raw_file(tmp_path, name='c', at=1750000101, sample=0)])[0]
    assert one.source_reuse_key == same.source_reuse_key != other.source_reuse_key


def test_partial_file_is_not_whole_file_proof_and_split_tail_survives(tmp_path):
    original = decoded([raw_file(tmp_path, name='a', seconds=2)])[0]
    partial = decoded([raw_file(tmp_path, name='b', seconds=1)])[0]
    split = decoded([raw_file(tmp_path, name='c', seconds=2.5)], maximum=1)
    assert original.source_reuse_key != partial.source_reuse_key
    assert [u.duration_seconds for u in split] == [1, 1, 0.5]
    assert len({u.source_reuse_key for u in split}) == 3


@pytest.mark.parametrize(
    'context',
    [
        {},
        {'client_device_id': 'd', 'source_reuse_excluded': True},
        {'client_device_id': 'd', 'capture_evidence_claims': {'proof': True}},
        {'client_device_id': 'd', 'recording_session_id': 'session'},
    ],
)
def test_unsupported_source_context_abstains(tmp_path, context):
    assert not source_reuse.eligible([raw_file(tmp_path)], context)


def test_kill_switch_restores_packing_and_unknown_clocks_abstain(tmp_path, monkeypatch):
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', 'false')
    units = decoded([raw_file(tmp_path, name='a'), raw_file(tmp_path, at=1750000101, name='b')])
    assert len(units) == 1 and units[0].source_reuse_key is None
    monkeypatch.delenv('BATCH_SOURCE_REUSE_ENABLED')
    assert not source_reuse.eligible([raw_file(tmp_path, at=788918400, name='early')], {'client_device_id': 'd'})


def setup_store(*, outcome='success', corrected=False):
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace=NS))
    store.run = lambda operation, **kwargs: operation(client.transaction())
    store.policy = lambda _: ProjectionPolicy()
    user = client.collection('users').document(UID)
    user.create({'data_protection_level': 'standard'})
    user.collection('conversations').document('visible').create(
        {
            'id': 'visible',
            'transcript_segments': (
                [{'id': 'kept', 'text': 'Synthetic corrected sentence.', 'translation': 'Synthetic translation.'}]
                if corrected
                else []
            ),
        }
    )
    original = WorkItem(
        SOURCE,
        UID,
        1750000100.0,
        'gs://synthetic/source#1',
        1,
        Priority.FRESH,
        conversation_id='input',
        privacy_generation=0,
        source_reuse_key=KEY,
    )
    binding = ProjectionBinding(UID, 'source-job', 'source-content', (SOURCE,), privacy_generation=0)
    receipt = {
        'state': 'ready',
        'conversation_id': 'visible',
        'created': True,
        'speech_seconds': 0.0 if outcome == 'silence' else 1.0,
        'audio_required': False,
        'enrichment_required': False,
    }
    job = {
        **original.to_dict(),
        'state': 'committed',
        'projection_binding': asdict(binding),
        'result': {'segment_id': SOURCE, 'result_uri': 'gs://synthetic/result#1', 'outcome': outcome},
    }
    store.ref('jobs', SOURCE).create(job)
    store.ref('results', SOURCE).create(
        {
            'protocol_version': 2,
            'source_reuse_version': 1,
            'segment_id': SOURCE,
            'owner_key': owner_key(UID),
            'owner_id': UID,
            'capture_at': original.capture_at,
            'previous_segment_id': None,
            'committed_at': NOW - 20,
            'result': job['result'],
            'projection': receipt,
            'projection_state': 'completed',
        }
    )
    store.ref(reuse.TABLE, reuse.receipt_id(KEY)).create(
        {
            'owner_id': UID,
            'owner_key': owner_key(UID),
            'segment_id': SOURCE,
            'privacy_generation': 0,
            'source_conversation_ids': ['input', 'visible'],
            'complete': True,
            'expires_at': datetime.fromtimestamp(NOW, timezone.utc) + timedelta(days=1),
        }
    )
    sync_content_ledger_ref(client, UID, binding.content_id).create(
        {
            'status': 'completed',
            'job_id': binding.job_id,
            'usage_committed_seconds': receipt['speech_seconds'],
        }
    )
    for uri in (original.audio_uri, job['result']['result_uri']):
        store.ref('artifacts', artifact_id(SOURCE, uri)).create(
            {
                'owner_id': UID,
                'privacy_generation': 0,
                'cleanup_after': datetime.fromtimestamp(NOW, timezone.utc) + timedelta(hours=1),
            }
        )
    store.ref('owners', owner_key(UID)).create({'projection_watermark': SOURCE})
    return store, original


def prepare_copy(store, original, *, accepted=True):
    item = replace(
        original,
        segment_id=COPY,
        audio_uri='gs://synthetic/copy#1',
        source_alias_of=SOURCE if accepted else None,
        source_conversation_ids=('input', 'visible') if accepted else (),
    )
    binding = ProjectionBinding(UID, 'copy-job', 'copy-content', (COPY,), privacy_generation=0)
    result = {'segment_id': COPY, 'result_uri': 'gs://synthetic/copy-result#1', 'outcome': 'success'}
    store.ref('jobs', COPY).create(
        {
            **item.to_dict(),
            'projection_binding': asdict(binding),
            'state': 'committed',
            'owner_key': owner_key(UID),
            'result': result,
            **({'source_alias': {'segment_id': SOURCE}} if accepted else {}),
        }
    )
    store.ref('results', COPY).create(
        {
            'segment_id': COPY,
            'owner_key': owner_key(UID),
            'owner_id': UID,
            'protocol_version': 2,
            'source_alias_version': 1 if accepted else None,
            'source_reuse_version': 1,
            'capture_at': item.capture_at,
            'result': result,
            'previous_segment_id': SOURCE,
            'committed_at': NOW,
            'projection_state': 'pending',
        }
    )
    sync_content_ledger_ref(store.client, UID, binding.content_id).create(
        {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {'protocol_version': 1, 'namespace': NS, 'segment_ids': [COPY]},
        }
    )
    for uri in (item.audio_uri, result['result_uri']):
        store.ref('artifacts', artifact_id(COPY, uri)).create({'owner_id': UID, 'privacy_generation': 0})
    return item, binding


@pytest.mark.parametrize('outcome', ['success', 'silence'])
def test_admission_alias_is_outside_every_paid_queue_and_retains_own_audio(outcome):
    store, original = setup_store(outcome=outcome)
    copy = replace(original, segment_id=COPY, audio_uri='gs://synthetic/copy#1', source_alias_of=SOURCE)
    raw = store.client.transaction()
    tx = FirestoreTransaction(store.client, NS, raw)
    candidate = reuse.current(tx, copy, NOW)
    assert candidate['segment_id'] == SOURCE
    assert reuse.enqueue_alias(
        tx,
        copy,
        NOW,
        policy=BatchUnitPolicy(),
        proposal={'segment_id': SOURCE, 'result_uri': 'gs://synthetic/marker#1'},
    )
    tx.flush()
    job = store.ref('jobs', COPY).get().to_dict()
    assert job['state'] == 'result_ready' and job['audio_uri'] == copy.audio_uri
    assert job['attempt'] == 0 and job['protocol_version'] == 2
    assert not any('queues' in path[0] or 'outbox' in path[0] for path in store.client.rows)


@pytest.mark.parametrize(
    'defect',
    [
        'different_bytes',
        'clock26',
        'device',
        'epoch',
        'missing',
        'expired',
        'generation',
        'retained_untranscribed',
        'incomplete_accounting',
    ],
)
def test_uncertain_or_unfinished_source_cannot_admit_alias(defect):
    store, original = setup_store()
    copy = replace(original, segment_id=COPY)
    if defect in {'different_bytes', 'device', 'epoch'}:
        copy = replace(copy, source_reuse_key='b' * 64)
    elif defect == 'clock26':
        copy = replace(copy, capture_at=original.capture_at + 26)
    elif defect in {'missing', 'expired'}:
        ref = store.ref('artifacts', artifact_id(SOURCE, original.audio_uri))
        if defect == 'missing':
            del store.client.rows[ref.path]
        else:
            store.client.rows[ref.path]['cleanup_after'] = datetime.fromtimestamp(NOW - 1, timezone.utc)
    elif defect == 'generation':
        copy = replace(copy, privacy_generation=1)
    elif defect == 'retained_untranscribed':
        store.client.rows[store.ref('jobs', SOURCE).path]['state'] = 'record_pending'
    else:
        ledger = sync_content_ledger_ref(store.client, UID, 'source-content')
        store.client.rows[ledger.path]['status'] = 'processing'
    before = deepcopy(store.client.rows)
    assert reuse.current(FirestoreTransaction(store.client, NS, store.client.transaction()), copy, NOW) is None
    assert store.client.rows == before


@pytest.mark.parametrize('accepted', [True, False])
def test_projection_refuses_second_copy_preserves_corrections_and_ancestry(accepted):
    store, original = setup_store(corrected=True)
    copy, binding = prepare_copy(store, original, accepted=accepted)
    row = store.client.collection('users').document(UID).collection('conversations').document('visible')
    before = deepcopy(store.client.rows[row.path])
    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    receipt = store.ref('results', COPY).get().to_dict()['projection']
    assert receipt['disposition'] == 'source_alias' and receipt['speech_seconds'] == 0
    assert receipt['conversation_id'] == 'visible'
    assert store.client.rows[row.path] == before
    assert store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict()['segment_id'] == SOURCE
    assert store.ref('jobs', COPY).get().to_dict()['source_conversation_ids'] == ['input', 'visible']
    assert project_alias(store, copy, binding, NOW + 1, policy=ProjectionPolicy())  # restart/reply lost
    assert store.ref('results', COPY).get().to_dict()['projection'] == receipt


def test_normal_assignment_cannot_bypass_source_fence():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original, accepted=False)
    session = store.session(COPY, binding, NOW, policy=ProjectionPolicy())
    before = deepcopy(store.client.rows)
    with pytest.raises(reuse.SourceReuseUnavailable, match='projection owner'):
        session.prepare(store.client.transaction())
    assert before == store.client.rows


@pytest.mark.parametrize('restore', [False, True])
def test_source_deletion_or_restore_generation_race_blocks_alias(restore):
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    before = deepcopy(store.client.rows)
    if restore:
        store.client.rows[store.ref(reuse.TABLE, reuse.receipt_id(KEY)).path]['privacy_generation'] = 1
    else:
        store.client.collection('users').document(UID).collection('deleted_conversations').document('visible').create(
            {}
        )
    with pytest.raises((BatchPrivacyBlocked, reuse.SourceReuseUnavailable)):
        project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('results', COPY).get().to_dict()['projection_state'] == 'pending'
    assert store.client.rows[store.ref('jobs', COPY).path] == before[store.ref('jobs', COPY).path]


def test_rollback_never_makes_accepted_alias_runnable_and_keeps_fence(monkeypatch):
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', 'false')
    assert reuse.lookup(SimpleNamespace(run=Mock()), copy, NOW) is None
    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'committed'
    assert store.ref('results', COPY).get().to_dict()['projection']['speech_seconds'] == 0


def test_alias_zero_charge_across_month_rollover_and_duplicate_completion():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    stamp = datetime(2026, 12, 1, tzinfo=timezone.utc).timestamp()
    accounting = store.prepare_accounting(binding, stamp)
    assert accounting['seconds'] == 0 and accounting['updates'] == {}
    ledger = sync_content_ledger_ref(store.client, UID, binding.content_id)
    for now in (stamp, stamp + 31 * 86400):
        snapshot = ledger.get().to_dict()
        tx = store.client.transaction()
        store._commit_usage(tx, ledger, snapshot, binding, accounting, 0, now)
    assert ledger.get().to_dict()['usage_committed_seconds'] == 0
    assert not any('hourly_usage' in path or 'monthly_usage' in path for path in store.client.rows)


def test_pre_admission_marker_registration_is_privacy_fenced_and_reachable(monkeypatch):
    from utils.batch_pipeline import retention

    store, original = setup_store()
    raw_store = SimpleNamespace(client=store.client, namespace=NS)
    copy = replace(
        original,
        segment_id=COPY,
        audio_uri='gs://synthetic/copy#1',
        source_alias_of=SOURCE,
        source_conversation_ids=('input', 'visible'),
    )
    uri = 'gs://synthetic/copy-result'
    monkeypatch.setattr(retention.time, 'time', lambda: NOW)
    context = retention.batch_artifact_authorize(raw_store, copy)
    retention.batch_artifact_register(raw_store, copy, uri, 'results', context)
    artifact = store.ref('artifacts', artifact_id(COPY, uri)).get().to_dict()
    assert {'input', 'visible'} <= set(artifact['conversation_ids'])
    assert artifact['write_pending_until']  # Cancellation stays in the staging outbox.
    store.client.collection('users').document(UID).collection('deleted_conversations').document('visible').create({})
    with pytest.raises(BatchPrivacyBlocked):
        retention.batch_artifact_authorize(raw_store, copy)
    with pytest.raises(BatchPrivacyBlocked):
        retention.batch_artifact_register(raw_store, copy, 'gs://synthetic/late-result', 'results', context)


def test_admit_alias_bypasses_provider_and_gpu_enqueuers_transactionally():
    from database.batch_pipeline_intake import admit

    store, original = setup_store()
    copy = replace(
        original,
        segment_id=COPY,
        audio_uri='gs://synthetic/copy#1',
        source_alias_of=SOURCE,
        source_conversation_ids=('input', 'visible'),
    )
    binding = ProjectionBinding(UID, 'copy-job', 'copy-content', (COPY,), privacy_generation=0)
    marker = 'gs://synthetic/copy-result#1'
    for uri in (copy.audio_uri, marker):
        store.ref('artifacts', artifact_id(COPY, uri)).create(
            {
                'owner_id': UID,
                'privacy_generation': 0,
                'write_pending_until': datetime.fromtimestamp(NOW + 100, timezone.utc),
            }
        )

    def run(body):
        tx = FirestoreTransaction(store.client, NS, store.client.transaction())
        answer = body(tx)
        tx.flush()
        return answer

    paid = Mock(side_effect=AssertionError('alias must never enter a paid queue'))
    adapter = SimpleNamespace(run=run, namespace=NS)
    policy = replace(BatchUnitPolicy(), batch_enabled=True)
    answer = admit(
        adapter,
        [copy],
        binding,
        NOW,
        namespace=NS,
        require_artifacts=True,
        policy=policy,
        enqueue=paid,
        source_aliases={COPY: {'segment_id': SOURCE, 'result_uri': marker}},
    )
    assert answer == {'outcome': 'batch', 'job_id': binding.job_id}
    paid.assert_not_called()
    for uri in (copy.audio_uri, marker):
        metadata = store.ref('artifacts', artifact_id(COPY, uri)).get().to_dict()
        assert metadata['source_conversation_ids'] == ['input', 'visible']
        assert 'write_pending_until' not in metadata
    answer = admit(adapter, [copy], binding, NOW + 1, namespace=NS, policy=policy, enqueue=paid)
    assert answer['job_id'] == binding.job_id
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'result_ready'


@pytest.mark.asyncio
async def test_stage_alias_has_no_language_or_asr_and_cancellation_never_enqueues(monkeypatch):
    import asyncio
    from utils.batch_pipeline import source_reuse_intake as intake
    from utils.batch_pipeline.audio import audio_unit

    store, original = setup_store()
    copy = replace(original, segment_id=COPY, audio_uri='gs://synthetic/placeholder')
    unit = replace(audio_unit(copy.capture_at, b'\x01\x00' * 16000), source_reuse_key=KEY)
    adapter = SimpleNamespace(run=lambda body: body(FirestoreTransaction(store.client, NS, store.client.transaction())))
    artifacts = SimpleNamespace(
        load_result=Mock(return_value={'words': []}),
        stage_audio=Mock(return_value='gs://synthetic/copy#1'),
        persist_result=Mock(return_value='gs://synthetic/marker#1'),
    )
    monkeypatch.setattr(intake.time, 'time', lambda: NOW)
    result = await intake.stage_alias(adapter, artifacts, copy, unit, {})
    assert result[0].source_alias_of == SOURCE and result[0].requires_compute_admission is False
    assert artifacts.stage_audio.call_count == artifacts.persist_result.call_count == 1
    assert artifacts.persist_result.call_args.args[1] == {
        'source_alias_version': 1,
        'source_reuse_key': KEY,
        'canonical_segment_id': SOURCE,
    }
    artifacts.persist_result.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await intake.stage_alias(adapter, artifacts, copy, unit, {})
    assert not store.ref('jobs', COPY).get().exists


def test_alias_and_registry_remain_reachable_by_erasure():
    from database.batch_pipeline_purge import row_belongs
    from database.batch_pipeline_conversation_purge import DEPENDENT_TABLES

    assert reuse.TABLE in DEPENDENT_TABLES
    store, original = setup_store()
    assert row_belongs(store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict(), 'visible')
    copy, binding = prepare_copy(store, original)
    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    artifact = store.ref('artifacts', artifact_id(COPY, copy.audio_uri)).get().to_dict()
    assert row_belongs(artifact, 'visible')


@pytest.mark.parametrize('first', [SOURCE, COPY])
def test_competing_sync_projections_claim_exactly_one_owner_in_either_order(first):
    store, original = setup_store()
    del store.client.rows[store.ref(reuse.TABLE, reuse.receipt_id(KEY)).path]

    def session(sid):
        return SimpleNamespace(
            job={**original.to_dict(), 'segment_id': sid},
            segment_id=sid,
            store=store,
            binding=ProjectionBinding(UID, 'job', 'content', (sid,), privacy_generation=0),
            now=NOW,
            receipt=lambda: {},
            allow_source_alias=False,
        )

    winner = session(first)
    tx = store.client.transaction()
    reuse.prepare(winner, tx)
    # The real assignment is a write between prepare and claim; claim may not read.
    tx.update(
        store.client.collection('users').document(UID).collection('conversations').document('visible'),
        {'source_range_owner': first},
    )
    reuse.claim(winner, tx, {'state': 'ready', 'conversation_id': 'visible'})
    loser = session(COPY if first == SOURCE else SOURCE)
    with pytest.raises(reuse.SourceReuseUnavailable):
        reuse.prepare(loser, store.client.transaction())
    assert store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict()['segment_id'] == first


def test_unfinished_owner_waits_and_never_projects_alias_text():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    store.client.rows[store.ref('results', SOURCE).path]['projection']['state'] = 'persisted'
    with pytest.raises(reuse.SourceReuseUnavailable, match='not ready'):
        project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert 'projection' not in store.ref('results', COPY).get().to_dict()
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'committed'


def test_long_exact_copy_never_selects_adjacent_short_native_row():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    user = store.client.collection('users').document(UID)
    user.collection('conversations').document('later-short-row').create(
        {
            'id': 'later-short-row',
            'record_lane_owner': 'batch_live_v1',
            'started_at': datetime.fromtimestamp(original.capture_at + 1735, timezone.utc),
            'finished_at': datetime.fromtimestamp(original.capture_at + 1779, timezone.utc),
            'transcript_segments': [],
        }
    )
    before = deepcopy(store.client.rows[(*user.path, 'conversations', 'later-short-row')])
    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('results', COPY).get().to_dict()['projection']['conversation_id'] == 'visible'
    assert store.client.rows[(*user.path, 'conversations', 'later-short-row')] == before


def test_accepted_alias_cannot_enter_paid_queues_or_missing_input_repair(monkeypatch):
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.batch_pipeline.provider_stt_admission import enqueue_in_transaction, SttRoute

    store, original = setup_store()
    copy = replace(original, segment_id=COPY, source_alias_of=SOURCE, requires_compute_admission=False)
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', 'false')
    paid = Mock()
    with pytest.raises(ValueError, match='cannot enter paid queues'):
        Scheduler.enqueue_in_transaction(paid, copy, NOW)
    with pytest.raises(ValueError, match='cannot enter paid queues'):
        enqueue_in_transaction(
            paid,
            copy,
            NOW,
            route=SttRoute('provider', 'unsupported_language', 'modulate', 'zh'),
            policy=BatchUnitPolicy(),
        )
    with pytest.raises(ValueError, match='cannot enter paid queues'):
        Scheduler.restore_audio_in_transaction(paid, {**copy.to_dict(), 'result': None}, NOW)
    paid.get.assert_not_called()


def test_overlapping_files_with_different_bytes_both_survive_inside_bundle(tmp_path):
    units = decoded([raw_file(tmp_path, name='a'), raw_file(tmp_path, name='b', sample=2)])
    assert len(units) == 2
    assert units[0].source_reuse_key != units[1].source_reuse_key


def test_bundle_order_does_not_change_source_unit_order(tmp_path):
    first = decoded([raw_file(tmp_path, at=1750000101, name='a'), raw_file(tmp_path, name='b')])
    second = decoded([raw_file(tmp_path, name='c'), raw_file(tmp_path, at=1750000101, name='d')])
    assert [unit.source_reuse_key for unit in first] == [unit.source_reuse_key for unit in second]


@pytest.mark.asyncio
async def test_missing_input_repair_preserves_accepted_file_boundaries_after_off(tmp_path, monkeypatch):
    from utils.batch_pipeline import artifact_reupload as repair

    paths = [raw_file(tmp_path, name='a'), raw_file(tmp_path, name='b', at=1750000101)]
    # Original admission has two source files even though they touch in time.
    units = decoded(paths)
    jobs = [
        WorkItem(
            hashlib.sha256(str(index).encode()).hexdigest(),
            UID,
            unit.capture_at,
            f'gs://synthetic/{index}#1',
            unit.duration_seconds,
            Priority.FRESH,
            conversation_id=f'input-{index}',
            privacy_generation=0,
            source_reuse_key=unit.source_reuse_key,
        ).to_dict()
        for index, unit in enumerate(units)
    ]
    paths = [raw_file(tmp_path, name='retry-b', at=1750000101), raw_file(tmp_path, name='retry-a')]
    binding = ProjectionBinding(
        UID, 'job', 'content', tuple(job['segment_id'] for job in jobs), client_device_id='device', privacy_generation=0
    )
    snapshots = {job['segment_id']: job for job in jobs}
    protocol = SimpleNamespace(restore_reupload=Mock(return_value='job'))
    monkeypatch.setattr(repair, '_repair_plan', lambda *a: (protocol, (binding, jobs, snapshots)))
    monkeypatch.setattr(repair, '_repair_evidence', lambda *a: ({}, {sid: {'stt_language': 'en'} for sid in snapshots}))
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', 'false')
    artifacts = SimpleNamespace(stage_audio=Mock(return_value='gs://synthetic/repaired#1'))
    assert (
        await repair.restore_upload(
            None,
            UID,
            'content',
            paths,
            source='omi',
            should_lock=False,
            conversation_id=None,
            client_device_id='device',
            client_platform=None,
            intake_context={},
            artifacts=artifacts,
        )
        == 'job'
    )
    assert artifacts.stage_audio.call_count == 2
    protocol.restore_reupload.assert_called_once()
    assert set(protocol.restore_reupload.call_args.args[3]) == set(snapshots)


def test_mixed_bundle_admits_only_the_new_tail_as_paid_work(monkeypatch):
    from database.batch_pipeline_intake import admit
    from utils.batch_pipeline.scheduler import Scheduler
    from database import batch_pipeline_store

    # Scalar scheduling hint; ordered queries are outside the strict document fixture.
    monkeypatch.setattr(batch_pipeline_store, 'service_frontier', lambda *args, **kwargs: 0.0)
    store, original = setup_store()
    copy = replace(
        original,
        segment_id=COPY,
        audio_uri='gs://synthetic/copy#1',
        source_alias_of=SOURCE,
        source_conversation_ids=('input', 'visible'),
        requires_compute_admission=False,
    )
    tail_id = hashlib.sha256(b'new-tail').hexdigest()
    tail = replace(
        original,
        segment_id=tail_id,
        capture_at=original.capture_at + 1,
        audio_uri='gs://synthetic/tail#1',
        source_reuse_key='b' * 64,
        conversation_id='tail-input',
        requires_compute_admission=True,
    )
    binding = ProjectionBinding(UID, 'mixed-job', 'mixed-content', (COPY, tail_id), privacy_generation=0)
    marker = 'gs://synthetic/copy-result#1'
    for item, uri in ((copy, copy.audio_uri), (copy, marker), (tail, tail.audio_uri)):
        store.ref('artifacts', artifact_id(item.segment_id, uri)).create({'owner_id': UID, 'privacy_generation': 0})

    def run(body):
        tx = FirestoreTransaction(store.client, NS, store.client.transaction())
        answer = body(tx)
        tx.flush()
        return answer

    paid = Mock(wraps=Scheduler.enqueue_in_transaction)
    adapter = SimpleNamespace(run=run, namespace=NS)
    assert (
        admit(
            adapter,
            [copy, tail],
            binding,
            NOW,
            namespace=NS,
            require_artifacts=True,
            policy=replace(BatchUnitPolicy(), batch_enabled=True),
            enqueue=paid,
            source_aliases={COPY: {'segment_id': SOURCE, 'result_uri': marker}},
        )['outcome']
        == 'batch'
    )
    assert paid.call_count == 1 and paid.call_args.args[1].segment_id == tail_id
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'result_ready'
    assert store.ref('jobs', tail_id).get().to_dict()['state'] == 'ready'
