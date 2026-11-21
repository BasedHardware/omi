"""Kill switches (default on) for live STT routing across rolling restarts.

Each switch restores the previous behaviour when set to false/0/off. They are
read per decision, so a listen env change takes effect at the next session.
"""

from __future__ import annotations

from config.refactor_switches import default_on as rollout_default_on

import os

# 1. A provider death caused by this pod draining is not provider evidence.
DRAIN_DEATH_CENSOR_ENV = 'LISTEN_STT_DRAIN_DEATH_CENSOR_ENABLED'
# 2. The availability escape never re-admits a benched (stage-0) target while
#    any stage>0 target can serve the session.
ESCAPE_EXCLUDES_BENCHED_ENV = 'LISTEN_STT_ESCAPE_EXCLUDES_BENCHED_ENABLED'
# 3. While the escape serves a user, that user's outcome counts as a trial vote
#    even outside the stt-reentry cohort, so a recovering provider can promote.
ESCAPE_TRIAL_VOTES_ENV = 'LISTEN_STT_ESCAPE_TRIAL_VOTES_ENABLED'
# 4. One jittered same-target retry after a connection-level failure, before
#    falling through to the next route.
SAME_TARGET_RETRY_ENV = 'LISTEN_STT_SAME_TARGET_RETRY_ENABLED'
# 5. Live TDT HTTP failures quarantine the contacted GPU replica and get one
#    different-replica retry inside the original POST/deadline budget.
WINDOW_REPLICA_RECOVERY_ENV = 'PARAKEET_WINDOW_REPLICA_RECOVERY_ENABLED'
# Recovery rejection needs a meaningful sample and the normal burst detector.
RECOVERY_SAMPLE_GUARD_ENV = 'STT_ROUTING_RECOVERY_SAMPLE_GUARD_ENABLED'
# 6. While the escape serves sessions, its lead target must not hold a worse
#    failure rate than a proven (trial-sized sample) stage-5+ candidate.
ESCAPE_BEST_RATE_PRIMARY_ENV = 'LISTEN_STT_ESCAPE_BEST_RATE_PRIMARY_ENABLED'
# 7. A held target never promotes to the only stage-100 share while its guard
#    target is at stage >= 5 (modulate-velma-2 vs soniox, 2026-10-28).
SOLE_PRIMARY_HOLD_ENV = 'LISTEN_STT_SOLE_PRIMARY_HOLD_ENABLED'
# 8. A leg death on a target inside a failover-surge window (another target's
#    bench just mass-failovered sessions onto it) is not burst-arm evidence.
FAILOVER_SURGE_CENSOR_ENV = 'LISTEN_STT_FAILOVER_SURGE_CENSOR_ENABLED'


def _default_on(name: str) -> bool:
    return rollout_default_on(name, os.getenv(name, 'true').strip().lower() not in {'false', '0', 'off'})


def drain_death_censor_enabled() -> bool:
    return _default_on(DRAIN_DEATH_CENSOR_ENV)


def escape_excludes_benched_enabled() -> bool:
    return _default_on(ESCAPE_EXCLUDES_BENCHED_ENV)


def escape_trial_votes_enabled() -> bool:
    return _default_on(ESCAPE_TRIAL_VOTES_ENV)


def same_target_retry_enabled() -> bool:
    return _default_on(SAME_TARGET_RETRY_ENV)


def window_replica_recovery_enabled() -> bool:
    return _default_on(WINDOW_REPLICA_RECOVERY_ENV)


def recovery_sample_guard_enabled() -> bool:
    return _default_on(RECOVERY_SAMPLE_GUARD_ENV)


def escape_best_rate_primary_enabled() -> bool:
    return _default_on(ESCAPE_BEST_RATE_PRIMARY_ENV)


def sole_primary_hold_enabled() -> bool:
    return _default_on(SOLE_PRIMARY_HOLD_ENV)


def failover_surge_censor_enabled() -> bool:
    return _default_on(FAILOVER_SURGE_CENSOR_ENV)
