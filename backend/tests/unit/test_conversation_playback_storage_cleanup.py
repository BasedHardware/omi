"""Deletion scopes for generated conversation playback artifacts."""

from __future__ import annotations

import pytest

from utils.other import conversation_playback_storage, storage


def test_delete_conversation_playback_artifacts_uses_exact_trailing_slash_prefix(monkeypatch):
    deleted_prefixes = []
    monkeypatch.setattr(
        conversation_playback_storage,
        'delete_private_cloud_sync_prefix',
        deleted_prefixes.append,
    )

    conversation_playback_storage.delete_conversation_playback_artifacts('uid-1', 'conversation-1')

    assert deleted_prefixes == ['playback/uid-1/conversation-1/']


def test_delete_all_conversation_playback_artifacts_uses_exact_account_prefix(monkeypatch):
    deleted_prefixes = []
    monkeypatch.setattr(
        conversation_playback_storage,
        'delete_private_cloud_sync_prefix',
        deleted_prefixes.append,
    )

    conversation_playback_storage.delete_all_conversation_playback_artifacts('uid-1')

    assert deleted_prefixes == ['playback/uid-1/']


def test_private_cloud_sync_prefix_delete_deletes_every_matching_blob(monkeypatch):
    deleted = []

    class Blob:
        def __init__(self, name):
            self.name = name

        def delete(self):
            deleted.append(self.name)

    class Bucket:
        def list_blobs(self, *, prefix):
            assert prefix == 'playback/uid-1/'
            return [Blob('first'), Blob('second')]

    class Client:
        def bucket(self, name):
            assert name == storage.private_cloud_sync_bucket
            return Bucket()

    monkeypatch.setattr(storage, '_get_storage_client', lambda: Client())

    storage.delete_private_cloud_sync_prefix('playback/uid-1/')

    assert deleted == ['first', 'second']


@pytest.mark.parametrize('prefix', ('', '/', '/playback/uid-1/', 'playback/'))
def test_private_cloud_sync_prefix_delete_rejects_broad_prefixes(prefix):
    with pytest.raises(ValueError, match='scoped directory'):
        storage.delete_private_cloud_sync_prefix(prefix)


@pytest.mark.parametrize(
    ('uid', 'conversation_id'),
    (
        ('', 'conversation-1'),
        ('uid/other', 'conversation-1'),
        ('uid-1', ''),
        ('uid-1', 'conversation/other'),
    ),
)
def test_delete_conversation_playback_artifacts_rejects_unsafe_components(uid, conversation_id):
    with pytest.raises(ValueError, match='invalid conversation playback'):
        conversation_playback_storage.delete_conversation_playback_artifacts(uid, conversation_id)
