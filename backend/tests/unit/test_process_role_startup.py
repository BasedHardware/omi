"""OMI_PROCESS_ROLE selects which main.startup_event work a process runs (SCA-3120).

A projection-pump process keeps the pump and what the projector needs and never starts or
leases the FSR reconcilers. Unset keeps today's full startup in today's order.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import main
from app_roles import AppRole, mounts_for, role_from_env
from config import process_role
from config.process_role import ProcessRole, ProcessRoleConfigError
from database import pinecone_mutation_lifecycle, pinecone_partition_state
from database.pinecone_mutation_lifecycle import MutationRegistry
from utils.batch_pipeline import serving
from utils.messaging.adapters import runtime as messaging_runtime
from utils.other import fsr_leader_lease
from utils.stt.parakeet_window import batch_pressure as real_batch_pressure
import utils.held_content_cohort as held_content_cohort

PUMP_FLAG = 'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED'
SERVING_FLAG = 'BATCH_PIPELINE_SERVING_ENABLED'

FULL_TASKS = [
    'stt_cap_cohort_refresh',
    'live_stt_fleet_health',
    'held_content_cohort_refresh',
    'executor_health',
    'episode_compose_settle',
    'mcp_daily_rollup',
    'startup_deletion_wipe_reconcile',
    'periodic_deletion_wipe_reconcile',
    'startup_listen_finalization_reconcile',
    'startup_stale_processing_reconcile',
    'startup_stale_in_progress_reconcile',
    'startup_byok_abandonment_reconcile',
    'periodic_listen_finalization_reconcile',
    'startup_conversation_batch_purge_reconcile',
    'periodic_conversation_batch_purge_reconcile',
    'periodic_durable_queue_age_publish',
    'proactive_message_dispatcher',
]
PUMP_DARK_TASKS = ['stt_cap_cohort_refresh', 'executor_health', 'episode_compose_settle']
PUMP_ACTIVE_TASKS = ['stt_cap_cohort_refresh', 'batch_projection_pump', 'executor_health', 'episode_compose_settle']
SKIPPED_ON_PUMP = (
    'start_mutations',
    'install_shutdown_drain',
    'start_adapters',
    'live_stt_health',
    'held_content_cohort',
    'batch_pressure',
    'soniox_usage',
    'run_blocking',
    'proactive_message_dispatcher',
)
KEPT_ON_PUMP = ('metrics_sidecar', 'validate_account_deletion', 'validate_streaming_stt')


@pytest.fixture
def startup(monkeypatch):
    """Run the real startup_event with every starter replaced by a recorder."""

    tasks: list[str] = []

    def record_task(coro, *, name):
        if hasattr(coro, 'close'):
            coro.close()
        tasks.append(name)
        return SimpleNamespace(name=name)

    calls = {
        'start_mutations': Mock(),
        'install_shutdown_drain': Mock(return_value='restore'),
        'start_adapters': AsyncMock(return_value=None),
        'metrics_sidecar': Mock(),
        'live_stt_health': Mock(return_value='live-health'),
        'held_content_cohort': Mock(return_value='held'),
        'batch_pressure': Mock(),
        'soniox_usage': Mock(),
        'validate_account_deletion': Mock(),
        'validate_streaming_stt': Mock(),
        'run_blocking': Mock(return_value='reconcile'),
        'proactive_message_dispatcher': Mock(return_value='dispatch'),
    }
    monkeypatch.setattr(main, 'app', SimpleNamespace(state=SimpleNamespace()))
    monkeypatch.setattr(main, 'start_background_task', record_task)
    monkeypatch.setattr(serving, 'start_background_task', record_task)
    monkeypatch.setattr(pinecone_partition_state, 'start_mutations', calls['start_mutations'])
    monkeypatch.setattr(pinecone_mutation_lifecycle, 'install_shutdown_drain', calls['install_shutdown_drain'])
    monkeypatch.setattr(messaging_runtime, 'start_adapters', calls['start_adapters'])
    monkeypatch.setattr(main, 'start_metrics_sidecar_server', calls['metrics_sidecar'])
    monkeypatch.setattr(main, 'refresh_stt_cap_cohort_forever', Mock(return_value='cohort'))
    monkeypatch.setattr(main, 'live_stt_health', SimpleNamespace(refresh_forever=calls['live_stt_health']))
    monkeypatch.setattr(held_content_cohort, 'refresh_held_content_cohort_forever', calls['held_content_cohort'])
    monkeypatch.setattr(main, 'batch_pressure', SimpleNamespace(start_from_env=calls['batch_pressure']))
    monkeypatch.setattr(main, 'start_soniox_usage_if_configured', calls['soniox_usage'])
    monkeypatch.setattr(main, 'validate_account_deletion_dispatch_configuration', calls['validate_account_deletion'])
    monkeypatch.setattr(main, 'validate_streaming_stt_env', calls['validate_streaming_stt'])
    monkeypatch.setattr(main, 'log_executor_health', Mock(return_value='health'))
    monkeypatch.setattr(main, 'retry_settled_composes', Mock(return_value='compose'))
    monkeypatch.setattr(main, 'run_blocking', calls['run_blocking'])
    monkeypatch.setattr(main, 'proactive_message_dispatcher', calls['proactive_message_dispatcher'])
    monkeypatch.setattr(main, 'OMI_APP_ROLE', AppRole.ALL)
    for name in (process_role.PROCESS_ROLE_ENV, PUMP_FLAG, SERVING_FLAG, 'MCP_DAILY_ROLLUP_ENABLED'):
        monkeypatch.delenv(name, raising=False)

    def run():
        asyncio.run(main.startup_event())
        return tasks

    return SimpleNamespace(run=run, calls=calls, tasks=tasks)


@pytest.mark.parametrize('raw', [None, '', 'all', ' ALL '])
def test_default_role_starts_todays_full_set_in_order(startup, monkeypatch, raw):
    if raw is not None:
        monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, raw)
    assert startup.run() == FULL_TASKS
    for name, call in startup.calls.items():
        assert call.called, name
    assert startup.calls['run_blocking'].call_count == 6
    assert main.app.state.batch_pipeline_serving is None
    assert main.app.state.messaging_runtime is None


@pytest.mark.parametrize(
    'role, enabled, starts',
    [
        (AppRole.API, 'true', True),
        (AppRole.API, 'false', False),
        (AppRole.REALTIME, 'true', False),
        (AppRole.WORKERS, 'true', False),
    ],
)
def test_mcp_sweeper_follows_service_role_and_kill_switch(startup, monkeypatch, role, enabled, starts):
    monkeypatch.setattr(main, 'OMI_APP_ROLE', role)
    monkeypatch.setenv('MCP_DAILY_ROLLUP_ENABLED', enabled)
    assert ('mcp_daily_rollup' in startup.run()) is starts


def test_dark_pump_role_starts_only_the_pump_keep_set(startup, monkeypatch):
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, 'projection_pump')
    monkeypatch.setenv(PUMP_FLAG, 'false')
    monkeypatch.setenv(SERVING_FLAG, 'false')
    assert startup.run() == PUMP_DARK_TASKS
    for name in SKIPPED_ON_PUMP:
        assert not startup.calls[name].called, name
    for name in KEPT_ON_PUMP:
        assert startup.calls[name].called, name
    assert main.app.state.batch_pipeline_serving is None
    assert not hasattr(main.app.state, 'messaging_runtime')
    assert not hasattr(main.app.state, 'pinecone_restore_signal')


def test_active_pump_role_adds_only_the_pump_supervisor(startup, monkeypatch):
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, 'projection_pump')
    monkeypatch.setenv(PUMP_FLAG, 'true')
    assert startup.run() == PUMP_ACTIVE_TASKS
    for name in SKIPPED_ON_PUMP:
        assert not startup.calls[name].called, name
    stop, task = main.app.state.batch_pipeline_serving
    assert isinstance(stop, asyncio.Event) and task.name == 'batch_projection_pump'


@pytest.mark.parametrize('raw', ['pump', 'projection-pump', 'api', 'none'])
def test_unknown_process_role_fails_before_anything_starts(startup, monkeypatch, raw):
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, raw)
    with pytest.raises(ProcessRoleConfigError, match='OMI_PROCESS_ROLE'):
        startup.run()
    assert startup.tasks == []
    assert not any(call.called for call in startup.calls.values())


@pytest.mark.parametrize('pump_flag', ['true', 'false'])
def test_pump_role_refuses_serving_before_anything_starts(startup, monkeypatch, pump_flag):
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, 'projection_pump')
    monkeypatch.setenv(PUMP_FLAG, pump_flag)
    monkeypatch.setenv(SERVING_FLAG, ' True ')
    with pytest.raises(ProcessRoleConfigError, match=SERVING_FLAG):
        startup.run()
    assert startup.tasks == []
    assert not any(call.called for call in startup.calls.values())


def test_serving_stays_allowed_on_the_default_role():
    assert process_role.startup_process_role({SERVING_FLAG: 'true'}) is ProcessRole.ALL


def test_pump_flag_off_does_not_restore_the_reconcilers(startup, monkeypatch):
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, 'projection_pump')
    monkeypatch.setenv(PUMP_FLAG, 'false')
    assert not set(startup.run()) & (set(FULL_TASKS) - set(PUMP_DARK_TASKS))


def test_run_fsr_loop_never_touches_the_lease_on_the_pump(monkeypatch):
    loop_lease = Mock(side_effect=AssertionError('pump must not lease'))
    callback = Mock(side_effect=AssertionError('pump must not reconcile'))
    monkeypatch.setattr(fsr_leader_lease, 'loop_lease', loop_lease)
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, 'projection_pump')
    assert main._run_fsr_loop('reconcile_pending_deletion_wipes', callback, 300) == {}
    assert not loop_lease.called and not callback.called


def test_run_fsr_loop_still_leases_on_the_default_role(monkeypatch):
    lease = SimpleNamespace(run=Mock(return_value={'requeued': 1}))
    monkeypatch.setattr(fsr_leader_lease, 'loop_lease', Mock(return_value=lease))
    monkeypatch.delenv(process_role.PROCESS_ROLE_ENV, raising=False)
    assert main._run_fsr_loop('reconcile_pending_deletion_wipes', Mock(), 300) == {'requeued': 1}
    fsr_leader_lease.loop_lease.assert_called_once_with('reconcile_pending_deletion_wipes')


def test_shutdown_after_pump_startup_completes(startup, monkeypatch):
    monkeypatch.setenv(process_role.PROCESS_ROLE_ENV, 'projection_pump')
    startup.run()
    # Real cleanup for what the pump skipped: empty Pinecone registry, no messaging runtime,
    # no serving runtime and a never-started batch-pressure poller. The lease release (the pump
    # never acquired one, see the _run_fsr_loop test) and unrelated cleanups are stubbed.
    monkeypatch.setattr(pinecone_partition_state, '_mutations', MutationRegistry())
    monkeypatch.setattr(main, 'batch_pressure', real_batch_pressure)
    for name in ('shutdown_managed_spend_ledger', 'shutdown_sync_metrics', 'close_all_clients'):
        monkeypatch.setattr(main, name, AsyncMock())
    stop_sidecar = Mock()
    monkeypatch.setattr(main, 'stop_metrics_sidecar_server', stop_sidecar)
    release = Mock()
    monkeypatch.setattr(fsr_leader_lease, 'release_loop_leases', release)
    asyncio.run(main.shutdown_event())
    assert stop_sidecar.called and release.called


def test_process_role_does_not_change_router_selection():
    pump = {process_role.PROCESS_ROLE_ENV: 'projection_pump'}
    assert role_from_env(pump) is AppRole.ALL
    assert mounts_for(role_from_env(pump)) == mounts_for(role_from_env({}))
    assert role_from_env({**pump, 'OMI_ROLE': 'workers'}) is AppRole.WORKERS
    assert process_role.process_role_from_env({'OMI_ROLE': 'workers'}) is ProcessRole.ALL
    assert process_role.process_role_from_env({**pump, 'OMI_ROLE': 'api'}) is ProcessRole.PROJECTION_PUMP
