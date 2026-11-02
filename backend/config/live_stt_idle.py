"""Kill switch for planned idle-boundary live STT cost reselection.

Default off after the 2026-10-27 listen bb5f6e7 first-text regression: the
reselect path retires the serving leg at every idle onset and rebuilds through
the full recovery/cost chain, which under fleet pressure terminated sessions
(listenlat RCA, data/run-2026-10-13-two-lane-nemotron/listenlat-rca-2026-10-27.md).
An explicit `true`/`1`/`on` re-enables it per deployment.
"""

import os


def idle_parakeet_failback_enabled() -> bool:
    """Kill switch (on unless set off) for the one-time idle return to Parakeet.

    An English session that a transient Parakeet exit (circuit_open, a censored
    death, first-text rescue residue) left on Soniox stays there for its whole
    life with reselect off: 29% of Soniox segments were English-primary at
    Parakeet stage 100 (2026-11-01). This reselects once, at the first idle
    onset where Parakeet is window-eligible, admitting and cooled down — not at
    every onset for every session, which was the 2026-10-27 regression.
    """
    return os.getenv('STT_IDLE_PARAKEET_FAILBACK_ENABLED', 'true').strip().lower() not in {
        '0',
        'false',
        'off',
        'no',
        'disabled',
    }


def idle_reopen_cost_reselect_enabled() -> bool:
    return os.getenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', 'false').strip().lower() in {
        '1',
        'true',
        'on',
        'yes',
        'enabled',
    }
