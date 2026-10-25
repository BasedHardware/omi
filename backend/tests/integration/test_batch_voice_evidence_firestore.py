"""Real loopback Firestore: retention, revocation and physical artifact deletion."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import time

import numpy as np
import pytest

from database import batch_voice_evidence as db
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from tests.integration.test_batch_pipeline_deletion_firestore import state  # noqa: F401
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from utils.batch_pipeline import retention, voice_evidence
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.contracts import WorkItem, Priority

pytestmark = pytest.mark.integration


def prepare(state, monkeypatch):
    store, uid, user, _, _ = state
    item = WorkItem(
        'centroid-unit',
        uid,
        time.time() - 10,
        'gs://synthetic/audio#42',
        10,
        Priority.FRESH,
        conversation_id='source',
        privacy_generation=0,
    )
    key = privacy_owner_key(uid)
    binding = SimpleNamespace(owner_id=uid, private_cloud_sync_enabled=False)
    store.client.collection(f'{store.namespace}_jobs').document(item.segment_id).set(
        {
            **asdict(item),
            'owner_key': key,
            'state': 'projected',
            'projection_binding': {'owner_id': uid, 'private_cloud_sync_enabled': False},
        }
    )
    result_ref = store.client.collection(f'{store.namespace}_results').document(item.segment_id)
    result_ref.set(
        {
            'owner_key': key,
            'projection_state': 'ready',
            'result': {'result_uri': 'synthetic-result'},
            'projection_parts': {'0': {'conversation_id': 'source', 'speaker_scope': f'final:batch:{item.segment_id}'}},
        }
    )
    objects = ObjectClient()
    artifacts = create_artifact_store(store, objects, 'synthetic-batch-bucket', b'v' * 32)
    projection_store = SimpleNamespace(
        store=store, ref=lambda table, key: store.client.collection(f'{store.namespace}_{table}').document(key)
    )
    projector = SimpleNamespace(
        store=projection_store,
        load_result=lambda *a: {'diarization': {'turns': [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 8}]}},
        fetch_audio=lambda item: audio_unit(item.capture_at, b'\x01\x00' * (10 * 16000)).wav,
    )
    monkeypatch.setattr(voice_evidence, 'speaker_embedding_configured', lambda: True)

    def embedding(*args, **kwargs):
        assert kwargs['use_cache'] is False
        return np.eye(1, 256)[0]

    monkeypatch.setattr(voice_evidence, 'extract_embedding_from_bytes', embedding)
    monkeypatch.setattr(voice_evidence, 'artifacts_for', lambda store: artifacts)
    voice_evidence.prepare(projector, item, binding, 'source')
    reference = db.load_reference(store, uid, item.segment_id, 'source')
    assert reference is not None and objects.uploads == 1
    # A restart/replay loads the registered reference without reading any audio.
    projector.fetch_audio = lambda *a: pytest.fail('replay must reuse immutable evidence')
    voice_evidence.prepare(projector, item, binding, 'source')
    assert objects.uploads == 1
    return item, reference, artifacts, objects


def test_completion_shortens_ttl_without_extending_capture_and_schedule_deletes_object(state, monkeypatch):
    store, uid, user, _, _ = state
    item, reference, artifacts, objects = prepare(state, monkeypatch)
    completed = time.time()
    assert retention.expire_completed_segment(store, uid, item.segment_id, completed)
    rows = list(store.client.collection(f'{store.namespace}_artifacts').stream())
    data = rows[0].to_dict()
    due = data['cleanup_after']
    assert due.timestamp() == pytest.approx(completed + 3600, abs=0.01)
    assert due.timestamp() <= item.capture_at + 86400
    assert retention.expire_completed_segment(store, uid, item.segment_id, completed + 100)
    assert rows[0].reference.get().to_dict()['cleanup_after'] == due
    monkeypatch.setattr(db.time, 'time', lambda: due.timestamp())
    assert db.load_reference(store, uid, item.segment_id, 'source') is None
    # Audio incident holds do not retain biometric-like derived evidence.
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_WINDOWS', 'invalid')

    def erase(owner, uri):
        assert owner == uid and '#' in uri
        name = uri.split('/', 3)[3].split('#')[0]
        generation = int(uri.split('#')[1])
        objects.blob(name, generation=generation).delete(if_generation_match=generation)

    assert retention.cleanup_completed_artifacts(store, due, delete_uri=erase) == 1
    assert not objects.objects
    assert 'uri' not in rows[0].reference.get().to_dict()
    assert not user.collection('conversations').document('source').get().to_dict().get('audio_files')


def test_hard_expiry_cleans_pending_evidence_then_late_completion_succeeds(state, monkeypatch):
    store, uid, _, _, _ = state
    item, reference, _, objects = prepare(state, monkeypatch)
    due = datetime.fromtimestamp(item.capture_at + 86400, timezone.utc)
    erased = []
    assert retention.cleanup_completed_artifacts(store, due, delete_uri=lambda owner, uri: erased.append(uri)) == 1
    assert erased == [reference[1]]
    assert retention.expire_completed_segment(store, uid, item.segment_id, due.timestamp() + 100)


def test_account_delete_revokes_reads_and_erases_registered_voice_object(state, monkeypatch):
    store, uid, user, purge, erased = state
    item, reference, artifacts, objects = prepare(state, monkeypatch)

    def erase(owner, uri):
        erased.append(uri)
        if '/voice_evidence/' in uri:
            name = uri.split('/', 3)[3].split('#')[0]
            objects.blob(name).delete(if_generation_match=int(uri.split('#')[1]))

    assert purge(delete_uri=erase) > 0
    assert reference[1] in erased
    assert not objects.objects
    with pytest.raises(BatchPrivacyBlocked):
        artifacts.load_voice_evidence(item, reference[1], expires_at=reference[2])
    rows = list(store.client.collection(f'{store.namespace}_artifacts').stream())
    # Pending upload tombstone survives until the provider's maximum IO window.
    assert rows and rows[0].to_dict()['erasure_requested']


def test_unknown_voice_upload_outcome_remains_scheduled_until_physical_erasure(state, monkeypatch):
    store, uid, _, _, _ = state
    item, reference, artifacts, objects = prepare(state, monkeypatch)
    payload = artifacts.load_voice_evidence(item, reference[1], expires_at=reference[2])

    def lost_reply():
        raise TimeoutError('synthetic upload acknowledgement loss')

    objects.after_upload = lost_reply
    with pytest.raises(TimeoutError):
        artifacts.persist_voice_evidence(item, payload)
    assert len(objects.objects) == 2
    rows = list(store.client.collection(f'{store.namespace}_artifacts').stream())
    assert len(rows) == 2 and any('#' not in row.to_dict()['uri'] for row in rows)

    def erase(owner, uri):
        assert owner == uid
        name = uri.split('/', 3)[3].split('#')[0]
        generation = int(uri.split('#')[1]) if '#' in uri else objects.objects[name][0]
        objects.blob(name).delete(if_generation_match=generation)

    assert (
        retention.cleanup_completed_artifacts(
            store, datetime.fromtimestamp(item.capture_at + 86400, timezone.utc), delete_uri=erase
        )
        == 2
    )
    assert not objects.objects
