"""Kill switch for planned idle-boundary live STT cost reselection.

Default off after the 2026-10-27 listen bb5f6e7 first-text regression: the
reselect path retires the serving leg at every idle onset and rebuilds through
the full recovery/cost chain, which under fleet pressure terminated sessions
(listenlat RCA, data/run-2026-10-13-two-lane-nemotron/listenlat-rca-2026-10-27.md).
An explicit `true`/`1`/`on` re-enables it per deployment.
"""

import os


def idle_reopen_cost_reselect_enabled() -> bool:
    return os.getenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', 'false').strip().lower() in {
        '1',
        'true',
        'on',
        'yes',
        'enabled',
    }
