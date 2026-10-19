"""Legacy dark (contract (h)): neutral at ``on``, fenced in ``draining``/``dark``."""

import json
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from database import sync_ledger
from utils.sync import legacy_dark
from utils.sync.legacy_dark import (
    DrainCensus,
    FenceAction,
    LegacyDarkReason,
    LegacyOwnership,
    LegacySyncMode,
    classify_ledger_row,
    dark_entry_verdict,
    fence_decision,
    fence_response,
)

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
COMPLETED = {'failed_segments': 0, 'total_segments': 3, 'errors': [], 'outcome': 'success'}
DRAINING, DARK, ON = LegacySyncMode.DRAINING, LegacySyncMode.DARK, LegacySyncMode.ON


@pytest.fixture
def runtime_mode(monkeypatch):
    """Install a fake (f) module; the real stub arrives with lane 1/6."""
    module = types.ModuleType('utils.rollout.runtime_percent')
    state = {'value': 'on'}

    def legacy_sync_mode():
        value = state['value']
        if isinstance(value, Exception):
            raise value
        return value

    module.legacy_sync_mode = legacy_sync_mode
    package = types.ModuleType('utils.rollout')
    package.runtime_percent = module
    monkeypatch.setitem(sys.modules, 'utils.rollout', package)
    monkeypatch.setitem(sys.modules, 'utils.rollout.runtime_percent', module)
    return state


def test_stale_window_matches_ledger():
    assert legacy_dark.CLAIM_STALE_SECONDS == sync_ledger.CLAIM_STALE_SECONDS


def test_mode_absent_serves_on(monkeypatch):
    monkeypatch.setitem(sys.modules, 'utils.rollout.runtime_percent', None)
    assert legacy_dark.current_mode() is ON
    assert legacy_dark.legacy_admission_allowed()
    assert legacy_dark.sequencer_registration_allowed()
    assert legacy_dark.sequencer_dispatch_allowed()


@pytest.mark.parametrize('raw', [RuntimeError('firestore'), 'off', None, 'DARK'])
def test_mode_failures_serve_on(runtime_mode, raw):
    runtime_mode['value'] = raw
    assert legacy_dark.current_mode() is ON


def test_mode_switches(runtime_mode):
    runtime_mode['value'] = 'draining'
    assert legacy_dark.current_mode() is DRAINING
    assert not legacy_dark.legacy_admission_allowed()
    assert not legacy_dark.sequencer_registration_allowed()
    assert legacy_dark.sequencer_dispatch_allowed()
    runtime_mode['value'] = 'dark'
    assert not legacy_dark.sequencer_dispatch_allowed()
    runtime_mode['value'] = 'on'
    assert legacy_dark.legacy_admission_allowed()


def test_mode_gauge_marks_one_mode(runtime_mode):
    runtime_mode['value'] = 'dark'
    legacy_dark.current_mode()
    values = {m.value: legacy_dark.OMI_LEGACY_SYNC_MODE.labels(mode=m.value)._value.get() for m in LegacySyncMode}
    assert values == {'on': 0, 'draining': 0, 'dark': 1}


@pytest.mark.parametrize(
    'row,expected',
    [
        (None, LegacyOwnership.NONE),
        ({}, LegacyOwnership.NONE),
        ({'dispatch_protocol': 'batch_v1', 'status': 'processing'}, LegacyOwnership.BATCH),
        ({'status': 'completed', 'result': COMPLETED, 'job_id': 'j'}, LegacyOwnership.COMPLETED),
        ({'status': 'completed', 'result': {'failed_segments': 1}}, LegacyOwnership.STRANDED),
        (
            {'dispatch_protocol': 'stt_cap_hold_v1', 'status': 'held', 'result': {**COMPLETED, 'held_audio': True}},
            LegacyOwnership.HELD,
        ),
        ({'status': 'processing', 'job_id': 'j', 'updated_at': NOW - timedelta(hours=1)}, LegacyOwnership.ACTIVE),
        ({'status': 'processing', 'job_id': 'j', 'updated_at': NOW - timedelta(days=3)}, LegacyOwnership.STRANDED),
        ({'status': 'retryable', 'job_id': 'j'}, LegacyOwnership.STRANDED),
        ({'status': 'retryable', 'repeat_failure_pause_until': NOW + timedelta(hours=2)}, LegacyOwnership.CAPPED),
        ({'status': 'retryable', 'repeat_failure_pause_until': NOW - timedelta(hours=2)}, LegacyOwnership.STRANDED),
        ({'status': 'mystery'}, LegacyOwnership.STRANDED),
    ],
)
def test_classify_ledger_row(row, expected):
    assert classify_ledger_row(row, now=NOW) is expected


def test_missing_redis_owner_strands_fresh_claim():
    row = {'status': 'processing', 'job_id': 'j', 'updated_at': NOW}
    assert classify_ledger_row(row, now=NOW, owner_job_present=True) is LegacyOwnership.ACTIVE
    assert classify_ledger_row(row, now=NOW, owner_job_present=False) is LegacyOwnership.STRANDED


LEGACY_ROWS = [
    {'status': 'completed', 'result': COMPLETED, 'job_id': 'j'},
    {'status': 'processing', 'job_id': 'j', 'updated_at': NOW},
    {'status': 'retryable', 'job_id': 'j'},
    {'status': 'retryable', 'repeat_failure_pause_until': NOW + timedelta(hours=1)},
]


@pytest.mark.parametrize('row', LEGACY_ROWS)
def test_on_is_behaviour_neutral(row):
    decision = fence_decision(row, ON, now=NOW)
    assert decision.action is FenceAction.LEGACY
    assert fence_response(decision, total_files=1, lane='backfill') is None


@pytest.mark.parametrize('mode', [ON, DRAINING, DARK])
def test_unowned_and_batch_content_admits_batch(mode):
    assert fence_decision(None, mode, now=NOW).action is FenceAction.ADMIT_BATCH
    assert fence_decision({'dispatch_protocol': 'batch_v1'}, mode, now=NOW).action is FenceAction.ADMIT_BATCH


@pytest.mark.parametrize('mode', [DRAINING, DARK])
def test_completed_legacy_content_is_acknowledged(mode):
    decision = fence_decision(LEGACY_ROWS[0], mode, now=NOW)
    assert (decision.action, decision.reason) == (FenceAction.ACK, LegacyDarkReason.LEGACY_COMPLETED)
    response = fence_response(decision, total_files=2, lane='fresh')
    body = json.loads(response.body)
    assert response.status_code == 202
    assert body == {
        'job_id': 'j',
        'status': 'completed',
        'total_files': 2,
        'total_segments': 3,
        'poll_after_ms': 0,
        'lane': 'fresh',
    }


def test_active_legacy_owner_keeps_its_job_in_draining():
    decision = fence_decision(LEGACY_ROWS[1], DRAINING, now=NOW)
    assert (decision.action, decision.reason) == (FenceAction.ACK, LegacyDarkReason.LEGACY_ACTIVE)
    response = fence_response(decision, total_files=1, lane='backfill')
    assert response.status_code == 409
    assert json.loads(response.body)['job_id'] == 'j'
    assert fence_decision(LEGACY_ROWS[1], DARK, now=NOW).reason is LegacyDarkReason.LEGACY_ACTIVE_IN_DARK


@pytest.mark.parametrize('mode', [DRAINING, DARK])
def test_stranded_and_capped_never_503(mode):
    for row, reason in (
        (LEGACY_ROWS[2], LegacyDarkReason.LEGACY_STRANDED),
        (LEGACY_ROWS[3], LegacyDarkReason.LEGACY_CAPPED),
    ):
        decision = fence_decision(row, mode, now=NOW)
        assert (decision.action, decision.reason) == (FenceAction.RETRY, reason)
        response = fence_response(decision, total_files=1, lane='backfill')
        assert response.status_code == 409
        assert int(response.headers['retry-after']) >= 1
        assert json.loads(response.body)['reason'] == 'dependency_warming'
    capped = fence_decision(LEGACY_ROWS[3], mode, now=NOW)
    assert capped.retry_after_seconds == 3601


@pytest.mark.parametrize('mode', [DRAINING, DARK])
def test_batch_adopts_stranded_when_supported(mode):
    decision = fence_decision(LEGACY_ROWS[2], mode, now=NOW, batch_adopts_stranded=True)
    assert (decision.action, decision.reason) == (FenceAction.ADMIT_BATCH, LegacyDarkReason.LEGACY_STRANDED_ADOPTED)
    # Never adopts content legacy is still finishing or already finished.
    for row in LEGACY_ROWS[:2]:
        assert fence_decision(row, mode, now=NOW, batch_adopts_stranded=True).action is FenceAction.ACK


def test_ack_counts_by_reason():
    counter = legacy_dark.OMI_LEGACY_DARK_ACK_TOTAL.labels(reason='legacy_completed')
    before = counter._value.get()
    fence_response(fence_decision(LEGACY_ROWS[0], DARK, now=NOW), total_files=1, lane='fresh')
    assert counter._value.get() == before + 1


def test_admission_counter_bounds_labels_and_flags_violations(caplog):
    counter = legacy_dark.OMI_LEGACY_SYNC_ADMISSIONS_TOTAL.labels(reason='unknown')
    before = counter._value.get()
    legacy_dark.record_legacy_admission('uid-shaped-free-text')
    assert counter._value.get() == before + 1
    legacy_dark.record_legacy_admission('intake_fallback', DARK)
    assert 'invariant_violation' in caplog.text


def test_refusal_and_sequencer_responses_are_not_5xx():
    refused = legacy_dark.admission_refused_response()
    assert refused.status_code == 409 and 'retry-after' in refused.headers
    swept = legacy_dark.sequencer_dark_response()
    assert swept.status_code == 200 and json.loads(swept.body)['status'] == 'legacy_dark'


def census(at, **overrides):
    values = dict.fromkeys(legacy_dark.CENSUS_FIELDS, 0)
    values.update(overrides)
    return DrainCensus(observed_at=at, **values)


def test_dark_entry_needs_two_zero_reads_ten_minutes_apart():
    assert dark_entry_verdict(census(0), census(600)).ready
    assert dark_entry_verdict(census(0), census(599)).blockers == ('confirmation_gap_under_10m',)
    verdict = dark_entry_verdict(census(0, sync_backfill_pending=3), census(600, queue_depth_sync_jobs=None))
    assert not verdict.ready
    assert verdict.blockers == ('first:sync_backfill_pending=3', 'second:queue_depth_sync_jobs=unavailable')


def test_informational_ledger_counts_never_gate():
    assert dark_entry_verdict(census(0, ledger_processing_legacy=None), census(600, ledger_retryable_legacy=5)).ready


def test_queue_spec_round_trips_to_gcloud_flags():
    from scripts.legacy_dark import legacy_queues

    live = {
        'rateLimits': {'maxConcurrentDispatches': 90, 'maxDispatchesPerSecond': 15.0},
        'retryConfig': {'maxAttempts': -1, 'minBackoff': '5s', 'maxBackoff': '60s', 'maxDoublings': 16},
        'stackdriverLoggingConfig': {'samplingRatio': 1.0},
        'state': 'RUNNING',
        'name': 'projects/p/locations/l/queues/sync-backfill',
    }
    spec = legacy_queues.spec_from_live(live)
    assert 'name' not in spec
    assert legacy_queues.flags_from_spec(spec) == [
        '--max-concurrent-dispatches=90',
        '--max-dispatches-per-second=15.0',
        '--max-attempts=-1',
        '--min-backoff=5s',
        '--max-backoff=60s',
        '--max-doublings=16',
        '--log-sampling-ratio=1.0',
    ]
    assert legacy_queues._queue_name('prod', 'sync-jobs') == 'sync-jobs'
    assert legacy_queues._queue_name('staging', 'sync-jobs') == 'staging-sync-jobs'
    assert set(legacy_queues.QUEUES) == set(legacy_dark.LEGACY_QUEUES)
