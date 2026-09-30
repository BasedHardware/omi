"""Live writes fence processors that read a lineage-bound transcript earlier."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from database import conversations as db
from tests.unit.test_manual_speaker_assignments import world, read


@pytest.mark.parametrize('flag', ['', 'off'])
def test_live_speech_after_sync_fences_an_older_processor(world, monkeypatch, flag):
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', flag)
    store, path, segments = world
    store.rows[path].update(sync_live_target=True, sync_content_revision=1, data_protection_level='standard')
    stale = deepcopy(store.rows[path])
    fresh = dict(segments[0], id='fresh', text='A distinct later synthetic sentence.', start=10, end=12)
    db.update_conversation_segments('u', 'c', [], live_segments=[fresh])
    expected_revision = 2 if flag == '' else 1
    assert store.rows[path]['sync_content_revision'] == expected_revision
    assert any(s['id'] == 'fresh' for s in read(world)['transcript_segments'])
    db.update_conversation_segments('u', 'c', [], live_segments=[fresh])
    assert store.rows[path]['sync_content_revision'] == expected_revision  # retry did not change speech
    if flag == 'off':
        return  # OFF keeps the previous live-write behavior.
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(db, '_sync_conversation_search_index', MagicMock())
    stale['status'] = 'completed'
    assert not db.persist_processing_result_with_lifecycle('u', stale)
    assert any(s['id'] == 'fresh' for s in read(world)['transcript_segments'])
