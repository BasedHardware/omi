"""Content-keyed pause keeps retry material while bounding repeated paid work."""

from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import Aborted, ServiceUnavailable
from google.cloud import firestore

from database import sync_ledger, sync_jobs
from database.firestore_transaction_retry import FirestoreContentionExhausted
from routers.sync import _terminal_repeat_failure_kwargs
from utils.sync.assignment_errors import SyncAssignmentConflict
from utils.sync.pipeline import _persistent_persistence_failure


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


def _fail(ref, job_id, now, key):
    return sync_ledger._release_claim_transaction.to_wrap(_Transaction(), ref, job_id, now, None, None, key)


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
    assert ref.data['repeat_failure_count'] == 1
    assert _claim(ref, 'third', start + timedelta(days=2))['outcome'] == 'owned'
    assert _fail(ref, 'third', start + timedelta(days=2), 'invalid_audio')
    assert ref.data['repeat_failure_count'] == 1


def test_repeated_persistence_failure_pauses_only_its_content():
    failing = _Ref()
    healthy = _Ref()
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    for index in range(3):
        now = start + timedelta(minutes=index)
        assert _claim(failing, f'bad-{index}', now)['outcome'] == 'owned'
        assert _fail(failing, f'bad-{index}', now, 'persistent_persistence')
    assert _claim(failing, 'bad-3', start + timedelta(minutes=3))['outcome'] == 'capped'
    assert _claim(healthy, 'good-0', start + timedelta(minutes=3))['outcome'] == 'owned'


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
        {'status': 'failed', 'result': {'repeat_failure_key': 'persistent_persistence'}}
    ) == {'failure_key': 'persistent_persistence'}
    assert _terminal_repeat_failure_kwargs({'status': 'partial_failure', 'reason_code': 'sync_invalid_audio'}) == {}


def test_persistence_conflict_is_countable_but_firestore_contention_and_outages_are_not():
    assert _persistent_persistence_failure(SyncAssignmentConflict('provenance mismatch'))
    wrapped = FirestoreContentionExhausted('retry exhausted')
    wrapped.__cause__ = Aborted('contention')
    assert not _persistent_persistence_failure(wrapped)
    assert not _persistent_persistence_failure(ServiceUnavailable('unavailable'))
    assert not _persistent_persistence_failure(TimeoutError('timeout'))


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
