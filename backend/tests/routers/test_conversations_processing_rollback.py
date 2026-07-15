"""A synchronous finalize failure must not strand a conversation on ``processing``.

POST /v1/conversations and POST /v1/conversations/{id}/finalize admit the
processing generation and then run the processor inside the request itself,
with no durable finalization job for the reconciler to replay. Before the
rollback guard, any processor exception left the conversation on
``processing`` forever — clients rendered a stuck "Processing" card that no
refresh could ever resolve.
"""

from types import SimpleNamespace

import pytest

from models.conversation_enums import ConversationStatus
from routers import conversations as conversations_router
from utils.conversations import lifecycle as lifecycle_service


@pytest.fixture
def conversation_state(monkeypatch):
    """Route the real lifecycle service at a dict-backed status store."""
    state = {'status': ConversationStatus.in_progress.value, 'discarded': False}

    def fake_get(uid, conversation_id):
        return dict(state) | {'id': conversation_id}

    def fake_claim(uid, conversation_id, expected, claimed, extra_updates=None):
        if state['discarded'] or state['status'] != expected.value:
            return False
        state['status'] = claimed.value
        if extra_updates:
            state.update(extra_updates)
        return True

    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', fake_get)
    monkeypatch.setattr(lifecycle_service.conversations_db, 'claim_conversation_status', fake_claim)
    return state


def _in_progress_conversation(conversation_id='conv1'):
    return SimpleNamespace(
        id=conversation_id,
        status=ConversationStatus.in_progress,
        external_data=None,
        language='en',
        geolocation=None,
    )


def _patch_request_seams(monkeypatch, conversation):
    monkeypatch.setattr(conversations_router, 'deserialize_conversation', lambda data: conversation)
    monkeypatch.setattr(conversations_router.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(conversations_router.redis_db, 'get_in_progress_conversation_id', lambda uid: None)
    monkeypatch.setattr(conversations_router.redis_db, 'remove_in_progress_conversation_id', lambda uid: None)

    def raise_processing(*args, **kwargs):
        raise RuntimeError('processor crashed')

    monkeypatch.setattr(conversations_router, 'process_conversation', raise_processing)


def test_finalize_rolls_back_admission_when_processing_raises(monkeypatch, conversation_state):
    conversation = _in_progress_conversation()
    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    _patch_request_seams(monkeypatch, conversation)

    with pytest.raises(RuntimeError, match='processor crashed'):
        conversations_router.finalize_conversation('conv1', request=None, uid='uid1')

    assert conversation_state['status'] == ConversationStatus.in_progress.value


def test_create_conversation_rolls_back_admission_when_processing_raises(monkeypatch, conversation_state):
    conversation = _in_progress_conversation()
    monkeypatch.setattr(conversations_router, 'retrieve_in_progress_conversation', lambda uid: {'id': conversation.id})
    _patch_request_seams(monkeypatch, conversation)

    with pytest.raises(RuntimeError, match='processor crashed'):
        conversations_router.process_in_progress_conversation(request=None, uid='uid1')

    assert conversation_state['status'] == ConversationStatus.in_progress.value
