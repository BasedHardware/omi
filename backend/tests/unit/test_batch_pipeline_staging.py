"""Uncertain/abandoned intake uploads cannot outlive cleanup or lose accepted audio."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from database.batch_pipeline_intake import admit
from database.batch_pipeline_staging import artifact_id, ORPHAN_GRACE, reap_one
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import ProjectionBinding

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def stage(store, *, kind='audio', deadline=None):
    work = replace(item('segment', owner='synthetic-owner'), privacy_generation=0, audio_uri='gs://synthetic/audio#1')
    key = artifact_id(work.segment_id, work.audio_uri)
    store.rows['artifacts', key] = {
        'segment_id': work.segment_id,
        'owner_id': work.owner_id,
        'privacy_generation': 0,
        'uri': work.audio_uri.split('#')[0],
        'kind': kind,
        'write_pending_until': deadline or NOW - ORPHAN_GRACE - timedelta(minutes=1),
    }
    return work, key


def test_abandoned_staging_becomes_durable_cleanup_obligation():
    store = MemoryStore()
    work, key = stage(store)
    assert reap_one(store, key, NOW)
    assert store.rows['artifacts', key]['cleanup_after'] == NOW
    assert not reap_one(store, key, NOW)


def test_accepted_audio_never_expires_because_the_queue_is_old():
    store = MemoryStore()
    work, key = stage(store)
    store.rows['jobs', work.segment_id] = {**work.__dict__, 'state': 'dead'}
    assert reap_one(store, key, NOW)
    assert 'cleanup_after' not in store.rows['artifacts', key]
    assert 'write_pending_until' not in store.rows['artifacts', key]
    assert store.rows['artifacts', key]['uri']  # D completion/deletion owns cleanup.


def test_recent_http_intake_and_live_compute_result_reservations_are_retained():
    store = MemoryStore()
    _, recent = stage(store, deadline=NOW - timedelta(minutes=2))
    assert not reap_one(store, recent, NOW)
    work, key = stage(store, kind='results')
    store.rows['jobs', work.segment_id] = {'state': 'leased', 'lease_until': NOW.timestamp() + 30}
    assert not reap_one(store, key, NOW)


def test_admission_and_reaping_serialize_on_the_staging_reservation(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    store = MemoryStore()
    work, key = stage(store)
    binding = ProjectionBinding(work.owner_id, 'bp_job', 'content', (work.segment_id,))
    assert reap_one(store, key, NOW)
    with pytest.raises(ValueError, match='reclaimed'):
        admit(store, [work], binding, NOW.timestamp(), namespace='batch_pipeline_test_staging', require_artifacts=True)
    assert ('jobs', work.segment_id) not in store.rows
    work, key = stage(store)
    assert (
        admit(store, [work], binding, NOW.timestamp(), namespace='batch_pipeline_test_staging', require_artifacts=True)[
            'outcome'
        ]
        == 'batch'
    )
    assert 'write_pending_until' not in store.rows['artifacts', key]
    assert not reap_one(store, key, NOW)
