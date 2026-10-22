"""POST /v1/onboarding/seed-conversation: one static, completed "Get Started" row per uid.

The row is written fully formed through the completed-conversation lifecycle
helper (idempotent create), so no processing, notification, memory extraction or
other paid work runs; a repeat call returns the existing row without writing.
"""

import os
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import routers.conversations as conv  # noqa: E402
from models.conversation import Conversation  # noqa: E402


class _Store:
    """Minimal per-uid conversation store standing in for conversations_db + lifecycle."""

    def __init__(self):
        self.rows: dict = {}
        self.creates = 0

    def get(self, uid, conversation_id, **_kw):
        return self.rows.get((uid, conversation_id))

    def create_completed(self, uid, data, *, idempotent=False):
        assert idempotent is True
        assert data['status'] == 'completed'
        self.creates += 1
        key = (uid, data['id'])
        if key in self.rows:
            return False
        self.rows[key] = data
        return True


@pytest.fixture
def store(monkeypatch):
    store = _Store()
    monkeypatch.setattr(conv.conversations_db, 'get_conversation', store.get)
    monkeypatch.setattr(conv.lifecycle_service, 'create_completed_conversation', store.create_completed)
    return store


def _no_paid_work(monkeypatch):
    for name in ('process_conversation', 'trigger_external_integrations', '_enrich_deferred_conversation'):
        if hasattr(conv, name):

            def _forbidden(*_a, _name=name, **_k):
                raise AssertionError(f'{_name} must not run for the onboarding seed')

            monkeypatch.setattr(conv, name, _forbidden)


def test_creates_one_completed_row_with_no_transcript_or_audio(store, monkeypatch):
    _no_paid_work(monkeypatch)
    before = datetime.now(timezone.utc)

    result = conv.seed_onboarding_conversation(uid='u1')

    assert store.creates == 1
    assert result['id'] == conv.ONBOARDING_SEED_CONVERSATION_ID
    assert result['source'] == 'onboarding'
    assert result['status'] == 'completed'
    assert result['discarded'] is False and result['is_locked'] is False
    assert result['transcript_segments'] == [] and result['audio_files'] == []
    assert result.get('conversation_audio') is None
    assert result['created_at'] >= before
    structured = result['structured']
    assert structured['title'] == 'Get Started with Omi'
    assert structured['category'] == 'other'
    assert 3 <= structured['overview'].count('.') <= 4
    assert [item['description'] for item in structured['action_items']] == ['Try asking Omi a question']
    assert structured['action_items'][0]['completed'] is False
    # Same wire shape as a GET /v1/conversations list item.
    assert Conversation(**result).structured.title == 'Get Started with Omi'
    assert 'retention_locked' not in result


def test_repeat_calls_return_the_existing_row_without_writing(store):
    first = conv.seed_onboarding_conversation(uid='u1')
    second = conv.seed_onboarding_conversation(uid='u1')
    third = conv.seed_onboarding_conversation(uid='u1')
    assert store.creates == 1
    assert first['id'] == second['id'] == third['id']
    assert second['created_at'] == first['created_at']


def test_rows_are_per_uid(store):
    conv.seed_onboarding_conversation(uid='u1')
    conv.seed_onboarding_conversation(uid='u2')
    assert store.creates == 2
    assert {uid for uid, _ in store.rows} == {'u1', 'u2'}


def test_a_deleted_seed_stays_deleted(store):
    conv.seed_onboarding_conversation(uid='u1')
    store.rows[('u1', conv.ONBOARDING_SEED_CONVERSATION_ID)]['deleted'] = True
    with pytest.raises(HTTPException) as exc_info:
        conv.seed_onboarding_conversation(uid='u1')
    assert exc_info.value.status_code == 404
    assert store.creates == 1
