"""Registry for desktop product experiments (EXP-002 and successors).

Pure constants and predicates — no IO, no clients — so routers, tests, and the
pre-registration docs share one source of truth. The experiment id is the
assignment salt: **never rename a running experiment** (see
``utils/experiments.bucket_of``).

Adding an arm to EXP-002 later is a registry change here (append a
``(name, weight)`` pair to ``EXP_002_ARMS``); no new enroll path is written.
The draw partitions buckets in list order, so inserting an arm re-splits only
the buckets after its bound — the pre-registration records the reweight rule.
"""

from __future__ import annotations

import os
from typing import Iterable

# v1 ships two arms at equal weight. Arm names are persisted verbatim as the
# ``variant`` field of the assignment document and attached to every tagged
# event, log, and crash report.
EXP_002_EXPERIMENT_ID = 'EXP-002-desktop-identity-memory-v1'
EXP_002_ARMS: tuple[tuple[str, float], ...] = (
    ('control', 1.0),
    ('memory_v1', 1.0),
)
EXP_002_TREATMENT_ARM = 'memory_v1'

# Kill switch, following the production PostHog flag pattern (server-side,
# keyed on Firebase uid, tri-state fail-closed — see ``utils/jit_rollout``).
# Both flags absent/unknown/error ⇒ no enrollment and control chrome.
EXP_002_FLAG_KEY = 'exp-002-desktop-identity-v1'
EXP_002_KILL_SWITCH_FLAG_KEY = 'exp-002-desktop-identity-kill-v1'

# v1 exposure: the Beta bundle only. Stable stays control until explicitly
# widened here. Named dev bundles never enroll; they exercise arms through the
# client-side local override instead.
EXP_002_ALLOWED_BUNDLE_IDS = frozenset({'com.omi.computer-macos.beta'})
EXP_002_ALLOWED_CHANNEL = 'beta'

# Only binaries that contain this chrome may enroll; older clients must not be
# enrolled into arms they cannot render. The endpoint is new, so no shipped
# binary can call it below this floor — this is defense in depth against
# misreported versions, not the primary gate. Override for local harness runs
# via EXP_002_MIN_DESKTOP_APP_VERSION.
EXP_002_MIN_DESKTOP_APP_VERSION = '0.12.273'


def exp_002_min_app_version() -> str:
    override = os.getenv('EXP_002_MIN_DESKTOP_APP_VERSION', '').strip()
    return override or EXP_002_MIN_DESKTOP_APP_VERSION


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.strip().split('.'):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


def version_meets_floor(version: str, floor: str) -> bool:
    """True when ``version`` >= ``floor`` under dotted-numeric comparison."""

    return _version_tuple(version) >= _version_tuple(floor)


def known_experiment_ids() -> Iterable[str]:
    return (EXP_002_EXPERIMENT_ID,)
