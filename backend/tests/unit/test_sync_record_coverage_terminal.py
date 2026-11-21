"""A final record's unproven WAL gets a terminal keep-local answer, never an endless 503.

Synthetic rows only. The answer must keep custody on the phone (400, never a
200/202 release), stay retryable while the record can still change, and leave
transient coverage failures retryable.
"""

import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from config.batch_pipeline_coverage_wait import COVERAGE_FINAL_AFTER_SECONDS
from config.policy import BatchUnitPolicy
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import live_upload
from utils.sync import fsr_metadata

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
UID, CID = 'synthetic-owner', 'synthetic-conversation'


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    monkeypatch.delenv('SYNC_RECORD_COVERAGE_TERMINAL', raising=False)
    monkeypatch.setattr(live_upload.record_wal_handoff.receipts, 'has_receipts', lambda *_: False)
    monkeypatch.setattr(live_upload, 'remember_coverage_wait', lambda *_: None)
    monkeypatch.setattr(live_upload, 'cached_record_wait', lambda *_: None)
    monkeypatch.setattr(live_upload, 'remember_record_wait', lambda *_: None)
    monkeypatch.setattr(live_upload, 'time', SimpleNamespace(time=NOW.timestamp))


def final_row(**changes):
    row = {
        'record_lane_owner': live_upload.OWNER,
        'source': 'omi',
        'client_device_id': 'synthetic-device',
        'status': 'completed',
        'record_audio_closed': True,
        'finished_at': NOW - timedelta(hours=9),
        'record_sealed_at': (NOW - timedelta(hours=7)).timestamp(),
    }
    row.update(changes)
    return {key: value for key, value in row.items() if value is not None}


def world(monkeypatch, *, gap='audio_bytes_differ', memo_hit=False):
    """``gap`` is the coverage answer (None = proven, a cause, or a raising callable).

    ``memo_hit`` makes the memo answer with that same cause.
    """
    store = MemoryStore()
    content, _ = live_upload.record_identity(UID, CID)
    store.rows['intakes', 'bp_' + content] = {'segment_ids': ['synthetic-segment']}
    store.rows['jobs', 'synthetic-segment'] = {'segment_id': 'synthetic-segment'}
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(live_upload, 'artifacts_for', lambda *_: object())
    monkeypatch.setattr(live_upload, '_upload_identity', lambda paths: (len(paths), 0))
    monkeypatch.setattr(live_upload, 'cached_coverage_wait', lambda *_: gap if memo_hit else None)
    if callable(gap):
        monkeypatch.setattr(live_upload, '_coverage_gap', gap)
    else:
        monkeypatch.setattr(live_upload, '_coverage_gap', lambda *_: gap)
    return store, content


async def answer(row):
    return await live_upload.registered_record_response(
        uid=UID,
        conversation_id=CID,
        content_id='synthetic-wal-content',
        paths=['synthetic-audio.bin'],
        source='omi',
        client_device_id='synthetic-device',
        loaded_conversation=row,
        policy=BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=True),
    )


def terminal_count(memo, cause='audio_bytes_differ'):
    labels = {'cause': cause, 'memo': memo}
    return REGISTRY.get_sample_value('omi_pipeline_record_coverage_terminal_total', labels) or 0


@pytest.mark.parametrize('memo_hit', [False, True])
async def test_final_record_answers_terminal_keep_local_refusal(monkeypatch, caplog, memo_hit):
    store, content = world(monkeypatch, memo_hit=memo_hit)
    before_rows = deepcopy(store.rows)
    memo = 'hit' if memo_hit else 'miss'
    before = terminal_count(memo)

    with caplog.at_level(logging.INFO, logger=live_upload.__name__):
        response = await answer(final_row())

    # 400 is the one terminal status every shipped app keeps audio for; it is
    # never the 200/202 that would let the phone release its WAL.
    assert response.status_code == 400
    assert 'retry-after' not in response.headers
    assert json.loads(response.body) == {
        'code': 'record_capture_unprovable',
        'detail': 'The registered record is final and cannot prove this audio; keep the local copy',
        'retryable': False,
    }
    assert store.rows == before_rows  # no alias, receipt or custody write
    assert terminal_count(memo) == before + 1
    messages = [record.getMessage() for record in caplog.records if 'event=sync_record_upload' in record.getMessage()]
    assert messages == [
        'event=sync_record_upload outcome=terminal reason=audio_coverage_unproven cause=audio_bytes_differ '
        f'record={content[:16]} path=coverage memo={memo}'
    ]
    assert UID not in messages[0] and CID not in messages[0]


@pytest.mark.parametrize(
    'changes',
    [
        {'record_audio_closed': None},
        {'record_audio_partial': True},
        {'record_sealed_at': None},
        {'finished_at': None},
        {'record_seal_refused_at': (NOW - timedelta(hours=8)).timestamp()},
        {'record_upload_sessions': {'synthetic-session': {'state': 'open'}}},
        # A recent reseal or finish restarts the clock: units may still change.
        {'record_sealed_at': (NOW - timedelta(seconds=COVERAGE_FINAL_AFTER_SECONDS - 60)).timestamp()},
        {'finished_at': NOW - timedelta(seconds=COVERAGE_FINAL_AFTER_SECONDS - 60)},
        # Unreadable clocks are never final.
        {'record_sealed_at': True},
        {'finished_at': 'not-a-time'},
        {'finished_at': datetime(2026, 11, 18, 0, 0)},
        {'finished_at': float('-inf')},
        {'record_sealed_at': float('nan')},
        {'record_sealed_at': float('inf')},
    ],
)
async def test_record_that_can_still_change_keeps_the_retryable_wait(monkeypatch, changes):
    world(monkeypatch)
    response = await answer(final_row(**changes))
    assert response.status_code == 503
    assert json.loads(response.body)['code'] == 'record_capture_pending'


@pytest.mark.parametrize('route', ['late_memo_hit', 'memo_off'])
async def test_every_coverage_negative_return_is_terminal_for_a_final_record(monkeypatch, route):
    memo = 'hit' if route == 'late_memo_hit' else 'off'
    world(monkeypatch, memo_hit=route == 'late_memo_hit')
    if route == 'late_memo_hit':
        # Memo-first off: the identical check answers after the retained copy.
        monkeypatch.setenv('SYNC_RECORD_WAIT_MEMO_FIRST', 'false')
    else:
        # No upload identity (a file vanished): no memo key, a fresh check.
        monkeypatch.setattr(live_upload, '_upload_identity', lambda paths: None)
    before = terminal_count(memo)
    response = await answer(final_row())
    assert response.status_code == 400
    assert json.loads(response.body)['code'] == 'record_capture_unprovable'
    assert terminal_count(memo) == before + 1


def test_unrepresentable_datetime_clock_is_not_final():
    class Broken(datetime):
        def timestamp(self):
            raise OverflowError('synthetic')

    row = final_row(finished_at=Broken(2026, 11, 18, tzinfo=timezone.utc))
    assert not live_upload.coverage_final(row, now=NOW.timestamp())


@pytest.mark.parametrize('memo_hit', [False, True])
@pytest.mark.parametrize(
    'cause', ['wal_audio_past_record', 'wal_audio_outside_record', 'record_unit_exhausted', 'unknown']
)
async def test_final_record_keeps_retrying_when_the_server_may_lack_the_audio(monkeypatch, cause, memo_hit):
    # Past/outside audio is not on the server: a terminal answer would let the
    # phone stop re-offering the only copy. Unknown causes (a legacy memo) too.
    world(monkeypatch, gap=cause, memo_hit=memo_hit)
    before = terminal_count('hit' if memo_hit else 'miss', cause)
    response = await answer(final_row())
    assert response.status_code == 503
    assert json.loads(response.body)['code'] == 'record_capture_pending'
    assert terminal_count('hit' if memo_hit else 'miss', cause) == before


def test_legacy_memo_marker_reads_as_unknown_cause():
    assert live_upload._cached_cause('1') == 'unknown'
    assert live_upload._cached_cause(True) == 'unknown'
    assert live_upload._cached_cause('audio_bytes_differ') == 'audio_bytes_differ'


async def test_kill_switch_restores_the_retryable_wait(monkeypatch):
    world(monkeypatch)
    monkeypatch.setenv('SYNC_RECORD_COVERAGE_TERMINAL', 'false')
    response = await answer(final_row())
    assert response.status_code == 503
    assert json.loads(response.body)['code'] == 'record_capture_pending'


async def test_transient_coverage_failure_on_a_final_record_stays_retryable(monkeypatch):
    def fail(*_):
        raise RuntimeError('synthetic storage failure')

    world(monkeypatch, gap=fail)
    response = await answer(final_row())
    assert response.status_code == 503
    assert json.loads(response.body)['code'] == 'record_capture_pending'


async def test_proven_coverage_on_a_final_record_still_reuses_the_record_result(monkeypatch):
    store, content = world(monkeypatch, gap=None)
    store.rows['content', f'{UID}/{content}'] = {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_' + content}
    status = {
        'job_id': 'bp_' + content,
        'status': 'completed',
        'total_files': 1,
        'total_segments': 1,
        'poll_after_ms': 0,
        'lane': 'fresh',
    }
    monkeypatch.setattr(live_upload, 'durable_status', lambda *_: status)
    response = await answer(final_row())
    assert response.status_code == 202
    assert json.loads(response.body)['job_id'] == 'bp_' + content


def test_coverage_final_accepts_firestore_datetimes_and_epoch_seconds():
    sealed = NOW - timedelta(seconds=COVERAGE_FINAL_AFTER_SECONDS)
    row = final_row(record_sealed_at=sealed, finished_at=sealed - timedelta(hours=1))
    assert live_upload.coverage_final(row, now=NOW.timestamp())
    row['record_sealed_at'] = sealed.timestamp() + 1
    assert not live_upload.coverage_final(row, now=NOW.timestamp())


def test_provenance_projection_carries_every_finality_marker():
    # The sync route's loaded row is this projection; a missing marker would
    # silently keep every upload on the retryable wait.
    assert {
        'record_audio_closed',
        'record_audio_partial',
        'record_sealed_at',
        'record_seal_refused_at',
        'record_upload_sessions',
        'finished_at',
        'deleted',
    } <= set(fsr_metadata.PROVENANCE_FIELDS)
