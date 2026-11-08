"""/reprocess of a discarded batch row: visibility waits for the restore obligation.

The real router, real processor and real restore run against the strict store. Only
the external model and app boundaries are controlled.
"""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException, Response

import routers.conversations as conv_router
from database import conversations as conversations_db
from database import dream_dirty
from database import processing_attention as attention_db
from models.structured import Structured
from tests.unit.test_restore_recording_obligation import CID, JOB_PATH, ROW_PATH, UID, restore_store  # noqa: F401
from utils.batch_pipeline import live
from utils.conversations import process_conversation as processor
from utils.conversations.process_conversation import ExplicitAppSelectionFailedError


@pytest.fixture
def reprocess(restore_store, monkeypatch):
    row = restore_store.rows[ROW_PATH]
    row.update(
        {
            'status': 'completed',
            'source': 'omi',
            'language': 'en',
            'created_at': row.get('created_at', '2026-11-01T00:00:00+00:00'),
            'started_at': '2026-11-01T00:00:00+00:00',
            'finished_at': '2026-11-01T00:10:00+00:00',
            'structured': {},
            'transcript_segments': [],
            'photos': [],
        }
    )
    monkeypatch.setattr(
        conv_router, '_get_valid_conversation_by_id', lambda uid, cid: deepcopy(restore_store.rows[ROW_PATH])
    )
    monkeypatch.setattr(conv_router, 'schedule_reprocessed_learning', lambda uid, processed, *a, **k: processed)
    monkeypatch.setattr(
        processor,
        '_get_structured',
        lambda *a, **k: (Structured(title='Synthetic title', overview='Synthetic overview'), False),
    )
    monkeypatch.setattr(processor, 'extract_memories', MagicMock(), raising=False)
    monkeypatch.setattr(processor, 'save_structured_vector', MagicMock(), raising=False)
    monkeypatch.setattr(processor, 'trigger_conversation_apps', lambda *a, **k: None)
    # Dream dirty marking is out of scope; its marker needs a document update StrictFirestore omits.
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'off')
    # The app-output write goes through update(), which StrictFirestore omits; merge into the row instead.
    monkeypatch.setattr(
        conversations_db,
        'update_conversation',
        lambda uid, cid, data, **kwargs: restore_store.rows[ROW_PATH].update(deepcopy(data)) or True,
    )
    monkeypatch.setattr(attention_db, 'claim', lambda *a, **k: ({'id': 'operation'}, True))
    monkeypatch.setattr(attention_db, 'owns_live_claim', lambda uid, operation: True)
    monkeypatch.setattr(attention_db, 'finish', lambda *a, **k: None)
    return restore_store


def _call():
    return conv_router.reprocess_conversation(
        conversation_id=CID, uid=UID, response=Response(), background_tasks=BackgroundTasks()
    )


def _count_restore_registrations(monkeypatch):
    registrations = []
    original = live.register_recording

    def counting(uid, conversation, **kwargs):
        registrations.append(kwargs.get('restoring'))
        return original(uid, conversation, **kwargs)

    monkeypatch.setattr(live, 'register_recording', counting)
    return registrations


def test_successful_reprocess_restores_with_exactly_one_obligation(reprocess, monkeypatch):
    registrations = _count_restore_registrations(monkeypatch)

    processed = _call()

    assert registrations == [True]
    assert reprocess.rows[ROW_PATH]['discarded'] is False
    assert processed.discarded is False
    assert reprocess.rows[JOB_PATH]['state'] == 'record_pending'


def test_failed_selected_app_leaves_the_row_hidden_without_visibility(reprocess, monkeypatch):
    registrations = _count_restore_registrations(monkeypatch)

    def failing_app(*a, **k):
        raise ExplicitAppSelectionFailedError('synthetic selected app failure')

    monkeypatch.setattr(processor, 'trigger_conversation_apps', failing_app)
    with pytest.raises(HTTPException):
        _call()

    assert registrations == []
    assert reprocess.rows[ROW_PATH]['discarded'] is True
    assert JOB_PATH not in reprocess.rows
