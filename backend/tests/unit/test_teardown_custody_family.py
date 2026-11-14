"""Teardown-custody family: the closed site table, classifier, channels, replay.

The pump's four flight-teardown exits -- the stop refund, the GPU-restart
refund, the skipped refund and the finished-lease release -- used to book
every exception on the ERROR fault channel, so one store storm reached the
production error sensor once more per refunded or released lease per
teardown. The closed contention class now reports on its honest channel
(WARNING for a lost refund, INFO for a finished lease's release) carrying
the losing store label, the attempt and the storm window the damper had
armed; real faults keep the historical lines byte-for-byte; a lost refund
replays on a bounded, storm-aligned schedule whose replays stay silent.

Failure-Class: FC-flight-custody-contention-losses-booked-as-production-faults
"""

import asyncio
import logging

import pytest
from google.api_core.exceptions import Aborted as FirestoreAborted
from google.api_core.exceptions import InvalidArgument as FirestoreInvalidArgument
from google.api_core.exceptions import NotFound as FirestoreNotFound
from google.api_core.exceptions import PermissionDenied as FirestorePermissionDenied

from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.pump import publication_loss_is_contention
from utils.batch_pipeline.scheduler import contention_operation_field
from utils.batch_pipeline.teardown_custody import (
    TEARDOWN_REPLAY_ATTEMPTS,
    TEARDOWN_REPLAY_BASE_SECONDS,
    TEARDOWN_REPLAY_MAX_SECONDS,
    TEARDOWN_REPLAY_STORM_MAX_SECONDS,
    TEARDOWN_SITES,
    LeaseTeardownSite,
    replay_teardown_refund,
    report_teardown_custody_loss,
    teardown_loss_is_contention,
    teardown_replay_delay,
    teardown_storm_after,
)

FC = 'FC-flight-custody-contention-losses-booked-as-production-faults'

RELEASE = TEARDOWN_SITES['release']
STOP_REFUND = TEARDOWN_SITES['stop_refund']
GPU_RESTART = TEARDOWN_SITES['gpu_restart_refund']
SKIPPED_REFUND = TEARDOWN_SITES['skipped_refund']

HISTORICAL_FAULT_LINES = {
    'stop_refund': 'event=batch_flight outcome=lease_recovery exception_type=%s',
    'gpu_restart_refund': 'event=batch_gpu_restart outcome=lease_recovery exception_type=%s',
    'skipped_refund': 'event=batch_flight outcome=lease_recovery exception_type=%s',
    'release': 'event=batch_flight outcome=lease_release exception_type=%s',
}


class Sink(logging.Handler):
    """Capture every record a drive emits, at every level."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def lines(self):
        return [record.getMessage() for record in self.records]


def sink_logger(name='utils.batch_pipeline.pump'):
    logger = logging.getLogger(name)
    sink = Sink()
    logger.addHandler(sink)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield logger, sink
    finally:
        logger.removeHandler(sink)
        logger.setLevel(old_level)


def raised(build):
    """Return the exception as a raise site produced it: real traceback attached."""
    try:
        raise build
    except BaseException as error:  # noqa: BLE001 - a real traceback is the point
        return error


def exhaustion(operation=None, **attrs):
    error = raised(FirestoreContentionExhausted('contention budget burned'))
    if operation is not None:
        attrs['operation'] = operation
    for key, value in attrs.items():
        setattr(error, key, value)
    return error


def cause_chain_contention():
    try:
        raise FirestoreAborted('read-time abort under load')
    except FirestoreAborted as cause:
        error = RuntimeError('teardown lost the race')
        error.__cause__ = cause
        return error


def expired_transaction():
    return raised(FirestoreInvalidArgument('transaction has expired, please retry'))


class JobStoreContentionExhausted(FirestoreContentionExhausted):
    """The Postgres job-store subclass the drain and re-strike lanes absorb."""


sink_logger = pytest.fixture(sink_logger)


# --- the closed site table -------------------------------------------------------


def test_the_site_table_is_exactly_the_four_teardown_exits():
    assert set(TEARDOWN_SITES) == {'stop_refund', 'gpu_restart_refund', 'skipped_refund', 'release'}


def test_site_rows_carry_the_historical_event_and_outcome_vocabulary():
    assert (STOP_REFUND.event, STOP_REFUND.outcome) == ('event=batch_flight', 'lease_recovery')
    assert (SKIPPED_REFUND.event, SKIPPED_REFUND.outcome) == ('event=batch_flight', 'lease_recovery')
    assert (GPU_RESTART.event, GPU_RESTART.outcome) == ('event=batch_gpu_restart', 'lease_recovery')
    assert (RELEASE.event, RELEASE.outcome) == ('event=batch_flight', 'lease_release')


def test_release_contention_reports_at_info_and_refunds_at_warning():
    assert RELEASE.contention_level == logging.INFO
    assert STOP_REFUND.contention_level == logging.WARNING
    assert SKIPPED_REFUND.contention_level == logging.WARNING
    assert GPU_RESTART.contention_level == logging.WARNING


def test_only_the_live_refund_sites_replay():
    assert STOP_REFUND.attempts == TEARDOWN_REPLAY_ATTEMPTS == 3
    assert SKIPPED_REFUND.attempts == TEARDOWN_REPLAY_ATTEMPTS
    assert GPU_RESTART.attempts == 1
    assert RELEASE.attempts == 1


def test_site_rows_are_frozen():
    frozen = STOP_REFUND
    with pytest.raises(Exception):
        setattr(frozen, 'event', 'event=batch_mutation')
    assert isinstance(frozen, LeaseTeardownSite)


# --- the closed contention class --------------------------------------------------


@pytest.mark.parametrize(
    'build',
    [
        lambda: exhaustion(),
        lambda: exhaustion(reason='deadline_exhausted'),
        lambda: JobStoreContentionExhausted('postgres budget burned'),
        lambda: raised(FirestoreAborted('read-time abort under load')),
        lambda: expired_transaction(),
        lambda: cause_chain_contention(),
    ],
)
def test_the_closed_contention_class_answers_true(build):
    assert teardown_loss_is_contention(build()) is True


@pytest.mark.parametrize(
    'build',
    [
        lambda: raised(FirestoreNotFound('job vanished')),
        lambda: raised(FirestorePermissionDenied('revoked owner')),
        lambda: raised(FirestoreInvalidArgument('plain 400 refusal')),
        lambda: raised(ValueError('payload refused')),
        lambda: raised(TimeoutError('deadline passed')),
        lambda: FatalGpuError('synthetic CUDA OOM'),
        lambda: raised(RuntimeError('write refused')),
        lambda: 'not an exception at all',
    ],
)
def test_everything_outside_the_closed_class_keeps_its_fault_verdict(build):
    assert teardown_loss_is_contention(build()) is False


def test_a_self_referential_cause_chain_never_classifies_forever():
    error = raised(RuntimeError('tangled chain'))
    error.__cause__ = error
    assert teardown_loss_is_contention(error) is False


def test_the_teardown_classifier_and_the_restrike_authority_agree():
    shapes = [
        exhaustion(operation='batch_defer'),
        JobStoreContentionExhausted('postgres'),
        raised(FirestoreAborted('abort')),
        expired_transaction(),
        cause_chain_contention(),
        raised(RuntimeError('write refused')),
        FatalGpuError('cuda'),
    ]
    for shape in shapes:
        assert teardown_loss_is_contention(shape) is publication_loss_is_contention(shape)


# --- the losing store label -------------------------------------------------------


@pytest.mark.parametrize(
    'operation,expected',
    [
        ('batch_defer', ' operation=batch_defer'),
        ('batch_release', ' operation=batch_release'),
        ('batch_pull shard=scheduler_07', ' operation=batch_pull shard=scheduler_07'),
        (None, ''),
        ('drop table jobs', ''),
        ('batch_pull shard=scheduler_99', ''),
        (7, ''),
    ],
)
def test_operation_field_renders_only_validated_labels(operation, expected):
    assert contention_operation_field(exhaustion(operation=operation)) == expected


def test_operation_field_on_a_foreign_exception_is_never_interpolated():
    assert contention_operation_field(ValueError('hostile')) == ''


# --- the storm window -------------------------------------------------------------


@pytest.mark.parametrize(
    'stamp,expected',
    [
        (0.0, 0.0),
        (0.25, 0.25),
        (0.5, 0.5),
        (1.0, 1.0),
        (2.0, 2.0),
        (4.0, 4.0),
        (5.0, 4.0),
        (99.0, 4.0),
    ],
)
def test_a_stamped_window_is_measured_and_clamped_at_the_damper_cap(stamp, expected):
    assert teardown_storm_after(exhaustion(retry_after=stamp)) == expected


@pytest.mark.parametrize(
    'build',
    [
        lambda: exhaustion(retry_after=True),
        lambda: exhaustion(retry_after=False),
        lambda: exhaustion(retry_after='0.5'),
        lambda: exhaustion(retry_after=float('nan')),
        lambda: exhaustion(retry_after=float('inf')),
        lambda: exhaustion(retry_after=-1.0),
        lambda: exhaustion(retry_after=None),
    ],
)
def test_hostile_stamps_collapse_to_the_ladder(build):
    assert teardown_storm_after(build()) == 0.0


def test_an_exhaustion_with_no_stamp_at_all_keeps_the_ladder():
    assert teardown_storm_after(exhaustion()) == 0.0


def test_foreign_exceptions_and_hostile_payloads_never_raise():
    assert teardown_storm_after(ValueError('foreign')) == 0.0
    assert teardown_storm_after(None) == 0.0


def test_a_cause_chain_contention_loss_has_no_damper_stamp():
    assert teardown_storm_after(cause_chain_contention()) == 0.0


def test_the_storm_cap_is_the_store_damper_window_cap():
    assert TEARDOWN_REPLAY_STORM_MAX_SECONDS == 4.0


# --- the bounded replay schedule ---------------------------------------------------


def test_the_ladder_doubles_from_the_base_and_caps():
    assert TEARDOWN_REPLAY_BASE_SECONDS == 0.25
    assert TEARDOWN_REPLAY_MAX_SECONDS == 2.0
    assert teardown_replay_delay(1) == 0.25
    assert teardown_replay_delay(2) == 0.5
    assert teardown_replay_delay(3) == 1.0
    assert teardown_replay_delay(4) == 2.0
    assert teardown_replay_delay(10) == 2.0


@pytest.mark.parametrize('hostile', [0, -1, True, False, 2.9, '2', None, [], {}])
def test_a_hostile_index_collapses_to_the_first_step(hostile):
    assert teardown_replay_delay(hostile) == TEARDOWN_REPLAY_BASE_SECONDS


def test_the_wait_raises_the_ladder_to_the_measured_window():
    assert max(teardown_replay_delay(1), teardown_storm_after(exhaustion(retry_after=1.0))) == 1.0
    assert max(teardown_replay_delay(2), teardown_storm_after(exhaustion(retry_after=0.1))) == 0.5


# --- the reporter ------------------------------------------------------------------


def test_foreign_faults_keep_the_historical_lines_byte_for_byte(sink_logger):
    logger, _ = sink_logger
    fault = raised(RuntimeError('write refused'))
    for site in TEARDOWN_SITES.values():
        report_teardown_custody_loss(logger, site=site, error=fault)
        assert _.lines()[-1] == HISTORICAL_FAULT_LINES[site.key] % 'RuntimeError'


def test_foreign_fault_lines_render_the_exception_name_only(sink_logger):
    logger, sink = sink_logger
    report_teardown_custody_loss(logger, site=STOP_REFUND, error=raised(RuntimeError('write refused')))
    assert sink.lines() == ['event=batch_flight outcome=lease_recovery exception_type=RuntimeError']
    assert sink.records[0].levelno == logging.ERROR
    assert sink.records[0].name == 'utils.batch_pipeline.pump'


def test_contention_on_a_refund_reports_at_warning_with_its_fields(sink_logger):
    logger, sink = sink_logger
    report_teardown_custody_loss(
        logger, site=STOP_REFUND, error=exhaustion(operation='batch_defer', retry_after=1.0), attempt=2
    )
    assert sink.lines() == [
        'event=batch_flight outcome=lease_recovery exception_type=FirestoreContentionExhausted'
        ' operation=batch_defer attempt=2 retry_after_ms=1000'
    ]
    assert sink.records[0].levelno == logging.WARNING


def test_release_contention_reports_at_info(sink_logger):
    logger, sink = sink_logger
    report_teardown_custody_loss(logger, site=RELEASE, error=exhaustion(operation='batch_release'), attempt=1)
    assert sink.lines() == [
        'event=batch_flight outcome=lease_release exception_type=FirestoreContentionExhausted'
        ' operation=batch_release attempt=1 retry_after_ms=0'
    ]
    assert sink.records[0].levelno == logging.INFO


def test_gpu_restart_contention_keeps_the_restart_event_prefix(sink_logger):
    logger, sink = sink_logger
    report_teardown_custody_loss(logger, site=GPU_RESTART, error=exhaustion(operation='batch_defer'))
    assert sink.lines() == [
        'event=batch_gpu_restart outcome=lease_recovery exception_type=FirestoreContentionExhausted'
        ' operation=batch_defer attempt=1 retry_after_ms=0'
    ]


def test_an_unstamped_contention_loss_reports_retry_after_ms_zero(sink_logger):
    logger, sink = sink_logger
    report_teardown_custody_loss(logger, site=RELEASE, error=cause_chain_contention())
    assert 'retry_after_ms=0' in sink.lines()[0]
    assert ' operation=' not in sink.lines()[0]


@pytest.mark.parametrize('hostile_attempt', [True, 0, -1, 2.9, '3', None, [], {}])
def test_a_hostile_attempt_never_breaks_the_line(sink_logger, hostile_attempt):
    logger, sink = sink_logger
    report_teardown_custody_loss(logger, site=RELEASE, error=exhaustion(), attempt=hostile_attempt)
    assert 'attempt=1' in sink.lines()[0]


# --- the replay loop ---------------------------------------------------------------


class SleepSink:
    def __init__(self):
        self.sleeps = []


def test_a_first_attempt_success_never_sleeps_nor_reports(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)

    assert replay_teardown_refund(call, site=STOP_REFUND, logger=logger, sleep=pauses.sleeps.append) == 1
    assert calls == [1]
    assert pauses.sleeps == []
    assert sink.records == []


def test_a_contention_loss_replays_and_converges_silently(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)
        if len(calls) == 1:
            raise exhaustion(retry_after=0.5, operation='batch_defer')

    assert replay_teardown_refund(call, site=SKIPPED_REFUND, logger=logger, sleep=pauses.sleeps.append) == 2
    assert calls == [1, 1]
    assert pauses.sleeps == [0.5]
    assert sink.records == [], 'a converged replay books no line at all'


def test_the_replay_wait_is_the_ladder_raised_to_the_storm(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)
        raise exhaustion(retry_after=4.0)

    assert replay_teardown_refund(call, site=STOP_REFUND, logger=logger, sleep=pauses.sleeps.append) == 3
    assert pauses.sleeps == [4.0, 4.0], 'the damper-cap window is waited in full, twice'


def test_a_shallow_storm_keeps_the_ladder_step(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)
        raise exhaustion(retry_after=0.1)

    replay_teardown_refund(call, site=STOP_REFUND, logger=logger, sleep=pauses.sleeps.append)
    assert pauses.sleeps == [0.25, 0.5]


def test_the_spent_budget_reports_once_on_the_honest_channel(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()

    def call():
        raise exhaustion(operation='batch_defer', retry_after=1.0)

    assert replay_teardown_refund(call, site=STOP_REFUND, logger=logger, sleep=pauses.sleeps.append) == 3
    assert pauses.sleeps == [1.0, 1.0], 'every wait rides the storm window the damper armed'
    assert len(sink.records) == 1
    assert sink.records[0].levelno == logging.WARNING
    assert sink.lines()[0] == (
        'event=batch_flight outcome=lease_recovery exception_type=FirestoreContentionExhausted'
        ' operation=batch_defer attempt=3 retry_after_ms=1000'
    )


def test_a_real_fault_reports_immediately_without_replaying(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)
        raise RuntimeError('storage unavailable')

    assert replay_teardown_refund(call, site=STOP_REFUND, logger=logger, sleep=pauses.sleeps.append) == 1
    assert calls == [1]
    assert pauses.sleeps == []
    assert sink.lines() == ['event=batch_flight outcome=lease_recovery exception_type=RuntimeError']
    assert sink.records[0].levelno == logging.ERROR


def test_contention_then_a_real_fault_stops_replaying(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)
        if len(calls) == 1:
            raise exhaustion(retry_after=0.5)
        raise FirestorePermissionDenied('revoked owner')

    assert replay_teardown_refund(call, site=SKIPPED_REFUND, logger=logger, sleep=pauses.sleeps.append) == 2
    assert pauses.sleeps == [0.5]
    assert sink.lines() == ['event=batch_flight outcome=lease_recovery exception_type=PermissionDenied']


def test_a_budget_one_site_is_the_single_attempt_report_path(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()
    calls = []

    def call():
        calls.append(1)
        raise exhaustion(operation='batch_release')

    assert replay_teardown_refund(call, site=RELEASE, logger=logger, sleep=pauses.sleeps.append) == 1
    assert calls == [1]
    assert pauses.sleeps == []
    assert sink.records[0].levelno == logging.INFO


def test_the_gpu_restart_site_reports_and_never_replays(sink_logger):
    logger, sink = sink_logger
    pauses = SleepSink()

    def call():
        raise exhaustion(operation='batch_defer', retry_after=4.0)

    assert replay_teardown_refund(call, site=GPU_RESTART, logger=logger, sleep=pauses.sleeps.append) == 1
    assert pauses.sleeps == []
    assert sink.lines()[0].startswith('event=batch_gpu_restart outcome=lease_recovery ')


def test_cancellation_is_never_booked_as_a_loss(sink_logger):
    logger, sink = sink_logger

    def call():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        replay_teardown_refund(call, site=STOP_REFUND, logger=logger)
    assert sink.records == []


def test_shutdown_never_swallows_system_exit(sink_logger):
    logger, sink = sink_logger

    def call():
        raise SystemExit(1)

    with pytest.raises(SystemExit):
        replay_teardown_refund(call, site=STOP_REFUND, logger=logger)
    assert sink.records == []
