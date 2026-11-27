"""Exact-byte reuse, fenced paid fallback, privacy and single-owner transactions."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from functools import partial
import hashlib
import struct
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from config.policy import BatchUnitPolicy, ProjectionPolicy
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_source_projection import project_alias
from database import batch_pipeline_source_reuse as reuse
from database.batch_pipeline_staging import artifact_id
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_pipeline_privacy import BatchPrivacyBlocked, PRIVACY_COLLECTION, privacy_owner_key
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import source_reuse
from utils.sync import source_reuse_decode
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding, Priority
from utils.batch_pipeline.result_protocol import REQUIRED, stamp
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.source_reuse_decode import decode_for_intake

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
    from database import batch_pipeline_store

    monkeypatch.setattr(batch_pipeline_store, 'service_frontier', lambda *args, **kwargs: 0.0)
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
    assert not source_reuse_decode.eligible([raw_file(tmp_path)], context)


@pytest.mark.parametrize('path', ['a.bin', 'audio_omi_pcm16_16000_invalid.bin'])
def test_unproven_filename_keeps_the_normal_decoder(path):
    from utils.batch_pipeline.audio import audio_unit

    unit = audio_unit(1750000100, b'\0\0' * 1600)
    decoder = Mock(return_value=iter([unit]))
    context = {'client_device_id': 'synthetic-device', 'capture_received_at': 1750000200}
    assert list(decode_for_intake([path], 600, UID, context, decoder=decoder)) == [unit]
    decoder.assert_called_once_with([path], max_seconds=600, received_at=1750000200)
    assert unit.source_reuse_key is None


def test_proof_miss_close_reaches_the_normal_decoder():
    from utils.batch_pipeline.audio import audio_unit

    unit, closed = audio_unit(1750000100, b'\0\0' * 1600), []

    def decoder(*args, **kwargs):
        try:
            yield unit
            raise AssertionError('close must not consume another unit')
        finally:
            closed.append(True)

    iterator = decode_for_intake(['a.bin'], 600, UID, {'client_device_id': 'synthetic-device'}, decoder=decoder)
    assert next(iterator) is unit
    iterator.close()
    assert closed == [True]


@pytest.mark.parametrize('policy', ['future_device_offset_v1', 'estimated_source_isolated_v1', 'unknown'])
def test_clock_recovery_policy_keeps_normal_decode_without_reuse(tmp_path, policy):
    path = raw_file(tmp_path)
    context = {'client_device_id': 'synthetic-device', 'capture_clock_policy': policy}
    assert not source_reuse_decode.eligible([path], context)
    assert len(list(decode_for_intake([path], 600, UID, context, decoder=decode_units))) == 1


def test_kill_switch_restores_packing_and_unknown_clocks_abstain(tmp_path, monkeypatch):
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', 'false')
    units = decoded([raw_file(tmp_path, name='a'), raw_file(tmp_path, at=1750000101, name='b')])
    assert len(units) == 1 and units[0].source_reuse_key is None
    monkeypatch.delenv('BATCH_SOURCE_REUSE_ENABLED')
    assert not source_reuse_decode.eligible([raw_file(tmp_path, at=788918400, name='early')], {'client_device_id': 'd'})


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
            'policy': BatchUnitPolicy().to_dict(),
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
            'privacy_generation': item.privacy_generation,
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


@pytest.mark.parametrize('provider', [False, True])
def test_pre_reuse_work_items_keep_normal_admission(provider):
    from database.batch_pipeline_intake import admit
    from utils.batch_pipeline.provider_stt_admission import SttRoute, enqueue_in_transaction

    store, original = setup_store()
    fields = asdict(replace(original, segment_id=COPY))
    for name in (
        'source_reuse_key',
        'source_alias_of',
        'source_conversation_ids',
        'capture_time_trust',
        'capture_source_conversation_id',
    ):
        fields.pop(name)
    serialized = {key: value for key, value in fields.items() if key != 'language_receipt_enabled' or value is not None}
    # The actual pinned-main WorkItem is exercised by early-clock parity. This
    # structural fixture also covers the provider boundary without new fields.
    legacy = cast(WorkItem, SimpleNamespace(**fields, to_dict=lambda: deepcopy(serialized)))

    def run(body):
        tx = FirestoreTransaction(store.client, NS, store.client.transaction())
        answer = body(tx)
        tx.flush()
        return answer

    binding = ProjectionBinding(UID, 'legacy-job', 'legacy-content', (COPY,), privacy_generation=0)
    answer = admit(
        SimpleNamespace(run=run),
        [legacy],
        binding,
        NOW,
        namespace=NS,
        policy=replace(BatchUnitPolicy(), batch_enabled=True),
        enqueue=(
            partial(enqueue_in_transaction, route=SttRoute('provider', 'unsupported_language', 'modulate', 'vi'))
            if provider
            else None
        ),
    )
    assert answer == {'outcome': 'batch', 'job_id': binding.job_id}
    job = store.ref('jobs', COPY).get().to_dict()
    assert job['state'] == ('provider_pending' if provider else 'ready')
    assert not job.get('source_reuse_key') and not job.get('source_alias')


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
def test_source_deletion_detaches_but_restore_generation_race_blocks_alias(restore):
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
    if restore:
        assert store.ref('results', COPY).get().to_dict()['projection_state'] == 'pending'
        assert store.client.rows[store.ref('jobs', COPY).path] == before[store.ref('jobs', COPY).path]
    else:
        assert store.ref('jobs', COPY).get().to_dict()['state'] == 'provider_pending'
        assert 'visible' not in store.ref('jobs', COPY).get().to_dict()['source_conversation_ids']
        assert not store.ref('results', COPY).get().exists


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
    result = await intake.stage_alias(adapter, artifacts, copy, unit, {}, record_origin=False)
    assert result[0].source_alias_of == SOURCE and result[0].requires_compute_admission is False
    assert artifacts.stage_audio.call_count == artifacts.persist_result.call_count == 1
    assert artifacts.stage_audio.call_args.kwargs == {'record_origin': False}
    assert artifacts.persist_result.call_args.kwargs == {'record_origin': False}
    assert artifacts.persist_result.call_args.args[1] == {
        'source_alias_version': 1,
        'source_reuse_key': KEY,
        'canonical_segment_id': SOURCE,
    }
    artifacts.persist_result.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await intake.stage_alias(adapter, artifacts, copy, unit, {}, record_origin=False)
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


def test_unfinished_owner_falls_back_and_never_projects_alias_text():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    store.client.rows[store.ref('results', SOURCE).path]['projection']['state'] = 'persisted'
    with pytest.raises(reuse.SourceReuseUnavailable, match='fallback enqueued'):
        project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert not store.ref('results', COPY).get().exists
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'provider_pending'


def test_long_exact_copy_never_selects_adjacent_short_native_row():
    store, original = setup_store()
    original = replace(original, duration_seconds=1729.0)
    store.client.rows[store.ref('jobs', SOURCE).path]['duration_seconds'] = original.duration_seconds
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


@pytest.fixture
def allowance_intake_probe(monkeypatch):
    from utils import stt_cap_dispatch
    from utils.batch_pipeline.intake import _probe_upload_allowance

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'true')
    monkeypatch.setenv('BATCH_ALLOWANCE_INTAKE_PARK_ENABLED', 'true')
    allowance = Mock()
    monkeypatch.setattr(stt_cap_dispatch, 'funded_allowance', allowance)
    return _probe_upload_allowance, allowance


@pytest.mark.parametrize(
    'reason,expected', [('plan_within_allowance', 'ready'), ('plan_allowance_exhausted', 'allowance_held')]
)
async def test_mixed_bundle_admits_only_the_new_tail_as_paid_work(
    monkeypatch, allowance_intake_probe, reason, expected
):
    from database.batch_pipeline_intake import admit
    from database.batch_pipeline_allowance_hold import OWNERS
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
    monkeypatch.setattr(Scheduler, 'enqueue_in_transaction', staticmethod(paid))
    adapter = SimpleNamespace(run=run, namespace=NS)
    policy = replace(BatchUnitPolicy(), batch_enabled=True)
    aliases = {COPY: {'segment_id': SOURCE, 'result_uri': marker}}
    probe, allowance = allowance_intake_probe
    allowance.return_value = SimpleNamespace(managed=expected == 'ready', reason=reason)
    refusal = await probe(adapter, UID, policy, 'fresh', [copy, tail], aliases)
    assert (
        admit(
            adapter,
            [copy, tail],
            binding,
            NOW,
            namespace=NS,
            require_artifacts=True,
            policy=policy,
            intake={'lane': 'fresh'},
            source_aliases=aliases,
            intake_refusal=refusal,
        )['outcome']
        == 'batch'
    )
    assert paid.call_count == 1 and paid.call_args.args[1].segment_id == tail_id
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'result_ready'
    assert store.ref('jobs', tail_id).get().to_dict()['state'] == expected
    allowance.assert_called_once_with(UID, lane='batch', ready_usage_only=True)
    owner = store.ref(OWNERS, owner_key(UID)).get().to_dict() or {}
    assert owner.get('held_count', 0) == int(expected == 'allowance_held')


def test_projection_refusal_finishes_after_temporary_canonical_artifacts_expire():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    # New compute-reuse admission must abstain, but a durable canonical output
    # still owns the source and must not strand or duplicate an existing job.
    del store.client.rows[store.ref('artifacts', artifact_id(SOURCE, original.audio_uri)).path]
    assert reuse.current(FirestoreTransaction(store.client, NS, store.client.transaction()), copy, NOW) is None
    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('results', COPY).get().to_dict()['projection']['speech_seconds'] == 0


def test_alias_preserves_the_existing_fresh_capture_class():
    store, original = setup_store()
    copy = replace(original, segment_id=COPY, source_alias_of=SOURCE)
    tx = FirestoreTransaction(store.client, NS, store.client.transaction())
    assert reuse.enqueue_alias(
        tx,
        copy,
        NOW + 1800,
        policy=BatchUnitPolicy(),
        proposal={'segment_id': SOURCE, 'result_uri': 'gs://synthetic/marker#1'},
    )
    assert tx.get('jobs', COPY)['fresh_capture'] is False


def test_off_stops_new_projection_aliases_but_retains_already_computed_work(monkeypatch):
    store, original = setup_store()
    copy, binding = prepare_copy(store, original, accepted=False)
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', 'false')
    before = store.ref('jobs', COPY).get().to_dict()
    with pytest.raises(reuse.SourceReuseUnavailable, match='disabled'):
        project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('jobs', COPY).get().to_dict() == before
    assert 'projection' not in store.ref('results', COPY).get().to_dict()


@pytest.mark.parametrize('defect', ['erased', 'quarantined', 'dead', 'ledger', 'expired', 'missing', 'disposition'])
@pytest.mark.parametrize('enabled', [True, False])
def test_lost_canonical_fallback_is_durable_idempotent_and_survives_off(defect, enabled, monkeypatch):
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    monkeypatch.setenv('BATCH_SOURCE_REUSE_ENABLED', str(enabled).lower())
    if defect == 'erased':
        store.client.rows[store.ref('results', SOURCE).path]['projection_state'] = 'erased'
    elif defect in {'quarantined', 'dead'}:
        store.client.rows[store.ref('jobs', SOURCE).path]['state'] = defect
    elif defect == 'ledger':
        patch_document(store, sync_content_ledger_ref(store.client, UID, 'source-content'), {'status': 'processing'})
    elif defect == 'expired':
        patch_document(
            store,
            store.ref(reuse.TABLE, reuse.receipt_id(KEY)),
            {'expires_at': datetime.fromtimestamp(NOW - 1, timezone.utc)},
        )
    elif defect == 'missing':
        del store.client.rows[store.ref(reuse.TABLE, reuse.receipt_id(KEY)).path]
    else:
        store.client.rows[store.ref('results', SOURCE).path]['projection']['disposition'] = 'superseded'
    observed = []
    monkeypatch.setattr(source_reuse, 'observe', lambda event, seconds=0: observed.append(event))
    with pytest.raises(reuse.SourceReuseUnavailable, match='fallback enqueued'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    queued = store.ref('jobs', COPY).get().to_dict()
    assert queued['audio_uri'] == item.audio_uri and not queued['requires_compute_admission']
    assert queued['stt_route']['stt_route'] == 'provider'
    assert queued['state'] == 'provider_pending' and queued['merge_pending']
    assert not queued.get('source_alias_of') and not queued.get('source_alias')
    assert queued['source_alias_fallback']['source_segment_id'] == SOURCE
    assert store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict()['segment_id'] == COPY
    assert not store.ref('results', COPY).get().exists
    before = deepcopy(store.client.rows)
    with pytest.raises(reuse.SourceReuseUnavailable, match='processing pending'):
        project_alias(store, item, binding, NOW + 1, policy=ProjectionPolicy())
    assert store.client.rows == before and observed.count('fallback') == 1


@pytest.mark.parametrize(
    'unsupported',
    [
        {REQUIRED: {'source_alias_version': 1, 'future_version': 1}},
        {REQUIRED: {'source_alias_version': 2}},
        {REQUIRED: {'source_alias_version': True}},
        {REQUIRED: {'source_reuse_version': 1}},
        {REQUIRED: ['source_alias_version']},
        {'protocol_version': 3},
    ],
)
def test_fallback_does_not_discard_unsupported_alias_requirements(unsupported):
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    job = store.client.rows[store.ref('jobs', COPY).path]
    stamp(job, 'source_alias_version')
    job.update(unsupported)
    # A legacy result row can enter projection without consulting the job's
    # requirements; the fallback writer must still refuse before any write.
    patch_document(store, store.ref('results', COPY), {'protocol_version': 1})
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    before = deepcopy(store.client.rows)
    with pytest.raises(ProjectionBlocked, match='unsupported alias result requirements'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    assert store.client.rows == before


@pytest.mark.parametrize('erasure', ['own_conversation', 'account_generation', 'own_artifact', 'own_result'])
def test_alias_erasure_prevents_fallback_compute(erasure):
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    if erasure == 'own_conversation':
        store.client.collection('users').document(UID).collection('deleted_conversations').document(
            item.conversation_id
        ).create({})
    elif erasure == 'account_generation':
        store.client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(UID)).create({'generation': 1})
    elif erasure == 'own_artifact':
        patch_document(store, store.ref('artifacts', artifact_id(COPY, item.audio_uri)), {'erasure_requested': True})
    else:
        patch_document(store, store.ref('results', COPY), {'projection_state': 'erased'})
    before = deepcopy(store.client.rows)
    with pytest.raises((BatchPrivacyBlocked, ProjectionBlocked)):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    assert before == store.client.rows


def test_successful_alias_never_counts_duplicate_projection_refusal(monkeypatch):
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    events = []
    monkeypatch.setattr(source_reuse, 'observe', lambda event, seconds=0: events.append(event))
    assert project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    assert events == ['reused']
    session = store.session(COPY, binding, NOW)
    # A real second visible assignment still records its refusal.
    session.receipt = lambda: {}
    session.job = store.ref('jobs', COPY).get().to_dict()
    with pytest.raises(reuse.SourceReuseUnavailable):
        reuse.prepare(session, store.client.transaction())
    assert events == ['reused', 'duplicate_projection_refusal']


@pytest.mark.parametrize('recovery_first', [True, False])
def test_canonical_recovery_races_one_fallback_owner(recovery_first):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event, RLock

    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    # The strict fixture enforces read-before-write. The shared lock gives the
    # two actual threads serializable commits; this does not emulate contention.
    lock, start, first_done = RLock(), Barrier(2), Event()
    store.run = lambda fn, **kwargs: serialized(fn)

    def serialized(fn):
        with lock:
            return fn(store.client.transaction())

    def recovery():
        start.wait()
        if not recovery_first:
            assert first_done.wait(10)
        with lock:
            patch_document(store, store.ref('jobs', SOURCE), {'state': 'committed'})
        if recovery_first:
            first_done.set()

    def fallback():
        start.wait()
        if recovery_first:
            assert first_done.wait(10)
        try:
            return project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
        except reuse.SourceReuseUnavailable as error:
            assert 'fallback enqueued' in str(error)
            return False
        finally:
            if not recovery_first:
                first_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        recovered, fallback_result = pool.submit(recovery), pool.submit(fallback)
        recovered.result(timeout=15)
        assert fallback_result.result(timeout=15) is recovery_first
    owner = store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict()['segment_id']
    assert owner == (SOURCE if recovery_first else COPY)
    job = store.ref('jobs', COPY).get().to_dict()
    assert job['state'] == ('committed' if recovery_first else 'provider_pending')
    if not recovery_first:
        # Recovery cannot reclaim the reserved range or undo its paid fallback.
        loser = store.session(
            SOURCE, ProjectionBinding(UID, 'source-job', 'source-content', (SOURCE,), privacy_generation=0), NOW
        )
        loser.job = store.ref('jobs', SOURCE).get().to_dict()
        loser.source_owner = store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict()
        with pytest.raises(reuse.SourceReuseUnavailable):
            reuse.claim(loser, store.client.transaction(), {'state': 'ready'})


@pytest.mark.parametrize(
    ('envelope', 'previously_projected'),
    [('canonical', False), ('legacy_alias', False), ('historical_dual', False), ('historical_dual', True)],
)
def test_fallback_restart_replaces_same_log_slot_and_charges_own_speech(monkeypatch, envelope, previously_projected):
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.batch_pipeline.merge import OrderedMerge
    from utils.batch_pipeline.contracts import WorkResult
    from database.batch_pipeline_source_fallback import merge_ready

    store, original = setup_store()
    original = replace(original, duration_seconds=120.0)
    patch_document(store, store.ref('jobs', SOURCE), {'duration_seconds': 120.0})
    item, binding = prepare_copy(store, original)
    job = store.client.rows[store.ref('jobs', COPY).path]
    stamp(job, 'source_alias_version')
    store.client.rows[store.ref('results', COPY).path].pop('source_reuse_version', None)
    if previously_projected:
        assert project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    slot = store.ref('results', COPY).get().to_dict()
    assert slot['projection_state'] == ('ready' if previously_projected else 'pending')
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    with pytest.raises(reuse.SourceReuseUnavailable, match='enqueued'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    queued = store.ref('jobs', COPY).get().to_dict()
    assert queued[REQUIRED] == {'source_reuse_version': 1}
    assert 'source_alias_version' not in queued

    def run(body):
        view = FirestoreTransaction(store.client, NS, store.client.transaction())
        value = body(view)
        view.flush()
        return value

    if envelope != 'canonical':
        required = {'source_alias_version': 1}
        if envelope == 'historical_dual':
            required['source_reuse_version'] = 1
        patch_document(store, store.ref('jobs', COPY), {REQUIRED: required})
    store.store.run = run
    # Query ordering is not modelled by the strict document fixture. This
    # selects the one pending job; all admission/merge writes remain real.
    monkeypatch.setattr(FirestoreTransaction, 'first_pending', lambda tx, key: tx.get('jobs', COPY))
    from utils.batch_pipeline.provider_stt import ProviderSttStage

    artifacts = Mock()
    artifacts.fetch_audio.return_value = b'synthetic-retained-audio'
    artifacts.persist_recovery_result.return_value = 'gs://synthetic/fresh-result#2'
    vendor = Mock(
        return_value={
            'audio_seconds': 120.0,
            'speech_seconds': 3.0,
            'speech_spans': [{'start': 0.0, 'end': 3.0}],
            'words': [{'word': 'synthetic', 'timestamp': [0.0, 1.0], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': 'modulate',
            'language': 'en',
            'recovery_version': 1,
        }
    )
    allowed = Mock(return_value=False)
    stage = ProviderSttStage(
        store.store,
        artifacts,
        stt=vendor,
        allowed=allowed,
        inspect=lambda *_: (b'\0\0' * 16000 * 120, 120.0, [{'start': 0.0, 'end': 3.0}]),
        clock=lambda: NOW + 2,
        armed=lambda: False,
    )
    assert stage.run(COPY).outcome == 'deferred'
    vendor.assert_not_called()
    artifacts.fetch_audio.assert_not_called()
    allowed.return_value = True
    assert stage.run(COPY).outcome == 'done'
    assert vendor.call_count == 1 and allowed.call_count == 3
    assert vendor.call_args.args[1] == 'multi'
    result = WorkResult(COPY, 'gs://synthetic/fresh-result#2')
    owner_before = store.ref('owners', owner_key(UID)).get().to_dict()
    # The preserved slot carries a stamp from an earlier head-wait episode.
    fallback = store.ref('jobs', COPY).get().to_dict()['source_alias_fallback']
    stamped = {
        **fallback['log_slot'],
        'projection_blocked_since': NOW,
        'projection_block_type': 'SyncAssignmentConflict',
    }
    patch_document(store, store.ref('jobs', COPY), {'source_alias_fallback': {**fallback, 'log_slot': stamped}})
    merged = OrderedMerge(store.store, head_wait_seconds=0, catch_up_depth=1).commit_next(UID, NOW + 3)
    assert merged['projection_blocked_since'] is None and merged['projection_block_type'] is None
    assert merged['previous_segment_id'] == slot['previous_segment_id']
    assert merged['committed_at'] == slot['committed_at']
    assert merged['result']['result_uri'] == 'gs://synthetic/fresh-result#2'
    assert merged['projection_redriven_at'] == NOW + 3
    assert store.ref('owners', owner_key(UID)).get().to_dict().get('log_sequence') == owner_before.get('log_sequence')
    with pytest.raises(ProjectionBlocked):
        run(lambda tx: merge_ready(tx, tx.get('jobs', COPY), NOW + 4))
    fresh_job = store.ref('jobs', COPY).get().to_dict()
    fresh_item = WorkItem(**{key: fresh_job[key] for key in WorkItem.__dataclass_fields__ if key in fresh_job})
    assert not project_alias(store, fresh_item, binding, NOW + 4, policy=ProjectionPolicy())
    monkeypatch.setattr('database.llm_usage.resolve_usage_plan_id', lambda *args, **kwargs: 'synthetic-plan')
    monkeypatch.setattr('database.hourly_usage_updates.prepare_hourly_usage_updates', lambda *args, **kwargs: {})
    # Normal fresh speech accounting, never the old zero-speech alias receipt.
    session = store.session(COPY, binding, NOW + 5)
    tx = store.client.transaction()
    session.prepare(tx)
    session.speech_seconds = 3.0
    receipt = session.persist(tx, ({'id': 'independent-output', 'language': 'en'}, True, []))
    receipt['state'] = 'ready'
    session.write_receipt(tx, receipt)
    monkeypatch.setattr('database.llm_usage.resolve_usage_plan_id', lambda *args, **kwargs: 'synthetic-plan')
    monkeypatch.setattr('database.hourly_usage_updates.prepare_hourly_usage_updates', lambda *args, **kwargs: {})
    accounting = store.prepare_accounting(binding, NOW + 6)
    assert accounting['seconds'] == 3.0
    ledger = sync_content_ledger_ref(store.client, UID, binding.content_id)
    for now in (NOW + 6, NOW + 7):
        store._commit_usage(store.client.transaction(), ledger, ledger.get().to_dict(), binding, accounting, 3, now)
    assert ledger.get().to_dict()['usage_committed_seconds'] == 3
    assert store.ref(reuse.TABLE, reuse.receipt_id(KEY)).get().to_dict()['complete']


def test_fallback_does_not_recreate_deleted_canonical_output():
    store, original = setup_store(corrected=True)
    item, binding = prepare_copy(store, original)
    user = store.client.collection('users').document(UID)
    user.collection('deleted_conversations').document('visible').create({})
    before = user.collection('conversations').document('visible').get().to_dict()
    with pytest.raises(reuse.SourceReuseUnavailable, match='enqueued'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    assert user.collection('conversations').document('visible').get().to_dict() == before
    job = store.ref('jobs', COPY).get().to_dict()
    assert 'visible' not in job['source_conversation_ids']
    artifact = store.ref('artifacts', artifact_id(COPY, item.audio_uri)).get().to_dict()
    assert 'visible' not in artifact['conversation_ids']
    # A new erasure of the alias's own independent capture still blocks work.
    user.collection('deleted_conversations').document(item.conversation_id).create({})
    with pytest.raises(BatchPrivacyBlocked):
        from database.batch_pipeline_policy import check_unit_privacy

        check_unit_privacy(FirestoreTransaction(store.client, NS, store.client.transaction()), job)


def test_canonical_loss_after_pointer_persist_still_falls_back():
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    assert project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    with pytest.raises(reuse.SourceReuseUnavailable, match='enqueued'):
        project_alias(store, item, binding, NOW + 1, policy=ProjectionPolicy())
    assert not store.ref('results', COPY).get().exists
    assert store.ref('jobs', COPY).get().to_dict()['state'] == 'provider_pending'


def patch_document(store, reference, changes):
    store.client.transaction().update(reference, changes)


def test_fallback_requires_own_audio_but_not_expired_alias_marker():
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    marker_uri = store.ref('jobs', COPY).get().to_dict()['result']['result_uri']
    del store.client.rows[store.ref('artifacts', artifact_id(COPY, marker_uri)).path]
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    with pytest.raises(reuse.SourceReuseUnavailable, match='enqueued'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('jobs', COPY).get().to_dict()['stt_route']['stt_route'] == 'provider'


def test_fallback_cannot_guess_missing_admission_funding_policy():
    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    del store.client.rows[store.ref('jobs', COPY).path]['policy']
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    before = deepcopy(store.client.rows)
    with pytest.raises(ProjectionBlocked, match='funding policy required'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    assert store.client.rows == before


def test_erasure_discovers_fallback_provenance_and_retains_suspended_ordering(monkeypatch):
    from database import batch_pipeline_purge as purge

    store, original = setup_store()
    item, binding = prepare_copy(store, original)
    slot = store.ref('results', COPY).get().to_dict()
    patch_document(store, store.ref('jobs', SOURCE), {'state': 'dead'})
    with pytest.raises(reuse.SourceReuseUnavailable, match='enqueued'):
        project_alias(store, item, binding, NOW, policy=ProjectionPolicy())
    job = store.ref('jobs', COPY).get().to_dict()
    assert 'visible' not in job['source_conversation_ids']
    assert purge.row_belongs(job, 'visible')
    assert not purge.row_belongs(job, 'unrelated')
    assert not store.ref('results', COPY).get().exists
    monkeypatch.setattr(purge.queries, 'predecessor_documents', lambda *args: [])
    monkeypatch.setattr(purge, 'mirror_refresh', lambda *args: None)
    purge.delete_job(
        store.client, NS, SimpleNamespace(id=COPY, reference=store.ref('jobs', COPY)), retain_ordering=True
    )
    erased = store.ref('results', COPY).get().to_dict()
    assert erased['projection_state'] == 'erased'
    assert erased['previous_segment_id'] == slot['previous_segment_id']
    assert erased.get('log_sequence') == slot.get('log_sequence')
    assert not erased.get('result') and not store.ref('jobs', COPY).get().exists
    with pytest.raises(ProjectionBlocked):
        project_alias(store, item, binding, NOW + 1, policy=ProjectionPolicy())
