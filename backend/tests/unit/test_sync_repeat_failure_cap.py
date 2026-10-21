"""Content-keyed pause keeps retry material while bounding repeated paid work."""

from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import Aborted, ServiceUnavailable, InvalidArgument
import pytest
from google.cloud import firestore

from database import sync_ledger, sync_jobs
from database.firestore_transaction_retry import FirestoreContentionExhausted
from routers.sync import _terminal_repeat_failure_kwargs
from utils.sync.assignment_errors import SyncAssignmentConflict
from utils.sync.pipeline import _persistence_failure_fingerprint, _whole_job_persistence_fingerprint


class _Snapshot:
    def __init__(self, data):
        self.data = data
        self.exists = bool(data)

    def to_dict(self):
        return dict(self.data)


class _Ref:
    def __init__(self):
        self.data = {}

    def get(self, transaction=None):
        return _Snapshot(self.data)


class _Transaction:
    def set(self, ref, updates, merge=False):
        assert merge
        for key, value in updates.items():
            if value is firestore.DELETE_FIELD:
                ref.data.pop(key, None)
            else:
                ref.data[key] = value


def _claim(ref, job_id, now):
    return sync_ledger._claim_transaction.to_wrap(_Transaction(), ref, job_id, 'backfill', now)


def _fail(ref, job_id, now, key, fingerprint=None):
    return sync_ledger._release_claim_transaction.to_wrap(
        _Transaction(), ref, job_id, now, None, None, key, fingerprint
    )


def test_three_identical_invalid_audio_failures_pause_same_content_without_acknowledging_it():
    ref = _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    for index in range(3):
        now = start + timedelta(minutes=index)
        job_id = f'job-{index}'
        assert _claim(ref, job_id, now)['outcome'] == 'owned'
        assert _fail(ref, job_id, now, 'invalid_audio')
    assert ref.data['status'] == 'retryable'
    capped = _claim(ref, 'job-3', start + timedelta(minutes=3))
    assert capped['outcome'] == 'capped'
    assert capped['failure_key'] == 'invalid_audio'
    assert 1 <= capped['retry_after'] <= 86400
    assert ref.data['status'] == 'retryable'
    assert _claim(ref, 'job-4', start + timedelta(days=1, minutes=3))['outcome'] == 'owned'


def test_retry_strikes_are_owner_fenced_and_transient_releases_do_not_increment():
    ref = _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert _claim(ref, 'first', start)['outcome'] == 'owned'
    assert not _fail(ref, 'stale', start, 'invalid_audio')
    assert _fail(ref, 'first', start, 'invalid_audio')
    assert not _fail(ref, 'first', start, 'invalid_audio')
    assert ref.data['repeat_failure_count'] == 1
    assert _claim(ref, 'second', start + timedelta(minutes=1))['outcome'] == 'owned'
    assert _fail(ref, 'second', start + timedelta(minutes=1), None)
    assert 'repeat_failure_count' not in ref.data
    assert _claim(ref, 'third', start + timedelta(days=2))['outcome'] == 'owned'
    assert _fail(ref, 'third', start + timedelta(days=2), 'invalid_audio')
    assert ref.data['repeat_failure_count'] == 1


_CLASSIFIED_FINGERPRINTS = [
    'persistence:ValueError',
    'persistence:TypeError',
    'persistence:provenance_mismatch',
    'persistence:redirect_cycle',
    'persistence:document_size_limit',
    'persistence:mixed',
]


@pytest.mark.parametrize('fingerprint', _CLASSIFIED_FINGERPRINTS)
def test_classified_persistence_failure_pauses_on_the_third_strike_and_is_readmitted(fingerprint):
    failing, healthy = _Ref(), _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    for index in range(3):
        now = start + timedelta(minutes=index)
        # The first and second strike never pause: each retry is still admitted.
        assert _claim(failing, f'bad-{index}', now)['outcome'] == 'owned'
        failing.data['partial_result'] = {'new_memories': ['retained']}
        failing.data['processed_segment_ids'] = ['healthy-sibling']
        assert _fail(failing, f'bad-{index}', now, 'persistent_persistence', fingerprint)
        assert failing.data['repeat_failure_count'] == index + 1
        assert ('repeat_failure_pause_until' in failing.data) is (index == 2)
    third = start + timedelta(minutes=2)
    assert failing.data['status'] == 'retryable'
    # Bounded, never permanent: the ledger TTL stays and no forever flag exists.
    assert failing.data['expires_at'] == third + timedelta(days=sync_ledger.LEDGER_RETENTION_DAYS)
    assert failing.data['repeat_failure_pause_until'] == third + sync_ledger.REPEAT_FAILURE_PAUSE
    assert 'persistence_quarantined' not in failing.data
    capped = _claim(failing, 'bad-3', start + timedelta(minutes=3))
    assert capped['outcome'] == 'capped' and capped['failure_key'] == 'persistent_persistence'
    assert 1 <= capped['retry_after'] <= 86400 and 'quarantined' not in capped
    assert _claim(failing, 'bad-4', third + timedelta(hours=24, seconds=-1))['outcome'] == 'capped'
    assert _claim(healthy, 'good-0', start + timedelta(minutes=3))['outcome'] == 'owned'
    # The pause expires by itself; sibling checkpoints survive it.
    readmitted = third + timedelta(hours=24)
    assert _claim(failing, 'bad-5', readmitted)['outcome'] == 'owned'
    assert failing.data['partial_result'] == {'new_memories': ['retained']}
    assert failing.data['processed_segment_ids'] == ['healthy-sibling']
    # A still-failing item starts a new three-strike window, not an instant pause.
    assert _fail(failing, 'bad-5', readmitted, 'persistent_persistence', fingerprint)
    assert failing.data['repeat_failure_count'] == 1
    assert 'repeat_failure_pause_until' not in failing.data
    assert _claim(failing, 'bad-6', readmitted + timedelta(minutes=1))['outcome'] == 'owned'


def test_bad_deploy_for_an_hour_does_not_pause_before_the_third_strike_and_recovers():
    """A TypeError from a bad deploy is a strike, never a first-occurrence stop."""
    assert _persistence_failure_fingerprint(TypeError('bad deploy'), 'persistence') == 'persistence:TypeError'
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)

    # Fixed after two failures: the item was never paused and its streak clears.
    fixed_early = _Ref()
    for index in range(2):
        now = start + timedelta(minutes=20 * index)
        assert _claim(fixed_early, f'job-{index}', now)['outcome'] == 'owned'
        assert _fail(fixed_early, f'job-{index}', now, 'persistent_persistence', 'persistence:TypeError')
    after_fix = start + timedelta(hours=1)
    assert _claim(fixed_early, 'after-fix', after_fix)['outcome'] == 'owned'
    completed = sync_ledger._mark_completed_transaction.to_wrap(
        _Transaction(),
        fixed_early,
        'after-fix',
        {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'},
        after_fix,
    )
    assert completed and fixed_early.data['status'] == 'completed'

    # Three failures inside the hour: paused for 24 hours, then admitted again
    # with no operator repair, and the fixed code completes it.
    paused = _Ref()
    for index in range(3):
        now = start + timedelta(minutes=20 * index)
        assert _claim(paused, f'job-{index}', now)['outcome'] == 'owned'
        assert _fail(paused, f'job-{index}', now, 'persistent_persistence', 'persistence:TypeError')
    assert _claim(paused, 'during-pause', after_fix)['outcome'] == 'capped'
    released = start + timedelta(minutes=40) + sync_ledger.REPEAT_FAILURE_PAUSE
    assert _claim(paused, 'after-pause', released)['outcome'] == 'owned'
    assert sync_ledger._mark_completed_transaction.to_wrap(
        _Transaction(),
        paused,
        'after-pause',
        {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'},
        released,
    )
    assert paused.data['status'] == 'completed'


def test_partial_batch_earns_strikes_pauses_after_three_and_keeps_sibling_checkpoints():
    """Two healthy siblings must not let one failing segment retry forever."""
    ref = _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    release = sync_ledger._release_claim_after_job_retired_transaction.to_wrap
    for index in range(3):
        now = start + timedelta(minutes=index)
        job_id = f'job-{index}'
        assert _claim(ref, job_id, now)['outcome'] == 'owned'
        ref.data['partial_result'] = {'new_memories': ['sibling-a', 'sibling-b']}
        ref.data['processed_segment_ids'] = ['sibling-a', 'sibling-b']
        fingerprint = _whole_job_persistence_fingerprint(1, 3, ['persistence:provenance_mismatch'])
        job = {
            'status': 'partial_failure',
            'result': {'repeat_failure_key': 'persistent_persistence', 'repeat_failure_fingerprint': fingerprint},
        }
        # The router's terminal cleanup carries the same strike as the worker.
        assert release(_Transaction(), ref, job_id, now, **_terminal_repeat_failure_kwargs(job))
        assert ref.data['repeat_failure_count'] == index + 1
    capped = _claim(ref, 'job-3', start + timedelta(minutes=3))
    assert capped['outcome'] == 'capped' and capped['failure_key'] == 'persistent_persistence'
    assert ref.data['partial_result'] == {'new_memories': ['sibling-a', 'sibling-b']}
    assert ref.data['processed_segment_ids'] == ['sibling-a', 'sibling-b']
    assert 'expires_at' in ref.data
    assert _claim(ref, 'job-4', start + timedelta(minutes=2) + sync_ledger.REPEAT_FAILURE_PAUSE)['outcome'] == 'owned'


def test_polling_release_records_strike_once_for_the_terminal_owner():
    ref = _Ref()
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert _claim(ref, 'job', now)['outcome'] == 'owned'
    kwargs = _terminal_repeat_failure_kwargs({'status': 'failed', 'reason_code': 'sync_invalid_audio'})
    release = sync_ledger._release_claim_after_job_retired_transaction.to_wrap
    assert release(_Transaction(), ref, 'job', now, **kwargs)
    assert not release(_Transaction(), ref, 'job', now, **kwargs)
    assert ref.data['repeat_failure_count'] == 1
    assert _terminal_repeat_failure_kwargs(
        {
            'status': 'failed',
            'result': {
                'repeat_failure_key': 'persistent_persistence',
                'repeat_failure_fingerprint': 'persistence:ValueError',
            },
        }
    ) == {'failure_key': 'persistent_persistence', 'failure_fingerprint': 'persistence:ValueError'}
    assert _terminal_repeat_failure_kwargs({'status': 'failed', 'reason_code': 'stt_invalid_input'}) == {}
    assert _terminal_repeat_failure_kwargs({'status': 'partial_failure', 'reason_code': 'sync_invalid_audio'}) == {}


def test_only_known_data_shape_persistence_errors_receive_fingerprints():
    assert _persistence_failure_fingerprint(ValueError('shape'), 'persistence') == 'persistence:ValueError'
    assert _persistence_failure_fingerprint(TypeError('shape'), 'persistence') == 'persistence:TypeError'
    assert _persistence_failure_fingerprint(ValueError('shape'), 'provider_call') is None
    assert _persistence_failure_fingerprint(SyncAssignmentConflict('provenance mismatch'), 'persistence') is None
    assert _persistence_failure_fingerprint(RuntimeError('unknown'), 'persistence') is None
    wrapped = FirestoreContentionExhausted('retry exhausted')
    wrapped.__cause__ = Aborted('contention')
    assert _persistence_failure_fingerprint(wrapped, 'persistence') is None
    wrapped_shape = ValueError('wrapped')
    wrapped_shape.__cause__ = ServiceUnavailable('unavailable')
    assert _persistence_failure_fingerprint(wrapped_shape, 'persistence') is None
    assert _persistence_failure_fingerprint(ServiceUnavailable('unavailable'), 'persistence') is None
    assert _persistence_failure_fingerprint(TimeoutError('timeout'), 'persistence') is None


def test_one_classified_segment_failure_gives_a_partial_or_mixed_batch_a_strike():
    fingerprint = 'persistence:ValueError'
    assert _whole_job_persistence_fingerprint(2, 2, [fingerprint, fingerprint]) == fingerprint
    # Differing fingerprints collapse to one bounded token on the same cap.
    mixed = _whole_job_persistence_fingerprint(2, 2, [fingerprint, 'persistence:TypeError'])
    assert mixed == 'persistence:mixed'
    assert sync_ledger._validated_failure_fingerprint('persistent_persistence', mixed) == mixed
    assert _whole_job_persistence_fingerprint(2, 3, [fingerprint, fingerprint]) == fingerprint
    assert _whole_job_persistence_fingerprint(2, 2, [fingerprint]) == fingerprint
    # No classified failure, or no failure at all: never a strike.
    assert _whole_job_persistence_fingerprint(2, 2, []) is None
    assert _whole_job_persistence_fingerprint(0, 2, [fingerprint]) is None
    result = {'repeat_failure_key': 'persistent_persistence', 'repeat_failure_fingerprint': fingerprint}
    assert _terminal_repeat_failure_kwargs({'status': 'partial_failure', 'result': result}) == {
        'failure_key': 'persistent_persistence',
        'failure_fingerprint': fingerprint,
    }
    assert _terminal_repeat_failure_kwargs({'status': 'completed', 'result': result}) == {}


def test_different_or_unclassified_persistence_failures_reset_the_streak():
    ref = _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    fingerprints = ['persistence:ValueError', 'persistence:TypeError', 'persistence:ValueError']
    for index, fingerprint in enumerate(fingerprints):
        now = start + timedelta(minutes=index)
        assert _claim(ref, f'job-{index}', now)['outcome'] == 'owned'
        assert _fail(ref, f'job-{index}', now, 'persistent_persistence', fingerprint)
    assert ref.data['repeat_failure_count'] == 1
    assert ref.data['repeat_failure_fingerprint'] == 'persistence:ValueError'
    assert _claim(ref, 'unknown', start + timedelta(minutes=3))['outcome'] == 'owned'
    assert _fail(ref, 'unknown', start + timedelta(minutes=3), 'persistent_persistence', 'persistence:OtherException')
    assert 'repeat_failure_count' not in ref.data
    assert _claim(ref, 'conflict', start + timedelta(minutes=4))['outcome'] == 'owned'
    assert _fail(ref, 'conflict', start + timedelta(minutes=4), None)
    assert 'repeat_failure_count' not in ref.data


@pytest.mark.parametrize('subtype', ['provenance_mismatch', 'redirect_cycle'])
def test_classified_assignment_conflicts_are_strikes_by_subtype(subtype):
    assert (
        _persistence_failure_fingerprint(SyncAssignmentConflict('private detail', subtype=subtype), 'persistence')
        == f'persistence:{subtype}'
    )


def test_only_recognized_document_size_invalid_argument_is_a_strike():
    size = InvalidArgument('Document private-id exceeds the maximum allowed size')
    assert _persistence_failure_fingerprint(size, 'persistence') == 'persistence:document_size_limit'
    for error in (InvalidArgument('transaction has expired'), InvalidArgument('unknown private detail')):
        assert _persistence_failure_fingerprint(error, 'persistence') is None
    assert _persistence_failure_fingerprint(size, 'provider_call') is None


def test_whole_job_provider_invalid_input_reaches_existing_app_terminal_reason():
    status, total, failed, updates = sync_jobs._sync_job_finalization_updates(
        {
            'total_segments': 1,
            'failed_segments': 1,
            'errors': ['stt_invalid_input'],
            'reason_code': 'stt_invalid_input',
        },
        completed_at=0,
    )
    assert (status, total, failed, updates['reason_code']) == ('failed', 1, 1, 'stt_invalid_input')
    assert (
        sync_jobs._sync_job_finalization_updates(
            {'total_segments': 1, 'failed_segments': 1, 'errors': ['stt_upstream_error']}, completed_at=0
        )[3]['reason_code']
        is None
    )


@pytest.mark.parametrize(
    'error',
    [
        SyncAssignmentConflict('wrapped', subtype='provenance_mismatch'),
        InvalidArgument('exceeds the maximum allowed size'),
    ],
)
def test_classified_error_wrapping_transport_is_never_a_strike(error):
    error.__cause__ = ServiceUnavailable('transient')
    assert _persistence_failure_fingerprint(error, 'persistence') is None
