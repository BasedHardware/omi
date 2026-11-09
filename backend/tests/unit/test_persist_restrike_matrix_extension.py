#!/usr/bin/env python3
"""Cross-product extension matrices for the persist re-strike lane.

The Google transport family membership and lane verdicts class by class, type times
IO-path recovery/exhaustion facets, unit shapes times strikes uri/payload/gpu facets, the
delay schedule in rounded milliseconds, committed-line literals per strike count, the
silent-unit type sweep, lane independence from the pump constants, config adjacency and
FC parity, and the harness semantics the grids are built on.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import logging
import os
import re

import pytest
from google.api_core.exceptions import InvalidArgument, InternalServerError, ServiceUnavailable
from google.api_core.exceptions import DeadlineExceeded, NotFound, ResourceExhausted, RetryError
from google.api_core.exceptions import Aborted, BadRequest, Cancelled, Conflict, FailedPrecondition
from google.api_core.exceptions import Forbidden, GoogleAPIError, PreconditionFailed, ClientError
from google.api_core.exceptions import ServerError, GoogleAPICallError
from google.api_core.exceptions import Unauthenticated, Unknown

from dataclasses import replace

from config.batch_pipeline import persist_restrike_enabled
from diarizer import batch_pipeline as bp
from utils.batch_pipeline import pump as pump_module
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (  # noqa: F401
    GATE,
    PerSegmentPersist,
    RecordingTimings,
    Samples,
    ScriptedPersist,
    SleepRecorder,
    WORKER_LOGGER,
    build_worker,
    exhaust_script,
    item,
    pin_full_gpu_stages,
    run_lane,
    run_two_units,
    script_for,
)

FC = 'FC-persist-transport-loss-discards-completed-gpu-results'

DOC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'persist-restrike-lane.md')


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def test_family_invalid_argument_subclasses_the_google_transport_family():
    assert issubclass(InvalidArgument, GoogleAPIError)


def test_family_invalid_argument_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(InvalidArgument('burst')) is True


def test_family_bad_request_subclasses_the_google_transport_family():
    assert issubclass(BadRequest, GoogleAPIError)


def test_family_bad_request_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(BadRequest('burst')) is True


def test_family_service_unavailable_subclasses_the_google_transport_family():
    assert issubclass(ServiceUnavailable, GoogleAPIError)


def test_family_service_unavailable_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(ServiceUnavailable('burst')) is True


def test_family_internal_server_error_subclasses_the_google_transport_family():
    assert issubclass(InternalServerError, GoogleAPIError)


def test_family_internal_server_error_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(InternalServerError('burst')) is True


def test_family_deadline_exceeded_subclasses_the_google_transport_family():
    assert issubclass(DeadlineExceeded, GoogleAPIError)


def test_family_deadline_exceeded_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(DeadlineExceeded('burst')) is True


def test_family_resource_exhausted_subclasses_the_google_transport_family():
    assert issubclass(ResourceExhausted, GoogleAPIError)


def test_family_resource_exhausted_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(ResourceExhausted('burst')) is True


def test_family_not_found_subclasses_the_google_transport_family():
    assert issubclass(NotFound, GoogleAPIError)


def test_family_not_found_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(NotFound('burst')) is True


def test_family_conflict_subclasses_the_google_transport_family():
    assert issubclass(Conflict, GoogleAPIError)


def test_family_conflict_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(Conflict('burst')) is True


def test_family_aborted_subclasses_the_google_transport_family():
    assert issubclass(Aborted, GoogleAPIError)


def test_family_aborted_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(Aborted('burst')) is True


def test_family_cancelled_subclasses_the_google_transport_family():
    assert issubclass(Cancelled, GoogleAPIError)


def test_family_cancelled_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(Cancelled('burst')) is True


def test_family_failed_precondition_subclasses_the_google_transport_family():
    assert issubclass(FailedPrecondition, GoogleAPIError)


def test_family_failed_precondition_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(FailedPrecondition('burst')) is True


def test_family_forbidden_subclasses_the_google_transport_family():
    assert issubclass(Forbidden, GoogleAPIError)


def test_family_forbidden_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(Forbidden('burst')) is True


def test_family_precondition_failed_subclasses_the_google_transport_family():
    assert issubclass(PreconditionFailed, GoogleAPIError)


def test_family_precondition_failed_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(PreconditionFailed('burst')) is True


def test_family_unauthenticated_subclasses_the_google_transport_family():
    assert issubclass(Unauthenticated, GoogleAPIError)


def test_family_unauthenticated_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(Unauthenticated('burst')) is True


def test_family_unknown_subclasses_the_google_transport_family():
    assert issubclass(Unknown, GoogleAPIError)


def test_family_unknown_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(Unknown('burst')) is True


def test_family_retry_error_subclasses_the_google_transport_family():
    assert issubclass(RetryError, GoogleAPIError)


def test_family_retry_error_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(RetryError('burst', None)) is True


def test_family_google_api_error_subclasses_the_google_transport_family():
    assert issubclass(GoogleAPIError, GoogleAPIError)


def test_family_google_api_error_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(GoogleAPIError('burst')) is True


def test_family_client_error_subclasses_the_google_transport_family():
    assert issubclass(ClientError, GoogleAPIError)


def test_family_client_error_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(ClientError('burst')) is True


def test_family_server_error_subclasses_the_google_transport_family():
    assert issubclass(ServerError, GoogleAPIError)


def test_family_server_error_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(ServerError('burst')) is True


def test_family_google_api_call_error_subclasses_the_google_transport_family():
    assert issubclass(GoogleAPICallError, GoogleAPIError)


def test_family_google_api_call_error_bare_instance_is_lane_strikeable(monkeypatch):
    assert bp.persist_loss_is_restrikeable(GoogleAPICallError('burst')) is True


def test_type_invalid_argument_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_invalid_argument_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch, ScriptedPersist([InvalidArgument('burst')] * 3, default=InvalidArgument('burst')), io_concurrency=2
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_invalid_argument_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_invalid_argument_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_invalid_argument_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')] * 3, default=InvalidArgument('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_invalid_argument_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([InvalidArgument('burst')] * 3, default=InvalidArgument('burst')), timings=timings
    )
    assert timings.spans.count('persist') == 3


def test_type_bad_request_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_bad_request_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch, ScriptedPersist([BadRequest('burst')] * 3, default=BadRequest('burst')), io_concurrency=2
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_bad_request_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_bad_request_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_bad_request_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')] * 3, default=BadRequest('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_bad_request_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([BadRequest('burst')] * 3, default=BadRequest('burst')), timings=timings
    )
    assert timings.spans.count('persist') == 3


def test_type_service_unavailable_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_service_unavailable_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist([ServiceUnavailable('burst')] * 3, default=ServiceUnavailable('burst')),
        io_concurrency=2,
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_service_unavailable_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_service_unavailable_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_service_unavailable_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')] * 3, default=ServiceUnavailable('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_service_unavailable_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        ScriptedPersist([ServiceUnavailable('burst')] * 3, default=ServiceUnavailable('burst')),
        timings=timings,
    )
    assert timings.spans.count('persist') == 3


def test_type_internal_server_error_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_internal_server_error_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist([InternalServerError('burst')] * 3, default=InternalServerError('burst')),
        io_concurrency=2,
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_internal_server_error_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_internal_server_error_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_internal_server_error_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(
        monkeypatch, ScriptedPersist([InternalServerError('burst')] * 3, default=InternalServerError('burst'))
    )
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_internal_server_error_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        ScriptedPersist([InternalServerError('burst')] * 3, default=InternalServerError('burst')),
        timings=timings,
    )
    assert timings.spans.count('persist') == 3


def test_type_deadline_exceeded_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_deadline_exceeded_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist([DeadlineExceeded('burst')] * 3, default=DeadlineExceeded('burst')),
        io_concurrency=2,
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_deadline_exceeded_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_deadline_exceeded_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_deadline_exceeded_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')] * 3, default=DeadlineExceeded('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_deadline_exceeded_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        ScriptedPersist([DeadlineExceeded('burst')] * 3, default=DeadlineExceeded('burst')),
        timings=timings,
    )
    assert timings.spans.count('persist') == 3


def test_type_resource_exhausted_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_resource_exhausted_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist([ResourceExhausted('burst')] * 3, default=ResourceExhausted('burst')),
        io_concurrency=2,
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_resource_exhausted_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_resource_exhausted_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_resource_exhausted_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')] * 3, default=ResourceExhausted('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_resource_exhausted_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        ScriptedPersist([ResourceExhausted('burst')] * 3, default=ResourceExhausted('burst')),
        timings=timings,
    )
    assert timings.spans.count('persist') == 3


def test_type_not_found_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_not_found_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')] * 3, default=NotFound('burst')), io_concurrency=2)
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_not_found_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_not_found_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_not_found_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')] * 3, default=NotFound('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_not_found_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')] * 3, default=NotFound('burst')), timings=timings)
    assert timings.spans.count('persist') == 3


def test_type_conflict_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_conflict_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')] * 3, default=Conflict('burst')), io_concurrency=2)
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_conflict_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_conflict_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_conflict_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')] * 3, default=Conflict('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_conflict_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')] * 3, default=Conflict('burst')), timings=timings)
    assert timings.spans.count('persist') == 3


def test_type_aborted_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_aborted_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')] * 3, default=Aborted('burst')), io_concurrency=2)
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_aborted_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_aborted_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_aborted_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')] * 3, default=Aborted('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_aborted_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')] * 3, default=Aborted('burst')), timings=timings)
    assert timings.spans.count('persist') == 3


def test_type_cancelled_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_cancelled_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')] * 3, default=Cancelled('burst')), io_concurrency=2)
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_cancelled_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_cancelled_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_cancelled_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')] * 3, default=Cancelled('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_cancelled_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')] * 3, default=Cancelled('burst')), timings=timings)
    assert timings.spans.count('persist') == 3


def test_type_failed_precondition_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_failed_precondition_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist([FailedPrecondition('burst')] * 3, default=FailedPrecondition('burst')),
        io_concurrency=2,
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_failed_precondition_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_failed_precondition_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_failed_precondition_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')] * 3, default=FailedPrecondition('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_failed_precondition_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        ScriptedPersist([FailedPrecondition('burst')] * 3, default=FailedPrecondition('burst')),
        timings=timings,
    )
    assert timings.spans.count('persist') == 3


def test_type_forbidden_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_forbidden_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')] * 3, default=Forbidden('burst')), io_concurrency=2)
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_forbidden_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_forbidden_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_forbidden_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')] * 3, default=Forbidden('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_forbidden_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')] * 3, default=Forbidden('burst')), timings=timings)
    assert timings.spans.count('persist') == 3


def test_type_precondition_failed_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_precondition_failed_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist([PreconditionFailed('burst')] * 3, default=PreconditionFailed('burst')),
        io_concurrency=2,
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_precondition_failed_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_precondition_failed_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_precondition_failed_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')] * 3, default=PreconditionFailed('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_precondition_failed_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        ScriptedPersist([PreconditionFailed('burst')] * 3, default=PreconditionFailed('burst')),
        timings=timings,
    )
    assert timings.spans.count('persist') == 3


def test_type_unauthenticated_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_unauthenticated_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(
        monkeypatch, ScriptedPersist([Unauthenticated('burst')] * 3, default=Unauthenticated('burst')), io_concurrency=2
    )
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_unauthenticated_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'), timings=timings, io_concurrency=2
    )
    assert timings.spans.count('persist') == 2


def test_type_unauthenticated_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_unauthenticated_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')] * 3, default=Unauthenticated('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_unauthenticated_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch, ScriptedPersist([Unauthenticated('burst')] * 3, default=Unauthenticated('burst')), timings=timings
    )
    assert timings.spans.count('persist') == 3


def test_type_unknown_io_path_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_type_unknown_io_path_exhaust_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')] * 3, default=Unknown('burst')), io_concurrency=2)
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_type_unknown_io_path_opens_two_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_type_unknown_recovered_lane_logs_no_error_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'))
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_type_unknown_exhaust_sleeps_exactly_two_delays(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')] * 3, default=Unknown('burst')))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_type_unknown_exhaust_opens_three_persist_spans(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')] * 3, default=Unknown('burst')), timings=timings)
    assert timings.spans.count('persist') == 3


def test_shape_two_second_strikes_1_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item())
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shape_two_second_strikes_1_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item())
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_two_second_strikes_1_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item())
    assert run['meta']['decoded'] == ['a']


def test_shape_two_second_strikes_2_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item())
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shape_two_second_strikes_2_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item())
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_two_second_strikes_2_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item())
    assert run['meta']['decoded'] == ['a']


def test_shape_two_second_exhaust_results_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item())
    assert run['results'] == []


def test_shape_two_second_exhaust_failures_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item())
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_shape_thirty_second_strikes_1_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item('a', 30))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shape_thirty_second_strikes_1_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item('a', 30))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_thirty_second_strikes_1_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item('a', 30))
    assert run['meta']['decoded'] == ['a']


def test_shape_thirty_second_strikes_2_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item('a', 30))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shape_thirty_second_strikes_2_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item('a', 30))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_thirty_second_strikes_2_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item('a', 30))
    assert run['meta']['decoded'] == ['a']


def test_shape_thirty_second_exhaust_results_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 30))
    assert run['results'] == []


def test_shape_thirty_second_exhaust_failures_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 30))
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_shape_short_capture_strikes_1_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item('a', 1))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shape_short_capture_strikes_1_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item('a', 1))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_short_capture_strikes_1_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=item('a', 1))
    assert run['meta']['decoded'] == ['a']


def test_shape_short_capture_strikes_2_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item('a', 1))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shape_short_capture_strikes_2_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item('a', 1))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_short_capture_strikes_2_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=item('a', 1))
    assert run['meta']['decoded'] == ['a']


def test_shape_short_capture_exhaust_results_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 1))
    assert run['results'] == []


def test_shape_short_capture_exhaust_failures_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 1))
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_shape_shadow_strikes_1_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), shadow=True))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shape_shadow_strikes_1_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), shadow=True))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_shadow_strikes_1_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), shadow=True))
    assert run['meta']['decoded'] == ['a']


def test_shape_shadow_strikes_2_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), shadow=True))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shape_shadow_strikes_2_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), shadow=True))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_shadow_strikes_2_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), shadow=True))
    assert run['meta']['decoded'] == ['a']


def test_shape_shadow_exhaust_results_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), shadow=True))
    assert run['results'] == []


def test_shape_shadow_exhaust_failures_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), shadow=True))
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_shape_receipt_strikes_1_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), language_receipt_enabled=True))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shape_receipt_strikes_1_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), language_receipt_enabled=True))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_receipt_strikes_1_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), language_receipt_enabled=True))
    assert run['meta']['decoded'] == ['a']


def test_shape_receipt_strikes_2_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), language_receipt_enabled=True))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shape_receipt_strikes_2_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), language_receipt_enabled=True))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_receipt_strikes_2_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), language_receipt_enabled=True))
    assert run['meta']['decoded'] == ['a']


def test_shape_receipt_exhaust_results_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), language_receipt_enabled=True))
    assert run['results'] == []


def test_shape_receipt_exhaust_failures_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), language_receipt_enabled=True))
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_shape_capture_span_strikes_1_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shape_capture_span_strikes_1_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_capture_span_strikes_1_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'))
    assert run['meta']['decoded'] == ['a']


def test_shape_capture_span_strikes_2_uri_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shape_capture_span_strikes_2_payload_identity_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'))
    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_shape_capture_span_strikes_2_gpu_once_facet(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'))
    assert run['meta']['decoded'] == ['a']


def test_shape_capture_span_exhaust_results_facet(monkeypatch):
    run = run_lane(
        monkeypatch, exhaust_script(), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1')
    )
    assert run['results'] == []


def test_shape_capture_span_exhaust_failures_facet(monkeypatch):
    run = run_lane(
        monkeypatch, exhaust_script(), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1')
    )
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_delay_attempt_25_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(25) * 1000) == 2000


def test_delay_attempt_26_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(26) * 1000) == 2000


def test_delay_attempt_27_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(27) * 1000) == 2000


def test_delay_attempt_28_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(28) * 1000) == 2000


def test_delay_attempt_29_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(29) * 1000) == 2000


def test_delay_attempt_30_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(30) * 1000) == 2000


def test_delay_attempt_31_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(31) * 1000) == 2000


def test_delay_attempt_32_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(32) * 1000) == 2000


def test_delay_attempt_33_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(33) * 1000) == 2000


def test_delay_attempt_34_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(34) * 1000) == 2000


def test_delay_attempt_35_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(35) * 1000) == 2000


def test_delay_attempt_36_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(36) * 1000) == 2000


def test_delay_attempt_37_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(37) * 1000) == 2000


def test_delay_attempt_38_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(38) * 1000) == 2000


def test_delay_attempt_39_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(39) * 1000) == 2000


def test_delay_attempt_40_rounds_to_the_cap_ms():
    assert round(bp.persist_restrike_delay(40) * 1000) == 2000


def test_delay_float_attempt_0_5_is_deterministic():
    assert round(bp.persist_restrike_delay(0.5), 6) == 0.176777


def test_delay_float_attempt_1_5_is_deterministic():
    assert round(bp.persist_restrike_delay(1.5), 6) == 0.353553


def test_delay_float_attempt_2_5_is_deterministic():
    assert round(bp.persist_restrike_delay(2.5), 6) == 0.707107


def test_delay_float_attempt_3_5_is_deterministic():
    assert round(bp.persist_restrike_delay(3.5), 6) == 2.0


def test_committed_attempt_literal_for_two_strikes(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=3']


def test_committed_attempt_literal_for_one_strike(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(1))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_third_wait_delay_literal_for_three_strikes(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(
        monkeypatch, script_for(2) if False else ScriptedPersist([InvalidArgument('a'), InvalidArgument('b'), 'OK'])
    )
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert len(waits) == 2
    assert 'delay_ms=250' in waits[0] and 'delay_ms=500' in waits[1]


def test_silent_unit_type_invalid_argument_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_bad_request_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_service_unavailable_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_internal_server_error_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_deadline_exceeded_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_resource_exhausted_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_not_found_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_conflict_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_aborted_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_cancelled_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_failed_precondition_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_forbidden_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_precondition_failed_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_unauthenticated_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_type_unknown_recovers_to_silence(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_retuning_pump_constants_does_not_move_the_worker_lane(monkeypatch):
    original = pump_module.PUBLICATION_RESTRIKE_BASE_SECONDS
    pump_module.PUBLICATION_RESTRIKE_BASE_SECONDS = 9.0
    try:
        assert bp.persist_restrike_delay(1) == bp.PERSIST_RESTRIKE_BASE_SECONDS
    finally:
        pump_module.PUBLICATION_RESTRIKE_BASE_SECONDS = original


def test_retuning_worker_constants_does_not_move_the_pump_lane(monkeypatch):
    original = bp.PERSIST_RESTRIKE_BASE_SECONDS
    bp.PERSIST_RESTRIKE_BASE_SECONDS = 9.0
    try:
        assert pump_module.publication_restrike_delay(1) == pump_module.PUBLICATION_RESTRIKE_BASE_SECONDS
    finally:
        bp.PERSIST_RESTRIKE_BASE_SECONDS = original


def test_config_persist_restrike_sibling_of_publication_restrike():
    import inspect
    from config import batch_pipeline as config

    source = inspect.getsource(config)
    persist_at = source.index('def persist_restrike_enabled')
    publication_at = source.index('def publication_restrike_enabled')
    assert persist_at < publication_at


def test_config_and_worker_fc_ids_are_identical():
    import inspect

    worker_source = inspect.getsource(bp.PipelineWorker._persist_with_restrike)
    config_source = inspect.getsource(persist_restrike_enabled)
    worker_fc = worker_source.split('Failure-Class: ')[1].splitlines()[0].strip()
    config_fc = config_source.split('Failure-Class: ')[1].splitlines()[0].strip()
    assert worker_fc == config_fc == FC


def test_lane_reads_the_gate_once_per_decision():
    import inspect

    source = inspect.getsource(bp.PipelineWorker._persist_with_restrike)
    assert source.count('persist_restrike_enabled()') == 1


def test_lane_calls_the_classifier_once_per_decision():
    import inspect

    source = inspect.getsource(bp.PipelineWorker._persist_with_restrike)
    assert source.count('persist_loss_is_restrikeable(') == 1


def test_lane_sleeps_through_the_time_module():
    import inspect

    source = inspect.getsource(bp.PipelineWorker._persist_with_restrike)
    assert 'time.sleep(delay)' in source


def test_lane_logs_share_the_batch_persist_event():
    import inspect

    source = inspect.getsource(bp.PipelineWorker._persist_with_restrike)
    assert source.count('event=batch_persist') == 2


def test_harness_script_for_builds_strikes_then_final():
    script = script_for(2)
    assert len(script) == 3 and isinstance(script[0], InvalidArgument) and script[-1] == 'OK'


def test_harness_exhaust_script_replays_the_fault():
    persist = exhaust_script()

    class Unit:
        segment_id = 'u'

    for _ in range(5):
        try:
            persist(Unit(), {})
        except InvalidArgument:
            pass
    assert persist.calls == ['u'] * 5


def test_harness_per_segment_routes_are_independent():
    routes = PerSegmentPersist({'a': ScriptedPersist([]), 'b': ScriptedPersist([])})

    class Unit:
        def __init__(self, segment_id):
            self.segment_id = segment_id

    routes(Unit('a'), {})
    routes(Unit('b'), {})
    assert routes.calls == ['a', 'b']


def test_harness_sleep_recorder_rounds_delays():
    recorder = SleepRecorder()
    recorder(0.25)
    recorder(0.5000001)
    assert recorder.delays == [0.25, 0.5]


def test_harness_recording_timings_counts_spans():
    timings = RecordingTimings()
    timings.call('persist', lambda: 1)
    timings.call('persist', lambda: 2)
    timings.call('other', lambda: 3)
    assert timings.spans == ['persist', 'persist', 'other']
