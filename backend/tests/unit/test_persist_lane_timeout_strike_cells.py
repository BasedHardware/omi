#!/usr/bin/env python3
"""Lane-level strike/recovery cells across both transport families.

Each cell drives the real worker persist boundary with a scripted transport fault from one of the two strikeable families at one strike position and pins the recovery result, the documented wait prefix, the exhaustion booking or the kill-switch behavior. A failing cell means the lane stopped riding out a burst the next strike survives, or started replaying a custody refusal.

Failure-Class: FC-persist-socket-transport-loss-discards-completed-gpu-results
"""

import logging
import socket

import pytest
from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    InternalServerError,
    InvalidArgument,
    ResourceExhausted,
    ServiceUnavailable,
)

from diarizer import batch_pipeline as bp
from tests.unit.persist_lane_harness import (
    GATE,
    ScriptedPersist,
    WORKER_LOGGER,
    exhaust_script,
    run_lane,
)

FAULTS = (
    ('timeout_error', TimeoutError),
    ('socket_timeout', socket.timeout),
    ('invalid_argument', InvalidArgument),
    ('internal_server_error', InternalServerError),
    ('service_unavailable', ServiceUnavailable),
    ('deadline_exceeded', DeadlineExceeded),
    ('aborted', Aborted),
    ('resource_exhausted', ResourceExhausted),
)


def _fault(label):
    return dict(FAULTS)[label]


def _expect_recovery(monkeypatch, label, strikes):
    fault = _fault(label)
    script = ScriptedPersist([fault('burst') for _ in range(strikes)], default='OK')
    run = run_lane(monkeypatch, script)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [round(0.25 * (2**i), 4) for i in range(strikes)]
    assert run['meta']['decoded'] == ['a']


def _expect_exhaustion(monkeypatch, label):
    fault = _fault(label)
    run = run_lane(monkeypatch, exhaust_script(fault))
    if label == 'invalid_argument':
        # The deterministic refusal books the typed custody handoff.
        assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
        assert run['results'][0].reason == 'persist_payload_invalid'
    else:
        assert run['results'] == []
    assert run['meta']['failures'] == [('a', fault.__name__)]


def _expect_gate_off(monkeypatch, label):
    fault = _fault(label)
    run = run_lane(monkeypatch, ScriptedPersist([fault('burst')], default=fault('burst')), gate='false')
    assert run['sleeps'].delays == []
    assert run['persist'].calls == ['a']
    assert run['meta']['failures'] == [('a', fault.__name__)]


def _expect_wait_log(monkeypatch, caplog, label):
    fault = _fault(label)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run_lane(monkeypatch, ScriptedPersist([fault('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=%s' % fault.__name__ in waits[0]


def test_cell_00000(monkeypatch):
    _expect_recovery(monkeypatch, 'timeout_error', 1)


def test_cell_00001(monkeypatch):
    _expect_recovery(monkeypatch, 'timeout_error', 2)


def test_cell_00002(monkeypatch):
    _expect_exhaustion(monkeypatch, 'timeout_error')


def test_cell_00003(monkeypatch):
    _expect_gate_off(monkeypatch, 'timeout_error')


def test_cell_00004(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'timeout_error')


def test_cell_00005(monkeypatch):
    _expect_recovery(monkeypatch, 'socket_timeout', 1)


def test_cell_00006(monkeypatch):
    _expect_recovery(monkeypatch, 'socket_timeout', 2)


def test_cell_00007(monkeypatch):
    _expect_exhaustion(monkeypatch, 'socket_timeout')


def test_cell_00008(monkeypatch):
    _expect_gate_off(monkeypatch, 'socket_timeout')


def test_cell_00009(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'socket_timeout')


def test_cell_00010(monkeypatch):
    _expect_recovery(monkeypatch, 'invalid_argument', 1)


def test_cell_00011(monkeypatch):
    _expect_recovery(monkeypatch, 'invalid_argument', 2)


def test_cell_00012(monkeypatch):
    _expect_exhaustion(monkeypatch, 'invalid_argument')


def test_cell_00013(monkeypatch):
    _expect_gate_off(monkeypatch, 'invalid_argument')


def test_cell_00014(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'invalid_argument')


def test_cell_00015(monkeypatch):
    _expect_recovery(monkeypatch, 'internal_server_error', 1)


def test_cell_00016(monkeypatch):
    _expect_recovery(monkeypatch, 'internal_server_error', 2)


def test_cell_00017(monkeypatch):
    _expect_exhaustion(monkeypatch, 'internal_server_error')


def test_cell_00018(monkeypatch):
    _expect_gate_off(monkeypatch, 'internal_server_error')


def test_cell_00019(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'internal_server_error')


def test_cell_00020(monkeypatch):
    _expect_recovery(monkeypatch, 'service_unavailable', 1)


def test_cell_00021(monkeypatch):
    _expect_recovery(monkeypatch, 'service_unavailable', 2)


def test_cell_00022(monkeypatch):
    _expect_exhaustion(monkeypatch, 'service_unavailable')


def test_cell_00023(monkeypatch):
    _expect_gate_off(monkeypatch, 'service_unavailable')


def test_cell_00024(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'service_unavailable')


def test_cell_00025(monkeypatch):
    _expect_recovery(monkeypatch, 'deadline_exceeded', 1)


def test_cell_00026(monkeypatch):
    _expect_recovery(monkeypatch, 'deadline_exceeded', 2)


def test_cell_00027(monkeypatch):
    _expect_exhaustion(monkeypatch, 'deadline_exceeded')


def test_cell_00028(monkeypatch):
    _expect_gate_off(monkeypatch, 'deadline_exceeded')


def test_cell_00029(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'deadline_exceeded')


def test_cell_00030(monkeypatch):
    _expect_recovery(monkeypatch, 'aborted', 1)


def test_cell_00031(monkeypatch):
    _expect_recovery(monkeypatch, 'aborted', 2)


def test_cell_00032(monkeypatch):
    _expect_exhaustion(monkeypatch, 'aborted')


def test_cell_00033(monkeypatch):
    _expect_gate_off(monkeypatch, 'aborted')


def test_cell_00034(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'aborted')


def test_cell_00035(monkeypatch):
    _expect_recovery(monkeypatch, 'resource_exhausted', 1)


def test_cell_00036(monkeypatch):
    _expect_recovery(monkeypatch, 'resource_exhausted', 2)


def test_cell_00037(monkeypatch):
    _expect_exhaustion(monkeypatch, 'resource_exhausted')


def test_cell_00038(monkeypatch):
    _expect_gate_off(monkeypatch, 'resource_exhausted')


def test_cell_00039(monkeypatch, caplog):
    _expect_wait_log(monkeypatch, caplog, 'resource_exhausted')
