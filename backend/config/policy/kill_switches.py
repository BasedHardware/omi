"""Allowlist of live E1/E2 ops_kill reads. True means the feature may run.

Worker-only ops switches remain in E1b. Process startup/auth/capacity config is
not per-unit rollout policy. Every entry here must match the flag registry.
"""

import logging
import os

KILL_SWITCHES = {
    'BATCH_ALLOWANCE_PARK_ENABLED': True,
    'BATCH_PIPELINE_FRESH_GUARD_ENABLED': True,
    'BATCH_PIPELINE_DELIVERED_SHARE_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_HOLD_LOG_ENABLED': False,
    'BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED': False,
    'CONVERSATION_TERMINAL_FAMILY_MODE': True,
    'BATCH_HELD_DEAD_LETTER_ENABLED': True,
    'BATCH_PIPELINE_LEADER_LEASE_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_TASKS_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED': True,
    'BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED': True,
    'BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_OWNER_ONLY_ENABLED': True,
    'BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED': True,
    'BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED': True,
    'BATCH_PIPELINE_READY_DISCOVERY_CURSOR_ENABLED': True,
    'BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED': True,
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PREDECESSOR_REPLAY_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED': True,
    'BATCH_PROJECTION_FINISH_BACKOFF_ENABLED': False,
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
    # Backlog state machine (config/backlog_state_machine.py). Defaults follow the
    # lead2 rule: ON only where the change just cuts wasted work or retries, OFF
    # where it changes custody, settle or expiry semantics.
    'CAPTURE_RETRY_CAP_ENFORCED': False,
    'BATCH_HELD_REDRIVE_COUNTER_ENABLED': True,
    'BATCH_HELD_REDRIVE_BUDGET_ENABLED': False,
}
DISABLE_ONLY_SWITCHES = frozenset({'BATCH_PIPELINE_LEADER_LEASE_ENABLED'})
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
            logger.info(
                'event=batch_policy_kill_switch policy_id=%s switch=%s enabled=%s count=1', policy_id, name, enabled
            )
        return enabled
    value = env.get(name, str(KILL_SWITCHES[name])).strip().lower()
    if name in {
        'BATCH_ALLOWANCE_PARK_ENABLED',
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
        'BATCH_PIPELINE_DELIVERED_SHARE_ENABLED',
    }:
        enabled = value not in {'false', '0', 'off', 'no'}
    elif name == 'PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED':
        enabled = value not in {'false', '0', 'off'}
    else:
        enabled = value != 'false' if name in DISABLE_ONLY_SWITCHES else value == 'true'
    from config.refactor_switches import default_on

    # Preserve the explicit off-only controls and true-only pump selector
    # in every parser mode.
    if name not in {
        'BATCH_ALLOWANCE_PARK_ENABLED',
        'BATCH_PIPELINE_SERVING_PROJECTION_SWEEP',
        'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED',
        'BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED',
        'BATCH_PROJECTION_FINISH_BACKOFF_ENABLED',
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
        logger.info(
            'event=batch_policy_kill_switch policy_id=%s switch=%s enabled=%s count=1', policy_id, name, enabled
        )
    return enabled
