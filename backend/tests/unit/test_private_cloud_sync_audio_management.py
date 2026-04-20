from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from routers import sync


def _conversation(idx: int, *, audio_files=None, discarded=False):
    return {
        'id': f'conv-{idx}',
        'structured': {'title': f'Title {idx}'},
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=idx),
        'audio_files': audio_files or [],
        'discarded': discarded,
    }


def test_list_conversations_with_audio_iterates_all_batches(monkeypatch):
    conversations = [_conversation(1, audio_files=[])]
    conversations.extend(_conversation(i, audio_files=[{'duration': 1.5}, {'duration': 2.5}]) for i in range(2, 505))

    iter_mock = MagicMock(return_value=iter(conversations))
    monkeypatch.setattr(sync.conversations_db, 'iter_audio_metadata_conversations', iter_mock)

    result = sync.list_conversations_with_audio(uid='user-1')

    iter_mock.assert_called_once_with('user-1', include_discarded=False)
    assert len(result['conversations']) == 503
    assert result['conversations'][0]['id'] == 'conv-504'
    assert result['conversations'][0]['audio_file_count'] == 2
    assert result['conversations'][0]['total_duration'] == 4.0
    assert result['conversations'][-1]['id'] == 'conv-2'


def test_list_conversations_with_audio_skips_locked_conversations(monkeypatch):
    conversations = [
        _conversation(1, audio_files=[{'duration': 1.0}], discarded=False),
        {**_conversation(2, audio_files=[{'duration': 2.0}], discarded=False), 'is_locked': True},
    ]

    monkeypatch.setattr(
        sync.conversations_db, 'iter_audio_metadata_conversations', MagicMock(return_value=iter(conversations))
    )

    result = sync.list_conversations_with_audio(uid='user-1')

    assert [conversation['id'] for conversation in result['conversations']] == ['conv-1']


def test_delete_all_cloud_audio_clears_every_matching_conversation(monkeypatch):
    conversations = [_conversation(i, audio_files=[{'duration': 1.0}]) for i in range(1, 505)]
    conversations.append(_conversation(999, audio_files=[]))

    iter_mock = MagicMock(return_value=iter(conversations))
    update_mock = MagicMock()
    delete_mock = MagicMock(return_value={'deleted_blobs': 77, 'failed_blobs': 0})

    monkeypatch.setattr(sync.conversations_db, 'iter_audio_metadata_conversations', iter_mock)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', update_mock)
    monkeypatch.setattr(sync, 'delete_all_user_cloud_audio', delete_mock)

    result = sync.delete_all_cloud_audio(uid='user-1')

    delete_mock.assert_called_once_with('user-1')
    iter_mock.assert_called_once_with('user-1', include_discarded=True)
    assert update_mock.call_count == 504
    update_mock.assert_any_call('user-1', 'conv-1', {'audio_files': []})
    update_mock.assert_any_call('user-1', 'conv-504', {'audio_files': []})
    assert result == {'deleted_blobs': 77, 'cleared_conversations': 504}


def test_delete_all_cloud_audio_still_runs_blob_cleanup_when_metadata_clear_fails(monkeypatch):
    # Blob cleanup must run even when metadata clears fail — skipping it leaves
    # orphaned blobs after metadata is already gone (privacy + cost leak).
    conversations = [_conversation(1, audio_files=[{'duration': 1.0}])]
    iter_mock = MagicMock(return_value=iter(conversations))
    update_mock = MagicMock(side_effect=RuntimeError('firestore down'))
    delete_mock = MagicMock(return_value={'deleted_blobs': 0, 'failed_blobs': 0})

    monkeypatch.setattr(sync.conversations_db, 'iter_audio_metadata_conversations', iter_mock)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', update_mock)
    monkeypatch.setattr(sync, 'delete_all_user_cloud_audio', delete_mock)

    with pytest.raises(sync.HTTPException) as exc_info:
        sync.delete_all_cloud_audio(uid='user-1')

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail['failed_metadata_conversations'] == 1
    assert exc_info.value.detail['cleared_conversations'] == 0
    # Blob cleanup must have been attempted despite metadata failure
    delete_mock.assert_called_once_with('user-1')


def test_delete_all_cloud_audio_returns_error_when_blob_delete_partially_fails(monkeypatch):
    conversations = [_conversation(1, audio_files=[{'duration': 1.0}])]

    monkeypatch.setattr(
        sync.conversations_db,
        'iter_audio_metadata_conversations',
        MagicMock(return_value=iter(conversations)),
    )
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', MagicMock())
    monkeypatch.setattr(
        sync,
        'delete_all_user_cloud_audio',
        MagicMock(return_value={'deleted_blobs': 4, 'failed_blobs': 1}),
    )

    with pytest.raises(sync.HTTPException) as exc_info:
        sync.delete_all_cloud_audio(uid='user-1')

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        'message': 'Partial failure during cloud audio deletion.',
        'deleted_blobs': 4,
        'failed_blobs': 1,
        'cleared_conversations': 1,
        'failed_metadata_conversations': 0,
    }


def test_delete_all_cloud_audio_returns_error_combining_metadata_and_blob_failures(monkeypatch):
    # 2 conversations: first fails metadata clear, second succeeds.
    # Blob cleanup runs and also partially fails.
    # Response must include both failure counts.
    conversations = [
        _conversation(1, audio_files=[{'duration': 1.0}]),
        _conversation(2, audio_files=[{'duration': 2.0}]),
    ]

    def update_side_effect(uid, conv_id, patch):
        if conv_id == 'conv-1':
            raise RuntimeError('firestore timeout')

    monkeypatch.setattr(
        sync.conversations_db,
        'iter_audio_metadata_conversations',
        MagicMock(return_value=iter(conversations)),
    )
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', MagicMock(side_effect=update_side_effect))
    monkeypatch.setattr(
        sync,
        'delete_all_user_cloud_audio',
        MagicMock(return_value={'deleted_blobs': 3, 'failed_blobs': 2}),
    )

    with pytest.raises(sync.HTTPException) as exc_info:
        sync.delete_all_cloud_audio(uid='user-1')

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail['failed_metadata_conversations'] == 1
    assert detail['cleared_conversations'] == 1
    assert detail['failed_blobs'] == 2
    assert detail['deleted_blobs'] == 3
