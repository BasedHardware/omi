"""Allowlist of live E1 ops_kill reads. True means the feature may run.

Worker-only ops switches remain in E1b. Process startup/auth/capacity config is
not per-unit rollout policy. Every entry here must match the flag registry.
"""

import logging
import os

KILL_SWITCHES = {
    'BATCH_PIPELINE_RECOVERY_TASKS_ENABLED': True,
    'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED': True,
}
logger = logging.getLogger(__name__)


def kill_switch(name: str, *, policy_id: str = 'control', flags=None) -> bool:
    if name not in KILL_SWITCHES:
        raise ValueError('unregistered live batch switch')
    env = os.environ if flags is None else flags
    enabled = env.get(name, str(KILL_SWITCHES[name])).strip().lower() == 'true'
    logger.info('event=batch_policy_kill_switch policy_id=%s switch=%s enabled=%s count=1', policy_id, name, enabled)
    return enabled
