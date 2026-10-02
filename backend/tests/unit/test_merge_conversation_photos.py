import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from datetime import datetime, timedelta, timezone

import database.conversations as conversations_db
import utils.conversations.merge_conversations as merge
import utils.conversations.process_conversation  # noqa: F401
import utils.notifications as notifications
from tests.unit.test_conversation_revision_contract import _Firestore, _PhotoConversationRef, _Snapshot
from tests.unit.test_merge_audio_chunk_copy_failure import _FakeBucket, _install


def test_merge_stores_photos_from_the_source_conversations(monkeypatch):
    now = datetime.now(timezone.utc)
    sources = [
        {
            'id': conv_id,
            'created_at': now - timedelta(minutes=offset),
            'started_at': now - timedelta(minutes=offset),
            'finished_at': now - timedelta(minutes=offset - 1),
            'language': 'en',
            'source': 'openglass',
            'transcript_segments': [],
        }
        for conv_id, offset in (('conv_a', 3), ('conv_b', 2))
    ]
    photo = {
        'id': 'photo-1',
        'base64': 'encoded',
        'description': 'a whiteboard',
        'created_at': now - timedelta(minutes=3),
        'data_protection_level': 'standard',
    }
    monkeypatch.setattr(
        merge.conversations_db,
        'get_conversation',
        lambda _uid, conv_id: next(c for c in sources if c['id'] == conv_id),
    )
    _install(monkeypatch, chunks_by_conv={}, bucket=_FakeBucket())
    monkeypatch.setattr(merge, '_collect_all_photos', lambda *_a, **_k: [dict(photo)])
    monkeypatch.setattr(merge, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(merge.lifecycle_service, 'create_processing_conversation', lambda *_a, **_k: None)
    monkeypatch.setattr(merge.lifecycle_service, 'complete', lambda *_a, **_k: None)
    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', lambda *_a, **_k: None)

    failures = []
    monkeypatch.setattr(merge, '_handle_merge_failure', lambda *args, **_k: failures.append(args))
    completed = []
    monkeypatch.setattr(notifications, 'send_merge_completed_message', lambda *args, **_k: completed.append(args))

    ref = _PhotoConversationRef(_Snapshot({'data_protection_level': 'standard'}))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    real_store = conversations_db.store_conversation_photos
    monkeypatch.setattr(
        merge.conversations_db,
        'store_conversation_photos',
        lambda uid, conversation_id, photos: real_store(uid, conversation_id, photos, firestore_client=_Firestore(ref)),
    )

    merge.perform_merge_async('user-1', ['conv_a', 'conv_b'], reprocess=False)

    assert failures == []
    assert len(completed) == 1
    stored = ref.photos.refs['photo-1'].set_calls[0][0]
    assert stored['id'] == 'photo-1'
    assert stored['base64'] == 'encoded'
    assert stored['description'] == 'a whiteboard'
