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
