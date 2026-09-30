"""Tests for users router Joan follow-up question soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / tombstone)
are properly guarded and return 404 Not Found in:
- DELETE /v1/joan/{memory_id}/followup-question
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import users as users_routes


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

    def test_joan_followup_rejects_deleted_conversation(self, monkeypatch):
        """Endpoint must return 404 when target conversation is soft-deleted."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: _make_conversation(deleted=True, conversation_id=mid),
        )

        with pytest.raises(HTTPException) as exc_info:
            users_routes.delete_person_endpoint(
                memory_id='conv-deleted-1',
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_joan_followup_rejects_nonexistent_conversation(self, monkeypatch):
        """Endpoint must return 404 when target conversation does not exist."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: None,
        )

        with pytest.raises(HTTPException) as exc_info:
            users_routes.delete_person_endpoint(
                memory_id='conv-nonexistent',
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_joan_followup_rejects_locked_conversation(self, monkeypatch):
        """Endpoint must return 402 when target conversation is locked."""
        monkeypatch.setattr(
            users_routes,
            'get_conversation',
            lambda uid, mid: _make_conversation(locked=True, conversation_id=mid),
        )

        with pytest.raises(HTTPException) as exc_info:
            users_routes.delete_person_endpoint(
                memory_id='conv-locked-1',
                uid='user-1',
            )

        assert exc_info.value.status_code == 402

    def test_joan_followup_allows_active_conversation(self, monkeypatch):
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

        result = users_routes.delete_person_endpoint(
            memory_id='conv-active-1',
            uid='user-1',
        )

        assert result == {'result': 'What are the next steps for the project?'}

    def test_joan_followup_handles_in_progress_conversation_zero(self, monkeypatch):
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

        result = users_routes.delete_person_endpoint(
            memory_id='0',
            uid='user-1',
        )

        assert result == {'result': 'What happened during the conversation?'}

    def test_joan_followup_rejects_missing_in_progress_conversation(self, monkeypatch):
        """Endpoint must return 400 when memory_id is '0' and no in-progress conversation exists."""
        monkeypatch.setattr(
            users_routes,
            'get_in_progress_conversation',
            lambda uid: None,
        )

        with pytest.raises(HTTPException) as exc_info:
            users_routes.delete_person_endpoint(
                memory_id='0',
                uid='user-1',
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == 'No memory in progres'
