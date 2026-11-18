"""Historical-tier (T1+) ingest: both producers stamp old backfill and settle it without enrichment."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from config import historical_tier
from tests.unit.test_conversation_smart_merge import World
from tests.unit.test_phone_batch_process_now import pipeline as merged_pipeline  # noqa: F401  (fixture)
from tests.unit.test_sync_capture_pipeline import pipeline  # noqa: F401  (fixture)
from tests.unit.test_sync_cross_job_assignment import conversations
from utils.conversations import historical_ingest, summary_delivery
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.enrichment import callback
from utils.sync import processing_hold as hold
from utils.sync.intake_completion import HISTORICAL_RESPONSE_KEY

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _tier_on(monkeypatch):
    monkeypatch.delenv(historical_tier.TIER_ENABLED_ENV, raising=False)
    monkeypatch.delenv(historical_tier.MIN_AGE_ENV, raising=False)


def test_lane_boundary_is_strictly_older_than_72_hours_on_a_trusted_clock(monkeypatch):
    exactly = NOW - timedelta(hours=72)
    assert not historical_ingest.applies_at_create(exactly, trusted=True, now=NOW)
    assert historical_ingest.applies_at_create(exactly - timedelta(seconds=1), trusted=True, now=NOW)
    assert not historical_ingest.applies_at_create(exactly - timedelta(days=9), trusted=False, now=NOW)
    monkeypatch.setenv(historical_tier.TIER_ENABLED_ENV, 'false')
    assert not historical_ingest.applies_at_create(exactly - timedelta(days=9), trusted=True, now=NOW)


def _segment(module, store, age_hours, **kwargs):
    stamp = int(time.time() - age_hours * 3600)
    response = {'new_memories': set(), 'updated_memories': set()}
    errors = []
    assert module.process_segment(f'{stamp}.wav', 'u', response, threading.Lock(), errors, **kwargs)
    assert errors == []
    return conversations(store)[-1], response


def test_sync_old_backfill_is_created_historical_with_a_final_title(pipeline):
    module, store = pipeline
    row, response = _segment(module, store, 80)
    assert row['processing_tier'] == 'historical'
    assert row['terminal_no_derived_effects'] is True
    assert row['summary_blocked_reason'] == 'historical_on_open'
    assert row['structured']['title'] and row['structured'].get('title_provenance') is None
    assert response[HISTORICAL_RESPONSE_KEY] == {row['id']}
    # The write codec owes it no summary: no due time, no provisional provenance.
    write = dict(row)
    summary_delivery.prepare(write, 'u')
    assert write.get('summary_due_at') is None and 'summary_title_provenance' not in write


def test_a_late_bridge_segment_still_merges_historical_neighbours(pipeline, monkeypatch):
    # A provenance-free historical title is not processing: the merge donor fence must keep
    # absorbing old backfill, or out-of-order uploads would split one capture into two rows.
    module, store = pipeline
    monkeypatch.setattr(module.real_bridge, 'finish_sync_bridges', MagicMock(side_effect=lambda uid, cid, **kw: cid))
    module.finish_sync_segment = module.real_bridge.finish_sync_segment
    response = {'new_memories': set(), 'updated_memories': set()}
    for timestamp in (1000, 1240, 1120):
        assert module.process_segment(f'{timestamp}.wav', 'u', response, threading.Lock(), [])
    rows = [row for row in conversations(store) if not row.get('deleted')]
    assert len(rows) == 1 and rows[0]['processing_tier'] == 'historical'


def test_an_opened_historical_row_is_protected_like_any_processed_row():
    from config import merge_before_processing

    raw = {'processing_tier': 'historical', 'structured': {'title': 'Final title'}}
    assert merge_before_processing.already_processed(raw) is False
    opened = {**raw, 'structured': {'title': 'Final title', 'overview': 'Notes'}}
    assert merge_before_processing.already_processed(opened) is True
    assert merge_before_processing.already_processed({**raw, 'summary_completed_at': 1.0}) is True


def test_sync_recent_backfill_keeps_full_processing(pipeline):
    module, store = pipeline
    row, response = _segment(module, store, 2)
    assert 'processing_tier' not in row or row['processing_tier'] is None
    assert row['structured']['title_provenance'] == 'server_minimum'
    assert HISTORICAL_RESPONSE_KEY not in response


def test_sync_shifted_clock_proves_no_age(pipeline):
    module, store = pipeline
    row, _ = _segment(module, store, 80, capture_time_offset=30.0)
    assert row.get('processing_tier') is None
    assert row['structured']['title_provenance'] == 'server_minimum'


def _merged_response(cid='recording'):
    return {
        'new_memories': {cid},
        'updated_memories': set(),
        '_merged': {cid: 'en'},
        HISTORICAL_RESPONSE_KEY: {cid},
    }


@pytest.mark.parametrize('coalescing', [True, False])
def test_historical_rows_settle_instead_of_enrolling_enrichment(merged_pipeline, monkeypatch, coalescing):
    module = merged_pipeline
    settle = MagicMock(return_value=True)
    monkeypatch.setattr(module.historical_ingest, 'settle', settle)
    monkeypatch.setattr(module.processing_hold, 'scheduling_enabled', lambda: coalescing)
    monkeypatch.setattr('config.sync_reprocess.coalesce_enabled', lambda: coalescing)
    monkeypatch.setattr('config.demand_processing.enabled', lambda uid: coalescing)
    reprocess = MagicMock(side_effect=AssertionError('no inline enrichment for a historical row'))
    monkeypatch.setattr(module, '_reprocess_conversation_after_update', reprocess)
    mark = MagicMock(side_effect=AssertionError('no outbox mark for a historical row'))
    monkeypatch.setattr('utils.sync.reprocess.mark', mark)
    response = _merged_response()
    module._reprocess_merged_conversations('uid', response)
    settle.assert_called_once_with('uid', 'recording', producer='sync')
    assert HISTORICAL_RESPONSE_KEY not in response


def test_process_now_on_a_historical_row_still_generates_its_summary(merged_pipeline, monkeypatch):
    module = merged_pipeline
    settle = MagicMock()
    monkeypatch.setattr(module.historical_ingest, 'settle', settle)
    monkeypatch.setattr(module.lifecycle_service, 'restore_discarded', lambda *a: True)
    processed = SimpleNamespace(id='recording')
    monkeypatch.setattr(module, '_reprocess_conversation_after_update', MagicMock(return_value=processed))
    monkeypatch.setattr(module, 'complete_explicit', MagicMock())
    monkeypatch.setattr('utils.conversations.demand_processing.promote_conversation_effects', MagicMock())
    module._reprocess_merged_conversations('uid', _merged_response(), user_selected=True)
    settle.assert_not_called()
    module._reprocess_conversation_after_update.assert_called_once()


def _historical_row(world, **updates):
    world.add(
        'parent',
        0,
        5,
        sync_content_revision=2,
        processing_tier='historical',
        **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100, 'held': True}},
        **updates,
    )
    return world.get('user-1', 'parent')


def test_settle_completes_the_hold_so_an_identical_append_is_unchanged(monkeypatch):
    world = World(monkeypatch)
    current = _historical_row(world)
    assert historical_ingest.settle('user-1', 'parent', producer='sync') is True
    state = world.raw('parent')[hold.FIELD]
    assert state['pending_since'] is None and state['held'] is False
    assert state['full_snapshot']['digest'] == hold.content_snapshot(current)['digest']
    assert not state.get('late_runs')
    replay = {**current, hold.FIELD: hold.activity_patch({hold.FIELD: state}, 1000)}
    assert hold.admission(replay, {'first_pending_at': 1000}, now=5000) == ('unchanged', None)


def test_settle_refuses_a_row_that_is_not_historical(monkeypatch):
    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2)
    complete = MagicMock()
    monkeypatch.setattr(historical_ingest.conversations_db, 'complete_sync_processing_hold', complete)
    assert historical_ingest.settle('user-1', 'parent', producer='batch') is False
    complete.assert_not_called()


def test_enrichment_callback_settles_a_historical_minimum_with_its_snapshot(monkeypatch):
    world = World(monkeypatch)
    current = _historical_row(world)
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *_: current)
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *_: True)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(callback, 'schedule_after_finalization', Mock(return_value=True))
    monkeypatch.setattr(callback.time, 'time', lambda: 700)
    minimum = callback.deserialize_conversation({**current, 'structured': {'title': 'We planned the garden'}})
    monkeypatch.setattr(callback, 'process_conversation', Mock(return_value=minimum))
    token = PROCESS_CONTEXT.set({'owner': 'worker', 'lease_until': 1000, 'first_pending_at': 100, 'sync_hold': True})
    try:
        callback.enrich_conversation('user-1', 'parent', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    state = world.raw('parent')[hold.FIELD]
    assert state['pending_since'] is None
    assert state['full_snapshot']['digest'] == hold.content_snapshot(current)['digest']


def test_settled_reads_rows_and_models():
    assert historical_ingest.settled({'processing_tier': 'historical', 'structured': {'title': 'T'}})
    assert not historical_ingest.settled({'processing_tier': 'historical', 'structured': {'overview': 'notes'}})
    assert not historical_ingest.settled({'processing_tier': None, 'structured': {'title': 'T'}})
    assert historical_ingest.settled(SimpleNamespace(processing_tier='historical', structured={'title': 'T'}))


def test_stamp_marks_the_row_terminal_and_blocked():
    incoming = {'structured': {'title': 'T'}}
    historical_ingest.stamp(incoming, producer='batch')
    assert incoming == {
        'structured': {'title': 'T'},
        'processing_tier': 'historical',
        'terminal_no_derived_effects': True,
        'summary_blocked_reason': 'historical_on_open',
    }
    # Batch projection debt never re-arms a historical row.
    assert summary_delivery.stamp_projection_debt({**incoming, 'status': 'completed'}) is False
