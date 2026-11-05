"""synceff 2026-11-05: enrichment stops a reprocess run once its conversation moved to a newer sync revision."""

import pytest

from utils.enrichment import callback
from utils.enrichment.admission import SyncConversationPersistenceFenced


@pytest.fixture
def reads(monkeypatch):
    monkeypatch.delenv('ENRICHMENT_EARLY_ABORT_ENABLED', raising=False)
    calls = []
    state = {'row': {'sync_content_revision': 3}, 'error': None}

    def snapshot(uid, conversation_id, *, field_paths=None, **_):
        calls.append((uid, conversation_id, tuple(field_paths or ())))
        if state['error'] is not None:
            raise state['error']
        return state['row']

    monkeypatch.setattr(callback.conversations_db, 'get_conversation_raw_snapshot', snapshot)
    return calls, state


def test_unchanged_revision_continues_with_a_masked_read(reads):
    calls, _ = reads
    check = callback._revision_checkpoint('u', {'id': 'c', 'sync_content_revision': 3})
    check('pre_notes')
    assert calls == [('u', 'c', ('sync_content_revision',))]


@pytest.mark.parametrize('row', [{'sync_content_revision': 4}, None, {}])
def test_moved_or_missing_revision_raises_the_persistence_fence(reads, row):
    _, state = reads
    state['row'] = row
    check = callback._revision_checkpoint('u', {'id': 'c', 'sync_content_revision': 3})
    with pytest.raises(SyncConversationPersistenceFenced, match='pre_persist'):
        check('pre_persist')


def test_failed_read_continues_the_run(reads):
    _, state = reads
    state['error'] = RuntimeError('synthetic outage')
    callback._revision_checkpoint('u', {'id': 'c', 'sync_content_revision': 3})('pre_notes')


@pytest.mark.parametrize(
    'data', [{'id': 'c'}, {'id': 'c', 'sync_content_revision': None}, {'sync_content_revision': 3}]
)
def test_rows_without_a_revision_or_id_are_never_checked(reads, data):
    calls, _ = reads
    assert callback._revision_checkpoint('u', data) is None
    assert calls == []


def test_kill_switch_off_disables_the_check(reads, monkeypatch):
    calls, _ = reads
    monkeypatch.setenv('ENRICHMENT_EARLY_ABORT_ENABLED', 'false')
    assert callback._revision_checkpoint('u', {'id': 'c', 'sync_content_revision': 3}) is None
    assert calls == []
