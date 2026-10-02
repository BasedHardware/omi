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


@pytest.mark.parametrize(
    'fingerprint',
    [
        'persistence:ValueError',
        'persistence:provenance_mismatch',
        'persistence:redirect_cycle',
        'persistence:document_size_limit',
        'persistence:deterministic',
    ],
)
def test_deterministic_failure_quarantines_only_its_content_without_ttl(fingerprint):
    failing, healthy = _Ref(), _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert _claim(failing, 'bad', start)['outcome'] == 'owned'
    failing.data['partial_result'] = {'new_memories': ['retained']}
    assert _fail(failing, 'bad', start, 'persistent_persistence', fingerprint)
    assert failing.data['status'] == 'retryable'
    assert 'expires_at' not in failing.data
    assert failing.data['partial_result'] == {'new_memories': ['retained']}
    for days in (0, 1, 46, 365):
        capped = _claim(failing, 'retry', start + timedelta(days=days))
        assert capped['outcome'] == 'capped' and capped['quarantined']
    assert _claim(healthy, 'good', start)['outcome'] == 'owned'


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


def test_partial_and_mixed_failures_cannot_rearm_deterministic_work():
    fingerprint = 'persistence:ValueError'
    assert _whole_job_persistence_fingerprint(2, 2, [fingerprint, fingerprint]) == fingerprint
    assert (
        _whole_job_persistence_fingerprint(2, 2, [fingerprint, 'persistence:TypeError']) == 'persistence:deterministic'
    )
    assert _whole_job_persistence_fingerprint(2, 3, [fingerprint, fingerprint]) == fingerprint
    assert _whole_job_persistence_fingerprint(2, 2, [fingerprint]) == fingerprint
    assert _whole_job_persistence_fingerprint(2, 2, []) is None
    result = {'repeat_failure_key': 'persistent_persistence', 'repeat_failure_fingerprint': fingerprint}
    assert _terminal_repeat_failure_kwargs({'status': 'partial_failure', 'result': result}) == {
        'failure_key': 'persistent_persistence',
        'failure_fingerprint': fingerprint,
    }


def test_unknown_persistence_error_does_not_quarantine():
    ref = _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert _claim(ref, 'job', start)['outcome'] == 'owned'
    assert _fail(ref, 'job', start, 'persistent_persistence', 'persistence:OtherException')
    assert 'persistence_quarantined' not in ref.data
    assert _claim(ref, 'retry', start)['outcome'] == 'owned'


@pytest.mark.parametrize('subtype', ['provenance_mismatch', 'redirect_cycle'])
def test_structural_assignment_conflicts_are_quarantined_by_subtype(subtype):
    assert (
        _persistence_failure_fingerprint(SyncAssignmentConflict('private detail', subtype=subtype), 'persistence')
        == f'persistence:{subtype}'
    )


def test_only_recognized_document_size_invalid_argument_is_quarantined():
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
