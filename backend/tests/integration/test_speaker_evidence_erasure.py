"""Speaker evidence custody on loopback Firestore, using synthetic accounts."""

import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import speaker_evidence, user_data_deletion
from database._client import delete_collection_recursive
from database.account_deletion_marker import account_deletion_document
from database.conversation_revisions import firestore_revision_datetime
from models.speaker_evidence import SpeakerEvidence

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required')
    return firestore.Client(project=f'evidence-{uuid4().hex[:12]}', credentials=AnonymousCredentials())


def test_deletion_marker_after_reservation_refuses_evidence(client, monkeypatch):
    uid = uuid4().hex
    parent = client.document(f'users/{uid}/conversations/c')
    reservation = parent.set({'status': 'completed'}).update_time
    evidence = SpeakerEvidence(status='unavailable', policy_version='synthetic')
    marker = account_deletion_document(uid, firestore_client=client)
    marker.set({})

    original_get = firestore.DocumentReference.get
    marker_reads = []

    def observe_get(ref, *args, **kwargs):
        if ref.path == marker.path:
            marker_reads.append(kwargs['transaction'])
        return original_get(ref, *args, **kwargs)

    monkeypatch.setattr(firestore.DocumentReference, 'get', observe_get)
    with pytest.raises(ValueError, match='account unavailable'):
        speaker_evidence.store_evidence(
            uid, 'c', evidence, expected_updated_at=firestore_revision_datetime(reservation), firestore_client=client
        )
    assert marker_reads and all(tx is not None for tx in marker_reads)
    assert not parent.collection('speaker_evidence').document('current').get().exists
    assert parent.get().update_time == reservation


@pytest.mark.parametrize('retry_with_parents_missing', [False, True])
def test_account_erasure_sweeps_late_evidence(client, monkeypatch, retry_with_parents_missing):
    uid = uuid4().hex
    root = client.document(f'users/{uid}')
    parent = root.collection('conversations').document('c')
    child = parent.collection('speaker_evidence').document('current')
    other = client.document('users/other/conversations/c/speaker_evidence/current')
    other.set({'version': 1})
    if retry_with_parents_missing:
        child.set({'version': 1})
    else:
        root.set({})
        parent.set({'status': 'completed'})

    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', lambda _uid: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(user_data_deletion, 'account_authority_writer_enabled', lambda: False)
    monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda *a, **kw: [])
    monkeypatch.setattr(user_data_deletion, 'delete_generic_cache', lambda *a: None)
    monkeypatch.setattr(user_data_deletion, 'stop_quiet_checks_for_account', lambda *a, **kw: None)
    original_collections = firestore.DocumentReference.collections
    injected = False

    def collections(ref, *args, **kwargs):
        nonlocal injected
        yield from original_collections(ref, *args, **kwargs)
        if ref.path == parent.path and not retry_with_parents_missing and not injected:
            assert parent.get().exists
            child.set({'version': 1})
            injected = True

    monkeypatch.setattr(firestore.DocumentReference, 'collections', collections)
    result = user_data_deletion.purge_user_subtree(uid, client, delete_collection_recursive)
    assert result['status'] == 'ok'
    assert injected == (not retry_with_parents_missing)
    assert not root.get().exists and not parent.get().exists
    assert not child.get().exists and other.get().exists
