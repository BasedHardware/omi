#!/usr/bin/env python3
"""Lane-level contention-arm cells: the register storm no longer discards the GPU result.

Each cell drives the real worker persist boundary with the atomic contention
family — the register's exhausted fresh-transaction budget
(`FirestoreContentionExhausted`, carrying the storm damper's measured
`retry_after` stamp) and the cause-chained raw `Aborted` shapes prod booked
as `error_class=Aborted stage=persist` — and pins the recovery result, the
storm-aligned wait (never below the documented ladder step, never above the
damper's own 4.0s ceiling), the exhaustion booking or the kill-switch
behavior. A failing cell means the lane discarded a completed GPU result for
a contention wave the next strike rides out, or started replaying a custody
refusal.

Failure-Class: FC-persist-contention-exhaustion-discards-completed-gpu-results
"""

import logging
import math

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database.firestore_transaction_retry import FirestoreContentionExhausted, is_transaction_contention
from diarizer import batch_pipeline as bp
from utils.batch_pipeline.audio import StagedAudioInvalid
from tests.unit.persist_lane_harness import (
    GATE,
    PerSegmentPersist,
    ScriptedPersist,
    StampCarrier,
    WORKER_LOGGER,
    contention,
    exhaust_script,
    run_lane,
    run_two_units,
)

FC = 'FC-persist-contention-exhaustion-discards-completed-gpu-results'


def _cap():
    return bp.PERSIST_RESTRIKE_STORM_MAX_SECONDS


def _max_attempts():
    return bp.PERSIST_RESTRIKE_MAX_ATTEMPTS


def _expect_contention_recovery(monkeypatch, strikes, stamp=None):
    faults = [contention(stamp) for _ in range(strikes)]
    script = ScriptedPersist(faults, default='OK')
    run = run_lane(monkeypatch, script)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['meta']['failures'] == []
    assert run['meta']['decoded'] == ['a']
    return run


def _expect_contention_exhaustion(monkeypatch, stamp=None):
    run = run_lane(monkeypatch, exhaust_script(lambda m='storm': contention(stamp, m)))
    assert run['results'] == []
    assert run['meta']['failures'] == [('a', 'FirestoreContentionExhausted')]
    assert len(run['persist'].calls) == _max_attempts()
    return run


def test_cell_00000(monkeypatch):
    # One stamped contention loss, then the register lands: the GPU result survives.
    run = _expect_contention_recovery(monkeypatch, 1, stamp=2.0)
    assert run['sleeps'].delays == [2.0]


def test_cell_00001(monkeypatch):
    # Two stamped contention losses: storm-aligned waits on both strikes.
    run = _expect_contention_recovery(monkeypatch, 2, stamp=1.5)
    assert run['sleeps'].delays == [1.5, 1.5]


def test_cell_00002(monkeypatch):
    # An unstamped exhaustion keeps the documented ladder byte-for-byte.
    run = _expect_contention_recovery(monkeypatch, 1, stamp=0.0)
    assert run['sleeps'].delays == [0.25]


def test_cell_00003(monkeypatch):
    run = _expect_contention_recovery(monkeypatch, 2, stamp=0.0)
    assert run['sleeps'].delays == [0.25, 0.5]


def test_cell_00004(monkeypatch):
    run = _expect_contention_recovery(monkeypatch, 1, stamp=0.6)
    # A stamp shallower than the ladder step never shortens the wait.
    assert run['sleeps'].delays == [0.6]


def test_cell_00005(monkeypatch):
    # A stamp deeper than the ladder step on strike 2 rides the window, not the step.
    faults = [contention(0.1), contention(3.0)]
    run = run_lane(monkeypatch, ScriptedPersist(faults, default='OK'))
    assert run['sleeps'].delays == [0.25, 3.0]


def test_cell_00006(monkeypatch):
    # The deepest measured window stays clearable: the storm cap is the damper's own.
    faults = [contention(50.0)]
    run = run_lane(monkeypatch, ScriptedPersist(faults, default='OK'))
    assert run['sleeps'].delays == [_cap()]
    assert run['sleeps'].delays[0] == 4.0


def test_cell_00007(monkeypatch):
    _expect_contention_exhaustion(monkeypatch, stamp=2.0)


def test_cell_00008(monkeypatch):
    # Exhaustion strikes ride the stamped window on every attempt.
    run = _expect_contention_exhaustion(monkeypatch, stamp=3.0)
    assert run['sleeps'].delays == [3.0, 3.0]


def test_cell_00009(monkeypatch):
    run = _expect_contention_exhaustion(monkeypatch, stamp=0.0)
    assert run['sleeps'].delays == [0.25, 0.5]


def test_cell_00010(monkeypatch):
    # Gate off: the immediate fault for a contention loss, byte-for-byte legacy.
    run = run_lane(
        monkeypatch,
        ScriptedPersist([contention(2.0)], default=contention(2.0)),
        gate='false',
    )
    assert run['sleeps'].delays == []
    assert run['persist'].calls == ['a']
    assert run['meta']['failures'] == [('a', 'FirestoreContentionExhausted')]


def test_cell_00011(monkeypatch, caplog):
    # The wait line names the contention type and carries the storm-aligned delay.
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run_lane(monkeypatch, ScriptedPersist([contention(2.0)], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=FirestoreContentionExhausted' in waits[0]
    assert 'delay_ms=2000' in waits[0]


def test_cell_00012(monkeypatch, caplog):
    # A landed lane logs restrike_committed with the strike number.
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run_lane(monkeypatch, ScriptedPersist([contention(0.5)], default='OK'))
    commits = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert commits == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_cell_00013(monkeypatch):
    # A raw read-time Aborted rides the same admission (its cause chain classifies).
    ve = RuntimeError('wrapper')
    ve.__cause__ = Aborted('inner')
    script = ScriptedPersist([ve], default='OK')
    run = run_lane(monkeypatch, script)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_cell_00014(monkeypatch):
    # An expired-transaction rejection classifies as contention and rides the lane.
    expired = InvalidArgument('400 The referenced transaction has expired or is no longer valid.')
    script = ScriptedPersist([expired], default='OK')
    run = run_lane(monkeypatch, script)
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_cell_00015(monkeypatch):
    # A custody fault stays out of the contention arm: one call, immediate fault.
    run = run_lane(monkeypatch, ScriptedPersist([StagedAudioInvalid('pinned bytes')], default='OK'))
    assert run['persist'].calls == ['a']
    assert run['sleeps'].delays == []
    assert run['meta']['failures'] and run['meta']['failures'][0][0] == 'a'


def test_cell_00016(monkeypatch):
    # A plain RuntimeError without a contention cause chain stays out.
    run = run_lane(monkeypatch, ScriptedPersist([RuntimeError('worker')], default='OK'))
    assert run['persist'].calls == ['a']
    assert run['sleeps'].delays == []


def test_cell_00017(monkeypatch):
    # A non-contention ValueError with a benign cause chain stays out.
    ve = ValueError('bounded artifact identity required')
    ve.__cause__ = InvalidArgument('transport')
    run = run_lane(monkeypatch, ScriptedPersist([ve], default='OK'))
    assert run['persist'].calls == ['a']
    assert run['sleeps'].delays == []


def test_cell_00018(monkeypatch):
    # Sibling independence: a storm-exhausted unit fails alone, its sibling lands.

    def storming(work, payload):
        raise contention(2.0)

    def landing(work, payload):
        return 'OK'

    routes = PerSegmentPersist({'a': storming, 'b': landing})
    run = run_two_units(monkeypatch, routes)
    failed = {unit for unit, _ in run['meta']['failures']}
    assert failed == {'a'}
    assert [r.result_uri for r in run['results']] == ['OK']


def test_cell_00019(monkeypatch):
    # The lane cap stays three strikes for contention: no budget growth.
    run = run_lane(monkeypatch, exhaust_script(lambda m='storm': contention(0.0, m)))
    assert len(run['persist'].calls) == 3


def test_classifier_admits_the_exhausted_budget():
    assert bp.persist_loss_is_contention(contention(0.0)) is True


def test_classifier_admits_a_raw_aborted():
    assert bp.persist_loss_is_contention(Aborted('read-time abort')) is True


def test_classifier_admits_the_expired_transaction_rejection():
    expired = InvalidArgument('The referenced transaction has expired or is no longer valid.')
    assert is_transaction_contention(expired) is True
    assert bp.persist_loss_is_contention(expired) is True


def test_classifier_walks_the_cause_chain():
    ve = ValueError('wrapper')
    ve.__cause__ = Aborted('inner')
    assert bp.persist_loss_is_contention(ve) is True


def test_classifier_keeps_transport_in_its_own_arm():
    # A transport fault stays strikeable but is not contention: no storm term.
    assert bp.persist_loss_is_contention(InvalidArgument('transport')) is False


def test_classifier_keeps_custody_out():
    assert bp.persist_loss_is_contention(StagedAudioInvalid('pinned bytes')) is False
    assert bp.persist_loss_is_contention(ValueError('bounded artifact identity required')) is False
    assert bp.persist_loss_is_contention(None) is False


def test_storm_helper_mirrors_the_pump_shape_on_hostile_stamps():
    class Carrier(RuntimeError):
        pass

    carrier = Carrier('x')
    carrier.retry_after = '9'
    assert bp.persist_restrike_storm_after(carrier) == 0.0
    carrier2 = Carrier('x')
    carrier2.retry_after = True
    assert bp.persist_restrike_storm_after(carrier2) == 0.0
    carrier3 = Carrier('x')
    carrier3.retry_after = float('nan')
    assert bp.persist_restrike_storm_after(carrier3) == 0.0
    carrier4 = Carrier('x')
    carrier4.retry_after = -1.0
    assert bp.persist_restrike_storm_after(carrier4) == 0.0
    assert bp.persist_restrike_storm_after(None) == 0.0
    assert bp.persist_restrike_storm_after(InvalidArgument('transport')) == 0.0


def test_storm_helper_clamps_at_the_documented_ceiling():
    assert bp.persist_restrike_storm_after(contention(50.0)) == 4.0
    assert bp.persist_restrike_storm_after(contention(4.0)) == 4.0
    assert bp.persist_restrike_storm_after(contention(3.9)) == 3.9
    assert math.isclose(
        bp.persist_restrike_storm_after(contention(2.5)),
        2.5,
    )


def test_storm_ceiling_is_the_documented_pinned_literal():
    assert _cap() == 4.0


def test_ladder_and_storm_never_mix_on_transport_faults(monkeypatch):
    # A transport burst on the same lane keeps the pure ladder schedule.
    from google.api_core.exceptions import InternalServerError

    script = ScriptedPersist([InternalServerError('burst') for _ in range(2)], default='OK')
    run = run_lane(monkeypatch, script)
    assert run['sleeps'].delays == [0.25, 0.5]
