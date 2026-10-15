"""Visibility observers follow successful terminal commits, never retry attempts."""

from datetime import datetime, timedelta, timezone
from functools import partial
from unittest.mock import MagicMock

import pytest

from database import conversation_finalization_jobs as jobs
from database import conversation_terminal_effects as effects
from database import oversized_conversation_terminal as oversized


@pytest.mark.parametrize('path', ['dead_letter', 'orphan', 'unstampable', 'byok', 'oversized'])
@pytest.mark.parametrize('commits', [True, False])
def test_real_terminal_entrypoints_refresh_only_after_success(monkeypatch, path, commits):
    client = MagicMock()
    now = datetime.now(timezone.utc)
    calls = []
    state = {'committed': False}

    def invalidated(uid):
        assert state['committed']
        calls.append(('cache', uid))

    monkeypatch.setattr(effects.conversations_db, 'invalidate_people_stats_cache', invalidated)
    monkeypatch.setattr(
        effects.conversations_db, '_sync_conversation_search_index', lambda uid, cid: calls.append(('index', uid, cid))
    )

    def run_transaction(*_args, **_kwargs):
        effects.stage_terminal_visibility_refresh('u', 'c')
        effects.stage_terminal_visibility_refresh('u', 'c')
        assert calls == []
        if not commits:
            raise RuntimeError('commit failed')
        state['committed'] = True
        return True

    monkeypatch.setattr(jobs.firestore, 'transactional', lambda _fn: run_transaction)
    operations = {
        'dead_letter': partial(jobs.mark_finalization_dead_letter, 'j', 1, 1, 5),
        'orphan': partial(jobs.complete_orphan_conversation, 'u', 'c', expected_admitted_at=now),
        'unstampable': partial(jobs.complete_unstampable_orphan_conversation, 'u', 'c', stale_after=timedelta(days=1)),
        'byok': partial(
            jobs.abandon_byok_finalization_job,
            'j',
            expected_status='queued',
            expected_dispatch_generation=1,
            expected_lease_epoch=0,
            abandoned_after=timedelta(days=14),
        ),
        'oversized': partial(
            oversized.complete_oversized_in_progress_conversation, 'u', 'c', quiet_for=timedelta(days=1)
        ),
    }
    if commits:
        assert operations[path](firestore_client=client) is True
        assert calls == [('cache', 'u'), ('index', 'u', 'c')]
    else:
        with pytest.raises(RuntimeError, match='commit failed'):
            operations[path](firestore_client=client)
        assert calls == []
    assert effects._pending.get() is None


def test_observer_failure_does_not_retry_committed_state(monkeypatch):
    def unavailable(*_args):
        raise RuntimeError('cache unavailable')

    monkeypatch.setattr(effects.conversations_db, 'invalidate_people_stats_cache', unavailable)
    index = MagicMock()
    monkeypatch.setattr(effects.conversations_db, '_sync_conversation_search_index', index)

    @effects.refresh_terminal_visibility_after_commit
    def committed():
        effects.stage_terminal_visibility_refresh('u', 'c')
        return 'stored'

    assert committed() == 'stored'
    index.assert_called_once_with('u', 'c')


@pytest.mark.parametrize('text,discarded', [('Huh?', True), ('Remind me to call mom', False)])
def test_real_rule_calculation_stages_visibility_observers(monkeypatch, text, discarded):
    from types import SimpleNamespace
    from database import conversation_terminal_title as terminal

    events = []
    state = {'committed': False}
    monkeypatch.setattr(terminal, 'calendar_retains', lambda *_: False)
    monkeypatch.setattr(terminal, '_has_described_photo', lambda *_, **__: False)

    def invalidated(uid):
        assert state['committed']
        events.append(('cache', uid))

    monkeypatch.setattr(effects.conversations_db, 'invalidate_people_stats_cache', invalidated)
    monkeypatch.setattr(
        effects.conversations_db, '_sync_conversation_search_index', lambda uid, cid: events.append(('index', uid, cid))
    )

    @effects.refresh_terminal_visibility_after_commit
    def committed():
        patch = terminal.with_terminal_relevance(
            'u',
            {'source': 'omi', 'discarded': False},
            {'status': 'completed'},
            [text],
            True,
            'dead_letter',
            SimpleNamespace(id='c'),
            object(),
        )
        assert events == []
        state['committed'] = True
        return patch

    patch = committed()
    assert patch['discarded'] is discarded
    assert events == ([('cache', 'u'), ('index', 'u', 'c')] if discarded else [])


def test_document_ceiling_failure_refreshes_visibility_after_commit(monkeypatch):
    from database import conversation_terminal_title as terminal
    from tests.unit.test_dead_letter_visible_row_title import (
        _conversation,
        _dead_letter,
        _reference_document_size,
        _segments,
    )

    items = [{'description': f'task {i}', 'completed': False} for i in range(128)]
    probe = _conversation(
        {'structured': {'title': '', 'overview': '', 'action_items': items}, 'transcript_segments': _segments('Hi.')}
    )
    size = _reference_document_size(probe.data, probe.path)
    row = _conversation(
        {
            'structured': probe.data['structured'],
            'transcript_segments': _segments('Hi. ' + 'x' * (terminal.FIRESTORE_MAX_DOCUMENT_BYTES - size - 32)),
        }
    )
    events = []
    monkeypatch.setattr(
        effects.conversations_db, 'invalidate_people_stats_cache', lambda uid: events.append(('cache', uid))
    )
    monkeypatch.setattr(
        effects.conversations_db, '_sync_conversation_search_index', lambda uid, cid: events.append(('index', uid, cid))
    )

    @effects.refresh_terminal_visibility_after_commit
    def committed():
        patch = _dead_letter(row)
        assert events == []
        assert patch['status'] == 'failed'
        return patch

    assert committed()['status'] == 'failed'
    assert events == [('cache', 'uid-1'), ('index', 'uid-1', 'conversation-1')]
