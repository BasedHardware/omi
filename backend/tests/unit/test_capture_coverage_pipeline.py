"""L1 ledger through the real WAL coordinator, VAD and assignment boundary."""

import hashlib

import pytest

from database import capture_coverage as ledger_store
from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_lineage_dedupe_replay import at, live_row, seeded_store
from tests.unit.test_wal_audio_coverage_pipeline import (
    real_pipeline,
    _coverage_env,
    _wire_real,
    _run_real,
    _live_segments,
    _stored_texts,
    ROOT,
    EPOCH,
    ORIGIN,
)
from utils.capture import coverage
from utils.conversations import lifecycle
from tests.unit.test_sync_cross_job_assignment import intake


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,provider_calls,repetitions', [('serve', 0, 1), ('shadow', 1, 2), ('off', 1, 2)])
async def test_same_audio_live_then_backup_serve_once_shadow_matches_legacy(
    real_pipeline, monkeypatch, tmp_path, mode, provider_calls, repetitions
):
    pipeline = real_pipeline
    _coverage_env(monkeypatch, coverage_flag='false')
    monkeypatch.setenv(coverage.FLAG, mode)
    if mode == 'serve':
        monkeypatch.setattr(pipeline, 'sync_safety_wal_enabled', lambda: True)

        async def no_clock_coverage(*args, **kwargs):
            pytest.fail('serving coverage must not fall through to clock/energy trimming')

        monkeypatch.setattr(pipeline, 'apply_safety_wal_coverage', no_clock_coverage)
    monkeypatch.setattr(ledger_store, '_client', lambda: ledger)
    ledger = StrictFirestore()
    key = CaptureKey(
        capture_root=ROOT, channel='mono', clock_epoch=str(EPOCH), device_id='pendant', recording_session_id=ORIGIN
    )

    def word(value):
        return hashlib.sha256(bytes([value])).hexdigest()

    row = live_row(started_at=at(1760000000), finished_at=at(1760000005), transcript_segments=_live_segments(word, 10))
    store = seeded_store([row])
    subject = next(path[1] for path in store.rows if path[0] == 'users')
    # The live writer's durable flush contract, not a receipt for socket sends.
    coverage.record(
        subject, key, CoverageRecord(conversation_id='live', origin='live', ranges=[FrameRange(start=0, end=10)])
    )

    before = _stored_texts(store, row)
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(pipeline, monkeypatch, tmp_path, lineage_rows=[], word=word)
    await _run_real(pipeline, tmp_path, target_conversation_id=row['id'])
    assert len(state.prerecorded_calls) == provider_calls
    from collections import Counter

    assert Counter(_stored_texts(store, row)) == Counter({text: repetitions for text in before})
    assert len(before) == 10
    assert sum(path[:3] == ('users', subject, 'conversations') for path in store.rows) == 1
    assert state.outcomes[-1].value == 'success'
