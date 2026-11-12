#!/usr/bin/env python3
"""Bare transport-timeout losses join the persist re-strike lane.

The lane's classifier accepted only ``GoogleAPIError`` instances, but the persist
boundary's own deadline guards and the socket layer raise the *builtin*
``TimeoutError`` (``socket.timeout`` is its alias on Python 3.10+): the upload
stream's 15-minute deadline, the 30-second registration grace, and raw socket
read timeouts surface at ``stage=persist`` unwrapped. The classifier booked each
one as a non-strikeable fault, so the worker discarded a fully completed GPU
result — decode, VAD, ASR and diarization all done — and lease recovery re-ran
the entire GPU chain to reproduce a result the worker already held (the
``event=batch_worker_failed error_class=TimeoutError stage=persist`` sensor
family). The transport-timeout family is the same burst-shaped storage loss the
lane exists to ride out, so it joins the strikeable verdict; every custody fault
(typed audio validity, privacy fences, policy refusals, the register contention
wrapper, disk faults) stays non-strikeable.

Failure-Class: FC-persist-socket-transport-loss-discards-completed-gpu-results
"""

import logging
import os
import socket

import pytest

from diarizer import batch_pipeline as bp
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (
    GATE,
    ScriptedPersist,
    WORKER_LOGGER,
    exhaust_script,
    run_lane,
    script_for,
)


class UploadDeadlineTimeout(TimeoutError):
    """The production stream-deadline fault's exact shape (a TimeoutError subclass)."""


class CustodyTimeoutLookalike(TimeoutError, ValueError):
    """A fault that is both a timeout and typed custody: the timeout family decides."""


SOCKET_TIMEOUT = socket.timeout('timed out')

STREAM_DEADLINE_FAULT = TimeoutError('batch artifact upload deadline exceeded')
REGISTRATION_GRACE_FAULT = TimeoutError('artifact registration too old to begin upload')


# --------------------------------------------------------------------------- #
# The classifier's transport-timeout family
# --------------------------------------------------------------------------- #


def test_builtin_timeout_error_is_restrikeable():
    assert bp.persist_loss_is_restrikeable(TimeoutError('transport')) is True


def test_socket_timeout_alias_is_restrikeable():
    # socket.timeout IS TimeoutError since Python 3.10; the raw socket fault
    # must classify through the alias, not a second list.
    assert bp.persist_loss_is_restrikeable(SOCKET_TIMEOUT) is True


def test_socket_timeout_is_the_builtin_type():
    assert isinstance(SOCKET_TIMEOUT, TimeoutError)


def test_upload_stream_deadline_fault_is_restrikeable():
    assert bp.persist_loss_is_restrikeable(STREAM_DEADLINE_FAULT) is True


def test_registration_grace_fault_is_restrikeable():
    assert bp.persist_loss_is_restrikeable(REGISTRATION_GRACE_FAULT) is True


def test_timeout_error_subclass_is_restrikeable():
    assert bp.persist_loss_is_restrikeable(UploadDeadlineTimeout('transport')) is True


def test_timeout_and_custody_hybrid_decides_by_the_timeout_family():
    assert bp.persist_loss_is_restrikeable(CustodyTimeoutLookalike('hybrid')) is True


def test_plain_os_error_stays_non_strikeable():
    assert bp.persist_loss_is_restrikeable(OSError('disk')) is False


def test_connection_error_stays_non_strikeable():
    assert bp.persist_loss_is_restrikeable(ConnectionError('reset')) is False


def test_value_error_stays_non_strikeable():
    assert bp.persist_loss_is_restrikeable(ValueError('bounded payload')) is False


def test_permission_error_stays_non_strikeable():
    assert bp.persist_loss_is_restrikeable(PermissionError('policy changed')) is False


def test_runtime_error_stays_non_strikeable():
    assert bp.persist_loss_is_restrikeable(RuntimeError('worker')) is False


def test_register_contention_wrapper_stays_non_strikeable():
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    assert bp.persist_loss_is_restrikeable(FirestoreContentionExhausted('exhausted')) is False


# --------------------------------------------------------------------------- #
# Lane behavior: a bare timeout no longer discards the completed GPU result
# --------------------------------------------------------------------------- #


def test_stream_deadline_timeout_at_strike_1_recovers_the_completed_result(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([STREAM_DEADLINE_FAULT], default='OK'))
    assert run['results'] and isinstance(run['results'][0], WorkResult)


def test_stream_deadline_timeout_at_strike_1_reports_the_final_uri(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([STREAM_DEADLINE_FAULT], default='OK'))
    assert run['results'][0].result_uri == 'OK'


def test_stream_deadline_timeout_at_strike_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([STREAM_DEADLINE_FAULT], default='OK'))
    assert run['sleeps'].delays == [0.25]


def test_stream_deadline_timeout_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run_lane(monkeypatch, ScriptedPersist([STREAM_DEADLINE_FAULT], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=TimeoutError' in waits[0]


def test_socket_timeout_at_strike_2_recovers_after_two_waits(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([SOCKET_TIMEOUT, SOCKET_TIMEOUT], default='OK'))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_registration_grace_timeout_at_strike_2_recovers_after_two_waits(monkeypatch):
    # The lane cap is three total attempts, so two faults are the deepest
    # recovery: 0.25s then 0.5s, with the third attempt landing the result.
    run = run_lane(monkeypatch, ScriptedPersist([REGISTRATION_GRACE_FAULT] * 2, default='OK'))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_builtin_timeout_exhaustion_books_the_legacy_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(TimeoutError))
    assert run['results'] == [] and run['meta']['failures'] == [('a', 'TimeoutError')]


def test_builtin_timeout_exhaustion_yields_no_work_result(monkeypatch):
    fault = TimeoutError('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == []


def test_gate_off_books_the_timeout_immediately_without_strikes(monkeypatch):
    fault = TimeoutError('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault], default=fault), gate='false')
    assert run['sleeps'].delays == []
    assert run['meta']['failures'] == [('a', 'TimeoutError')]


def test_gate_off_persists_exactly_one_call(monkeypatch):
    fault = TimeoutError('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault], default=fault), gate='false')
    assert run['persist'].calls == ['a']


def test_gpu_chain_runs_exactly_once_across_timeout_strikes(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([SOCKET_TIMEOUT, SOCKET_TIMEOUT], default='OK'))
    assert run['meta']['decoded'] == ['a']


def test_timeout_exhaustion_fail_line_names_the_class_not_the_message(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=WORKER_LOGGER)
    run_lane(
        monkeypatch,
        ScriptedPersist([TimeoutError('burst-with-identifiers')], default=TimeoutError('retry-with-identifiers')),
    )
    lines = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert lines and 'error_class=TimeoutError' in lines[0]
    assert 'burst-with-identifiers' not in lines[0]
    assert 'retry-with-identifiers' not in lines[0]


def test_timeout_exhaustion_fail_line_keeps_the_persist_stage(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=WORKER_LOGGER)
    run_lane(monkeypatch, exhaust_script(TimeoutError))
    lines = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert lines and 'stage=persist' in lines[0]


def test_script_for_accepts_the_timeout_fault_builder(monkeypatch):
    run = run_lane(monkeypatch, script_for(1, final='OK', fault=TimeoutError))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_the_gate_still_gates_the_timeout_family_by_name(monkeypatch):
    # The env pin is the same kill switch the Google family uses: one gate,
    # both transport families.
    fault = TimeoutError('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault], default=fault), gate='false')
    assert run['meta']['failures'] == [('a', 'TimeoutError')]
    assert os.getenv('BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED') == 'false'
