"""A user-managed sync anchor is a terminal outcome at every request boundary.

The pipeline's per-segment loop already maps ``SyncAssignmentSuperseded`` to a
non-retryable success. These tests pin the request-facing boundaries that used
to re-raise it: post-persist reprocessing of a batch (siblings must survive) and
the size-limit backstop's retry leg (the guard is never retried as a rollover).
"""

import logging

import config.demand_processing
import config.sync_reprocess
from utils.sync import legacy_segment_core as pipeline, processing_hold
from utils.sync.assignment_errors import SyncAssignmentSuperseded


def _disable_coalescing(monkeypatch):
    # Force the eager per-conversation reprocess branch; the coalescing branch
    # only marks the outbox and never reaches an assignment.
    monkeypatch.setattr(processing_hold, 'scheduling_enabled', lambda: False)
    monkeypatch.setattr(config.sync_reprocess, 'coalesce_enabled', lambda: False)
    monkeypatch.setattr(config.demand_processing, 'enabled', lambda uid=None: False)


def test_superseded_reprocess_keeps_siblings_and_never_fails_the_batch(monkeypatch, caplog):
    _disable_coalescing(monkeypatch)
    calls = []

    def reprocess(uid, conversation_id, language, user_selected=False):
        calls.append(conversation_id)
        if conversation_id == 'managed':
            raise SyncAssignmentSuperseded('sync anchor is user managed')
        return None

    monkeypatch.setattr(pipeline, '_reprocess_conversation_after_update', reprocess)
    response = {
        '_merged': {'managed': 'en', 'sibling': 'en'},
        'new_memories': {'managed', 'sibling'},
        'updated_memories': set(),
    }

    with caplog.at_level(logging.DEBUG, logger=pipeline.__name__):
        pipeline._reprocess_merged_conversations('u', response)

    # The sibling is still reprocessed and neither conversation leaves the result.
    assert calls == ['managed', 'sibling']
    assert response['new_memories'] == {'managed', 'sibling'}
    assert '_merged' not in response
    assert 'event=sync_conversation_reprocess outcome=superseded' in caplog.text


def test_superseded_reprocess_is_not_reported_as_a_fenced_conversation(monkeypatch):
    _disable_coalescing(monkeypatch)
    monkeypatch.setattr(
        pipeline,
        '_reprocess_conversation_after_update',
        lambda *a, **kw: (_ for _ in ()).throw(SyncAssignmentSuperseded('sync anchor is user managed')),
    )
    response = {'_merged': {'managed': 'en'}, 'new_memories': {'managed'}, 'updated_memories': set()}

    # No raise: the pipeline published a completed job for speech that did land.
    pipeline._reprocess_merged_conversations('u', response)
    assert response['new_memories'] == {'managed'}
    assert not response.get(pipeline._RESPONSE_FENCED_CONVERSATION_IDS)
