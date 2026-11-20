"""Historical tier (T1+): the merge builder keeps the marker, and the DB writer records an open-time summary."""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from datetime import datetime, timedelta, timezone

import pytest

import utils.conversations.merge_conversations as merge
import utils.notifications
from database import conversations as db
from tests.unit.test_merge_audio_chunk_copy_failure import _FakeBucket, _install
from tests.unit.test_summary_persistence import writer  # noqa: F401  (fixture)


def _source(cid, minutes, **updates):
    now = datetime.now(timezone.utc)
    row = {
        'id': cid,
        'created_at': now - timedelta(minutes=minutes),
        'started_at': now - timedelta(minutes=minutes),
        'finished_at': now - timedelta(minutes=minutes - 1),
        'language': 'en',
        'source': 'omi',
        'transcript_segments': [],
    }
    row.update(updates)
    return row


def _merged(monkeypatch, sources):
    monkeypatch.setattr(
        merge.conversations_db, 'get_conversation', lambda _uid, cid: next(c for c in sources if c['id'] == cid)
    )
    _install(monkeypatch, chunks_by_conv={}, bucket=_FakeBucket())
    monkeypatch.setattr(merge, '_collect_all_photos', lambda *_a, **_k: [])
    monkeypatch.setattr(merge, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(merge.lifecycle_service, 'complete', lambda *_a, **_k: None)
    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', lambda *_a, **_k: None)
    monkeypatch.setattr(utils.notifications, 'send_merge_completed_message', lambda *_a, **_k: None)
    created = {}
    monkeypatch.setattr(
        merge.lifecycle_service, 'create_processing_conversation', lambda uid, data: created.update(data=data)
    )
    merge.perform_merge_async('u1', [s['id'] for s in sources], reprocess=False)
    return created['data']


def test_merging_a_historical_source_keeps_the_merged_row_historical(monkeypatch):
    data = _merged(monkeypatch, [_source('old', 2, processing_tier='historical'), _source('recent', 1)])
    assert data['processing_tier'] == 'historical'


def test_merging_ordinary_sources_stays_ordinary(monkeypatch):
    data = _merged(monkeypatch, [_source('a', 2), _source('b', 1)])
    assert data.get('processing_tier') is None


def _historical_existing(writer):
    writer.document.update(
        processing_tier='historical',
        terminal_no_derived_effects=True,
        summary_blocked_reason='historical_on_open',
        summary_output_present=False,
    )
    for name in ('summary_due_at', 'summary_title_provenance'):
        writer.document.pop(name, None)


def _payload(overview):
    return {
        'id': 'c',
        'status': 'completed',
        'sync_content_revision': 3,
        'data_protection_level': 'standard',
        'processing_tier': 'historical',
        'terminal_no_derived_effects': True,
        'structured': {'title': 'Planning the garden', 'overview': overview},
    }


def test_an_open_time_summary_is_recorded_as_delivered(writer):
    _historical_existing(writer)
    assert db.persist_processing_result_with_lifecycle('u', _payload('We chose what to plant.'))
    committed = writer.commits[-1]
    assert committed['summary_completed_at'] and committed['summary_title_provenance'] == 'generated'
    assert committed['summary_blocked_reason'] is None and committed.get('summary_due_at') is None


def test_an_empty_historical_write_keeps_its_open_time_block(writer):
    _historical_existing(writer)
    assert db.persist_processing_result_with_lifecycle('u', _payload(''))
    committed = writer.commits[-1]
    assert committed['summary_blocked_reason'] == 'historical_on_open'
    assert not committed.get('summary_completed_at')
