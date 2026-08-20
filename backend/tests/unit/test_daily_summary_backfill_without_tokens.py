"""Web recap backfill must persist even when the account has no push tokens."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import database.conversations as conversations_db
import database.daily_summaries as daily_summaries_db
import database.notifications as notification_db
from routers.users import test_daily_summary


def _conversation():
    return {
        'id': 'conv-2',
        'is_locked': False,
        'structured': {
            'title': 'Test Conversation',
            'overview': 'Test overview',
            'action_items': [{'description': 'do something'}],
            'events': [{'title': 'event1', 'start': '2024-01-01T12:00:00'}],
            'category': 'personal',
        },
        'transcript_segments': [{'text': 'hello', 'speaker_id': 0, 'is_user': False, 'start': 0.0, 'end': 1.0}],
        'apps_results': [],
        'plugins_results': [],
        'suggested_summarization_apps': [],
        'audio_files': [
            {
                'id': 'af-1',
                'uid': 'test-uid',
                'conversation_id': 'conv-2',
                'chunk_timestamps': [1.0],
                'duration': 60.0,
            }
        ],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
        'visibility': 'private',
        'geolocation': None,
        'language': 'en',
        'status': 'completed',
        'source': 'friend',
    }


def test_daily_summary_backfill_without_push_tokens_still_persists():
    conversations_db.get_conversations = MagicMock(return_value=[_conversation()])
    notification_db.get_user_time_zone = MagicMock(return_value=None)
    notification_db.get_all_tokens = MagicMock(return_value=[])
    daily_summaries_db.create_daily_summary = MagicMock(return_value='summary-1')

    mock_gen = MagicMock(return_value={'headline': 'Test', 'overview': 'Overview'})
    with patch('routers.users.enforce_chat_quota'):
        with patch('routers.users.generate_comprehensive_daily_summary', mock_gen):
            with patch('routers.users.send_notification') as notify:
                result = test_daily_summary(uid='test-uid')

    notify.assert_not_called()
    assert result['summary_id'] == 'summary-1'
    assert result['status'] == 'ok'
