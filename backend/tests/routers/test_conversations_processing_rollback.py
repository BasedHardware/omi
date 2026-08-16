"""A legacy synchronous finalize failure must not strand a conversation.

POST /v1/conversations still runs its processor in the request and must roll
back its admission if that processor raises. The exact-ID finalize route uses
the durable finalization job worker instead; its terminal failure is covered
by the worker and lifecycle contracts.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_create_conversation_rolls_back_admission_when_processing_raises(monkeypatch, conversation_state):
    conversation = _in_progress_conversation()
    monkeypatch.setattr(conversations_router, 'retrieve_in_progress_conversation', lambda uid: {'id': conversation.id})
    _patch_request_seams(monkeypatch, conversation)

    with pytest.raises(RuntimeError, match='processor crashed'):
        conversations_router.process_in_progress_conversation(request=None, uid='uid1')

    assert conversation_state['status'] == ConversationStatus.in_progress.value


def test_rollback_error_does_not_mask_the_original_processing_exception(monkeypatch, conversation_state):
    # A conversation deleted mid-processing makes the rollback CAS raise
    # NotFound; the caller must still see the original processor error.
    conversation = _in_progress_conversation()
    monkeypatch.setattr(conversations_router, 'retrieve_in_progress_conversation', lambda uid: {'id': conversation.id})
    _patch_request_seams(monkeypatch, conversation)

    admission_claim = lifecycle_service.conversations_db.claim_conversation_status

    def raise_on_rollback(uid, conversation_id, expected, claimed, extra_updates=None):
        if claimed == ConversationStatus.in_progress:
            raise LookupError('conversation deleted mid-processing')
        return admission_claim(uid, conversation_id, expected, claimed, extra_updates)

    monkeypatch.setattr(lifecycle_service.conversations_db, 'claim_conversation_status', raise_on_rollback)

    with pytest.raises(RuntimeError, match='processor crashed'):
        conversations_router.process_in_progress_conversation(request=None, uid='uid1')


def test_deferred_enrichment_renews_processing_lease_during_live_processing(monkeypatch):
    """Lazy enrichment of a deferred conversation must keep its admission lease
    fresh while process_conversation runs in the background thread (#10461
    ownership fence for every live producer). Behavioral test through the actual
    _enrich_deferred_conversation path, not the context manager."""
    import threading

    from database import conversation_finalization_jobs as jobs_db

    lease_renewed = threading.Event()

    def fake_renew(_uid, _conversation_id):
        lease_renewed.set()
        return True

    monkeypatch.setattr(jobs_db, 'renew_processing_lease', fake_renew)
    monkeypatch.setattr(lifecycle_service, '_processing_lease_renewal_interval', lambda: 0.001)
    monkeypatch.setattr(lifecycle_service, 'reacquire_deferred_processing', lambda *_args: True)

    enrichment_done = threading.Event()

    def blocking_process(_uid, _language, conversation, **kwargs):
        assert lease_renewed.wait(timeout=5.0), 'lease not renewed during deferred enrichment'
        enrichment_done.set()
        return conversation

    monkeypatch.setattr(conversations_router, 'process_conversation', blocking_process)
    monkeypatch.setattr(conversations_router.conversations_db, 'update_conversation', MagicMock())

    conv_obj = SimpleNamespace(id='deferred-conv-1', language='en', deferred=False)
    monkeypatch.setattr(conversations_router, 'deserialize_conversation', lambda data: conv_obj)

    conversations_router._enrich_deferred_conversation(
        'uid1', {'id': 'deferred-conv-1', 'status': 'processing', 'deferred': True, 'language': 'en'}
    )

    # The enrichment runs in a background thread; wait for it to prove the lease was renewed.
    assert enrichment_done.wait(timeout=10.0), 'deferred enrichment did not complete'
    assert lease_renewed.is_set()


def test_deferred_enrichment_atomically_reacquires_ownership_before_processing(monkeypatch):
    """#10468 r4: clearing deferred must be an atomic guarded transition that
    renews the admission lease immediately — not a clear-then-first-heartbeat
    gap where the orphan sweep can terminalize the row."""
    import threading

    reacquired = threading.Event()

    def fake_reacquire(_uid, _conversation_id):
        reacquired.set()
        return True

    monkeypatch.setattr(lifecycle_service, 'reacquire_deferred_processing', fake_reacquire)

    enrichment_done = threading.Event()

    def blocking_process(_uid, _language, conversation, **kwargs):
        assert reacquired.is_set(), 'ownership not reacquired before processing'
        enrichment_done.set()
        return conversation

    monkeypatch.setattr(conversations_router, 'process_conversation', blocking_process)
    monkeypatch.setattr(lifecycle_service, '_processing_lease_renewal_interval', lambda: 0.001)
    monkeypatch.setattr(conversations_router.conversations_db, 'update_conversation', MagicMock())

    conv_obj = SimpleNamespace(id='deferred-conv-1', language='en', deferred=False)
    monkeypatch.setattr(conversations_router, 'deserialize_conversation', lambda data: conv_obj)

    conversations_router._enrich_deferred_conversation(
        'uid1', {'id': 'deferred-conv-1', 'status': 'processing', 'deferred': True, 'language': 'en'}
    )

    assert enrichment_done.wait(timeout=10.0), 'deferred enrichment did not complete'
    assert reacquired.is_set(), 'reacquire_deferred_processing was not called'


def test_deferred_enrichment_skips_when_reacquisition_fails(monkeypatch):
    """#10468 r4: if reacquisition fails (row terminalized/discarded), no
    enrichment or derived side effect happens — the stale processor fails closed."""
    import time

    monkeypatch.setattr(lifecycle_service, 'reacquire_deferred_processing', lambda *_args: False)
    process_called = MagicMock()
    monkeypatch.setattr(conversations_router, 'process_conversation', process_called)

    conversations_router._enrich_deferred_conversation(
        'uid1', {'id': 'deferred-conv-1', 'status': 'processing', 'deferred': True, 'language': 'en'}
    )

    time.sleep(0.2)  # Give any background task time to (not) run
    process_called.assert_not_called()
