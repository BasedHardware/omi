"""Per-arm session outcomes for the Soniox idle-close cohort (utils.observability.soniox_idle_arm)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from config.soniox_idle import COHORT_SALT
from config.policy.batch import cohort_bucket
from models.users import PlanType
from utils.observability import demand_cohort, soniox_idle_arm
from utils.observability.soniox_idle_arm import IdleArmLedger


def _value(metric, **labels):
    return metric.labels(**labels)._value.get()


def _hist_count(metric, **labels):
    child = metric.labels(**labels)
    return sum(bucket.get() for bucket in child._buckets)


def _uid_in(arm_treatment: bool, percent: float) -> str:
    for index in range(10000):
        uid = f'user-{index}'
        if (cohort_bucket(uid, COHORT_SALT, bits=64) < percent) == arm_treatment:
            return uid
    raise AssertionError('no uid found')


@pytest.fixture
def cohort_env(monkeypatch):
    monkeypatch.delenv('SONIOX_IDLE_CLOSE_SECONDS', raising=False)
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '50')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '20')


def test_arm_follows_idle_settings(cohort_env):
    assert IdleArmLedger(_uid_in(True, 50)).arm == 'treatment'
    assert IdleArmLedger(_uid_in(False, 50)).arm == 'control'
    assert IdleArmLedger(None).arm == 'control'


def test_arm_is_control_when_cohort_is_off(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '0')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '20')
    assert IdleArmLedger(_uid_in(True, 50)).arm == 'control'


@pytest.mark.parametrize(
    ('subscription', 'plan'),
    [
        (None, 'free'),
        (SimpleNamespace(plan=PlanType.basic), 'free'),
        (SimpleNamespace(plan=PlanType.plus), 'paid'),
    ],
)
def test_plan_from_subscription(subscription, plan):
    ledger = IdleArmLedger(None)
    assert ledger.plan == 'unknown'
    ledger.set_plan(subscription)
    assert ledger.plan == plan


def test_final_words_use_last_text_per_segment_and_drop_removed():
    ledger = IdleArmLedger(None)
    ledger.segments([{'id': 'a', 'text': 'hello there'}, {'id': 'b', 'text': 'one'}], [])
    ledger.segments([{'id': 'a', 'text': 'hello there my friend'}], [])
    ledger.segments([{'id': 'c', 'text': 'gone soon'}], ['b'])
    ledger.segments([], ['c'])
    assert ledger.words == 4


def test_record_once_with_bounded_labels(cohort_env):
    ledger = IdleArmLedger(_uid_in(True, 50))
    ledger.set_plan(SimpleNamespace(plan=PlanType.plus))
    ledger.outcome = 'transcribed'
    ledger.add_connected(30.0)
    ledger.add_wire(12.0)
    ledger.add_capture(40.0)
    ledger.first_output(1.5)
    ledger.segments([{'id': 'a', 'text': 'three words here'}], [])
    labels = {'arm': 'treatment', 'plan': 'paid'}
    before = {
        'sessions': _value(soniox_idle_arm.SESSIONS, outcome='transcribed', **labels),
        'connected': _value(soniox_idle_arm.CONNECTED_SECONDS, **labels),
        'wire': _value(soniox_idle_arm.WIRE_AUDIO_SECONDS, **labels),
        'capture': _value(soniox_idle_arm.CAPTURE_AUDIO_SECONDS, **labels),
        'words': _value(soniox_idle_arm.TRANSCRIPT_WORDS, **labels),
        'rotations': _value(soniox_idle_arm.SPEAKER_SCOPE_ROTATIONS, **labels),
        'first': _hist_count(soniox_idle_arm.FIRST_OUTPUT_SECONDS, **labels),
        'ordinals': _hist_count(soniox_idle_arm.SPEAKER_ORDINALS, **labels),
    }
    ledger.record((3, 2))
    ledger.record((3, 2))  # second call is a no-op
    assert _value(soniox_idle_arm.SESSIONS, outcome='transcribed', **labels) == before['sessions'] + 1
    assert _value(soniox_idle_arm.CONNECTED_SECONDS, **labels) == before['connected'] + 30.0
    assert _value(soniox_idle_arm.WIRE_AUDIO_SECONDS, **labels) == before['wire'] + 12.0
    assert _value(soniox_idle_arm.CAPTURE_AUDIO_SECONDS, **labels) == before['capture'] + 40.0
    assert _value(soniox_idle_arm.TRANSCRIPT_WORDS, **labels) == before['words'] + 3
    assert _value(soniox_idle_arm.SPEAKER_SCOPE_ROTATIONS, **labels) == before['rotations'] + 2
    assert _hist_count(soniox_idle_arm.FIRST_OUTPUT_SECONDS, **labels) == before['first'] + 1
    assert _hist_count(soniox_idle_arm.SPEAKER_ORDINALS, **labels) == before['ordinals'] + 1


def test_unknown_outcome_and_plan_fall_back_to_closed_labels():
    ledger = IdleArmLedger(None)
    ledger.outcome = 'surprise'
    ledger.plan = 'enterprise'
    before = _value(soniox_idle_arm.SESSIONS, arm='control', plan='unknown', outcome='unknown')
    ledger.record(None)
    assert _value(soniox_idle_arm.SESSIONS, arm='control', plan='unknown', outcome='unknown') == before + 1


def test_demand_telemetry_feeds_the_ledger(monkeypatch):
    telemetry = demand_cohort.DemandTelemetry('eligible_control')
    ledger = IdleArmLedger(None)
    telemetry.idle_arm = ledger
    token = demand_cohort.current_demand.set(telemetry)
    try:
        telemetry.capture(2.0)
        telemetry.delivered()
        connected = demand_cohort.ConnectedSecondsMeter()
        connected.accounted_at -= 7.0
        connected.flush(close=True)
        demand_cohort.WireAudioMeter('soniox', 16000).written(b'\x00' * 32000)
        demand_cohort.WireAudioMeter('modulate', 16000).written(b'\x00' * 32000)
    finally:
        demand_cohort.current_demand.reset(token)
    assert ledger.capture_seconds == 2.0
    assert ledger.first_output_seconds is not None
    assert ledger.connected_seconds >= 7.0
    assert ledger.wire_seconds == 1.0  # Soniox only


def test_session_ledger_ignores_missing_or_foreign_values():
    assert soniox_idle_arm.session_ledger(None) is None
    assert soniox_idle_arm.session_ledger(SimpleNamespace(idle_arm='x')) is None


def test_plan_is_pinned_once():
    ledger = IdleArmLedger(None)
    ledger.set_plan(SimpleNamespace(plan=PlanType.plus))
    ledger.set_plan(None)
    assert ledger.plan == 'paid'


def test_word_overflow_sessions_are_excluded_from_the_word_bar(monkeypatch):
    monkeypatch.setattr(soniox_idle_arm, 'MAX_TRACKED_SEGMENTS', 1)
    ledger = IdleArmLedger(None)
    ledger.add_capture(10.0)
    ledger.segments([{'id': 'a', 'text': 'one two'}, {'id': 'b', 'text': 'three'}], [])
    assert ledger.words_truncated
    labels = {'arm': 'control', 'plan': 'unknown'}
    words = _value(soniox_idle_arm.TRANSCRIPT_WORDS, **labels)
    word_capture = _value(soniox_idle_arm.WORD_CAPTURE_SECONDS, **labels)
    overflow = _value(soniox_idle_arm.WORD_OVERFLOW_SESSIONS, **labels)
    ledger.record(None)
    assert _value(soniox_idle_arm.TRANSCRIPT_WORDS, **labels) == words
    assert _value(soniox_idle_arm.WORD_CAPTURE_SECONDS, **labels) == word_capture
    assert _value(soniox_idle_arm.WORD_OVERFLOW_SESSIONS, **labels) == overflow + 1


def test_live_speaker_decisions_by_arm_with_bounded_labels():
    ledger = IdleArmLedger(None)
    ledger.speaker_decision('owner', 'accepted')
    ledger.speaker_decision('owner', 'accepted')
    ledger.speaker_decision('robot', 'maybe')
    labels = {'arm': 'control', 'plan': 'unknown'}
    accepted = _value(soniox_idle_arm.SPEAKER_DECISIONS, target='owner', decision='accepted', **labels)
    fallback = _value(soniox_idle_arm.SPEAKER_DECISIONS, target='person', decision='rejected', **labels)
    ledger.record(None)
    assert _value(soniox_idle_arm.SPEAKER_DECISIONS, target='owner', decision='accepted', **labels) == accepted + 2
    assert _value(soniox_idle_arm.SPEAKER_DECISIONS, target='person', decision='rejected', **labels) == fallback + 1


def test_pin_plan_reads_once_in_the_background(monkeypatch):
    calls = []

    class _Persistence:
        async def call(self, fn, uid):
            calls.append(uid)
            return fn(uid)

    telemetry = demand_cohort.DemandTelemetry('ineligible')
    telemetry.idle_arm = IdleArmLedger(None)
    host = SimpleNamespace(demand_telemetry=telemetry, persistence=_Persistence(), request=SimpleNamespace(uid='u1'))
    asyncio.run(soniox_idle_arm.pin_plan(host, lambda uid: SimpleNamespace(plan=PlanType.plus)))
    assert calls == ['u1']
    assert telemetry.idle_arm.plan == 'paid'


def test_record_session_tolerates_missing_runtime():
    soniox_idle_arm.record_session(None, None)
    soniox_idle_arm.note_speaker_decision(None, 'owner', 'accepted')


def test_start_plan_pin_without_supervisor_does_not_raise():
    telemetry = demand_cohort.DemandTelemetry('ineligible')
    telemetry.idle_arm = IdleArmLedger(None)

    class _Host:
        demand_telemetry = telemetry

        def spawn(self, coro, *, name):
            raise AttributeError('no task_supervisor')

    soniox_idle_arm.start_plan_pin(_Host(), lambda uid: None)
    assert telemetry.idle_arm.plan == 'unknown'


def test_pin_plan_failure_leaves_plan_unknown(monkeypatch):
    class _Persistence:
        async def call(self, fn, uid):
            raise RuntimeError('firestore down')

    telemetry = demand_cohort.DemandTelemetry('ineligible')
    telemetry.idle_arm = IdleArmLedger(None)
    host = SimpleNamespace(demand_telemetry=telemetry, persistence=_Persistence(), request=SimpleNamespace(uid='u1'))
    asyncio.run(soniox_idle_arm.pin_plan(host, lambda uid: None))
    assert telemetry.idle_arm.plan == 'unknown'
