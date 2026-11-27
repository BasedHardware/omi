"""Poll-independent receipt fanout: strict Firestore read/write boundary."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from prometheus_client import REGISTRY

from config.policy import BatchUnitPolicy
from database import batch_pipeline_coalescing_completion as completion
from database import batch_pipeline_upload_metrics as metrics
from database.batch_pipeline_staging import artifact_id
from database.sync_ledger import sync_content_ledger_ref
from routers import sync as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_batch_pipeline_projection import native_finish_completion
from tests.unit.test_batch_upload_coalescing import group, member, store
from tests.unit.test_sync_capture_time_skew import client, _default_skew  # noqa: F401
from utils.batch_pipeline import intake, upload_coalescing, upload_entitlement
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.stt import batch_language
from utils.sync import legacy_dark


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['merged', 'individual'])
async def test_mobile_hold_headers_survive_coalescing_and_publication(client, tmp_path, monkeypatch, mode):
    db = store()
    uid, cid = 'synthetic-uid', 'recording'
    now = int(router.time.time())
    db.rows['coalesce_quota', 'global']['last_scan_at'] = now
    monkeypatch.setattr(router.time, 'time', lambda: now)
    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'false')
    monkeypatch.setattr(router, 'resolve_batch_policy', lambda _: BatchUnitPolicy(batch_enabled=True))
    monkeypatch.setattr(router, 'compute_sync_content_id', lambda _uid, paths: Path(paths[0]).stem)
    monkeypatch.setattr(router, 'registered_record_response', AsyncMock(return_value=router.RecordUploadRoute.BATCH))
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda _: legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(upload_entitlement, 'classify', lambda _: 'free')
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_: db)
    monkeypatch.setattr(intake, 'serving_for', lambda *a, **k: False)
    monkeypatch.setattr(intake, 'admission_language_exclusion_enabled', lambda: False)
    monkeypatch.setattr(intake, 'language_guard_enabled', lambda: False)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )
    monkeypatch.setattr(
        batch_language,
        'resolve_language',
        lambda *a, **k: SimpleNamespace(
            language='en', parakeet_safe=True, evidence=None, confidence=1.0, probe_seconds=0.0
        ),
    )

    def authorize(_store, _work, snapshots):
        snapshots['user'] = {'language': 'en', 'transcription_preferences': {'single_language_mode': True}}
        snapshots['conversations'] = {cid: {'language': 'en'}}
        return ProtectionContext('standard', 0)

    bodies = {}

    def stage(item, body):
        uri = f'gs://synthetic/{item.segment_id}#1'
        bodies[uri] = body
        db.rows['artifacts', artifact_id(item.segment_id, uri)] = {
            'owner_id': item.owner_id,
            'privacy_generation': item.privacy_generation,
            'uri': uri,
        }
        return uri

    artifacts = SimpleNamespace(stage_audio=stage, fetch_audio=lambda item: bodies[item.audio_uri])
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: artifacts)
    monkeypatch.setattr(intake, 'with_context', lambda wav, _: wav)

    states = ['fg60', 'bg300', 'fg_preview300']

    def phone_age_count(state):
        return (
            REGISTRY.get_sample_value(
                'omi_batch_pipeline_upload_hold_age_seconds_count',
                {'gate': 'none', 'hold_state': state, 'recovered': 'false'},
            )
            or 0
        )

    age_counts_before = [phone_age_count(state) for state in states]
    job_ids = []
    for index, state in enumerate(states):
        path = Path(pcm(tmp_path, now - 30 + index * 2, 16000))
        name = path.name.replace('audio_omi_', 'audio_omimobilebatch001_', 1)
        response = client.post(
            '/v2/sync-local-files',
            params={'conversation_id': cid, 'recording_session_id': 'session'},
            headers={
                'X-App-Platform': 'ios',
                'X-Device-Id-Hash': 'abcd1234',
                'X-Omi-Upload-Hold': state,
                'X-Omi-Upload-Hold-Age-Ms': '000086400',
                'X-Omi-Upload-Trace': f'sealed={now - 100};gate=none',
                'X-Omi-Upload-Journal-Recovery': 'fresh',
                'X-Omi-Upload-Recovered': '0',
            },
            files=[('files', (name, path.read_bytes(), 'application/octet-stream'))],
        )
        assert response.status_code == 202, response.text
        job_ids.append(response.json()['job_id'])
    assert [phone_age_count(state) for state in states] == [count + 1 for count in age_counts_before]
    held = group(db)
    assert [member['job_id'] for member in held['members']] == job_ids
    assert [db.rows['intakes', job]['upload_hold_state'] for job in job_ids] == states

    if mode == 'individual':
        monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    now = held['release_by']
    assert await upload_coalescing.drain_group(db, artifacts, held['id'], now=now)
    assert group(db)['mode'] == mode
    originals = [db.rows['intakes', job] for job in job_ids]
    assert [original['upload_hold_state'] for original in originals] == states

    # Hand the real admission rows to the strict transaction fake at the
    # projection boundary. The worker's finished siblings are synthetic.
    projected = StrictFirestore({('users', uid, 'conversations', cid): {'status': 'completed'}})
    for (table, key), row in db.rows.items():
        if table == 'intakes':
            projected.rows[f'{db.namespace}_intakes', key] = row
        elif table == 'content':
            owner, content = key.split('/', 1)
            projected.rows[sync_content_ledger_ref(projected, owner, content).path] = row
    targets = list(dict.fromkeys(row.get('coalesce_target', job) for row, job in zip(originals, job_ids)))
    assert len(targets) == (1 if mode == 'merged' else len(states))
    delivered = Mock()
    monkeypatch.setattr(metrics, 'DELIVERED', delivered)
    for target in targets:
        segment_ids = db.rows['intakes', target]['segment_ids']
        binding = ProjectionBinding(**db.rows['jobs', segment_ids[0]]['projection_binding'])
        publish, _, _ = native_finish_completion(
            monkeypatch,
            projected,
            uid,
            cid,
            len(segment_ids),
            admitted_binding=binding,
            namespace=db.namespace,
        )
        assert publish(now + 20) is not None
    assert delivered.labels.call_args_list == [call('free', state, 'false') for state in states]
    for original in originals:
        ref = sync_content_ledger_ref(projected, uid, original['content_id'])
        assert projected.rows[ref.path]['status'] == 'completed'


@pytest.fixture
def receipts(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StrictFirestore()
    original = member('first')
    original['coalesce_group'] = 'group'
    intake_ref = client.collection('synthetic_intakes').document(original['job_id'])
    content_ref = sync_content_ledger_ref(client, 'owner', original['content_id'])
    client.rows[intake_ref.path] = original
    client.rows[content_ref.path] = {
        'job_id': original['job_id'],
        'dispatch_protocol': 'batch_v1',
        'status': 'processing',
    }
    binding = ProjectionBinding(
        'owner', 'bp_merged', 'merged', ('unit',), privacy_generation=0, target_conversation_id='recording'
    )
    ledger = {'status': 'processing', **completion.manifest({'id': 'group', 'mode': 'merged', 'members': [original]})}
    return client, binding, ledger, intake_ref, content_ref


def test_ordinary_completion_adds_no_reads():
    assert completion.manifest(None) == {}
    assert completion.prepare(object(), 'synthetic', object(), object(), {}) == []


def test_completion_reads_before_writes_and_replay_does_not_extend_expiry(receipts):
    client, binding, ledger, intake_ref, content_ref = receipts
    transaction = client.transaction()
    prepared = completion.prepare(client, 'synthetic', transaction, binding, ledger)
    result = {'new_memories': [], 'updated_memories': [], 'failed_segments': 0, 'total_segments': 2, 'errors': []}
    completion.write(transaction, prepared, result, 100)
    saved = deepcopy(client.rows)
    assert saved[content_ref.path]['status'] == 'completed'
    assert saved[content_ref.path]['result']['total_segments'] == 1
    assert saved[intake_ref.path]['coalesce_target'] == binding.job_id
    ledger['status'] = 'completed'
    prepared = completion.prepare(client, 'synthetic', client.transaction(), binding, ledger)
    assert prepared == []
    completion.write(client.transaction(), prepared, result, 999)
    assert client.rows == saved
    del client.rows[intake_ref.path]
    del client.rows[content_ref.path]
    assert completion.prepare(client, 'synthetic', client.transaction(), binding, ledger) == []


@pytest.mark.parametrize('mismatch', ['owner', 'conversation', 'generation', 'group', 'target', 'ledger', 'missing'])
def test_original_identity_mismatch_never_writes(receipts, mismatch):
    client, binding, ledger, intake_ref, content_ref = receipts
    updates = {
        'owner': {'owner_id': 'foreign'},
        'conversation': {'conversation_id': 'foreign'},
        'generation': {'privacy_generation': 1},
        'group': {'coalesce_group': 'foreign'},
        'target': {'coalesce_target': 'foreign'},
    }
    if mismatch in updates:
        client.rows[intake_ref.path].update(updates[mismatch])
    elif mismatch == 'ledger':
        client.rows[content_ref.path]['job_id'] = 'foreign'
    else:
        del client.rows[intake_ref.path]
    before = deepcopy(client.rows)
    with pytest.raises(ValueError, match='identity'):
        completion.prepare(client, 'synthetic', client.transaction(), binding, ledger)
    assert client.rows == before


def test_partial_result_never_acknowledges_originals(receipts):
    client, binding, ledger, _, _ = receipts
    transaction = client.transaction()
    prepared = completion.prepare(client, 'synthetic', transaction, binding, ledger)
    before = deepcopy(client.rows)
    with pytest.raises(ValueError, match='authoritative'):
        completion.write(transaction, prepared, {'failed_segments': 1}, 100)
    assert client.rows == before


def test_sixteen_originals_complete_with_windows_unset_and_keep_each_original_clock(receipts, monkeypatch):
    client, binding, _, _, _ = receipts
    for name in ('FREE', 'BACKLOG'):
        monkeypatch.delenv(f'BATCH_PIPELINE_COALESCING_{name}_WINDOW_SECONDS', raising=False)
    originals = []
    states = ['bg300', 'fg60'] * 8
    for i, state in enumerate(states):
        original = {
            **member(str(i)),
            'coalesce_group': 'group',
            'upload_arrived_at': 10 + i,
            'upload_entitlement': 'free',
            'upload_hold_state': state,
            'upload_recovered': i == 0,
        }
        intake_ref = client.collection('synthetic_intakes').document(original['job_id'])
        content_ref = sync_content_ledger_ref(client, 'owner', original['content_id'])
        client.rows[intake_ref.path] = original
        client.rows[content_ref.path] = {
            'job_id': original['job_id'],
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
        }
        originals.append(original)
    ledger = {'status': 'processing', **completion.manifest({'id': 'group', 'mode': 'merged', 'members': originals})}
    tx = client.transaction()
    prepared = completion.prepare(client, 'synthetic', tx, binding, ledger)
    members = [m for _, _, m, _ in prepared]
    assert [m['upload_arrived_at'] for m in members] == list(range(10, 26))
    assert [m['upload_hold_state'] for m in members] == states
    result = {'new_memories': [], 'updated_memories': [], 'failed_segments': 0, 'total_segments': 1, 'errors': []}
    completion.write(tx, prepared, result, 400)
    delivered = Mock()
    monkeypatch.setattr(metrics, 'DELIVERED', delivered)
    metrics.observe_completion({}, members, merged=True, changed=True, result=result, now=400)
    assert delivered.labels.call_args_list == [
        call('free', state, 'true' if index == 0 else 'false') for index, state in enumerate(states)
    ]
    for original in originals:
        ref = sync_content_ledger_ref(client, 'owner', original['content_id'])
        assert client.rows[ref.path]['status'] == 'completed'
    ledger['status'] = 'completed'
    assert completion.prepare(client, 'synthetic', client.transaction(), binding, ledger) == []
