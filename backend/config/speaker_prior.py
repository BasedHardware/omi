"""Pinned-speaker prior switch (default on). Read at the call boundary, never at import."""

import os

from config.refactor_switches import default_on as rollout_default_on
from typing import Mapping, Optional

PINNED_SPEAKER_PRIOR_ENV = 'PINNED_SPEAKER_PRIOR_ENABLED'


def pinned_speaker_prior_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """When on, near-misses on pinned people become suggestions and voice candidates are recorded.

    It never loosens the automatic-label threshold or margin.
    """
    value = (environ if environ is not None else os.environ).get(PINNED_SPEAKER_PRIOR_ENV, '')
    return rollout_default_on(
        PINNED_SPEAKER_PRIOR_ENV, value.strip().lower() not in {'false', 'off', '0'}, environ=environ
    )
