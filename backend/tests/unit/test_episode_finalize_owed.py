"""An unchanged processing pass still owes the first finalize for every attach stamp."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import pytest

from database import episode_attach_memo
from tests.unit.test_episode_attach_cost import seed
from tests.unit.test_episode_live_integrity import lane, T0  # noqa: F401
from utils.conversations.episode_attach_key import should_schedule
from utils.episodes import finalize, service


@pytest.mark.parametrize('pending', [False, True])
@pytest.mark.parametrize('prior_finalize', [False, True])
def test_intake_completed_but_finalize_owed_schedules_even_without_processing_changes(
    lane, monkeypatch, pending, prior_finalize
):
    store, c, _ = lane
    fields = {'sync_content_revision': 7}
    if pending:
        fields.update(episode_transcription_pending_at=T0, episode_transcription_deadline_at=T0 + timedelta(minutes=5))
    service._attach_synced('u', 'same', seed(store, **fields), c)
    fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    if prior_finalize:
        episode_attach_memo.complete('u', 'same', fresh, None, finalized=True, firestore_client=store)
        fresh['sync_content_revision'] += 1
        fresh['recorded_end'] += timedelta(seconds=10)
        store.rows[('users', 'u', 'conversations', 'same')] = deepcopy(fresh)
        # Intake for the next append invalidates the prior finalized stamp.
        service._attach_synced('u', 'same', fresh, c)
        fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    link = store.rows[('users', 'u', 'episode_links', 'same')]
    assert link['attach_completed'] == link['attach_revision']
    assert link.get('attach_finalized') is None
    assert not should_schedule(fresh, deepcopy(fresh))
    monkeypatch.setattr(episode_attach_memo, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(finalize, 'episodes_enabled_for', lambda _: True)
    monkeypatch.setattr(finalize, 'lifecycle_executor', lambda *a, **kw: object())
    submit = Mock()
    monkeypatch.setattr(finalize, 'submit_with_context', submit)
    assert finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=fresh)
    assert submit.call_count == 1
    episode_attach_memo.complete('u', 'same', fresh, None, finalized=True, firestore_client=store)
    assert not finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=fresh)
    assert submit.call_count == 1
