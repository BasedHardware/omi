"""Conversation deletion forwards the captured vector generation."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import BackgroundTasks
import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

import routers.conversations as conversations_router
from database.conversation_vector_cleanup import ConversationVectorCleanupBusy


def test_delete_routes_through_the_captured_generation_cleanup_owner(monkeypatch):
    calls = []
    descriptor = SimpleNamespace(
        conversation_id='conversation-1',
        finalization_incarnation_id='incarnation-1',
        finalization_vector_generation_id='generation-1',
        transcript_vector_count=2,
    )
    monkeypatch.setattr(
        conversations_router,
        'claim_conversation_vector_cleanup_descriptor',
        lambda uid, conversation_id: calls.append(('capture', uid, conversation_id)) or descriptor,
    )
    monkeypatch.setattr(
        conversations_router,
        'delete_claimed_conversation_source',
        lambda uid, claimed, **kwargs: calls.append(('delete_claimed', uid, claimed, kwargs)),
    )

    result = conversations_router.delete_conversation(
        'conversation-1',
        BackgroundTasks(),
        cascade=False,
        uid='uid-1',
    )

    assert result == {'status': 'Ok'}
    assert calls == [
        ('capture', 'uid-1', 'conversation-1'),
        (
            'delete_claimed',
            'uid-1',
            descriptor,
            {'delete_source_artifacts': conversations_router.delete_conversation_playback_artifacts},
        ),
    ]


def test_delete_retains_fenced_source_when_required_generation_cleanup_fails(monkeypatch):
    monkeypatch.setattr(conversations_router, 'release_conversation_vector_cleanup_descriptor', MagicMock())
    monkeypatch.setattr(
        conversations_router,
        'claim_conversation_vector_cleanup_descriptor',
        lambda *_: SimpleNamespace(
            finalization_incarnation_id='incarnation-1',
            finalization_vector_generation_id='generation-1',
            transcript_vector_count=2,
        ),
    )
    monkeypatch.setattr(
        conversations_router,
        'delete_claimed_conversation_source',
        MagicMock(side_effect=RuntimeError('vector provider unavailable')),
    )

    with pytest.raises(RuntimeError, match='vector provider unavailable'):
        conversations_router.delete_conversation(
            'conversation-1',
            BackgroundTasks(),
            cascade=False,
            uid='uid-1',
        )


def test_delete_reports_an_active_finalizer_as_retryable(monkeypatch):
    monkeypatch.setattr(
        conversations_router,
        'claim_conversation_vector_cleanup_descriptor',
        MagicMock(side_effect=ConversationVectorCleanupBusy('conversation_vector_cleanup_fanout_active')),
    )
    delete_claimed = MagicMock()
    monkeypatch.setattr(conversations_router, 'delete_claimed_conversation_source', delete_claimed)

    with pytest.raises(conversations_router.HTTPException) as exc_info:
        conversations_router.delete_conversation(
            'conversation-1',
            BackgroundTasks(),
            cascade=False,
            uid='uid-1',
        )

    assert exc_info.value.status_code == 409
    delete_claimed.assert_not_called()
