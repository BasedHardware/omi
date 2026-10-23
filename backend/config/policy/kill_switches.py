"""Allowlist of live E1/E2 ops_kill reads. True means the feature may run.

Worker-only ops switches remain in E1b. Process startup/auth/capacity config is
not per-unit rollout policy. Every entry here must match the flag registry.
"""

import logging
import os

KILL_SWITCHES = {
    'BATCH_PIPELINE_LEADER_LEASE_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_TASKS_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED': True,
    'BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED': True,
    'BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED': True,
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PREDECESSOR_REPLAY_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED': True,
    'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED': True,
    'PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED': True,
    'BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED': True,
    'BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED': True,
    'BATCH_PIPELINE_HELD_PARTIAL_ENABLED': True,
}
DISABLE_ONLY_SWITCHES = frozenset({'BATCH_PIPELINE_LEADER_LEASE_ENABLED'})
logger = logging.getLogger(__name__)


def kill_switch(name: str, *, policy_id: str = 'control', flags=None) -> bool:
    if name not in KILL_SWITCHES:
        raise ValueError('unregistered live batch switch')
    env = os.environ if flags is None else flags
    value = env.get(name, str(KILL_SWITCHES[name])).strip().lower()
    if name == 'PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED':
        enabled = value not in {'false', '0', 'off'}
    else:
        enabled = value != 'false' if name in DISABLE_ONLY_SWITCHES else value == 'true'
    from config.refactor_switches import default_on

    enabled = default_on(name, enabled, environ=env)
    logger.info('event=batch_policy_kill_switch policy_id=%s switch=%s enabled=%s count=1', policy_id, name, enabled)
    return enabled
