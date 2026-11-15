"""Session-exit custody family: the closed step table and its drivers.

Behavioral contract tests for ``routers.listen.session_exit``: the row
table's shape, the report path's two line shapes (contention vs real
fault), the replay ladder's storm alignment and silence, the sync twin,
cancellation propagation and hostile-shape immunity.

Failure-Class: FC-listen-session-exit-custody-faults-escape-as-asgi-crashes
"""

import asyncio
import logging
import math

import pytest
from google.api_core.exceptions import Aborted as Aborted_
from google.api_core.exceptions import InvalidArgument as InvalidArgument_

from database.firestore_transaction_retry import FirestoreContentionExhausted
from routers.listen.session_exit import (
    SESSION_EXIT_EVENT,
    SESSION_EXIT_REPLAY_ATTEMPTS,
    SESSION_EXIT_REPLAY_STEPS,
    SESSION_EXIT_STEPS,
    exit_fault_is_contention,
    exit_replay_delay,
    exit_step_site_field,
    exit_storm_after,
    report_exit_step_fault,
    run_exit_step,
    run_exit_step_replay,
    run_exit_step_sync,
)

pytestmark = [pytest.mark.filterwarnings('ignore::DeprecationWarning')]

LOGGER_NAME = 'routers.listen.session_exit'


class Sink(logging.Handler):
    def __init__(self):
        super().__init__(level=0)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self):
        return [record.getMessage() for record in self.records]


def _bound_logger(sink):
    logger = logging.getLogger(f'{LOGGER_NAME}.probe.{id(sink)}')
    logger.handlers = [sink]
    logger.setLevel(1)
    logger.propagate = False
    return logger


class SleepRecorder:
    """An async stand-in for asyncio.sleep that records its waits."""

    def __init__(self):
        self.sleeps = []

    async def __call__(self, seconds):
        self.sleeps.append(seconds)


def _contention(operation=None, retry_after=None):
    error = FirestoreContentionExhausted('synthetic contention exhaustion')
    if operation is not None:
        error.operation = operation
    if retry_after is not None:
        error.retry_after = retry_after
    return error


def _chain_contention():
    try:
        try:
            raise Aborted_('transaction aborted under load')
        except Aborted_ as aborted:
            raise RuntimeError('store call failed') from aborted
    except RuntimeError as error:
        return error


def _raise_and_catch(factory):
    try:
        raise factory()
    except Exception as caught:
        return caught


class TestStepTableShape:
    def test_table_has_twenty_one_rows(self):
        assert len(SESSION_EXIT_STEPS) == 21

    def test_replay_rows_are_exactly_the_usage_flush(self):
        assert SESSION_EXIT_REPLAY_STEPS == frozenset({'usage_flush'})

    def test_usage_flush_budget_is_three(self):
        assert SESSION_EXIT_STEPS['usage_flush'].attempts == SESSION_EXIT_REPLAY_ATTEMPTS == 3

    def test_every_report_row_is_budget_one(self):
        for key, row in SESSION_EXIT_STEPS.items():
            if key != 'usage_flush':
                assert row.attempts == 1, key

    def test_every_row_carries_the_event_token(self):
        for row in SESSION_EXIT_STEPS.values():
            assert row.event == SESSION_EXIT_EVENT == 'event=listen_session_exit'

    def test_every_row_reports_contention_at_warning(self):
        for row in SESSION_EXIT_STEPS.values():
            assert row.contention_level == logging.WARNING

    def test_every_phase_is_closed(self):
        for row in SESSION_EXIT_STEPS.values():
            assert row.phase in {'pre_session', 'record', 'exit'}

    def test_outcome_tokens_are_unique(self):
        outcomes = [row.outcome for row in SESSION_EXIT_STEPS.values()]
        assert len(outcomes) == len(set(outcomes)) == 21

    def test_row_keys_match_their_own_key_field(self):
        for key, row in SESSION_EXIT_STEPS.items():
            assert row.key == key

    def test_pre_session_phase_is_only_the_cohort_warm(self):
        assert [key for key, row in SESSION_EXIT_STEPS.items() if row.phase == 'pre_session'] == ['warm_cohorts']

    @pytest.mark.parametrize(
        'key',
        [
            'no_audio_observation_close',
            'ws_close_record',
            'cohort_finish',
            'unregister_session',
            'finish_live_transcription',
            'transcript_outcome',
            'lane_meter',
            'demand_publish',
            'usage_flush',
            'multi_channel_tail',
            'onboarding_cleanup',
            'language_summary',
            'final_drain',
            'speaker_ordinals',
            'idle_arm_record',
            'receiver_clear',
            'transcripts_clear',
            'speakers_clear',
            'idle_arm_session',
            'no_audio_record',
            'warm_cohorts',
        ],
    )
    def test_site_row_is_present(self, key):
        assert key in SESSION_EXIT_STEPS


class TestContentionClass:
    def test_exhaustion_instance_is_contention(self):
        assert exit_fault_is_contention(_contention()) is True

    def test_cause_chain_abort_is_contention(self):
        assert exit_fault_is_contention(_chain_contention()) is True

    def test_value_error_is_not_contention(self):
        assert exit_fault_is_contention(ValueError('plain')) is False

    def test_value_error_wrapping_exhaustion_is_not_contention(self):
        try:
            try:
                raise _contention()
            except FirestoreContentionExhausted as exhaustion:
                raise ValueError('wrapped') from exhaustion
        except ValueError as error:
            assert exit_fault_is_contention(error) is False

    def test_invalid_argument_chain_is_not_contention(self):
        try:
            try:
                raise InvalidArgument_('bad request')
            except InvalidArgument_ as invalid:
                raise RuntimeError('store call failed') from invalid
        except RuntimeError as error:
            assert exit_fault_is_contention(error) is False

    def test_never_raises_on_hostile_input(self):
        assert exit_fault_is_contention(None) is False
        assert exit_fault_is_contention(object()) is False
        assert exit_fault_is_contention(42) is False


class TestStormWindow:
    @pytest.mark.parametrize('stamped', [0.25, 1.0, 2.0, 4.0])
    def test_positive_finite_stamp_is_returned(self, stamped):
        assert exit_storm_after(_contention(retry_after=stamped)) == stamped

    def test_deep_stamp_clamps_at_the_store_damper_cap(self):
        assert exit_storm_after(_contention(retry_after=30.0)) == 4.0

    @pytest.mark.parametrize('stamped', [0.0, -1.0, True, False, '2.0', None, float('inf'), float('nan')])
    def test_hostile_stamp_keeps_the_ladder(self, stamped):
        assert exit_storm_after(_contention(retry_after=stamped)) == 0.0

    def test_stamp_on_a_foreign_exception_is_ignored(self):
        error = ValueError('plain')
        error.retry_after = 3.0
        assert exit_storm_after(error) == 0.0

    def test_no_error_keeps_the_ladder(self):
        assert exit_storm_after(None) == 0.0


class TestReplayLadder:
    @pytest.mark.parametrize('index,expected', [(1, 0.25), (2, 0.5), (3, 1.0), (4, 2.0), (5, 2.0)])
    def test_documented_ladder_steps(self, index, expected):
        assert exit_replay_delay(index) == expected

    @pytest.mark.parametrize('index', [0, -1, True, False, 1.5, '2', None])
    def test_hostile_index_collapses_to_first_step(self, index):
        assert exit_replay_delay(index) == 0.25


class TestReportPathContentionLine:
    def test_contention_line_is_warning(self):
        sink = Sink()
        report_exit_step_fault(_bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=_contention())
        assert sink.records[0].levelno == logging.WARNING

    def test_contention_line_shape(self):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['lane_meter'], error=_contention(operation='lane_meter_store')
        )
        message = sink.records[0].getMessage()
        assert message.startswith('event=listen_session_exit outcome=lane_meter_failed phase=exit step=lane_meter')
        assert 'fault_type=FirestoreContentionExhausted' in message
        assert 'operation=lane_meter_store' in message
        assert 'attempt=1' in message
        assert 'retry_after_ms=0' in message

    def test_unstamped_contention_reports_zero_window(self):
        sink = Sink()
        report_exit_step_fault(_bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=_contention())
        assert 'retry_after_ms=0' in sink.records[0].getMessage()

    def test_stamped_window_reports_milliseconds(self):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=_contention(retry_after=2.0)
        )
        assert 'retry_after_ms=2000' in sink.records[0].getMessage()

    def test_deep_window_reports_the_clamp(self):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=_contention(retry_after=9.0)
        )
        assert 'retry_after_ms=4000' in sink.records[0].getMessage()

    @pytest.mark.parametrize('attempt', [2, 3, 99])
    def test_attempt_is_rendered_verbatim_when_positive(self, attempt):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['usage_flush'], error=_contention(), attempt=attempt
        )
        assert f'attempt={attempt}' in sink.records[0].getMessage()

    @pytest.mark.parametrize('attempt', [0, -1, True, False, 1.5, '2', None])
    def test_hostile_attempt_collapses_to_one(self, attempt):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['usage_flush'], error=_contention(), attempt=attempt
        )
        assert 'attempt=1' in sink.records[0].getMessage()


class TestReportPathRealFaultLine:
    def test_real_fault_line_is_error(self):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=_raise_and_catch(ValueError)
        )
        assert sink.records[0].levelno == logging.ERROR

    def test_real_fault_line_has_no_race_fields(self):
        sink = Sink()
        error = _raise_and_catch(ValueError)
        error.operation = 'sneaky_label'
        error.retry_after = 3.0
        report_exit_step_fault(_bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=error)
        message = sink.records[0].getMessage()
        assert 'operation=' not in message
        assert 'attempt=' not in message
        assert 'retry_after_ms=' not in message
        assert 'fault_type=ValueError' in message

    def test_chain_contention_line_names_the_top_fault_type(self):
        sink = Sink()
        report_exit_step_fault(_bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=_chain_contention())
        assert 'fault_type=RuntimeError' in sink.records[0].getMessage()


class TestLinePayloadHygiene:
    def test_exception_message_never_interpolates(self):
        sink = Sink()
        error = _raise_and_catch(ValueError)
        error.uid_like = None
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=ValueError('uid=secret-user-42')
        )
        assert 'secret-user-42' not in sink.records[0].getMessage()

    def test_site_field_is_a_static_file_line(self):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink),
            step=SESSION_EXIT_STEPS['final_drain'],
            error=_raise_and_catch(ValueError),
        )
        assert ' site=test_session_exit_wiring.py:' in sink.records[0].getMessage()

    def test_tracebackless_fault_reports_no_site_and_never_raises(self):
        sink = Sink()
        report_exit_step_fault(
            _bound_logger(sink), step=SESSION_EXIT_STEPS['final_drain'], error=ValueError('never raised')
        )
        assert len(sink.records) == 1
        assert ' site=' not in sink.records[0].getMessage()

    def test_site_skips_site_packages_frames(self):
        try:
            try:
                raise Aborted_('deep in the sdk')
            except Aborted_ as aborted:
                raise RuntimeError('wrapped') from aborted
        except RuntimeError as error:
            field = exit_step_site_field(error)
            assert field == '' or 'site-packages' not in field


class TestRunExitStep:
    def test_success_returns_one_and_books_no_line(self):
        sink = Sink()
        ran = []

        async def step():
            ran.append(1)

        assert asyncio.run(run_exit_step(SESSION_EXIT_STEPS['final_drain'], step, logger=_bound_logger(sink))) == 1
        assert ran == [1]
        assert sink.records == []

    def test_fault_books_one_line_and_returns_one(self):
        sink = Sink()

        async def step():
            raise ValueError('boom')

        assert asyncio.run(run_exit_step(SESSION_EXIT_STEPS['lane_meter'], step, logger=_bound_logger(sink))) == 1
        assert len(sink.records) == 1
        assert sink.records[0].levelno == logging.ERROR

    def test_return_value_is_discarded(self):
        sink = Sink()

        async def step():
            return {'kept': 'internally'}

        assert (
            asyncio.run(run_exit_step(SESSION_EXIT_STEPS['transcript_outcome'], step, logger=_bound_logger(sink))) == 1
        )

    def test_cancellation_propagates(self):
        sink = Sink()

        async def step():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_exit_step(SESSION_EXIT_STEPS['final_drain'], step, logger=_bound_logger(sink)))
        assert sink.records == []

    def test_step_arguments_pass_through(self):
        sink = Sink()
        seen = {}

        async def step(*args, **kwargs):
            seen['args'] = args
            seen['kwargs'] = kwargs

        asyncio.run(
            run_exit_step(SESSION_EXIT_STEPS['ws_close_record'], step, 7, held=True, logger=_bound_logger(sink))
        )
        assert seen == {'args': (7,), 'kwargs': {'held': True}}


class TestRunExitStepSync:
    def test_success_returns_one_and_books_no_line(self):
        sink = Sink()
        ran = []

        def step():
            ran.append(1)

        assert run_exit_step_sync(SESSION_EXIT_STEPS['speaker_ordinals'], step, logger=_bound_logger(sink)) == 1
        assert ran == [1]
        assert sink.records == []

    def test_fault_books_one_line_and_does_not_raise(self):
        sink = Sink()

        def step():
            raise RuntimeError('boom')

        assert run_exit_step_sync(SESSION_EXIT_STEPS['receiver_clear'], step, logger=_bound_logger(sink)) == 1
        assert len(sink.records) == 1

    def test_cancellation_propagates(self):
        sink = Sink()

        def step():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            run_exit_step_sync(SESSION_EXIT_STEPS['idle_arm_session'], step, logger=_bound_logger(sink))


class TestReplayDriver:
    def _always(self, error):
        async def step():
            raise error

        return step

    def _converge_at(self, attempt, error):
        calls = []

        async def step():
            calls.append(1)
            if len(calls) < attempt:
                raise error

        return step

    def test_first_try_success_spends_one_and_stays_silent(self):
        sink = Sink()
        sleeps = SleepRecorder()
        spent = asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._converge_at(1, _contention()),
                logger=_bound_logger(sink),
                sleep=sleeps,
            )
        )
        assert spent == 1
        assert sleeps.sleeps == []
        assert sink.records == []

    def test_converge_on_second_attempt_replays_once_after_the_storm(self):
        sink = Sink()
        sleeps = SleepRecorder()
        spent = asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._converge_at(2, _contention(retry_after=2.0)),
                logger=_bound_logger(sink),
                sleep=sleeps,
            )
        )
        assert spent == 2
        assert sleeps.sleeps == [2.0]
        assert sink.records == []

    def test_converge_on_third_attempt_replays_twice(self):
        sink = Sink()
        sleeps = SleepRecorder()
        spent = asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._converge_at(3, _contention(retry_after=0.1)),
                logger=_bound_logger(sink),
                sleep=sleeps,
            )
        )
        assert spent == 3
        assert sleeps.sleeps == [0.25, 0.5]
        assert sink.records == []

    def test_exhaustion_reports_once_at_warning(self):
        sink = Sink()
        sleeps = SleepRecorder()
        spent = asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._always(_contention(operation='usage_store', retry_after=1.0)),
                logger=_bound_logger(sink),
                sleep=sleeps,
            )
        )
        assert spent == 3
        assert len(sink.records) == 1
        assert sink.records[0].levelno == logging.WARNING
        message = sink.records[0].getMessage()
        assert 'attempt=3' in message
        assert 'operation=usage_store' in message
        assert 'retry_after_ms=1000' in message

    def test_every_wait_is_raised_to_the_stamped_window(self):
        sleeps = SleepRecorder()
        asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._always(_contention(retry_after=1.5)),
                logger=_bound_logger(Sink()),
                sleep=sleeps,
            )
        )
        assert sleeps.sleeps == [1.5, 1.5]

    def test_ladder_and_storm_take_the_max_each_wait(self):
        sleeps = SleepRecorder()
        asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._always(_contention(retry_after=0.3)),
                logger=_bound_logger(Sink()),
                sleep=sleeps,
            )
        )
        assert sleeps.sleeps == [0.3, 0.5]

    def test_real_fault_reports_immediately_without_replaying(self):
        sink = Sink()
        sleeps = SleepRecorder()
        spent = asyncio.run(
            run_exit_step_replay(
                SESSION_EXIT_STEPS['usage_flush'],
                self._always(ValueError('real')),
                logger=_bound_logger(sink),
                sleep=sleeps,
            )
        )
        assert spent == 1
        assert sleeps.sleeps == []
        assert len(sink.records) == 1
        assert sink.records[0].levelno == logging.ERROR

    def test_real_fault_after_a_contention_loss_stops_the_replay(self):
        sink = Sink()
        sleeps = SleepRecorder()
        calls = []

        async def step():
            calls.append(1)
            if len(calls) == 1:
                raise _contention()
            raise KeyError('real')

        spent = asyncio.run(
            run_exit_step_replay(SESSION_EXIT_STEPS['usage_flush'], step, logger=_bound_logger(sink), sleep=sleeps)
        )
        assert spent == 2
        assert sleeps.sleeps == [0.25]
        assert len(sink.records) == 1

    def test_cancellation_propagates_and_skips_the_report(self):
        sink = Sink()
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(
                run_exit_step_replay(
                    SESSION_EXIT_STEPS['usage_flush'],
                    self._always(asyncio.CancelledError()),
                    logger=_bound_logger(sink),
                    sleep=SleepRecorder(),
                )
            )
        assert sink.records == []

    def test_default_wait_resolves_asyncio_sleep_at_call_time(self):
        sleeps = SleepRecorder()
        original = asyncio.sleep
        asyncio.sleep = sleeps
        try:
            asyncio.run(
                run_exit_step_replay(
                    SESSION_EXIT_STEPS['usage_flush'],
                    self._always(_contention()),
                    logger=_bound_logger(Sink()),
                )
            )
        finally:
            asyncio.sleep = original
        assert sleeps.sleeps == [0.25, 0.5]


class TestSiteField:
    def test_site_names_the_raising_file_and_line(self):
        error = _raise_and_catch(ValueError)
        field = exit_step_site_field(error)
        assert field.startswith(' site=test_session_exit_wiring.py:')

    def test_tracebackless_fault_yields_empty_field(self):
        assert exit_step_site_field(ValueError('never raised')) == ''

    def test_never_raises_on_hostile_shapes(self):
        error = ValueError('x')
        error.__traceback__ = None
        assert exit_step_site_field(error) == ''


class TestMathImportedForSpec:
    def test_ladder_is_monotone_until_cap(self):
        values = [exit_replay_delay(index) for index in range(1, 6)]
        assert all(later >= earlier for earlier, later in zip(values, values[1:]))
        assert math.isfinite(values[0])
