"""Contained-donor bridge merge; explicit off restores the blanket processed fence.

A sync donor summarized before its live target closed is refused forever by the
``already_processed`` fence. When the donor's recorded span is fully inside the
target's, the merge cannot drop speech the target missed, so the bridge may
absorb it. Every other fence (custody, privacy, partial overlap, open target)
still applies. Off restores the pre-change refusal exactly.
"""

import os

from config.refactor_switches import default_on as rollout_default_on

ENV = 'SYNC_BRIDGE_CONTAINED_DONOR_MERGE_ENABLED'
_ON = frozenset({'1', 'true', 'on', 'yes', 'enabled'})

# Clock jitter between a device-clocked sync span and a live capture span. Kept
# well under a second so a real partial overlap is never rounded into a merge.
CONTAINMENT_TOLERANCE_SECONDS = 0.5


def contained_donor_merge_enabled() -> bool:
    """Unset or blank is on; only an explicit on-value keeps it on, anything else is off.

    Off restores the pre-change refusal exactly: a processed donor is never
    absorbed, no span is compared, and the assignment keeps its blanket
    ``already_processed`` protection. A typo therefore disables the merge,
    never the fence.
    """
    raw = os.getenv(ENV, '').strip().lower()
    return rollout_default_on(ENV, not raw or raw in _ON)
