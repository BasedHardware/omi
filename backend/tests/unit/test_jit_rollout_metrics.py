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


def _rendered_lazy_sample(payload: str, event: str) -> float:
    prefix = f'lazy_desktop_deferral_total{{event="{event}"}} '
    for line in payload.splitlines():
        if line.startswith(prefix):
            return float(line[len(prefix) :])
    raise AssertionError(f'no rendered lazy_desktop_deferral_total sample for event={event}')


def test_lazy_desktop_deferral_metric_is_bounded_and_uid_free():
    assert LAZY_DESKTOP_DEFERRAL_TOTAL._labelnames == ('event',)
    assert 'uid' not in LAZY_DESKTOP_DEFERRAL_TOTAL._labelnames
    assert LAZY_DESKTOP_DEFERRAL_EVENTS == {
        'stored',
        'fenced',
        'enrich_started',
        'enrich_lost_ownership',
        'enrich_reacquire_error',
        'enrich_complete',
        'enrich_failed',
    }

    payload = generate_latest().decode()
    # Every bounded child is pre-seeded, so a healthy but idle process still
    # exports a sample: "not deployed" and "no captures" must not look alike.
    for event in LAZY_DESKTOP_DEFERRAL_EVENTS | {'other'}:
        _rendered_lazy_sample(payload, event)

    # The HELP text has to carry the three constraints on reading the ratio,
    # because whoever writes the PromQL will not read utils/metrics.py.
    help_line = next(line for line in payload.splitlines() if line.startswith('# HELP lazy_desktop_deferral_total'))
    assert 'sum by (event)' in help_line  # stored is emitted by backend AND pusher
    assert 'pusher' in help_line
    assert 'attempt/persist ratio' in help_line  # not per-conversation
    assert 'FREE_TIER_LOCAL_PROCESSING' in help_line  # ratio undefined while on

    # Assert on a rendered sample after a real increment, not just the HELP line.
    before = _rendered_lazy_sample(payload, 'fenced')
    record_lazy_desktop_deferral(event='fenced')
    assert _rendered_lazy_sample(generate_latest().decode(), 'fenced') == before + 1


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
