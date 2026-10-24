"""Recovery narrowing intersects effective dispatch scope at every owner entry."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
from threading import Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from config import stt_cap_dispatch as policy
from models.users import ProcessingBacklog
from routers import users as route
from utils import funded_processing, processing_backlog as backlog, processing_backlog_worker as worker
from utils.observability import stt_cap_dispatch as metrics
from utils.sync import cap_hold_recovery as recovery, cap_hold_redrive as redrive, pipeline


@pytest.fixture(
    params=[
        (None, 'probe', True),
        (None, 'peer', True),
        (None, 'outside', False),
        ('uid:probe', 'probe', True),
        ('uid:probe', 'peer', False),
        ('uid:outside', 'outside', False),
        ('uid:probe,typo', 'probe', False),
        ('', 'probe', False),
        ('pct:0', 'probe', False),
        ('pct:100', 'peer', True),
        ('all', 'outside', False),
    ],
    ids=lambda case: f'{case[0] or repr(case[0])}-{case[1]}',
)
def admission(request, monkeypatch):
    raw, uid, expected = request.param
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    # The effective document resolver wins over a deliberately broad env fallback.
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setattr(policy, '_cohort_resolver', lambda: 'uid:probe,uid:peer')
    monkeypatch.delenv('STT_CAP_RECOVERY_COHORT', raising=False)
    if raw is not None:
        monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', raw)
    return SimpleNamespace(uid=uid, allowed=expected)


@pytest.fixture
def consent(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(funded_processing, 'period_id', lambda: now.strftime('%Y-%m'))
    allowance = Mock()
    monkeypatch.setattr(funded_processing, 'allowance', allowance)
    snapshot = Mock(return_value=ProcessingBacklog(state='waiting_choice', held_audio_count=1, remaining_units=10))
    monkeypatch.setattr(backlog, 'snapshot', snapshot)
    start = Mock(return_value={'token': 'synthetic-run'})
    monkeypatch.setattr(worker.store, 'start', start)
    return SimpleNamespace(start=start, snapshot=snapshot, allowance=allowance, now=now)


@pytest.mark.parametrize('legacy,ladder', [(False, False), (True, False), (False, True), (True, True)])
def test_recovery_policy_preserves_listen_admission(admission, monkeypatch, legacy, ladder):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(legacy).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    uid, allowed = admission.uid, admission.allowed and (legacy or ladder)
    assert policy.any_recovery_admission_enabled(uid) is allowed
    assert policy.recovery_admission_enabled(uid, 'live') is allowed
    assert not policy.recovery_admission_enabled(uid, 'sync')
    assert policy.execution_admission_enabled(uid, 'live') is (uid != 'outside' and (legacy or ladder))
    assert policy.enabled_for(uid, 'live') is (uid != 'outside' and legacy)


def test_manual_consent_only_starts_selected_owner(admission, consent):
    chosen = backlog.choose(admission.uid, request_key='synthetic-request')
    assert bool(chosen) is admission.allowed
    assert consent.start.called is admission.allowed
    assert consent.allowance.called is admission.allowed


@pytest.mark.parametrize('asynchronous', [False, True])
async def test_upgrade_consent_only_starts_selected_owner(admission, consent, monkeypatch, asynchronous):
    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    if asynchronous:
        await worker.upgrade_async(admission.uid, 'synthetic-upgrade', intent_at=consent.now)
    else:
        worker.upgrade(admission.uid, 'synthetic-upgrade', intent_at=consent.now)
    assert consent.start.called is admission.allowed
    if admission.allowed:
        assert consent.start.call_args.kwargs['automatic'] is True
        assert consent.start.call_args.kwargs['begin'] is True


def test_backlog_process_api_gates_before_consent(admission, consent):
    app = FastAPI()
    app.post('/v1/users/processing-backlog/process')(route.process_waiting_recordings)
    app.dependency_overrides[route.auth.get_current_user_uid] = lambda: admission.uid
    with TestClient(app) as client:
        response = client.post('/v1/users/processing-backlog/process', headers={'Idempotency-Key': 'synthetic-request'})
    assert response.status_code == (200 if admission.allowed else 404)
    assert consent.start.called is admission.allowed
    assert consent.snapshot.called is admission.allowed


@pytest.mark.parametrize('continuation', [False, True])
async def test_worker_gates_before_cooldown_or_backlog_reads(admission, monkeypatch, continuation):
    cooldown = Mock(return_value=True)
    read = Mock(return_value={})
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', cooldown)
    monkeypatch.setattr(worker.store, 'read', read)
    await worker.run(admission.uid, continuation=continuation)
    assert cooldown.called is (admission.allowed and not continuation)
    assert read.called is admission.allowed


async def test_redrive_skips_excluded_owners_but_keeps_custody_maintenance(admission, monkeypatch):
    monkeypatch.setenv('CAP_HOLD_DURABLE_REDRIVE_ENABLED', 'true')
    choice = SimpleNamespace(reference=SimpleNamespace(path=f'users/{admission.uid}/processing_backlog/current'))
    held = SimpleNamespace(id='hold', reference=SimpleNamespace(path=f'users/{admission.uid}/stt_cap_holds/hold'))
    monkeypatch.setattr(redrive.store, 'fleet_snapshot', lambda: {})
    monkeypatch.setattr(redrive, 'publish_fleet', Mock())
    monkeypatch.setattr(redrive.store, 'discover', lambda kind: [choice] if kind == 'choices' else [held])
    seal, cleanup = Mock(return_value=True), Mock()
    monkeypatch.setattr(redrive.live_cap_staging, 'seal', seal)
    monkeypatch.setattr(redrive.live_cap_staging, 'cleanup', cleanup)
    run = AsyncMock(return_value=False)
    monkeypatch.setattr(redrive.processing_backlog_worker, 'run', run)
    result = await redrive.sweep()
    assert result == {'sealed': 1, 'visited': int(admission.allowed)}
    assert run.called is admission.allowed
    seal.assert_called_once()
    cleanup.assert_called_once()


async def test_direct_wake_gates_registered_backlog_runner(admission, monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr(recovery, '_backlog_runner', run)
    await recovery.recover(admission.uid)
    assert run.called is admission.allowed


async def test_selected_manifest_gates_before_claim_or_settlement(admission, monkeypatch):
    metadata = Mock(return_value={'origin': 'live'})
    monkeypatch.setattr(recovery.cap_hold, 'metadata', metadata)
    settle = Mock()
    monkeypatch.setattr(recovery, '_settle_and_erase', settle)
    snapshot = SimpleNamespace(to_dict=lambda: {'state': 'completed'})
    assert await recovery.recover_selected(admission.uid, snapshot) is admission.allowed
    assert metadata.called is admission.allowed
    assert settle.called is admission.allowed


async def test_recovery_row_gates_before_metadata_and_new_provider_dispatch(admission, monkeypatch):
    # Finalized rows avoid unrelated provider fixtures; the per-piece dispatch
    # check separately verifies the same predicate before allowance/provider work.
    assert await recovery._recover_row(admission.uid, Mock(), {'finalized': True}) is admission.allowed
    allowance = Mock(return_value=True)
    monkeypatch.setattr(recovery, 'sync_allowed', allowance)
    monkeypatch.setattr(recovery, 'get_hard_restriction_status', lambda uid: (False, None))
    monkeypatch.setattr(recovery, 'is_daily_audio_ceiling_exceeded', lambda uid: False)
    assert recovery._new_dispatch_allowed(admission.uid, 'live') is admission.allowed
    assert allowance.called is admission.allowed


def test_sync_pipeline_entry_gates_before_io(admission, monkeypatch):
    class Admitted(BaseException):
        pass

    # A local sentinel at the first IO boundary proves admission without a
    # provider, signed URL, account read or pipeline persistence.
    first_io = Mock(side_effect=Admitted)
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', first_io)

    def process():
        return pipeline.process_segment(
            'synthetic.wav', admission.uid, {}, Lock(), [], cap_recovery=True, cap_dispatch_lane='live'
        )

    if admission.allowed:
        with pytest.raises(Admitted):
            process()
    else:
        assert process() is False
    assert first_io.called is admission.allowed


@pytest.mark.parametrize('raw,state', [(None, 'unset'), ('uid:probe', 'set'), ('all', 'set'), ('', 'malformed')])
def test_narrowing_metric_has_only_fixed_state_labels(monkeypatch, raw, state):
    monkeypatch.delenv('STT_CAP_RECOVERY_COHORT', raising=False)
    if raw is not None:
        monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', raw)
    samples = list(metrics.RECOVERY_COHORT_NARROWED.collect())[0].samples
    assert {tuple(sample.labels.items()): sample.value for sample in samples} == {
        (('state', label),): int(label == state) for label in ('unset', 'set', 'malformed')
    }


def test_malformed_warning_once_without_private_tokens_even_under_concurrency(monkeypatch, caplog):
    monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', 'uid:synthetic-private,typo')
    monkeypatch.setattr(policy, '_recovery_warning_emitted', False)
    caplog.set_level(logging.WARNING, logger=policy.__name__)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert not any(pool.map(policy.any_recovery_admission_enabled, ['probe', 'peer'] * 20))
    records = [record for record in caplog.records if record.name == policy.__name__]
    assert len(records) == 1
    assert records[0].getMessage() == 'Malformed STT cap recovery cohort; denying all recovery'
    assert not records[0].args


@pytest.mark.parametrize('narrowed', ['uid:peer', 'pct:0', 'typo'])
def test_pipeline_rechecks_narrowing_at_provider_boundary(monkeypatch, narrowed):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    monkeypatch.setattr(policy, '_cohort_resolver', lambda: 'all')
    monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', 'uid:probe')
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *args: False)
    monkeypatch.setattr(pipeline, 'sync_allowed', lambda *args, **kwargs: True)
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', lambda path: 'https://synthetic.invalid')

    async def keyterms(uid, vocabulary):
        monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', narrowed)
        return vocabulary

    monkeypatch.setattr(pipeline, 'keyterms', keyterms)
    transcribe = Mock(side_effect=AssertionError('excluded owner reached provider'))
    monkeypatch.setattr(pipeline.cap_recovery_provider, 'transcribe', transcribe)
    outcome, errors = {}, []
    assert not pipeline.process_segment(
        'synthetic.wav',
        'probe',
        {},
        Lock(),
        errors,
        cap_recovery=True,
        cap_dispatch_lane='live',
        cap_recovery_service=('modulate', 'en', 'velma-2'),
        deferred_outcome=outcome,
    )
    assert outcome == {'provider_called': False, 'cap_held': True}
    assert not errors
    transcribe.assert_not_called()
