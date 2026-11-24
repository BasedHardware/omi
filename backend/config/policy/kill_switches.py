"""Allowlist of live E1/E2 ops_kill reads. True means the feature may run.

Worker-only ops switches remain in E1b. Process startup/auth/capacity config is
not per-unit rollout policy. Every entry here must match the flag registry.
"""

from collections import OrderedDict
import logging
import os
from threading import Lock

KILL_SWITCHES = {
    'BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED': True,
    'BATCH_RESULT_PROTOCOL_GUARD_ENABLED': True,
    'BATCH_ALLOWANCE_PARK_ENABLED': True,
    'BATCH_ALLOWANCE_INTAKE_PARK_ENABLED': True,
    'BATCH_PIPELINE_FRESH_GUARD_ENABLED': True,
    'BATCH_PIPELINE_DELIVERED_SHARE_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_HOLD_LOG_ENABLED': False,
    'BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED': False,
    'CONVERSATION_TERMINAL_FAMILY_MODE': True,
    'BATCH_HELD_DEAD_LETTER_ENABLED': True,
    'BATCH_PARKED_JOB_SWEEPER_ENABLED': True,
    'BATCH_PIPELINE_LEADER_LEASE_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_TASKS_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED': True,
    'BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED': True,
    'BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED': True,
    'BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_OWNER_ONLY_ENABLED': True,
    'BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED': True,
    'BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED': True,
    'BATCH_PIPELINE_MERGE_STALE_HEAD_PROMOTE_ENABLED': True,
    'BATCH_PIPELINE_MERGE_AGED_GPU_RELEASE_ENABLED': True,
    'BATCH_PIPELINE_READY_DISCOVERY_CURSOR_ENABLED': True,
    'BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED': True,
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PREDECESSOR_REPLAY_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED': True,
    'BATCH_PIPELINE_FOLLOWUP_EARLY_COALESCE_ENABLED': True,
    'BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED': True,
    'BATCH_PROJECTION_OUTBOX': True,
    'BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED': True,
    'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': True,
    'BATCH_PIPELINE_SERVING_PROJECTION_SWEEP': True,
    'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED': False,
    'BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED': False,
    'BATCH_PIPELINE_PROJECTION_RESTORABLE_CAP_EXPIRY_ENABLED': False,
    'BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_WAKE_ENABLED': True,
    'PROJECTION_DRAIN_CLAIM_AWARE': True,
    'PROJECTION_DRAIN_PRIVACY_BACKOFF': True,
    'PROJECTION_DRAIN_LIVE_TARGET_BACKOFF': True,
    'PROJECTION_PRIVACY_REFUSAL_RESUME': True,
    'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED': True,
    'PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED': True,
    'BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED': True,
    'BATCH_PIPELINE_HELD_PARTIAL_ENABLED': True,
    'AUDIO_SILENCE_CENSUS_ENABLED': True,
    'CONVERSATION_BATCH_PURGE_COALESCING_ENABLED': True,
    # Backlog state machine (config/backlog_state_machine.py). Defaults follow the
    # lead2 rule: ON only where the change just cuts wasted work or retries, OFF
    # where it changes custody, settle or expiry semantics.
    'CAPTURE_RETRY_CAP_ENFORCED': False,
    'BATCH_HELD_REDRIVE_COUNTER_ENABLED': True,
    'BATCH_HELD_REDRIVE_BUDGET_ENABLED': False,
    'BATCH_PIPELINE_RETAINED_DIGEST_HOLD_ENABLED': True,
}
DISABLE_ONLY_SWITCHES = frozenset(
    {
        'BATCH_PIPELINE_LEADER_LEASE_ENABLED',
        'BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED',
        'BATCH_PARKED_JOB_SWEEPER_ENABLED',
        'AUDIO_SILENCE_CENSUS_ENABLED',
    }
)
# Trimmed, case-insensitive true means on; never use the capture-coverage
# serve-mode parser, which treats an unset default-off switch as on.
BACKLOG_STATE_MACHINE_SWITCHES = frozenset(
    {
        'CAPTURE_RETRY_CAP_ENFORCED',
        'BATCH_HELD_REDRIVE_COUNTER_ENABLED',
        'BATCH_HELD_REDRIVE_BUDGET_ENABLED',
    }
)
logger = logging.getLogger(__name__)
_MAX_LOGGED_SWITCHES = 1024
_last_logged: OrderedDict[tuple[str, str], bool] = OrderedDict()
_log_lock = Lock()


def _log_switch(env, policy_id: str, name: str, enabled: bool) -> None:
    message = 'event=batch_policy_kill_switch policy_id=%s switch=%s enabled=%s count=1'
    if env.get('BATCH_POLICY_KILL_SWITCH_LOG_ON_CHANGE_ENABLED', '').strip().lower() != 'true':
        logger.info(message, policy_id, name, enabled)
        return
    if not logger.isEnabledFor(logging.INFO):
        return
    key = (policy_id, name)
    with _log_lock:
        previous = _last_logged.get(key)
        _last_logged[key] = enabled
        _last_logged.move_to_end(key)
        if len(_last_logged) > _MAX_LOGGED_SWITCHES:
            _last_logged.popitem(last=False)
        if previous != enabled:
            logger.info(message + ' changed=%s', policy_id, name, enabled, 'false' if previous is None else 'true')


def kill_switch(name: str, *, policy_id: str = 'control', flags=None, log: bool = True) -> bool:
    if name not in KILL_SWITCHES:
        raise ValueError('unregistered live batch switch')
    env = os.environ if flags is None else flags
    if name in BACKLOG_STATE_MACHINE_SWITCHES:
        # Match the other true-only switches: trim and case-fold; unknown
        # values fail closed and unset uses the registered default.
        raw = env.get(name)
        enabled = KILL_SWITCHES[name] if raw is None else raw.strip().lower() == 'true'
        if log:
            _log_switch(env, policy_id, name, enabled)
        return enabled
    value = env.get(name, str(KILL_SWITCHES[name])).strip().lower()
    if name in {
        'BATCH_ALLOWANCE_PARK_ENABLED',
        'BATCH_ALLOWANCE_INTAKE_PARK_ENABLED',
        'BATCH_PIPELINE_SERVING_PROJECTION_SWEEP',
        'BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED',
        'PROJECTION_DRAIN_CLAIM_AWARE',
        'PROJECTION_DRAIN_PRIVACY_BACKOFF',
        'PROJECTION_DRAIN_LIVE_TARGET_BACKOFF',
        'PROJECTION_PRIVACY_REFUSAL_RESUME',
    }:
        enabled = value != 'off'
        if value in {'false', '0', 'no'}:
            logger.warning("only 'off' disables %s; value '%s' keeps it ON", name, value)
    elif name in {
        'CONVERSATION_TERMINAL_FAMILY_MODE',
        'BATCH_PIPELINE_FRESH_GUARD_ENABLED',
        'BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED',
        'BATCH_PIPELINE_DELIVERED_SHARE_ENABLED',
        'BATCH_PROJECTION_OUTBOX',
    }:
        enabled = value not in {'false', '0', 'off', 'no'}
    elif name == 'CONVERSATION_BATCH_PURGE_COALESCING_ENABLED':
        enabled = value not in {'false', '0', 'off', 'no'}
    elif name == 'PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED':
        enabled = value not in {'false', '0', 'off'}
    else:
        enabled = value != 'false' if name in DISABLE_ONLY_SWITCHES else value == 'true'
    from config.refactor_switches import default_on

    # Preserve the explicit off-only controls and true-only pump selector
    # in every parser mode.
    if name not in {
        'BATCH_PARKED_JOB_SWEEPER_ENABLED',
        'BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED',
        'CONVERSATION_BATCH_PURGE_COALESCING_ENABLED',
        'BATCH_ALLOWANCE_PARK_ENABLED',
        'BATCH_ALLOWANCE_INTAKE_PARK_ENABLED',
        'BATCH_PIPELINE_SERVING_PROJECTION_SWEEP',
        'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED',
        'BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED',
        'BATCH_PIPELINE_PROJECTION_HOLD_LOG_ENABLED',
        'BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED',
        'BATCH_PIPELINE_PROJECTION_RESTORABLE_CAP_EXPIRY_ENABLED',
        'BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED',
        'PROJECTION_DRAIN_CLAIM_AWARE',
        'PROJECTION_DRAIN_PRIVACY_BACKOFF',
        'PROJECTION_DRAIN_LIVE_TARGET_BACKOFF',
        'PROJECTION_PRIVACY_REFUSAL_RESUME',
    }:
        enabled = default_on(name, enabled, environ=env)
    # Dark observability callers suppress even the switch-read log when disabled.
    if log:
        _log_switch(env, policy_id, name, enabled)
    return enabled
