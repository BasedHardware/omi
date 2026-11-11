"""Withheld conversation rows are counted without becoming model-facing evidence."""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.notifications as notifications_db
import utils.retrieval.tool_services.conversations as conversations_service


def test_get_reports_locked_conversations_without_rendering_content(monkeypatch):
    monkeypatch.setattr(notifications_db, 'get_user_time_zone', lambda _uid: 'Asia/Ho_Chi_Minh')
    calls = []

    def get_conversations(*_args, **kwargs):
        calls.append(kwargs)
        return [
            {
                'id': 'locked-1',
                'is_locked': True,
                'structured': {'title': 'private locked title'},
                'transcript_segments': [{'text': 'private locked transcript'}],
            },
        ]

    monkeypatch.setattr(conversations_service.conversations_db, 'get_conversations', get_conversations)

    result = conversations_service.get_conversations_text(uid='test-uid')

    # Discarded rows are filtered before limit/offset so they cannot shrink the visible page.
    assert calls[0]['include_discarded'] is False
    assert 'No conversations found in the requested scope' in result
    assert '1 conversations exist here but were not read: locked on the current plan' in result
    assert 'private locked' not in result


def test_search_reports_discarded_hits_without_rendering_content(monkeypatch):
    monkeypatch.setattr(notifications_db, 'get_user_time_zone', lambda _uid: 'Asia/Ho_Chi_Minh')
    monkeypatch.setattr(conversations_service, 'keyword_search_conversation_ids', lambda **_kwargs: ['discarded-1'])
    monkeypatch.setattr(conversations_service.vector_db, 'index', None, raising=False)
    monkeypatch.setattr(conversations_service.vector_db, 'query_vectors', lambda **_kwargs: ['discarded-1'])
    monkeypatch.setattr(conversations_service, 'merge_chat_conversation_ids', lambda *_args: ['discarded-1'])
    monkeypatch.setattr(conversations_service, 'conversation_matches_date_range', lambda *_args: True)
    monkeypatch.setattr(
        conversations_service.conversations_db,
        'get_conversations_by_id',
        lambda *_args, **_kwargs: [
            {
                'id': 'discarded-1',
                'discarded': True,
                'structured': {'title': 'private discarded title'},
                'transcript_segments': [{'text': 'private discarded transcript'}],
            }
        ],
    )

    result = conversations_service.search_conversations_text(uid='test-uid', query='planning')

    assert 'No conversations found matching query' in result
    assert '1 conversations exist here but were not read: discarded' in result
    assert 'private discarded' not in result
