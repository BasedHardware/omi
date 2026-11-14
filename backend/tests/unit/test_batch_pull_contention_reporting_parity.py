"""Pull-lane contention reporting parity: the label stamp and the honest channels.

``FirestoreStore.run`` stamps the label that burned its contention budget onto
the raised exhaustion (``operation``, the same ride-along contract as
``retry_after``), and the scheduler's pull lane reports its two designed
outcomes on their honest channels: the storm response (the counted,
storm-aligned backoff the next pull cycle clears with no lost work) at INFO,
and the partial lease handoff (committed leases handed to the caller instead
of stranding them until lease expiry) at WARNING. The engine's
``outcome=exhausted`` line stays the single ERROR signal per storm. Each cell
below drives the real store, the real scheduler catch site or the real field
helper and pins the exact channel, level and fields.

Failure-Class: FC-pull-storm-response-and-lease-handoff-booked-as-production-errors
"""

import logging
from unittest.mock import Mock

import pytest

from config.batch_pipeline import pull_multi_lease_enabled
from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from google.api_core.exceptions import Aborted as FirestoreAborted
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem
from utils.batch_pipeline.scheduler import (
    Scheduler,
    contention_operation_field,
)

FC = 'FC-pull-storm-response-and-lease-handoff-booked-as-production-errors'


class AbortThenCommitTx:
    """Minimal firestore_v1.Transaction: the first ``abort_times`` commits abort."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        if self.abort_times > 0:
            self.abort_times -= 1
            raise FirestoreAborted('synthetic commit contention')
        self._id = None

    def _rollback(self):
        self._id = None


def exhausting_client(abort_times=10**6):
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(abort_times)
    return client


def healthy_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    return client


def silence_chain_sleep(monkeypatch):
    """Skip the retry chain's own jitter sleeps; the drive stays instant."""
    actual = run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def build_store(monkeypatch, client=None, namespace='batch_pipeline_dev'):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    # The damper kill switch keeps the drive off the shared process registry:
    # the stamp cells pin the bare-lane contract (retry_after 0.0, label stamped).
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    return storage.FirestoreStore(
        namespace, firestore_client=client if client is not None else exhausting_client(), storm_damper=None
    )


def exhaust_run(store, label):
    """Drive ``label`` to exhaustion once; return the raised chain."""
    try:
        store.run(lambda tx: True, operation=label)
    except FirestoreContentionExhausted as caught:
        return caught
    raise AssertionError('expected exhaustion')


def raised_exhaustion(**kwargs):
    """An exhaustion with a real traceback, so the site field has a frame."""
    try:
        raise exhaustion(**kwargs)
    except FirestoreContentionExhausted as caught:
        return caught


class _PullStore:
    """A pull-lane store stub: the scheduler drives the handler directly."""

    def run(self, body, *, operation=None):
        return body(None)


def exhaustion(stamp=None, operation=None):
    error = FirestoreContentionExhausted('bounded contention')
    if stamp is not None:
        error.retry_after = stamp
    if operation is not None:
        error.operation = operation
    return error


def work_item(segment='a' * 64):
    return WorkItem(
        segment_id=segment,
        owner_id='owner-1',
        capture_at=100.0,
        audio_uri='gs://bucket/owner/segment.enc#1',
        duration_seconds=2.0,
        priority=Priority.FRESH,
    )


def lease(item=None):
    return LeasedWork(item if item is not None else work_item(), 'token', 1, 220.0)


# --------------------------------------------------------------------------
# Section A — the exhaustion carries its label
# --------------------------------------------------------------------------


def test_exhaustion_defaults_stay_untouched():
    error = FirestoreContentionExhausted('bounded contention')
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == 0.0
    assert error.operation is None


def test_exhaustion_accepts_an_explicit_label():
    error = FirestoreContentionExhausted('bounded contention', operation='batch_fail')
    assert error.operation == 'batch_fail'
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == 0.0


def test_exhaustion_kwargs_stay_keyword_only():
    with pytest.raises(TypeError):
        FirestoreContentionExhausted('bounded contention', 'attempts_exhausted')  # noqa: wrap-ok


def test_worker_family_subclass_carries_the_label_contract():
    class _Sub(FirestoreContentionExhausted):
        pass

    error = _Sub('bounded contention', operation='batch_claim shard=scheduler_07')
    assert error.operation == 'batch_claim shard=scheduler_07'


# --------------------------------------------------------------------------
# Section B — the store stamps the label that burned the budget
# --------------------------------------------------------------------------


def test_store_run_stamps_the_plain_label(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_fail')
    assert error.operation == 'batch_fail'
    assert error.retry_after == 0.0


def test_store_run_stamps_the_merge_label(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.operation == 'batch_merge_commit'


def test_store_run_stamps_the_first_pull_shard_label(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_pull shard=scheduler_00')
    assert error.operation == 'batch_pull shard=scheduler_00'


def test_store_run_stamps_a_mid_pull_shard_label(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_pull shard=scheduler_31')
    assert error.operation == 'batch_pull shard=scheduler_31'


def test_store_run_stamps_the_last_pull_shard_label(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_pull shard=scheduler_63')
    assert error.operation == 'batch_pull shard=scheduler_63'


def test_store_run_stamps_the_claim_shard_label(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_claim shard=scheduler_07')
    assert error.operation == 'batch_claim shard=scheduler_07'


def test_stamped_exhaustion_still_returns_a_healthy_run(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch, client=healthy_client())
    assert store.run(lambda tx: 'ok', operation='batch_fail') == 'ok'


def test_bare_engine_raise_stays_unstamped(monkeypatch):
    """The bare engine has no label scope; only the labeled store run stamps."""
    silence_chain_sleep(monkeypatch)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')

    def body(transaction):
        raise FirestoreAborted('synthetic commit contention')

    with pytest.raises(FirestoreContentionExhausted) as caught:
        run_with_transaction_contention_retry(lambda: Mock(), body, operation_name='batch_fail')
    assert caught.value.operation is None
    assert caught.value.retry_after == 0.0


def test_a_foreign_body_fault_propagates_without_a_stamp(monkeypatch):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch, client=healthy_client())
    with pytest.raises(ValueError) as caught:
        store.run(lambda tx: (_ for _ in ()).throw(ValueError('refused')), operation='batch_fail')
    assert getattr(caught.value, 'operation', 'missing') == 'missing'


# --------------------------------------------------------------------------
# Section C — the pull lane reports its designed outcomes honestly
# --------------------------------------------------------------------------


def _capture_pull_backoff(monkeypatch, caplog, error, *, failures_first=0, generation=0):
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: 100.0)
    monkeypatch.setattr('utils.batch_pipeline.scheduler.random.random', lambda: 0.0)
    queue = Scheduler(_PullStore())
    queue._pull_one = Mock(side_effect=error)
    queue._contention_failures = failures_first
    queue._contention_generation = generation
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        result = queue.pull(1)
    records = [r for r in caplog.records if r.name == 'utils.batch_pipeline.scheduler']
    return result, records


def test_backoff_reports_at_info_with_the_stamped_label(monkeypatch, caplog):
    result, records = _capture_pull_backoff(
        monkeypatch, caplog, exhaustion(stamp=0.0, operation='batch_pull shard=scheduler_31')
    )
    assert result == []
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert 'event=batch_pull outcome=backoff failures=1 retry_after_ms=500' in record.getMessage()
    assert ' operation=batch_pull shard=scheduler_31' in record.getMessage()
    assert not any(r.levelno >= logging.ERROR for r in records)


def test_backoff_reports_the_measured_storm_window(monkeypatch, caplog):
    result, records = _capture_pull_backoff(
        monkeypatch, caplog, exhaustion(stamp=1.5, operation='batch_pull shard=scheduler_05')
    )
    assert result == []
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert 'retry_after_ms=1500' in records[0].getMessage()
    assert ' operation=batch_pull shard=scheduler_05' in records[0].getMessage()


def test_backoff_without_a_stamped_label_reports_no_operation_field(monkeypatch, caplog):
    result, records = _capture_pull_backoff(monkeypatch, caplog, exhaustion(stamp=2.0))
    assert result == []
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    message = records[0].getMessage()
    assert 'event=batch_pull outcome=backoff failures=1 retry_after_ms=2000' in message
    assert ' operation=' not in message


def test_backoff_counts_chained_failures_and_keeps_the_label(monkeypatch, caplog):
    now = [100.0]
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: now[0])
    monkeypatch.setattr('utils.batch_pipeline.scheduler.random.random', lambda: 0.5)
    queue = Scheduler(_PullStore())
    queue._pull_one = Mock(side_effect=[raised_exhaustion(operation='batch_pull shard=scheduler_00') for _ in range(2)])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        queue.pull(1)
        now[0] = queue._contention_backoff_until
        queue.pull(1)
    backoffs = [r for r in caplog.records if 'outcome=backoff' in r.getMessage()]
    assert len(backoffs) == 2
    assert all(r.levelno == logging.INFO for r in backoffs)
    assert 'failures=1' in backoffs[0].getMessage()
    assert 'failures=2' in backoffs[1].getMessage()
    assert all(' operation=batch_pull shard=scheduler_00' in r.getMessage() for r in backoffs)


def test_backoff_with_a_hostile_label_shape_reports_no_operation_field(monkeypatch, caplog):
    result, records = _capture_pull_backoff(monkeypatch, caplog, raised_exhaustion(operation='not a valid label!'))
    assert result == []
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert ' operation=' not in records[0].getMessage()


def test_backoff_keeps_the_site_field_last(monkeypatch, caplog):
    result, records = _capture_pull_backoff(
        monkeypatch, caplog, raised_exhaustion(operation='batch_pull shard=scheduler_00')
    )
    message = records[0].getMessage()
    assert ' site=' in message
    assert message.index(' operation=') < message.rindex(' site=')


def test_partial_handoff_reports_at_warning_and_keeps_the_leases(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'false')
    assert not pull_multi_lease_enabled()
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: 100.0)
    queue = Scheduler(_PullStore())
    queue._pull_one = Mock(side_effect=[[lease()], ValueError('late shard refused')])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        result = queue.pull(100.0, 2)
    assert len(result) == 1
    assert result[0].token == 'token'
    records = [r for r in caplog.records if r.name == 'utils.batch_pipeline.scheduler']
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert 'event=batch_pull outcome=partial leased=1 exception_type=ValueError' in record.getMessage()
    assert not any(r.levelno >= logging.ERROR for r in records)


def test_partial_handoff_after_a_contention_loss_takes_the_backoff_branch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'false')
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: 100.0)
    monkeypatch.setattr('utils.batch_pipeline.scheduler.random.random', lambda: 0.0)
    queue = Scheduler(_PullStore())
    queue._pull_one = Mock(side_effect=[[lease()], raised_exhaustion(operation='batch_pull shard=scheduler_02')])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        result = queue.pull(100.0, 2)
    records = [r for r in caplog.records if r.name == 'utils.batch_pipeline.scheduler']
    assert len(result) == 1
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert 'outcome=backoff' in records[0].getMessage()
    assert ' operation=batch_pull shard=scheduler_02' in records[0].getMessage()


def test_a_clean_pull_resets_the_storm_state(monkeypatch):
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: 100.0)
    queue = Scheduler(_PullStore())
    queue._pull_one = Mock(return_value=[lease()])
    queue._contention_failures = 3
    queue._contention_backoff_until = 50.0
    queue._contention_generation = 5
    assert queue.pull(1)
    assert queue._contention_failures == 0
    assert queue._contention_backoff_until == 0.0


def test_a_sibling_generation_bump_blocks_the_reset(monkeypatch):
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: 100.0)
    queue = Scheduler(_PullStore())

    def bump_and_lease(now, **_kwargs):
        queue._contention_generation += 1
        return [lease()]

    queue._pull_one = Mock(side_effect=bump_and_lease)
    queue._contention_failures = 3
    queue._contention_backoff_until = 50.0
    assert queue.pull(1)
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 50.0


# --------------------------------------------------------------------------
# Section D — the label field helper never interpolates hostile shapes
# --------------------------------------------------------------------------


def test_field_for_a_valid_plain_label():
    assert contention_operation_field(exhaustion(operation='batch_fail')) == ' operation=batch_fail'


def test_field_for_a_valid_composite_label():
    field = contention_operation_field(exhaustion(operation='batch_pull shard=scheduler_42'))
    assert field == ' operation=batch_pull shard=scheduler_42'


def test_field_for_a_missing_attribute():
    assert contention_operation_field(ValueError('foreign')) == ''


def test_field_for_none():
    assert contention_operation_field(exhaustion()) == ''


def test_field_for_a_hostile_type():
    class _Hostile:
        operation = 12345

    assert contention_operation_field(_Hostile()) == ''


def test_field_for_a_bool():
    class _Hostile:
        operation = True

    assert contention_operation_field(_Hostile()) == ''


def test_field_for_an_invalid_label_text():
    assert contention_operation_field(exhaustion(operation='drop table jobs')) == ''


def test_field_for_an_out_of_range_shard():
    assert contention_operation_field(exhaustion(operation='batch_pull shard=scheduler_99')) == ''


def test_field_for_an_empty_label():
    assert contention_operation_field(exhaustion(operation='')) == ''


# --------------------------------------------------------------------------
# Section E — the real stamped chain drives the real reporting lane
# --------------------------------------------------------------------------


def test_real_stamped_exhaustion_reports_info_with_the_exact_fields(monkeypatch, caplog):
    silence_chain_sleep(monkeypatch)
    store = build_store(monkeypatch)
    error = exhaust_run(store, 'batch_pull shard=scheduler_31')
    assert error.operation == 'batch_pull shard=scheduler_31'
    monkeypatch.setattr('utils.batch_pipeline.scheduler.monotonic', lambda: 100.0)
    monkeypatch.setattr('utils.batch_pipeline.scheduler.random.random', lambda: 0.0)
    queue = Scheduler(_PullStore())
    queue._pull_one = Mock(side_effect=error)
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        queue.pull(1)
    records = [r for r in caplog.records if r.name == 'utils.batch_pipeline.scheduler']
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert 'event=batch_pull outcome=backoff failures=1 retry_after_ms=500' in records[0].getMessage()
    assert ' operation=batch_pull shard=scheduler_31' in records[0].getMessage()
