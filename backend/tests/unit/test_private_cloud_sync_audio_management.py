from datetime import datetime, timezone
from unittest.mock import MagicMock

from routers import sync


def _conversation(idx: int, *, audio_files=None, discarded=False):
    return {
        'id': f'conv-{idx}',
        'structured': {'title': f'Title {idx}'},
        'created_at': datetime(2026, 1, min(idx, 28), tzinfo=timezone.utc),
        'audio_files': audio_files or [],
        'discarded': discarded,
    }


def test_list_conversations_with_audio_iterates_all_batches(monkeypatch):
    conversations = [_conversation(1, audio_files=[])]
    conversations.extend(_conversation(i, audio_files=[{'duration': 1.5}, {'duration': 2.5}]) for i in range(2, 505))

    iter_mock = MagicMock(return_value=iter(conversations))
    monkeypatch.setattr(sync.conversations_db, 'iter_all_conversations', iter_mock)

    result = sync.list_conversations_with_audio(uid='user-1')

    iter_mock.assert_called_once_with('user-1', include_discarded=False)
    assert len(result['conversations']) == 503
    assert result['conversations'][0]['id'] == 'conv-504'
    assert result['conversations'][0]['audio_file_count'] == 2
    assert result['conversations'][0]['total_duration'] == 4.0
    assert result['conversations'][-1]['id'] == 'conv-2'


def test_delete_all_cloud_audio_clears_every_matching_conversation(monkeypatch):
    conversations = [_conversation(i, audio_files=[{'duration': 1.0}]) for i in range(1, 505)]
    conversations.append(_conversation(999, audio_files=[]))

    iter_mock = MagicMock(return_value=iter(conversations))
    update_mock = MagicMock()
    delete_mock = MagicMock(return_value=77)

    monkeypatch.setattr(sync.conversations_db, 'iter_all_conversations', iter_mock)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', update_mock)
    monkeypatch.setattr(sync, 'delete_all_user_cloud_audio', delete_mock)

    result = sync.delete_all_cloud_audio(uid='user-1')

    delete_mock.assert_called_once_with('user-1')
    iter_mock.assert_called_once_with('user-1', include_discarded=True)
    assert update_mock.call_count == 504
    update_mock.assert_any_call('user-1', 'conv-1', {'audio_files': []})
    update_mock.assert_any_call('user-1', 'conv-504', {'audio_files': []})
    assert result == {'deleted_blobs': 77, 'cleared_conversations': 504}
