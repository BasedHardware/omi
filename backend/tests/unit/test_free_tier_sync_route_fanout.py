"""S6: the synchronous create route must honour TERMINAL_NO_DERIVED_EFFECTS.

POST /v1/conversations (process_in_progress_conversation) is a second caller of
process_conversation. The durable finalizer already skips app/webhook fan-out
when the coordinator reports a terminal minimum; this route used to disagree
and call trigger_external_integrations after persistence True. Section 1.7 of
10-backend-plumbing.md puts apps in the "nothing written" column.

The coordinator-cell mapping lives in test_free_tier_entrypoint_matrix.py; this
file drives the real route function so a caller-side skip cannot hide behind
coordinator-only coverage.

red-proof (1): drop derived_effects_disposition_observer from the process_conversation
    call → flag-on basic stays at default RUN and fans out
red-proof (2): delete the TERMINAL_NO_DERIVED_EFFECTS early return → flag-on basic
    still calls trigger_external_integrations
red-proof (3): treat every disposition as TERMINAL_NO_DERIVED_EFFECTS → flag-on paid
    and both flag-off cells stop calling trigger_external_integrations
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from models.chat import Message, MessageSender, MessageType
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured

_UID = 'sync-route-uid'
_STARTED = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
_FANOUT_MESSAGES = [
    Message(
        id='app-msg-1',
        text='webhook ping',
        created_at=_STARTED,
        sender=MessageSender.ai,
        type=MessageType.text,
    )
]


@pytest.fixture(scope='module')
def conv():
    """Pay the routers.conversations import graph once, outside CALL-phase timing."""
    import routers.conversations as conversations_router

    return conversations_router


def _desktop_conversation(*, status: ConversationStatus) -> Conversation:
    return Conversation(
        id='conv-sync-route',
        created_at=_STARTED,
        started_at=_STARTED,
        finished_at=_STARTED,
        language='en',
        structured=Structured(title='desktop capture'),
        transcript_segments=[],
        status=status,
        source=ConversationSource.desktop,
    )


@contextmanager
def _noop_guard(*_args: Any, **_kwargs: Any):
    yield


def _drive_create_route(conv: Any, monkeypatch: pytest.MonkeyPatch, *, disposition: Any):
    """Call the real route with the coordinator mocked at its observer seam."""
    in_progress = _desktop_conversation(status=ConversationStatus.in_progress)
    processed = _desktop_conversation(status=ConversationStatus.completed)
    seen_kwargs: dict[str, Any] = {}

    def process(_uid: str, _language: str, conversation: Conversation, **kwargs: Any) -> Conversation:
        seen_kwargs.update(kwargs)
        observer = kwargs.get('persistence_observer')
        if observer is not None:
            observer(True)
        reported = kwargs.get('derived_effects_disposition_observer')
        if reported is not None:
            reported(disposition)
        return processed

    integrations = AsyncMock(return_value=list(_FANOUT_MESSAGES))
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': in_progress.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', lambda uid, cid: True)
    monkeypatch.setattr(conv.lifecycle_service, 'processing_admission_guard', _noop_guard)
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: in_progress.id)
    monkeypatch.setattr(conv.redis_db, 'remove_in_progress_conversation_id', lambda uid: None)
    monkeypatch.setattr(conv, 'process_conversation', process)
    monkeypatch.setattr(conv, 'trigger_external_integrations', integrations)

    response = conv.process_in_progress_conversation(uid=_UID)
    return response, integrations, processed, seen_kwargs


def _disposition_for(conv: Any, *, flag_on: bool, user: str) -> Any:
    # Flag-on identified-basic desktop is the terminal minimum. Flag-off (legacy
    # force_process bypass) and paid both report RUN — today's fan-out.
    if flag_on and user == 'basic':
        return conv.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
    return conv.DerivedEffectsDisposition.RUN


def test_flag_on_basic_desktop_returns_conversation_without_app_fanout(conv, monkeypatch) -> None:
    response, integrations, processed, seen = _drive_create_route(
        conv,
        monkeypatch,
        disposition=_disposition_for(conv, flag_on=True, user='basic'),
    )

    assert seen.get('force_process') is True
    assert seen.get('derived_effects_disposition_observer') is not None
    assert response.conversation is processed
    assert response.messages == []
    integrations.assert_not_called()


def test_flag_on_paid_desktop_fans_out_exactly_as_today(conv, monkeypatch) -> None:
    response, integrations, processed, seen = _drive_create_route(
        conv,
        monkeypatch,
        disposition=_disposition_for(conv, flag_on=True, user='paid'),
    )

    assert seen.get('force_process') is True
    assert seen.get('derived_effects_disposition_observer') is not None
    assert response.conversation is processed
    assert response.messages == _FANOUT_MESSAGES
    integrations.assert_called_once_with(_UID, processed)


@pytest.mark.parametrize('user', ['basic', 'paid'])
def test_flag_off_is_byte_identical_to_today_for_basic_and_paid(conv, monkeypatch, user: str) -> None:
    response, integrations, processed, seen = _drive_create_route(
        conv,
        monkeypatch,
        disposition=_disposition_for(conv, flag_on=False, user=user),
    )

    assert seen.get('force_process') is True
    assert seen.get('derived_effects_disposition_observer') is not None
    assert response.conversation is processed
    assert response.messages == _FANOUT_MESSAGES
    integrations.assert_called_once_with(_UID, processed)
