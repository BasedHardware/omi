"""Episode-join variant F admission: the runtime flag store first, the env bucket as fallback.

The Omi flag store rule ``episode_f_join`` (``scripts/omi_flags.py set episode_f_join --rollout N``)
is the ramp and the instant kill (``--inactive``). With no rule, an unconfigured store, or a store
that never loaded, ``EPISODE_F_JOIN_PERCENT`` decides (default 0, so nothing ships on by accident).
``EPISODE_F_JOIN_ENABLED=off`` overrides both. Never raises: any failure admits nobody.
"""

from __future__ import annotations

import logging

from config.episodes import F_JOIN_FLAG_KEY, f_join_enabled, f_join_env_admitted
from utils import omi_flags

logger = logging.getLogger(__name__)


def admitted(uid: str) -> bool:
    try:
        if not uid or not f_join_enabled():
            return False
        resolved = omi_flags.resolve(F_JOIN_FLAG_KEY, uid)
        if resolved is not None:
            return resolved.enabled
        return f_join_env_admitted(uid)
    except Exception as error:
        logger.warning('event=episode_f_join outcome=admission_failed exception_type=%s', type(error).__name__)
        return False
