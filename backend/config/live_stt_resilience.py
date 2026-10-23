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
