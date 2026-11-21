# LIFECYCLE: permanent
"""PL-571: durable funding denials cannot loop at the transient retry cadence.

Run the same ProviderSttStage and admission transactions on old Firestore,
replacement Postgres and the simulator. Vendor, VAD, artifact IO and funding
answers are synthetic; the refusal, intent and settlement paths are real.
Require OMI_REQUIRE_STORE_BACKENDS=all for complete local qualification.
This proves the stage's returned schedule and custody, not Cloud Tasks fairness
or the serving cross-database privacy bridge.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.provider_stt import ProviderSttStage
from utils.batch_pipeline.provider_stt_admission import enqueue_in_transaction, resolve_route

pytestmark = pytest.mark.integration
T0 = 1_000_000.0
HOLD = 7200.0  # Independent contract oracle, not imported from the implementation.
TRANSIENT = 60.0


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BATCH_ALLOWANCE_HOLD_RETRY_SECONDS', str(int(HOLD)))
    return store_backend


def pending(h, label='parked', *, byok=False):
    owner = h.seed_user(label)
    conversation = f'{label}-conversation'
    h.customer.add_conversation(owner, conversation)
    work = WorkItem(
        label,
        owner,
        T0 - 10,
        f'gs://synthetic/{label}/audio#17',
        5.0,
        Priority.FRESH,
        conversation_id=conversation,
        privacy_generation=0,
    )
    route = resolve_route('ja', byok=byok)
    policy = replace(
        BatchUnitPolicy(batch_enabled=True, batch_percent=100),
        stt_route=route.stt_route,
        provider_reason=route.provider_reason,
        provider_service=route.provider_service,
    )
    binding = ProjectionBinding(owner, f'{label}-upload', f'{label}-content', (work.segment_id,), language='ja')
    assert (
        admit(
            h.store,
            [work],
            binding,
            T0 - 1,
            namespace=h.namespace,
            policy=policy,
            enqueue=lambda tx, item, now, *, policy: enqueue_in_transaction(tx, item, now, route=route, policy=policy),
        )['outcome']
        == 'batch'
    )
    return work


def row(h, work):
    return h.store.run(lambda tx: tx.get('jobs', work.segment_id))


def stage(h, decision, clock):
    artifacts = Mock()
    artifacts.fetch_audio.return_value = b'synthetic audio'
    artifacts.find_recovery_result.return_value = None
    artifacts.persist_recovery_result.return_value = 'gs://synthetic/results#18'
    vendor = Mock(
        return_value={
            'audio_seconds': 5.0,
            'speech_seconds': 1.0,
            'speech_spans': [{'start': 0.5, 'end': 1.5}],
            'words': [{'word': 'synthetic', 'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': 'modulate',
            'language': 'ja',
            'recovery_version': 1,
        }
    )
    inspect = Mock(return_value=(b'\0\0' * 80000, 5.0, [{'start': 0.5, 'end': 1.5}]))
    runner = ProviderSttStage(
        h.store,
        artifacts,
        stt=vendor,
        allowed=decision,
        inspect=inspect,
        clock=lambda: clock[0],
    )
    return runner, artifacts, vendor, inspect


@pytest.mark.parametrize('gate', ['before_download', 'after_inspection'])
@pytest.mark.parametrize(
    'decision,wait',
    [
        ((False, 'allowance_exhausted'), HOLD),
        ((False, 'budget_exhausted'), HOLD),
        ((False, 'allowance_unavailable'), TRANSIENT),
        ((False, 'consent_denied'), TRANSIENT),
        ((False, 'unknown_reason'), TRANSIENT),
        (False, TRANSIENT),
    ],
)
def test_pl571_each_funding_gate_returns_the_reason_specific_schedule_without_spending_custody(h, gate, decision, wait):
    work = pending(h)
    original = row(h, work)
    clock = [T0]
    answers = [decision] if gate == 'before_download' else [(True, 'allowed'), decision]
    allowed = Mock(side_effect=answers)
    runner, artifacts, vendor, inspect = stage(h, allowed, clock)
    result = runner.run(work.segment_id)
    assert (result.outcome, result.reason, result.available_at) == ('deferred', 'not_due', T0 + wait)
    assert row(h, work) == original, 'deferral retains exact input, policy, binding and unspent provider intent'
    assert h.store.run(lambda tx: tx.get('results', work.segment_id)) == {}
    assert allowed.call_count == (1 if gate == 'before_download' else 2)
    assert all(call.args == (work.owner_id, 5.0, 'modulate') for call in allowed.call_args_list)
    vendor.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()
    artifacts.find_recovery_result.assert_not_called()
    if gate == 'before_download':
        artifacts.fetch_audio.assert_not_called()
        inspect.assert_not_called()
    else:
        artifacts.fetch_audio.assert_called_once_with(work)
        inspect.assert_called_once()


@pytest.mark.parametrize('reason', ['allowance_exhausted', 'budget_exhausted'])
def test_pl571_restart_rechecks_funding_and_other_owners_progress_without_releasing_parked_audio(h, reason):
    work = pending(h)
    original = row(h, work)
    clock = [T0]
    refused, refused_artifacts, refused_vendor, _ = stage(h, Mock(return_value=(False, reason)), clock)
    result = refused.run(work.segment_id)
    assert result.available_at == T0 + HOLD

    # A separate eligible owner uses the same Store while the refused row retains custody.
    other = pending(h, 'eligible')
    funded, artifacts, vendor, _ = stage(h, Mock(return_value=(True, 'allowed')), clock)
    assert funded.run(other.segment_id).outcome == 'done'
    assert row(h, other)['state'] == 'result_ready'
    vendor.assert_called_once()
    assert row(h, work) == original
    assert refused_artifacts.method_calls == []
    refused_vendor.assert_not_called()

    # A reconstructed worker at the returned due time reevaluates funding; it cannot
    # inherit a process-local refusal or consume a paid-once token on the refused run.
    clock[0] = result.available_at
    resumed, resumed_artifacts, resumed_vendor, _ = stage(h, Mock(return_value=(True, 'allowed')), clock)
    assert resumed.run(work.segment_id).outcome == 'done'
    completed = row(h, work)
    assert completed['state'] == 'result_ready'
    assert completed['provider_intent']['settled_at'] == T0 + HOLD
    assert completed['audio_uri'] == original['audio_uri']
    assert completed['policy'] == original['policy']
    assert completed['projection_binding'] == original['projection_binding']
    assert completed['capture_at'] == original['capture_at']
    assert resumed.run(work.segment_id).outcome == 'done'
    resumed_vendor.assert_called_once()
    resumed_artifacts.persist_recovery_result.assert_called_once()


def test_pl571_byok_funding_snapshot_cannot_be_replaced_by_a_keyless_denial(h):
    work = pending(h, byok=True)
    allowed = Mock(side_effect=AssertionError('BYOK was already funded at admission'))
    runner, artifacts, vendor, _ = stage(h, allowed, [T0])
    assert runner.run(work.segment_id).outcome == 'done'
    assert row(h, work)['state'] == 'result_ready'
    allowed.assert_not_called()
    vendor.assert_called_once()
    artifacts.persist_recovery_result.assert_called_once()


@pytest.mark.parametrize('configured,expected', [(None, 1800.0), ('invalid', 1800.0), ('60', 60.0)])
def test_pl571_hold_configuration_and_rollback_change_only_the_retry_deadline(h, monkeypatch, configured, expected):
    if configured is None:
        monkeypatch.delenv('BATCH_ALLOWANCE_HOLD_RETRY_SECONDS', raising=False)
    else:
        monkeypatch.setenv('BATCH_ALLOWANCE_HOLD_RETRY_SECONDS', configured)
    work = pending(h)
    original = row(h, work)
    runner, artifacts, vendor, _ = stage(h, Mock(return_value=(False, 'allowance_exhausted')), [T0])
    result = runner.run(work.segment_id)
    assert (result.outcome, result.available_at) == ('deferred', T0 + expected)
    assert row(h, work) == original
    assert artifacts.method_calls == []
    vendor.assert_not_called()
