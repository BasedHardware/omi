"""Contained-donor bridge merge; explicit off restores the blanket processed fence.

A sync donor summarized before its live target closed is refused forever by the
``already_processed`` fence. When both the donor's and the target's recorded
segment span exist and the donor's is fully inside the target's, the merge cannot
drop speech the target missed, so the bridge may absorb it. Every other fence
(custody, privacy, partial overlap, open target) still applies. Off restores the
pre-change refusal exactly.

This switch gates notes and memories the merge cannot restore, so an unreadable
value fails closed in every capture-coverage mode: only an absent variable keeps
the default on. A typo while disabling disables; it never leaves the merge
enabled.
"""

import os

ENV = 'SYNC_BRIDGE_CONTAINED_DONOR_MERGE_ENABLED'
# Only these words enable the merge. A digit, a blank value, or a typo is not an
# enable word, so it resolves off.
_ON = frozenset({'true', 'on', 'yes', 'enabled'})

# Clock jitter between a device-clocked sync span and a live capture span. Kept
# well under a second so a real partial overlap is never rounded into a merge.
CONTAINMENT_TOLERANCE_SECONDS = 0.5


def contained_donor_merge_enabled() -> bool:
    """Absent is on; any set value must be an explicit on-word or the merge is off.

    Deliberately not routed through the shared ``default_on`` parser: that
    parser keeps unknown values on in ``CAPTURE_COVERAGE_MODE=serve``, which
    would leave an irreversible merge enabled after a typo. Here a blank,
    empty, digit or misspelled value resolves off in every mode, and only an
    absent variable keeps the default on. Off restores the pre-change refusal
    exactly: a processed donor is never absorbed, no span is compared, and the
    assignment keeps its blanket ``already_processed`` protection.
    """
    raw = os.getenv(ENV)
    return raw is None or raw.strip().lower() in _ON
