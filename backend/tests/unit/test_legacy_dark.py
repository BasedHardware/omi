"""Legacy dark (contract (h)): neutral at ``on``, fenced in ``draining``/``dark``."""

import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from database import sync_ledger
from utils.rollout import runtime_percent
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
    """Drive the (f) reader; lane 6 implements it behind the same name."""
    state = {'value': 'on'}

    def legacy_sync_mode():
        value = state['value']
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(runtime_percent, 'legacy_sync_mode', legacy_sync_mode)
    return state


def test_missing_reader_module_serves_on(monkeypatch):
    monkeypatch.setitem(sys.modules, 'utils.rollout', None)
    assert legacy_dark.current_mode() is ON


def test_stale_window_matches_ledger():
    assert legacy_dark.CLAIM_STALE_SECONDS == sync_ledger.CLAIM_STALE_SECONDS


def test_unimplemented_stub_serves_on_without_error_log(runtime_mode, caplog):
    runtime_mode['value'] = NotImplementedError('legacy_sync_mode: lane 6')
    counter = legacy_dark.OMI_LEGACY_SYNC_MODE_READ_TOTAL.labels(source='absent')
    before = counter._value.get()
    assert legacy_dark.current_mode() is ON
    assert counter._value.get() == before + 1
    assert 'outcome=error' not in caplog.text
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


def test_sequencer_kick_and_sweep_are_inert_in_dark(monkeypatch):
    from unittest.mock import MagicMock

    from utils.sync import uid_sequencer

    monkeypatch.setattr(uid_sequencer.registry, 'production_stage', lambda: True)
    claim = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_claim_next', claim)
    monkeypatch.setattr(uid_sequencer.registry, 'due_owners', claim)
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda: DARK)
    assert uid_sequencer.kick('test-uid') is False
    assert uid_sequencer.sweep() == {'legacy_dark': 1}
    claim.assert_not_called()


# --- M1 review (Grok) fixes ---


def test_claim_without_timestamp_is_stranded_like_claim_transaction():
    """L10-3: ``_claim_transaction`` takes over a processing claim without ``updated_at``."""
    assert classify_ledger_row({'status': 'processing', 'job_id': 'j'}, now=NOW) is LegacyOwnership.STRANDED


@pytest.mark.parametrize(
    'row, job, expected',
    [
        ({'status': 'processing', 'job_id': 'j', 'updated_at': NOW}, None, False),
        ({'status': 'processing', 'job_id': 'j', 'updated_at': NOW}, {'job_id': 'j'}, True),
        ({'status': 'completed', 'job_id': 'j', 'result': COMPLETED}, None, None),
        ({'dispatch_protocol': 'batch_v1', 'status': 'processing', 'job_id': 'j'}, None, None),
        ({'status': 'processing'}, None, None),
        (None, None, None),
    ],
)
def test_owner_probe_matches_claim_sync_content(monkeypatch, row, job, expected):
    """L10-3: the fence makes the same Redis existence check as ``claim_sync_content``."""
    from database import sync_jobs

    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda job_id: job)
    assert legacy_dark.legacy_owner_job_present(row) is expected


def test_owner_probe_failure_is_unknown_not_absent(monkeypatch):
    from database import sync_jobs

    def unavailable(job_id):
        raise ConnectionError('redis down')

    monkeypatch.setattr(sync_jobs, 'get_sync_job', unavailable)
    row = {'status': 'processing', 'job_id': 'j', 'updated_at': NOW}
    assert legacy_dark.legacy_owner_job_present(row) is None
    assert fence_decision(row, DARK, now=NOW, owner_job_present=None).ownership is LegacyOwnership.ACTIVE


@pytest.mark.parametrize('mode', [DRAINING, DARK])
def test_expired_redis_owner_is_adopted_not_followed(mode):
    """L10-3: a fresh claim whose Redis job expired is stranded, so batch adopts it."""
    row = {'status': 'processing', 'job_id': 'j', 'updated_at': NOW}
    decision = fence_decision(row, mode, now=NOW, owner_job_present=False, batch_adopts_stranded=True)
    assert decision.action is FenceAction.ADMIT_BATCH
    assert decision.reason is LegacyDarkReason.LEGACY_STRANDED_ADOPTED


@pytest.mark.parametrize('mode', [DRAINING, DARK])
def test_live_repeat_failure_pause_is_never_adopted(mode):
    """L10-4: CAPPED answers 409 for the remaining pause even when the caller can adopt."""
    row = {'status': 'retryable', 'job_id': 'j', 'repeat_failure_pause_until': NOW + timedelta(hours=1)}
    decision = fence_decision(row, mode, now=NOW, batch_adopts_stranded=True)
    assert decision.action is FenceAction.RETRY
    assert decision.reason is LegacyDarkReason.LEGACY_CAPPED
    assert decision.retry_after_seconds == 3601


@pytest.mark.parametrize('state, verb', [('RUNNING', 'resume'), ('PAUSED', 'pause')])
def test_recreate_restores_queue_state_both_ways(monkeypatch, tmp_path, state, verb):
    """L10-5: ``queues update`` never changes state, so recreate resumes a RUNNING spec too."""
    from scripts.legacy_dark import legacy_queues

    spec_path = tmp_path / 'spec.json'
    spec_path.write_text(
        json.dumps(
            {
                'spec_version': legacy_queues.SPEC_VERSION,
                'env': 'staging',
                'queues': {'sync-jobs': {'state': state, 'max_attempts': 5}},
            }
        )
    )
    calls = []
    monkeypatch.setattr(legacy_queues, 'describe', lambda env, queue: {'name': queue})
    monkeypatch.setattr(legacy_queues, 'flags_from_spec', lambda spec: [])
    monkeypatch.setattr(legacy_queues, '_gcloud', lambda command: calls.append(command))
    assert legacy_queues.recreate('staging', str(spec_path), apply=True) == 0
    assert [command[2] for command in calls] == ['update', verb]
    assert calls[1][3] == 'staging-sync-jobs'


@pytest.mark.parametrize('env, counted', [('staging', 0), ('prod', 981)])
def test_census_counts_only_the_envs_own_queues(env, counted):
    """Staging shares based-hardware-dev with dev: dev's unprefixed queues are not staging's."""
    from scripts.legacy_dark import drain_census

    def series(queue_id, depth):
        return {'resource': {'labels': {'queue_id': queue_id}}, 'points': [{'value': {'int64Value': str(depth)}}]}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'timeSeries': [
                    series('staging-sync-jobs', 0),
                    series('sync-jobs', 981),
                    series('staging-sync-jobs-fresh', 0),
                    series('sync-backfill', 0),
                    series('sync-backfill-fresh', 0),
                    series('sync-jobs-fresh', 0),
                    series('staging-sync-backfill', 0),
                    series('staging-sync-backfill-fresh', 0),
                ]
            }

    class Session:
        def get(self, url, params=None, timeout=None):
            return Response()

    errors: dict = {}
    depths = drain_census._queue_depths(Session(), 'project', env, errors)
    assert depths['sync-jobs'] == counted
    assert set(depths.values()) <= {0, 981} and None not in depths.values()
    assert errors == {}
