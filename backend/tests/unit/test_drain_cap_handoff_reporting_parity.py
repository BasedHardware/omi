"""Cap-exhausted drain handoff reporting parity.

The deferred publication-drain lane's whole budget spent inside one
contention storm is a designed handoff to the maintenance ready page, not a
fault: the terminal report leaves the ERROR fault channel and logs WARNING
``event=batch_merge_drain outcome=maintenance_backstop`` with the spent
attempt, the lane cap, the stamped storm window and the validated losing
operation label. Non-contention faults keep the historical
``event=batch_merge outcome=retry`` ERROR line byte-for-byte at both catch
sites. These pins fail when code and contract drift apart in either
direction.

Failure-Class: FC-drain-cap-storm-handoff-booked-as-production-error
"""

import asyncio
import inspect
import logging
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import utils.batch_pipeline.pump as pump_module
from database.firestore_transaction_retry import FirestoreContentionExhausted
from database.jobstore.postgres_store import JobStoreContentionExhausted
from utils.batch_pipeline.pump import (
    DRAIN_BACKLOG_CONTINUATION_ATTEMPTS,
    DRAIN_RETRY_MAX_ATTEMPTS,
    contention_retry_after,
    deferred_drain_delay,
    drain_backstop_report,
    publication_loss_is_contention,
)
from utils.batch_pipeline.pump import Pump

FC = 'FC-drain-cap-storm-handoff-booked-as-production-error'
DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-deferred-drain-convergence.md'
PUMP_SOURCE = inspect.getsource(pump_module)

EXHAUSTED = 'chain budget burned'


def chain_exhaustion(**stamps):
    return FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {EXHAUSTED}', **stamps)


class ScriptScheduler:
    def __init__(self):
        self.store = self
        self.calls = []

    def defer(self, segment_id, token, now, retry_after=30, held_reason=None, admission_refused=False):
        self.calls.append(('defer', segment_id, retry_after, held_reason, admission_refused))
        return True

    def fail(self, segment_id, token, now, **kwargs):
        self.calls.append(('fail', segment_id, kwargs))
        return True

    def complete(self, result, token, now):
        self.calls.append(('complete', result.segment_id))
        return True

    def release(self, segment_id, token, now):
        self.calls.append(('release', segment_id))
        return True

    def heartbeat(self, segment_id, token, now):
        return True

    def probe(self, table, key):
        return {'owner_id': 'owner-1'} if key.startswith('seg') else {}


class ScriptMerge:
    def __init__(self):
        self.held_owners = set()
        self.drained = []
        self.marked_page_result = []
        self.released = []
        self.commit_script = {}

    def marked_page(self, limit=50):
        return self.marked_page_result

    def release_hold(self, key, *, force=False):
        self.released.append((key, force))

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        script = self.commit_script.get(owner_id) or []
        if script:
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return None


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):
    """Run the pump's blocking leaves inline on the event loop."""

    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


def make_pump(**overrides):
    scheduler = overrides.pop('scheduler', None) or ScriptScheduler()
    merge = overrides.pop('merge', None) or ScriptMerge()
    pump = Pump(
        scheduler,
        SimpleNamespace(),
        merge=merge,
        publish_concurrency=overrides.pop('publish_concurrency', 1),
        on_committed=overrides.pop('on_committed', None),
    )
    for name, value in overrides.items():
        setattr(pump, name, value)
    return pump


async def _drive_publication_boundary_to_cap(pump, owner='owner-1'):
    """Lose the publication boundary until the ledger refuses to re-arm."""
    now = 1000.0
    pump._monotonic = lambda: now
    for _ in range(64):
        now += 30.0
        await pump._drain_after_publication(owner)
        if not pump._deferred_drains:
            break
    await pump.flush_deferred_drains()


async def _drive_due_lane_to_cap(pump, owner='owner-1', *, continuation=False):
    """Arm once, then lose the due-lane re-drains until the cap refuses."""
    now = 1000.0
    pump._monotonic = lambda: now
    assert pump._defer_drain(owner, continuation=continuation)
    for _ in range(64):
        now += 30.0
        await pump._drain_deferred_due()
        if not pump._deferred_drains:
            break
    await pump.flush_deferred_drains()


# --------------------------------------------------------------------------
# Site 1 — the publication boundary catch (_drain_after_publication)
# --------------------------------------------------------------------------


async def test_cap_contention_reports_the_maintenance_backstop_not_an_error(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=2.5, operation='batch_merge_commit')

    pump.merge.commit_next = always_hot
    await _drive_publication_boundary_to_cap(pump)
    backstop = [r for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert backstop[0].levelno == logging.WARNING
    assert backstop[0].getMessage() == (
        'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 '
        'retry_after_ms=2500 operation=batch_merge_commit exception_type=FirestoreContentionExhausted'
    )
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == []


async def test_cap_fault_keeps_the_historical_error_line_byte_for_byte(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_broken(owner_id, now):
        raise ValueError('revoked owner')

    pump.merge.commit_next = always_broken
    await _drive_publication_boundary_to_cap(pump)
    retry = [r.getMessage() for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert retry == ['event=batch_merge outcome=retry exception_type=ValueError']
    assert all(
        r.levelno == logging.ERROR
        for r in caplog.records
        if 'event=batch_merge' in r.getMessage() and 'outcome=retry' in r.getMessage()
    )
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert backstop == []


async def test_cap_contention_clamps_the_stamped_window_at_the_lane_max(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=20.0, operation='take')

    pump.merge.commit_next = always_hot
    await _drive_publication_boundary_to_cap(pump)
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert 'retry_after_ms=8000' in backstop[0]


async def test_cap_contention_reports_an_unstamped_window_as_zero(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion()

    pump.merge.commit_next = always_hot
    await _drive_publication_boundary_to_cap(pump)
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert 'retry_after_ms=0' in backstop[0]
    assert ' operation=' not in backstop[0]


async def test_cap_contention_omits_a_hostile_operation_label(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=1.0, operation='drop table owners')

    pump.merge.commit_next = always_hot
    await _drive_publication_boundary_to_cap(pump)
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert ' operation=' not in backstop[0]


async def test_cap_contention_accepts_the_postgres_jobstore_exhaustion(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise JobStoreContentionExhausted(
            'pg chain exhausted', retry_after=4.0, operation='batch_claim shard=scheduler_07'
        )

    pump.merge.commit_next = always_hot
    await _drive_publication_boundary_to_cap(pump)
    backstop = [r for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert backstop[0].levelno == logging.WARNING
    assert 'exception_type=JobStoreContentionExhausted' in backstop[0].getMessage()
    assert ' operation=batch_claim shard=scheduler_07' in backstop[0].getMessage()


async def test_cap_contention_reports_the_spent_attempt_budget(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=0.5)

    pump.merge.commit_next = always_hot
    now = 1000.0
    pump._monotonic = lambda: now
    for attempt in range(1, DRAIN_RETRY_MAX_ATTEMPTS + 1):
        now += 30.0
        await pump._drain_after_publication('owner-1')
        deferred = [r.getMessage() for r in caplog.records if 'outcome=deferred' in r.getMessage()]
        assert len(deferred) == attempt
    now += 30.0
    await pump._drain_after_publication('owner-1')
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert 'attempt=6' in backstop[0]
    assert 'cap=6' in backstop[0]
    await pump.flush_deferred_drains()


# --------------------------------------------------------------------------
# Site 2 — the due-lane catch (_drain_deferred_due)
# --------------------------------------------------------------------------


async def test_due_lane_cap_contention_reports_attempt_and_cap(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=1.5, operation='handoff')

    pump.merge.commit_next = always_hot
    await _drive_due_lane_to_cap(pump)
    backstop = [r for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert backstop[0].levelno == logging.WARNING
    assert backstop[0].getMessage() == (
        'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 '
        'retry_after_ms=1500 operation=handoff exception_type=FirestoreContentionExhausted'
    )
    retry = [r.getMessage() for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert retry == []


async def test_due_lane_cap_fault_keeps_the_historical_error_line(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_broken(owner_id, now):
        raise TimeoutError('db leaf timed out')

    pump.merge.commit_next = always_broken
    await _drive_due_lane_to_cap(pump)
    retry = [r.getMessage() for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert len(retry) == 1
    assert 'exception_type=TimeoutError' in retry[0]
    assert ' attempt=6' in retry[0]
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert backstop == []


async def test_continuation_cap_contention_reports_the_continuation_cap(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=0.25, operation='reap')

    pump.merge.commit_next = always_hot
    await _drive_due_lane_to_cap(pump, continuation=True)
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert 'cap=4' in backstop[0]
    assert 'attempt=4' in backstop[0]
    assert 'retry_after_ms=250' in backstop[0]
    assert DRAIN_BACKLOG_CONTINUATION_ATTEMPTS == 4


async def test_due_lane_deferrals_stay_info_until_the_cap(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion()

    pump.merge.commit_next = always_hot
    now = 1000.0
    pump._monotonic = lambda: now
    assert pump._defer_drain('owner-1')
    for attempt in range(1, DRAIN_RETRY_MAX_ATTEMPTS):
        now += 30.0
        await pump._drain_deferred_due()
        deferred = [r for r in caplog.records if 'outcome=deferred' in r.getMessage()]
        assert len(deferred) == attempt
        assert all(r.levelno == logging.INFO for r in deferred)
    await pump.flush_deferred_drains()


async def test_converged_re_drain_stays_info(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()
    now = 1000.0
    pump._monotonic = lambda: now
    assert pump._defer_drain('owner-1')
    now += 30.0
    await pump._drain_deferred_due()
    converged = [r.getMessage() for r in caplog.records if 'outcome=converged' in r.getMessage()]
    assert converged == ['event=batch_merge_drain outcome=converged attempt=1']
    assert pump._deferred_drains == {}


async def test_flush_still_clears_the_ledger():
    pump = make_pump()
    assert pump._defer_drain('owner-1')
    await pump.flush_deferred_drains()
    assert pump._deferred_drains == {}


# --------------------------------------------------------------------------
# The pure report helper — exact (level, line) pins
# --------------------------------------------------------------------------


def test_report_for_the_canonical_stamped_storm():
    error = chain_exhaustion(retry_after=2.5, operation='batch_merge_commit')
    assert drain_backstop_report(error, attempt=6, cap=6) == (
        30,
        'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 '
        'retry_after_ms=2500 operation=batch_merge_commit exception_type=FirestoreContentionExhausted',
    )


def test_report_boundaries_of_the_storm_window():
    unstamped = chain_exhaustion()
    at_cap = chain_exhaustion(retry_after=8.0)
    over_cap = chain_exhaustion(retry_after=12.0)
    below_cap = chain_exhaustion(retry_after=7.99)
    assert 'retry_after_ms=0' in drain_backstop_report(unstamped, attempt=1, cap=6)[1]
    assert 'retry_after_ms=8000' in drain_backstop_report(at_cap, attempt=1, cap=6)[1]
    assert 'retry_after_ms=8000' in drain_backstop_report(over_cap, attempt=1, cap=6)[1]
    assert 'retry_after_ms=7990' in drain_backstop_report(below_cap, attempt=1, cap=6)[1]


def test_report_hostile_stamps_collapse_to_zero_and_never_raise():
    for hostile in (True, False, '4.2', None, float('nan'), float('inf'), float('-inf'), -4.2, 0):
        carrier = SimpleNamespace(retry_after=hostile, operation='take')
        level, line = drain_backstop_report(carrier, attempt=3, cap=4)
        assert level == logging.WARNING
        assert 'retry_after_ms=0' in line
        assert 'exception_type=SimpleNamespace' in line


def test_report_deep_but_finite_stamp_clamps_at_the_lane_max():
    carrier = SimpleNamespace(retry_after=1e308, operation='take')
    level, line = drain_backstop_report(carrier, attempt=3, cap=4)
    assert level == logging.WARNING
    assert 'retry_after_ms=8000' in line


def test_report_composite_and_absent_labels():
    composite = chain_exhaustion(retry_after=1.0, operation='batch_pull shard=scheduler_63')
    absent = chain_exhaustion(retry_after=1.0)
    assert ' operation=batch_pull shard=scheduler_63 ' in drain_backstop_report(composite, attempt=2, cap=4)[1]
    assert ' operation=' not in drain_backstop_report(absent, attempt=2, cap=4)[1]


def test_contention_retry_after_reads_only_positive_finite_windows():
    assert contention_retry_after(None) == 0.0
    assert contention_retry_after(ValueError('foreign')) == 0.0
    assert contention_retry_after(chain_exhaustion(retry_after=True)) == 1.0
    assert contention_retry_after(SimpleNamespace(retry_after=float('nan'))) == 0.0
    assert contention_retry_after(chain_exhaustion(retry_after=100.0)) == 8.0


def test_loss_classifier_keeps_faults_out_of_the_handoff():
    assert publication_loss_is_contention(chain_exhaustion()) is True
    assert publication_loss_is_contention(JobStoreContentionExhausted('pg')) is True
    assert publication_loss_is_contention(ValueError('fault')) is False
    assert publication_loss_is_contention(TimeoutError('db')) is False
    assert publication_loss_is_contention(None) is False


def test_deferred_drain_delay_shape_is_unchanged():
    assert [deferred_drain_delay(a) for a in range(1, 7)] == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]
    assert deferred_drain_delay(99) == 8.0


# --------------------------------------------------------------------------
# Contract preservation — the channels this change must not touch
# --------------------------------------------------------------------------


def test_engine_exhaustion_signal_stays_error_in_the_retry_engine():
    import database.firestore_transaction_retry as retry_module

    source = inspect.getsource(retry_module)
    assert 'outcome=exhausted' in source
    assert 'logger.error' in source


def test_completion_lane_terminal_stays_in_pump_source():
    assert 'event=batch_completion outcome=retry exception_type=%s' in PUMP_SOURCE


def test_fault_terminal_line_shape_unchanged_at_both_sites():
    assert "'event=batch_merge outcome=retry exception_type=%s'" in PUMP_SOURCE
    assert PUMP_SOURCE.count("'event=batch_merge outcome=retry exception_type=%s'") == 1
    assert PUMP_SOURCE.count("'event=batch_merge outcome=retry exception_type=%s attempt=%d'") == 2


async def test_flush_cap_contention_reports_the_maintenance_backstop(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise chain_exhaustion(retry_after=3.0, operation='paid')

    pump.merge.commit_next = always_hot
    assert pump._defer_drain('owner-1')
    await pump.flush_deferred_drains()
    backstop = [r for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert len(backstop) == 1
    assert backstop[0].levelno == logging.WARNING
    assert backstop[0].getMessage() == (
        'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 '
        'retry_after_ms=3000 operation=paid exception_type=FirestoreContentionExhausted'
    )
    retry = [r.getMessage() for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert retry == []


async def test_flush_cap_fault_keeps_the_historical_error_line(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_broken(owner_id, now):
        raise KeyError('owner row gone')

    pump.merge.commit_next = always_broken
    assert pump._defer_drain('owner-1')
    await pump.flush_deferred_drains()
    retry = [r.getMessage() for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert retry == ['event=batch_merge outcome=retry exception_type=KeyError attempt=1']
    backstop = [r.getMessage() for r in caplog.records if 'outcome=maintenance_backstop' in r.getMessage()]
    assert backstop == []


def test_backstop_line_shape_present_in_pump_source():
    assert (
        'event=batch_merge_drain outcome=maintenance_backstop attempt=%d cap=%d retry_after_ms=%d%s exception_type=%s'
        in PUMP_SOURCE
    )


# --------------------------------------------------------------------------
# Doc parity — the contract page is the record of the reporting change
# --------------------------------------------------------------------------


def docs_text():
    return DOCS.read_text()


def test_doc_documents_the_backstop_line():
    assert 'event=batch_merge_drain outcome=maintenance_backstop' in docs_text()


def test_doc_keeps_the_historical_fault_line():
    assert 'event=batch_merge outcome=retry exception_type=...' in docs_text()


def test_doc_names_the_honest_channel_section():
    assert 'The cap-exhausted handoff reports on its honest channel' in docs_text()


def test_doc_carries_the_failure_class():
    assert FC in docs_text()
    assert FC in PUMP_SOURCE


def test_doc_states_the_storm_never_changes_whether_convergence_lands():
    text = ' '.join(docs_text().split())
    assert (
        'A storm shifts WHEN convergence lands (the sweep), never whether it lands: the durable backstop is unchanged'
        in text
    )


def test_doc_states_faults_keep_the_historical_line():
    assert 'non-contention faults keep the historical ERROR line byte-for-byte' in docs_text()
