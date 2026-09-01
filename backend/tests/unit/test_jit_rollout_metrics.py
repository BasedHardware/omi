from __future__ import annotations

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
