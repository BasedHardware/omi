"""Internal sync failures carry their own cause instead of the vendor upstream_error.

Every persistence/finalize exception used to become TranscriptionOutcome.UPSTREAM_ERROR,
so GCS 429s on the bridge copy, Firestore contention and assignment conflicts read as an
STT vendor outage. Assignment conflicts with subtype ``other`` also never earned a strike,
so a conflict that could not resolve retried paid work forever.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, TooManyRequests
from prometheus_client import REGISTRY

from config.prerecorded_stt import TranscriptionOutcome
from config.sync_telemetry import SYNC_REPEAT_FAILURE_PERSISTENCE_FINGERPRINTS, SyncFailureReason
from database import sync_ledger
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.live_projection import replace_record
from utils.observability.transcription import record_sync_transcription_outcome
from utils.stt.outcomes import TranscriptionFailure
from utils.sync.assignment_errors import (
    SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER,
    SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL,
    SyncAssignmentConflict,
    SyncAssignmentConflictReason,
    bounded_sync_assignment_subtype,
)
from utils.sync.failure_reason import (
    job_failure_reason,
    outcome_label,
    persistence_failure_fingerprint,
    stamped_failure_kwargs,
    sync_failure_error_code,
    sync_failure_reason,
)


@pytest.mark.parametrize(
    ('phase', 'error', 'reason'),
    [
        ('finalize', TooManyRequests('429'), SyncFailureReason.STORAGE_RATE_LIMITED),
        ('finalize', ResourceExhausted('quota'), SyncFailureReason.QUOTA_EXHAUSTED),
        ('persistence', FirestoreContentionExhausted('busy'), SyncFailureReason.FIRESTORE_CONTENTION),
        ('persistence', SyncAssignmentConflict('x'), SyncFailureReason.ASSIGNMENT_CONFLICT),
        ('persistence', ValueError('shape'), SyncFailureReason.PERSISTENCE_ERROR),
        ('finalize', RuntimeError('boom'), SyncFailureReason.FINALIZE_ERROR),
        ('provider_call', TooManyRequests('vendor 429'), SyncFailureReason.NONE),
        (None, FirestoreContentionExhausted('busy'), SyncFailureReason.NONE),
        (
            'persistence',
            TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='parakeet'),
            SyncFailureReason.NONE,
        ),
    ],
)
def test_internal_cause_is_classified_by_phase_and_bounded_class(phase, error, reason):
    assert sync_failure_reason(phase, error) is reason
    # Deferred labels replay only the bounded class token, never the exception object.
    assert sync_failure_reason(phase, type(error).__name__) is reason


def test_provider_failure_reraised_from_the_persistence_loop_stays_a_vendor_failure():
    # minimal_redrive.ProviderUnavailable is a TranscriptionFailure that the coordinator
    # re-raises while job_phase is still 'persistence'.
    class ProviderUnavailable(TranscriptionFailure):
        def __init__(self):
            super().__init__(TranscriptionOutcome.UPSTREAM_ERROR, provider='parakeet', retryable=True)

    assert sync_failure_reason('persistence', ProviderUnavailable()) is SyncFailureReason.NONE
    wrapped = RuntimeError('job failed')
    wrapped.__cause__ = ProviderUnavailable()
    assert sync_failure_reason('finalize', wrapped) is SyncFailureReason.NONE


def test_rate_limit_and_contention_get_their_own_job_error_codes():
    assert sync_failure_error_code(SyncFailureReason.STORAGE_RATE_LIMITED, 'finalize') == 'sync_storage_rate_limited'
    assert sync_failure_error_code(SyncFailureReason.FIRESTORE_CONTENTION, 'persistence') == 'sync_firestore_contention'
    assert sync_failure_error_code(SyncFailureReason.ASSIGNMENT_CONFLICT, 'persistence') == 'sync_persistence_failed'
    assert sync_failure_error_code(SyncFailureReason.FINALIZE_ERROR, 'finalize') == 'sync_finalize_failed'


def test_job_is_internal_only_when_no_segment_failed_at_the_vendor():
    internal = ['sync_storage_rate_limited', 'sync_persistence_failed']
    assert job_failure_reason(internal, 'finalize', 'TooManyRequests') is SyncFailureReason.STORAGE_RATE_LIMITED
    assert job_failure_reason([*internal, 'stt_timeout'], 'finalize', 'TooManyRequests') is SyncFailureReason.NONE
    assert job_failure_reason([], 'none', 'none') is SyncFailureReason.NONE
    assert outcome_label('upstream_error', SyncFailureReason.FIRESTORE_CONTENTION) == 'internal_error'
    assert outcome_label('upstream_error', SyncFailureReason.NONE) == 'upstream_error'


def _sample(name, labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_internal_failure_metric_is_not_counted_as_upstream_error():
    base = {'provider': 'unknown', 'model': 'unknown', 'lane': 'fresh'}
    upstream = {**base, 'outcome': 'upstream_error'}
    internal = {**base, 'outcome': 'internal_error'}
    cause = {'kind': 'segment', 'lane': 'fresh', 'failure_reason': 'storage_rate_limited'}

    def counts():
        return (
            sum(
                sample.value
                for metric in REGISTRY.collect()
                if metric.name == 'omi_sync_transcription_segments'
                for sample in metric.samples
                if sample.name.endswith('_total') and all(sample.labels.get(k) == v for k, v in upstream.items())
            ),
            sum(
                sample.value
                for metric in REGISTRY.collect()
                if metric.name == 'omi_sync_transcription_segments'
                for sample in metric.samples
                if sample.name.endswith('_total') and all(sample.labels.get(k) == v for k, v in internal.items())
            ),
            _sample('omi_sync_internal_failures_total', cause),
        )

    before = counts()
    record_sync_transcription_outcome(
        kind='segment',
        provider=None,
        model='unknown',
        lane='fresh',
        outcome=TranscriptionOutcome.UPSTREAM_ERROR,
        failure_reason=SyncFailureReason.STORAGE_RATE_LIMITED,
    )
    after = counts()
    assert after[0] == before[0]
    assert after[1] == before[1] + 1
    assert after[2] == before[2] + 1


def test_every_conflict_reason_is_a_bounded_label():
    for reason in SyncAssignmentConflictReason:
        assert re.fullmatch(r'[a-z][a-z0-9_]{0,39}', reason.value)
        assert bounded_sync_assignment_subtype(reason) == reason.value
        assert SyncAssignmentConflict('m', subtype=reason).subtype == reason.value
    assert bounded_sync_assignment_subtype('free text from somewhere') == 'other'
    assert not SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL & SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER


@pytest.mark.parametrize('reason', sorted(SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL))
def test_structural_conflict_strikes_on_every_lane(reason):
    for lane in ('fresh', 'backfill'):
        fingerprint = persistence_failure_fingerprint(SyncAssignmentConflict('m', subtype=reason), 'persistence', lane)
        assert fingerprint == f'persistence:{reason}'
        # The ledger only counts fingerprints from its closed set.
        assert fingerprint in SYNC_REPEAT_FAILURE_PERSISTENCE_FINGERPRINTS


@pytest.mark.parametrize('reason', sorted(SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER))
def test_awaiting_writer_conflict_strikes_only_on_backfill(reason):
    error = SyncAssignmentConflict('m', subtype=reason)
    assert persistence_failure_fingerprint(error, 'persistence', 'fresh') is None
    fingerprint = persistence_failure_fingerprint(error, 'persistence', 'backfill')
    assert fingerprint == f'persistence:{reason}'
    assert fingerprint in SYNC_REPEAT_FAILURE_PERSISTENCE_FINGERPRINTS


def test_unlabeled_or_transient_conflict_never_strikes():
    assert persistence_failure_fingerprint(SyncAssignmentConflict('m'), 'persistence', 'backfill') is None
    wrapped = SyncAssignmentConflict('m', subtype=SyncAssignmentConflictReason.RECORD_ROUTE_OWNER_CHANGED)
    wrapped.__cause__ = ServiceUnavailable('flaky')
    assert persistence_failure_fingerprint(wrapped, 'persistence', 'backfill') is None
    structural = SyncAssignmentConflict('m', subtype=SyncAssignmentConflictReason.RECORD_ROUTE_OWNER_CHANGED)
    assert persistence_failure_fingerprint(structural, 'finalize', 'backfill') is None


def test_backfill_conflict_pauses_after_three_strikes_then_admits_again():
    error = SyncAssignmentConflict('m', subtype=SyncAssignmentConflictReason.LIVE_TARGET_NOT_PERSISTED)
    fingerprint = persistence_failure_fingerprint(error, 'persistence', 'backfill')
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    existing: dict = {}
    for strike in range(3):
        existing = sync_ledger._repeat_failure_updates(
            existing, 'persistent_persistence', fingerprint, now + timedelta(minutes=strike)
        )
    assert existing['repeat_failure_count'] == 3
    assert sync_ledger._repeat_failure_capped(existing, now + timedelta(hours=1))
    assert not sync_ledger._repeat_failure_capped(existing, now + timedelta(hours=25))


def _record(**overrides):
    return {
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'started_at': datetime(2026, 10, 21, tzinfo=timezone.utc),
        **overrides,
    }


@pytest.mark.parametrize(
    ('row', 'reason'),
    [
        (_record(record_lane_owner='legacy'), 'record_route_owner_changed'),
        (_record(deleted=True), 'record_target_retired'),
        (_record(discarded=True, status='processing'), 'record_target_discarded'),
        (_record(status='processing'), 'record_finalize_pending'),
        (_record(uses_custom_stt=True), 'record_privacy_changed'),
    ],
)
def test_record_projection_conflicts_name_their_reason(row, reason):
    with pytest.raises(SyncAssignmentConflict) as exc_info:
        replace_record(row, {'transcript_segments': []}, {'start': 0.0, 'end': 1.0})
    assert exc_info.value.subtype == reason


def test_task_mode_reraise_carries_the_internal_cause_to_the_final_attempt():
    error = FirestoreContentionExhausted('busy')
    setattr(error, 'sync_failure_reason', SyncFailureReason.FIRESTORE_CONTENTION)
    setattr(error, 'sync_failure_phase', 'persistence')
    assert stamped_failure_kwargs(error) == {
        'failure_phase': 'persistence',
        'failure_class': 'FirestoreContentionExhausted',
        'failure_reason': SyncFailureReason.FIRESTORE_CONTENTION,
    }
    unstamped = stamped_failure_kwargs(RuntimeError('provider'))
    assert unstamped['failure_reason'] is SyncFailureReason.NONE and unstamped['failure_phase'] is None


@pytest.mark.parametrize('phase', ['postprocess', 'usage'])
def test_whole_job_coordinator_phases_are_internal(phase):
    assert sync_failure_reason(phase, ServiceUnavailable('firestore')) is SyncFailureReason.FINALIZE_ERROR
    assert sync_failure_error_code(SyncFailureReason.FINALIZE_ERROR, phase) == 'sync_finalize_failed'
