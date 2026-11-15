"""Released-client wire contract for DELETE /v1/conversations/{conversation_id}.

The 2026-07-04 response_model backfill (e22938ac78) silently converted this
route from ``status_code=204`` to a 200-with-body. The released mobile client
(``app/lib/backend/http/api/conversations.dart::deleteConversationServer``)
gates delete success on exactly 204, so every conversation delete read as a
failure there: the optimistic tombstone was dropped, the server-cursor bookkeeping
skipped the rebase, and once the server delete itself could not complete the
conversation resurfaced on the next refresh (#10446 recurrence class).

Two layers assert the same contract so one layer failing alone cannot hide the
drift: the router declaration and the generated app-client OpenAPI spec.
"""

from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from routers import conversations
from database.legal_holds import DestructiveOperationInProgress

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_CLIENT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'

CONVERSATION_DELETE_PATH = '/v1/conversations/{conversation_id}'


def _conversation_delete_route() -> APIRoute:
    matches = [
        route
        for route in conversations.router.routes
        if isinstance(route, APIRoute) and route.path == CONVERSATION_DELETE_PATH and 'DELETE' in route.methods
    ]
    assert matches, 'conversation delete route must stay registered'
    return matches[0]


def test_conversation_delete_declares_released_204_contract():
    route = _conversation_delete_route()

    assert route.status_code == 204
    # A 204 route has no body; a response_model forces FastAPI to serialize one.
    assert route.response_model is None


def test_app_client_spec_declares_204_not_200_for_conversation_delete():
    spec = json.loads(APP_CLIENT_SPEC_PATH.read_text())
    responses = spec['paths'][CONVERSATION_DELETE_PATH]['delete']['responses']

    assert '204' in responses
    # The released mobile client treats a 200 body as a failed DELETE.
    assert '200' not in responses


def _delete_client(monkeypatch) -> TestClient:
    """The real route and FastAPI serialization; only storage side effects are stubbed."""
    for name in (
        'delete_owner_prompt_embedding_cache',
        'delete_conversation_screen_frames',
        'delete_conversation_and_frame_evidence',
        'delete_privacy_conversation_audio',
        'delete_vector',
        'delete_transcript_chunk_vectors',
        'delete_action_item_vectors_batch',
        'record_product_event',
        'MemoryService',
    ):
        monkeypatch.setattr(conversations, name, MagicMock())
    monkeypatch.setattr(conversations.conversation_tombstones, 'record_deletion', MagicMock())
    monkeypatch.setattr(conversations, 'destructive_operation_gate', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(conversations.conversations_db, 'get_conversation', lambda *args: {})
    monkeypatch.setattr(conversations.conversations_db, 'get_conversation_raw_snapshot', lambda *args, **kwargs: {})
    monkeypatch.setattr(conversations, 'retraction_can_be_skipped', lambda *args, **kwargs: True)
    monkeypatch.setattr(conversations.action_items_db, 'get_action_items_by_conversation', lambda *args, **kwargs: [])
    monkeypatch.setattr(conversations.action_items_db, 'delete_action_items_for_conversation', MagicMock())
    app = FastAPI()
    app.include_router(conversations.router)
    app.dependency_overrides[conversations.auth.get_current_user_uid] = lambda: 'uid-delete-contract'
    return TestClient(app)


@pytest.mark.parametrize('cascade', ['false', 'true'])
def test_conversation_delete_answers_204_with_an_empty_body_over_http(monkeypatch, cascade):
    # The released mobile client reads anything but exactly 204 as a failed delete
    # and lets the conversation reappear on the next refresh.
    with _delete_client(monkeypatch) as client:
        response = client.delete(f'/v1/conversations/conversation-1?cascade={cascade}')

    assert response.status_code == 204
    assert response.content == b''


def test_busy_delete_leaves_no_tombstone_or_cleanup_and_remains_retryable(monkeypatch):
    with _delete_client(monkeypatch) as client:
        monkeypatch.setattr(conversations, 'retraction_can_be_skipped', lambda *args, **kwargs: False)

        @contextmanager
        def busy(*args, **kwargs):
            raise DestructiveOperationInProgress('synthetic busy account')
            yield

        monkeypatch.setattr(conversations, 'destructive_operation_gate', busy)
        response = client.delete('/v1/conversations/conversation-1?cascade=true')

    assert response.status_code == 409
    assert response.json() == {'detail': 'account_gate_busy'}
    assert response.headers['Retry-After'] == '2'
    conversations.conversation_tombstones.record_deletion.assert_not_called()
    conversations.delete_owner_prompt_embedding_cache.assert_not_called()
    conversations.delete_conversation_and_frame_evidence.assert_not_called()


def test_cascade_gate_precedes_intent_and_covers_retraction_and_cleanup(monkeypatch):
    events = []
    with _delete_client(monkeypatch) as client:

        def retraction_required(*args, **kwargs):
            assert events == ['gate', 'intent']
            return False

        monkeypatch.setattr(conversations, 'retraction_can_be_skipped', retraction_required)

        @contextmanager
        def gate(*args, **kwargs):
            events.append('gate')
            yield 'synthetic-token'
            events.append('release')

        monkeypatch.setattr(conversations, 'destructive_operation_gate', gate)
        conversations.conversation_tombstones.record_deletion.side_effect = lambda *args: events.append('intent')
        conversations.MemoryService.return_value.retract_conversation_memories.side_effect = (
            lambda *args: events.append('retract')
        )
        conversations.delete_conversation_and_frame_evidence.side_effect = lambda *args: events.append('delete')
        response = client.delete('/v1/conversations/conversation-1?cascade=true')

    assert response.status_code == 204
    assert events == ['gate', 'intent', 'retract', 'delete', 'release']


class _GateDocs:
    """Minimal Firestore for the real account gate and external write fence."""

    def __init__(self):
        self.docs = {}

    def document(self, path):
        docs = self.docs
        return MagicMock(
            path=path,
            get=lambda transaction=None: MagicMock(exists=path in docs, to_dict=lambda: dict(docs.get(path) or {})),
        )

    def transaction(self):
        docs = self.docs
        return MagicMock(set=lambda ref, payload, merge=False: docs.__setitem__(ref.path, dict(payload)))


def test_cascade_delete_nested_fenced_writes_do_not_hit_their_own_gate(monkeypatch):
    """Prod regression: every cascade delete 409'd on its own explicit_memory_deletion gate.

    The real gate is acquired; nested cleanup then performs the same fenced writes
    production does (transactional speaker retraction inside conversation deletion,
    non-transactional Pinecone transcript-chunk delete).
    """
    from database import legal_holds

    gate_docs = _GateDocs()
    monkeypatch.setattr(
        legal_holds,
        '_acquire_destructive_operation_transaction',
        legal_holds._acquire_destructive_operation_transaction.to_wrap,
    )
    monkeypatch.setattr(
        legal_holds,
        '_finish_destructive_operation_transaction',
        legal_holds._finish_destructive_operation_transaction.to_wrap,
    )
    with _delete_client(monkeypatch) as client:
        monkeypatch.setattr(conversations, 'destructive_operation_gate', legal_holds.destructive_operation_gate)
        monkeypatch.setattr(conversations, 'db_client_module', MagicMock(db=gate_docs))

        def speaker_retraction_then_delete(uid, conversation_id):
            with legal_holds.external_write_fence(uid, firestore_client=gate_docs, transaction=gate_docs.transaction()):
                pass

        def transcript_chunk_delete(uid, conversation_id):
            with legal_holds.external_write_fence(uid, firestore_client=gate_docs):
                pass

        conversations.delete_conversation_and_frame_evidence.side_effect = speaker_retraction_then_delete
        conversations.delete_transcript_chunk_vectors.side_effect = transcript_chunk_delete
        response = client.delete('/v1/conversations/conversation-1?cascade=true')

    assert response.status_code == 204
    gate = gate_docs.docs['legal_hold_deletion_gates/uid-delete-contract']
    assert gate['state'] == 'completed'
    conversations.delete_transcript_chunk_vectors.assert_called_once()


@pytest.mark.parametrize('cascade', ['false', 'true'])
@pytest.mark.parametrize('failure', ['purge', 'inventory'])
def test_lake_failure_answers_retryable_503_with_intent_and_documents_intact(monkeypatch, cascade, failure):
    from services import conversation_frame_evidence
    from utils.other import object_lake, lake_wipe

    monkeypatch.setattr(lake_wipe, '_fence_conversation_uploads', lambda *args: None)
    with _delete_client(monkeypatch) as client:
        monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'synthetic-lake')
        monkeypatch.setattr(
            conversation_frame_evidence.conversations_db, 'get_conversation_raw_snapshot', lambda *args, **kwargs: {}
        )
        deleted = MagicMock()
        monkeypatch.setattr(
            conversations,
            'delete_conversation_and_frame_evidence',
            lambda uid, cid: conversation_frame_evidence.delete_conversation_and_frame_evidence(
                uid, cid, delete_conversation=deleted
            ),
        )
        monkeypatch.setattr(conversation_frame_evidence.conversations_db, 'get_conversation_photos', lambda *args: [])
        monkeypatch.setattr(
            conversation_frame_evidence.frame_requests_db,
            'list_all_frame_request_storage_ids',
            lambda *args, **kwargs: [],
        )
        monkeypatch.setattr(
            conversation_frame_evidence.frame_requests_db, 'persist_conversation_frame_deletion_outbox', MagicMock()
        )
        monkeypatch.setattr(
            object_lake, 'delete_space_entity', MagicMock(side_effect=object_lake.LakeFetchError('lake down'))
        )
        if failure == 'inventory':
            monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
            monkeypatch.setattr(
                conversation_frame_evidence.conversations_db,
                'get_conversation_raw_snapshot',
                MagicMock(side_effect=RuntimeError('synthetic Firestore read failure')),
            )
        response = client.delete(f'/v1/conversations/conversation-1?cascade={cascade}')
    assert response.status_code == 503
    assert response.json()['detail'] == 'Conversation storage deletion is busy, please retry'
    conversations.conversation_tombstones.record_deletion.assert_called_once_with(
        'uid-delete-contract', 'conversation-1'
    )
    deleted.assert_not_called()


def test_cascade_retry_preserves_canonical_audio_donors_after_partial_lake_purge(monkeypatch):
    from utils.other import object_lake

    with _delete_client(monkeypatch) as client:
        monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'synthetic-canonical')
        # A partial lake purge makes the decoded read return no conversation,
        # while the raw parent still owns its retained donor inventory.
        decoded = MagicMock(return_value=None)
        monkeypatch.setattr(conversations.conversations_db, 'get_conversation', decoded)
        monkeypatch.setattr(
            conversations.conversations_db,
            'get_conversation_raw_snapshot',
            lambda *args, **kwargs: {'sync_merged_from': ['donor-a', 'donor-b']},
        )
        conversations.delete_conversation_and_frame_evidence.side_effect = [
            object_lake.LakeFetchError('lake down'),
            None,
        ]
        assert client.delete('/v1/conversations/conversation-1?cascade=true').status_code == 503
        conversations.delete_privacy_conversation_audio.assert_not_called()
        assert client.delete('/v1/conversations/conversation-1?cascade=true').status_code == 204

    decoded.assert_not_called()
    conversations.delete_privacy_conversation_audio.assert_called_once_with(
        'uid-delete-contract', 'conversation-1', source_ids=['donor-a', 'donor-b']
    )


def test_cascade_donor_inventory_read_failure_is_retryable_503(monkeypatch):
    with _delete_client(monkeypatch) as client:
        monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'synthetic-canonical')
        read = MagicMock(side_effect=RuntimeError('synthetic Firestore read failure'))
        monkeypatch.setattr(conversations.conversations_db, 'get_conversation_raw_snapshot', read)
        response = client.delete('/v1/conversations/conversation-1?cascade=true')
    assert response.status_code == 503
    assert response.json()['detail'] == 'Conversation storage deletion is busy, please retry'
    assert read.call_args.kwargs == {'field_paths': ['sync_merged_from']}
    conversations.delete_privacy_conversation_audio.assert_not_called()
    conversations.delete_conversation_and_frame_evidence.assert_not_called()


def _real_lake_delete(monkeypatch, tmp_path):
    from services import conversation_frame_evidence
    from tests.unit.fixtures.lake_firestore import LakeFirestore as StrictFirestore
    from utils.other import object_lake, space_keys, lake_wipe
    from utils.other.local_storage import LocalStorageClient

    store = StrictFirestore()
    bucket = LocalStorageClient(tmp_path).bucket('synthetic-lake')
    for key, value in {
        'BUCKET_OBJECT_LAKE': bucket.name,
        'OBJECT_LAKE_WRITE_ENABLED': 'true',
        'OBJECT_LAKE_WRITE_PERCENT': '100',
        'OBJECT_LAKE_RELEASE': 'v1',
        'OMI_ENV_STAGE': 'offline',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    monkeypatch.setattr(
        space_keys, 'space_key_firestore_client', lambda supplied=None: store if supplied is None else supplied
    )
    monkeypatch.setattr(space_keys, '_cache', None)
    monkeypatch.setattr(object_lake, '_lake_bucket', lambda: bucket)
    monkeypatch.setattr(object_lake, 'create_storage_client', lambda: bucket.client)
    monkeypatch.setattr(conversation_frame_evidence.conversations_db, 'get_conversation_photos', lambda *args: [])
    monkeypatch.setattr(
        conversation_frame_evidence.frame_requests_db, 'list_all_frame_request_storage_ids', lambda *args, **kw: []
    )
    for name in ('persist_conversation_frame_deletion_outbox', 'delete_frame_requests_for_conversation'):
        monkeypatch.setattr(conversation_frame_evidence.frame_requests_db, name, MagicMock())
    doc = (
        store.collection('users').document('uid-delete-contract').collection('conversations').document('conversation-1')
    )
    doc.create({'id': 'conversation-1'})
    monkeypatch.setattr(
        conversation_frame_evidence.conversations_db,
        'get_conversation_raw_snapshot',
        lambda *args, **kwargs: doc.get().to_dict(),
    )
    deleted = MagicMock(side_effect=lambda *args: store.rows.pop(doc.path, None))
    monkeypatch.setattr(
        conversations,
        'delete_conversation_and_frame_evidence',
        lambda uid, cid: conversation_frame_evidence.delete_conversation_and_frame_evidence(
            uid, cid, delete_conversation=deleted
        ),
    )
    return bucket, doc, deleted


def test_verified_absence_failure_is_http_503_and_retains_documents(monkeypatch, tmp_path):
    from utils.other import object_lake
    from utils.other.local_storage import LocalBlob

    with _delete_client(monkeypatch) as client:
        bucket, doc, deleted = _real_lake_delete(monkeypatch, tmp_path)
        object_lake.put_space_object('uid-delete-contract', 'transcript', 'conversation-1', b'private')
        original_delete = LocalBlob.delete
        monkeypatch.setattr(LocalBlob, 'delete', lambda *args, **kwargs: None)
        response = client.delete('/v1/conversations/conversation-1')
        assert response.status_code == 503
        assert response.json()['detail'] == 'Conversation storage deletion is busy, please retry'
        assert doc.get().exists and list(bucket.list_blobs())
        deleted.assert_not_called()
        conversations.conversation_tombstones.record_deletion.assert_called_once()
        monkeypatch.setattr(LocalBlob, 'delete', original_delete)
        response = client.delete('/v1/conversations/conversation-1')
        assert response.status_code == 204 and response.content == b''
        assert not doc.get().exists and not list(bucket.list_blobs())
        deleted.assert_called_once()


def test_upload_finishing_after_http_delete_final_listing_leaves_no_object(monkeypatch, tmp_path):
    from utils.other import object_lake

    with _delete_client(monkeypatch) as client:
        bucket, doc, deleted = _real_lake_delete(monkeypatch, tmp_path)
        statuses = []

        def finish_after_delete(method, uri, data, headers):
            if method != 'PUT' or str(headers.get('Content-Range', '')).startswith('bytes */'):
                return
            bucket.client._http.before_request = None
            response = client.delete('/v1/conversations/conversation-1')
            statuses.append(response.status_code)
            assert response.status_code == 204 and response.content == b''
            assert not list(bucket.list_blobs())

        bucket.client._http.before_request = finish_after_delete
        with pytest.raises(object_lake.LakeFetchError):
            object_lake.put_space_object('uid-delete-contract', 'transcript', 'conversation-1', b'late candidate')
        assert statuses == [204]
        assert not doc.get().exists and not list(bucket.list_blobs())
        deleted.assert_called_once()
