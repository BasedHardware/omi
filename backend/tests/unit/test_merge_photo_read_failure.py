import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from datetime import datetime, timedelta, timezone
import utils.conversations.merge_conversations as merge
import utils.notifications as notifications

_NOW = datetime.now(timezone.utc)
_SOURCES = [
    {
        'id': 'conv_a',
        'created_at': _NOW - timedelta(minutes=2),
        'started_at': _NOW - timedelta(minutes=2),
        'finished_at': _NOW - timedelta(minutes=1),
        'language': 'en',
        'source': 'omi',
        'transcript_segments': [],
    },
    {
        'id': 'conv_b',
        'created_at': _NOW - timedelta(minutes=1),
        'started_at': _NOW - timedelta(minutes=1),
        'finished_at': _NOW,
        'language': 'en',
        'source': 'omi',
        'transcript_segments': [],
    },
]


def _install(monkeypatch, photos_by_conv, written, deleted, failed):
    monkeypatch.setattr(
        merge.conversations_db, 'get_conversation', lambda _uid, cid: next(c for c in _SOURCES if c['id'] == cid)
    )

    def _photos(_uid, cid):
        value = photos_by_conv.get(cid, [])
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(merge.conversations_db, 'get_conversation_photos', _photos)
    monkeypatch.setattr(
        merge.conversations_db, 'store_conversation_photos', lambda _uid, cid, photos: written.append((cid, photos))
    )
    monkeypatch.setattr(merge, '_copy_audio_chunks_for_merge', lambda *_a, **_k: [])
    monkeypatch.setattr(merge, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(merge, 'canonical_intake_is_fenced', lambda: False)
    monkeypatch.setattr(merge.lifecycle_service, 'create_processing_conversation', lambda *_a, **_k: None)
    monkeypatch.setattr(merge.lifecycle_service, 'complete', lambda *_a, **_k: None)
    monkeypatch.setattr(merge, '_cleanup_merged_target_after_failure', lambda *_a, **_k: True)
    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', lambda _uid, cid, **_k: deleted.append(cid))
    monkeypatch.setattr(merge, '_handle_merge_failure', lambda _uid, ids, **_k: failed.append(list(ids)))
    monkeypatch.setattr(notifications, 'send_merge_completed_message', lambda *_a, **_k: None)


def test_photo_read_failure_keeps_the_sources(monkeypatch):
    written, deleted, failed = [], [], []
    _install(monkeypatch, {'conv_a': RuntimeError('firestore unavailable'), 'conv_b': []}, written, deleted, failed)

    merge.perform_merge_async('u1', ['conv_a', 'conv_b'], reprocess=False)

    assert written == []
    assert deleted == []
    assert failed == [['conv_a', 'conv_b']]
