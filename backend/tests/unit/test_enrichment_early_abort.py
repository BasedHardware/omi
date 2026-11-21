"""synceff 2026-11-05: enrichment stops a reprocess run once its conversation moved to a newer sync revision."""

from types import SimpleNamespace

import pytest

from database import conversations as conversations_db
from utils.enrichment import early_abort
from utils.enrichment.admission import SyncConversationPersistenceFenced

CONVERSATION = SimpleNamespace(id='c', sync_content_revision=3)


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

    monkeypatch.setattr(conversations_db, 'get_conversation_raw_snapshot', snapshot)
    token = early_abort.ACTIVE.set(True)
    yield calls, state
    early_abort.ACTIVE.reset(token)


def test_unchanged_revision_continues_with_one_masked_read(reads):
    calls, _ = reads
    early_abort.checkpoint_for('u', CONVERSATION)('pre_notes')
    assert calls == [('u', 'c', ('sync_content_revision', 'deleted', 'sync_merged_into'))]


def test_moved_revision_on_a_live_row_raises_the_persistence_fence(reads):
    _, state = reads
    state['row'] = {'sync_content_revision': 4}
    with pytest.raises(SyncConversationPersistenceFenced, match='pre_persist'):
        early_abort.checkpoint_for('u', CONVERSATION)('pre_persist')


@pytest.mark.parametrize(
    'row',
    [
        None,
        {},
        {'sync_content_revision': 4, 'deleted': True},
        {'sync_content_revision': 4, 'deleted': True, 'sync_merged_into': 'survivor'},
        {'sync_content_revision': 4, 'sync_merged_into': 'survivor'},
    ],
)
def test_missing_deleted_or_redirected_rows_keep_todays_path(reads, row):
    # A concurrent merge must reach before_notes' redirect handling, which transfers the outbox obligation.
    _, state = reads
    state['row'] = row
    early_abort.checkpoint_for('u', CONVERSATION)('pre_notes')


def test_failed_read_continues_the_run(reads):
    _, state = reads
    state['error'] = RuntimeError('synthetic outage')
    early_abort.checkpoint_for('u', CONVERSATION)('pre_notes')


@pytest.mark.parametrize(
    'conversation',
    [SimpleNamespace(id='c', sync_content_revision=None), SimpleNamespace(id=None, sync_content_revision=3)],
)
def test_conversations_without_a_revision_or_id_are_never_checked(reads, conversation):
    calls, _ = reads
    assert early_abort.checkpoint_for('u', conversation) is None
    assert calls == []


def test_kill_switch_off_disables_the_check(reads, monkeypatch):
    calls, _ = reads
    monkeypatch.setenv('ENRICHMENT_EARLY_ABORT_ENABLED', 'false')
    assert early_abort.checkpoint_for('u', CONVERSATION) is None
    assert calls == []


def test_outside_an_enrichment_delivery_nothing_is_checked(reads):
    calls, _ = reads
    token = early_abort.ACTIVE.set(False)
    try:
        assert early_abort.checkpoint_for('u', CONVERSATION) is None
    finally:
        early_abort.ACTIVE.reset(token)
    assert calls == []
