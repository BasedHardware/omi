"""/reprocess of a discarded batch row: visibility waits for the restore obligation.

The real router, real processor and real restore run against the strict store. Only
the external model and app boundaries are controlled.
"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException, Response

import routers.conversations as conv_router
from database import apps as apps_db
from database import notifications as notification_db
from database import conversations as conversations_db
from database import dream_dirty
from database import processing_attention as attention_db
from models.structured import Structured
from tests.unit.test_restore_recording_obligation import CID, JOB_PATH, ROW_PATH, UID, restore_store  # noqa: F401
from utils import apps as utils_apps
from utils.batch_pipeline import live
from utils.conversations import process_conversation as processor

APP_ID = 'summary-app'


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
    # The selected app is validated against the app store and the user's enablement; the
    # app model call returns the summary. The processor's real explicit-selection check runs on it.
    app = SimpleNamespace(id=APP_ID, disabled=False, enabled=True, works_with_memories=lambda: True)
    monkeypatch.setattr(apps_db, 'get_app_by_id_db', lambda app_id: {'id': app_id})
    monkeypatch.setattr(utils_apps, 'get_available_app_model_by_id', lambda *a, **k: app)
    monkeypatch.setattr(utils_apps, 'is_user_app_enabled', lambda *a, **k: True)
    monkeypatch.setattr(processor, 'get_available_apps', lambda uid: [app])
    # The app prompt reads the user's timezone from Firestore; without it the app call fails
    # before the model boundary, which would look like an empty summary.
    monkeypatch.setattr(notification_db, 'get_user_time_zone', lambda uid: '')
    monkeypatch.setattr(processor, 'get_app_result', lambda *a, **k: 'Synthetic app summary.')
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
        conversation_id=CID, app_id=APP_ID, uid=UID, response=Response(), background_tasks=BackgroundTasks()
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
    # The selected app returns no summary: the processor's explicit-selection branch raises.
    monkeypatch.setattr(processor, 'get_app_result', lambda *a, **k: '')

    with pytest.raises(HTTPException) as error:
        _call()

    # The HTTP error is chained to the processor's explicit-selection failure, not a generic one.
    assert isinstance(error.value.__cause__, processor.ExplicitAppSelectionFailedError)
    assert registrations == []
    assert reprocess.rows[ROW_PATH]['discarded'] is True
    assert JOB_PATH not in reprocess.rows
