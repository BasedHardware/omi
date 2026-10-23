"""Default-on finite-allowance refusal is independent of the live rollout."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import stt_cap_dispatch as policy
from utils import stt_cap_dispatch as dispatch, subscription
from utils.observability.stt_cap_dispatch import (
    DISPATCH_DECISIONS,
    DispatchPath,
    DispatchReason,
    record_decision,
)


@pytest.fixture(autouse=True)
def offline_defaults(monkeypatch):
    monkeypatch.delenv('STT_CAP_OFFLINE_ENFORCEMENT', raising=False)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', '')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    monkeypatch.setattr(policy, '_cohort_resolver', None)


@pytest.mark.parametrize('lane', ['sync', 'batch'])
@pytest.mark.parametrize('cohort', ['', 'pct:0', 'pct:50', 'malformed'])
def test_offline_scope_cannot_be_disabled_by_live_rollout(monkeypatch, lane, cohort):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', cohort)
    assert policy.offline_admission_enabled('synthetic', lane)
    assert not policy.execution_admission_enabled('synthetic', 'live')
    assert not policy.selected('synthetic', 'batch')  # code-owned legacy fence remains
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false')
    assert not policy.offline_admission_enabled('synthetic', lane)


@pytest.mark.parametrize('path', list(DispatchPath))
@pytest.mark.parametrize(
    'managed,reason',
    [
        (False, 'plan_allowance_exhausted'),
        (False, 'allowance_unavailable'),
        (True, 'marketplace_reviewer'),
        (True, 'plan_within_allowance'),
        (True, 'plan_unlimited'),
    ],
)
def test_each_spend_boundary_uses_current_allowance_and_bounded_metrics(monkeypatch, path, managed, reason):
    resolver = Mock(return_value=SimpleNamespace(managed=managed, reason=reason))
    monkeypatch.setattr(subscription, 'resolve_transcription_allowance', resolver)
    lane = 'batch' if path.value.startswith('batch_') else 'sync'
    metric_reason = (
        DispatchReason.ENTITLED
        if managed
        else (
            DispatchReason.ALLOWANCE_EXHAUSTED
            if reason == 'plan_allowance_exhausted'
            else DispatchReason.ALLOWANCE_UNAVAILABLE
        )
    )
    metric = DISPATCH_DECISIONS.labels(path.value, 'allowed' if managed else 'held', metric_reason.value)
    before = metric._value.get()
    assert dispatch.sync_allowed('synthetic', 1, 'modulate', lane=lane, path=path) is managed
    resolver.assert_called_once_with('synthetic', source=None, byok_active=False, omi_funded=True)
    assert metric._value.get() == before + 1


@pytest.mark.parametrize('lane', ['sync', 'batch'])
def test_only_actual_customer_funded_provider_bypasses_allowance(monkeypatch, lane):
    resolver = Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    monkeypatch.setattr(dispatch, 'funded_allowance', resolver)
    monkeypatch.setattr(dispatch, 'get_byok_key', lambda provider: 'synthetic-key')
    monkeypatch.delenv('DEEPGRAM_SELF_HOSTED_ENABLED', raising=False)
    assert dispatch.sync_allowed('synthetic', provider='deepgram', lane=lane)
    resolver.assert_not_called()
    assert not dispatch.sync_allowed('synthetic', provider='modulate', lane=lane)


@pytest.mark.parametrize('lane', ['sync', 'batch'])
def test_kill_switch_restores_legacy_scope_without_allowance_read(monkeypatch, lane):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false')
    resolver = Mock(side_effect=AssertionError('disabled scope must retain old behavior'))
    monkeypatch.setattr(dispatch, 'funded_allowance', resolver)
    assert dispatch.sync_allowed('synthetic', lane=lane)
    resolver.assert_not_called()


def test_metrics_reject_unbounded_labels():
    with pytest.raises(ValueError):
        record_decision('unbounded', False, DispatchReason.ACCESS_DENIED)
    with pytest.raises(ValueError):
        record_decision(DispatchPath.BATCH_GPU, False, 'raw-provider-error')
