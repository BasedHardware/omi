"""#21968 regression: a lifecycle fence settles the enrichment claim as superseded instead of a retry.

Before C2 the fence escaped ``reprocess.run`` and the task handler answered 500, so Cloud Tasks retried a
delivery this worker could never win (backend-sync-backfill error group, 10-17).
"""

from unittest.mock import Mock

import pytest

from tests.unit.test_sync_reprocess_coalesce import state  # noqa: F401
from utils.batch_pipeline import enrichment
from utils.enrichment import callback
from utils.enrichment import outbox as reprocess


@pytest.fixture
def delivery(state, monkeypatch):  # noqa: F811
    monkeypatch.setattr(enrichment, 'discard_blocked', lambda _document_id: False)
    reprocess.mark('u', 'c', 'en', now=0)
    rows, tasks = state
    return rows, tasks, reprocess.key('u', 'c'), tasks[-1]['task_token']


def test_fenced_callback_retires_the_unchanged_obligation(delivery):
    rows, _tasks, key, token = delivery
    fenced = Mock(side_effect=callback.SyncConversationPersistenceFenced('synthetic fence'))
    assert enrichment.run_enrichment(key, token, now=10_000, process=fenced) == 'superseded'
    fenced.assert_called_once_with('u', 'c', 'en')
    assert key not in rows  # No newer mark: the winning writer owns the conversation.


def test_fenced_callback_rearms_when_a_newer_mark_landed(delivery):
    rows, tasks, key, token = delivery

    def fenced(uid, conversation_id, language):
        reprocess.mark(uid, conversation_id, language, now=9_000)  # the newer ingest
        raise callback.SyncConversationPersistenceFenced('synthetic fence')

    assert enrichment.run_enrichment(key, token, now=10_000, process=fenced) == 'superseded'
    assert rows[key]['lease_until'] == 0 and rows[key]['task_token'] != token
    assert tasks[-1]['task_token'] == rows[key]['task_token']


def test_other_callback_errors_keep_their_taxonomy(delivery):
    _rows, _tasks, key, token = delivery
    with pytest.raises(ValueError, match='synthetic'):
        enrichment.run_enrichment(key, token, now=10_000, process=Mock(side_effect=ValueError('synthetic')))


def test_default_callback_is_the_enrichment_package_not_legacy_pipeline(delivery, monkeypatch):
    _rows, _tasks, key, token = delivery
    leaf = Mock(return_value=None)
    monkeypatch.setattr(callback, 'enrich_conversation', leaf)
    assert enrichment.run_enrichment(key, token, now=10_000) == 'processed'
    leaf.assert_called_once_with('u', 'c', 'en')
