"""Tests for users router Joan follow-up question soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / tombstone)
are properly guarded and return 404 Not Found in:
- DELETE /v1/joan/{memory_id}/followup-question
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import users as users_routes


@pytest.fixture(scope='module')
def client():
    app = FastAPI()
    app.include_router(users_routes.router)
    app.dependency_overrides[users_routes.auth.get_current_user_uid] = lambda: 'user-1'
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _deny_unexpected_prompt(monkeypatch):
    prompt = MagicMock(side_effect=AssertionError('Blocked conversations must not generate a prompt'))
    monkeypatch.setattr(users_routes, 'followup_question_prompt', prompt)
    yield
    prompt.assert_not_called()


def _make_conversation(
    deleted: bool = False,
    locked: bool = False,
    conversation_id: str = 'conv-1',
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        'id': conversation_id,
        'uid': 'user-1',
        'deleted': deleted,
        'is_locked': locked,
        'created_at': now,
        'started_at': now,
        'finished_at': now,
        'structured': {
            'title': 'Test Conversation',
            'action_items': [],
        },
        'transcript_segments': [
            {
                'text': 'Test segment for follow-up question',
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'is_user': True,
                'start': 0.0,
                'end': 5.0,
            }
        ],
        'discarded': False,
    }


class TestJoanFollowupQuestionTombstoneGuard:
    """DELETE /v1/joan/{memory_id}/followup-question access guard tests."""

    def test_joan_followup_rejects_deleted_conversation(self, monkeypatch, client):
        """Endpoint must return 404 when target conversation is soft-deleted."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: _make_conversation(deleted=True, conversation_id=mid),
        )

        response = client.delete('/v1/joan/conv-deleted-1/followup-question')

        assert response.status_code == 404
        assert response.json()['detail'] == 'Conversation not found'

    def test_joan_followup_rejects_nonexistent_conversation(self, monkeypatch, client):
        """Endpoint must return 404 when target conversation does not exist."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: None,
        )

        response = client.delete('/v1/joan/conv-nonexistent/followup-question')

        assert response.status_code == 404
        assert response.json()['detail'] == 'Conversation not found'

    def test_joan_followup_rejects_locked_conversation(self, monkeypatch, client):
        """Endpoint must return 402 when target conversation is locked."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: _make_conversation(locked=True, conversation_id=mid),
        )

        response = client.delete('/v1/joan/conv-locked-1/followup-question')

        assert response.status_code == 402

    def test_joan_followup_allows_active_conversation(self, monkeypatch, client):
        """Endpoint must succeed and return generated prompt for active conversation."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: _make_conversation(deleted=False, conversation_id=mid),
        )
        monkeypatch.setattr(
            users_routes,
            'followup_question_prompt',
            lambda uid, segments: 'What are the next steps for the project?',
        )

        response = client.delete('/v1/joan/conv-active-1/followup-question')

        assert response.status_code == 200
        assert response.json() == {'result': 'What are the next steps for the project?'}

    def test_joan_followup_handles_in_progress_conversation_zero(self, monkeypatch, client):
        """Endpoint must look up in-progress conversation when memory_id is '0'."""
        monkeypatch.setattr(
            users_routes,
            'get_in_progress_conversation',
            lambda uid: _make_conversation(deleted=False, conversation_id='in-progress-1'),
        )
        monkeypatch.setattr(
            users_routes,
            'followup_question_prompt',
            lambda uid, segments: 'What happened during the conversation?',
        )

        response = client.delete('/v1/joan/0/followup-question')

        assert response.status_code == 200
        assert response.json() == {'result': 'What happened during the conversation?'}

    def test_joan_followup_rejects_missing_in_progress_conversation(self, monkeypatch, client):
        """Endpoint must return 400 when memory_id is '0' and no in-progress conversation exists."""
        monkeypatch.setattr(
            users_routes,
            'get_in_progress_conversation',
            lambda uid: None,
        )

        response = client.delete('/v1/joan/0/followup-question')

        assert response.status_code == 400
        assert response.json()['detail'] == 'No memory in progres'
