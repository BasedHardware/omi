from __future__ import annotations

from typing import Any

import pytest

from prometheus_client import generate_latest

from utils.jit_rollout import (
    JITDecisionReason,
    JITDecisionStage,
    JITFlagEvaluation,
    JITRolloutAuthority,
    TriState,
)
from utils.metrics import (
    JIT_FIRST_OPEN_TOTAL,
    LAZY_DESKTOP_DEFERRAL_EVENTS,
    LAZY_DESKTOP_DEFERRAL_TOTAL,
    record_lazy_desktop_deferral,
    JIT_ROLLOUT_DECISION_LATENCY_SECONDS,
    JIT_ROLLOUT_DECISION_TOTAL,
    JIT_WRITER_MODE_TRANSITION_TOTAL,
)


def test_jit_rollout_metric_names_exist():
    payload = generate_latest().decode()
    assert 'jit_rollout_decision_total' in payload
    assert 'jit_rollout_decision_latency_seconds' in payload
    assert 'jit_writer_mode_transition_total' in payload
    assert 'jit_first_open_total' in payload
    assert JIT_ROLLOUT_DECISION_TOTAL._labelnames == ('effective', 'reason', 'stage', 'error_class')
    assert JIT_WRITER_MODE_TRANSITION_TOTAL._labelnames == ('from_mode', 'to_mode')
    assert JIT_FIRST_OPEN_TOTAL._labelnames == ('event', 'effect')
    for labels in (
        JIT_ROLLOUT_DECISION_TOTAL._labelnames,
        JIT_ROLLOUT_DECISION_LATENCY_SECONDS._labelnames,
        JIT_WRITER_MODE_TRANSITION_TOTAL._labelnames,
        JIT_FIRST_OPEN_TOTAL._labelnames,
    ):
        assert 'uid' not in labels


@pytest.mark.asyncio
async def test_authority_increments_uid_free_rollout_counters():
    async def provider(uid: str) -> JITFlagEvaluation:
        assert uid == 'named-user'
        return JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)

    before = JIT_ROLLOUT_DECISION_TOTAL.labels(
        effective='enabled',
        reason='rollout_enabled',
        stage='ingress',
        error_class='none',
    )._value.get()
    await JITRolloutAuthority(provider).resolve('named-user', stage=JITDecisionStage.INGRESS)
    after = JIT_ROLLOUT_DECISION_TOTAL.labels(
        effective='enabled',
        reason='rollout_enabled',
        stage='ingress',
        error_class='none',
    )._value.get()
    assert after == before + 1


def test_lazy_desktop_deferral_metric_is_bounded_and_uid_free():
    payload = generate_latest().decode()
    assert 'lazy_desktop_deferral_total' in payload
    assert LAZY_DESKTOP_DEFERRAL_TOTAL._labelnames == ('event',)
    assert 'uid' not in LAZY_DESKTOP_DEFERRAL_TOTAL._labelnames
    assert LAZY_DESKTOP_DEFERRAL_EVENTS == {
        'stored',
        'fenced',
        'enrich_started',
        'enrich_lost_ownership',
        'enrich_complete',
        'enrich_failed',
    }


def _lazy_count(event: str) -> float:
    return LAZY_DESKTOP_DEFERRAL_TOTAL.labels(event=event)._value.get()


def test_lazy_desktop_deferral_unknown_event_collapses_to_other():
    before_other = _lazy_count('other')
    before_stored = _lazy_count('stored')
    record_lazy_desktop_deferral(event='stored')
    record_lazy_desktop_deferral(event='uid:abc')  # a caller cannot mint a new series
    assert _lazy_count('stored') == before_stored + 1
    assert _lazy_count('other') == before_other + 1
    assert 'uid:abc' not in generate_latest().decode()


def test_lazy_desktop_deferral_recorder_never_raises(monkeypatch):
    # The finalizer and router call this on persistence/enrichment paths; a
    # registry failure must not change their outcome.
    monkeypatch.setattr(
        LAZY_DESKTOP_DEFERRAL_TOTAL, 'labels', lambda **_kw: (_ for _ in ()).throw(RuntimeError('down'))
    )
    assert record_lazy_desktop_deferral(event='stored') is None


def test_lazy_desktop_deferral_unhashable_event_collapses_to_other():
    # An unhashable/invalid runtime value must not raise before the guarded
    # metric operation; it collapses to `other` like any unknown label.
    before_other = _lazy_count('other')
    before_stored = _lazy_count('stored')
    bad_event: Any = ['not', 'hashable']
    assert record_lazy_desktop_deferral(event=bad_event) is None
    assert _lazy_count('other') == before_other + 1
    assert _lazy_count('stored') == before_stored
