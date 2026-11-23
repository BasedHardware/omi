"""Bounded metadata walk for the per-route, per-language delivered share.

The signal is "of recordings admitted, what share reached the user within the
target". It is read from job metadata only: admission clock, route, declared
language and the delivery stamp the projection acknowledge writes. The page
projects exactly those fields, so no owner id, content id, conversation id,
audio reference, transcript or email is read, and no document is streamed past
the page cap.

A ``record_pending`` row is a reservation, not an admitted unit: it has no
projection binding yet and its ``enqueued_at`` is the reservation clock. The
walk therefore selects the census job vocabulary minus that state, so a new
state registered in ``config.batch_census`` is covered without editing this
module.
"""

from config.batch_census import JOB_STATES

# The user-facing target is p90 five minutes (project bar: p50 two minutes).
TARGET_SECONDS = 300
# A 15-minute admission cohort keeps a per-language share stable at low volume.
COHORT_SECONDS = 900
# About 2,800 units are admitted in a 20-minute window at the 2026-11 peak
# (205k provider units/day plus the Parakeet lane). The cap bounds one sample
# to 5,000 document reads; a saturated page is reported, never silently
# treated as complete.
PAGE_LIMIT = 5000

ADMITTED_STATES = tuple(state for state in JOB_STATES if state != 'record_pending')
# Projection, not a filter: the page must not materialize owner ids, content
# ids, conversation ids or audio references it never reads. ``segment_id`` is
# the result join key the backfill report needs.
FIELDS = (
    'segment_id',
    'enqueued_at',
    'state',
    'stt_route',
    'policy.stt_route',
    'projection_binding.language',
    'delivered_in_target',
    'delivered_at',
)


def delivered_share_page(client, namespace: str, now: float, limit: int = PAGE_LIMIT):
    """Jobs admitted in the cohort window, oldest first, plus a truncation flag.

    The cohort ends one target before ``now``, so every row has had the full
    target to be delivered. Ordering by admission makes a saturated page the
    oldest rows of the window, a lower bound on coverage rather than a biased
    sample.
    """
    start = now - COHORT_SECONDS - TARGET_SECONDS
    end = now - TARGET_SECONDS
    query = (
        client.collection(f'{namespace}_jobs')
        .where('state', 'in', list(ADMITTED_STATES))
        .where('enqueued_at', '>=', start)
        .where('enqueued_at', '<=', end)
        .order_by('enqueued_at')
        .select(FIELDS)
        .limit(limit)
    )
    rows = [doc.to_dict() for doc in query.stream(timeout=10, retry=None)]
    return rows, len(rows) == limit


def delivery_stamp(job: dict, now: float) -> tuple[float, bool]:
    """The first acknowledge time and whether it fell inside the target.

    Sticky on replay: a retried acknowledge never moves an earlier delivery
    time later, and a unit already stamped in-target stays in-target. The job
    row is the stamp's home, so a replay reads the value it wrote.
    """
    admitted = job.get('enqueued_at')
    within = (
        isinstance(admitted, (int, float)) and not isinstance(admitted, bool) and 0 <= now - admitted <= TARGET_SECONDS
    )
    delivered_at = job.get('delivered_at')
    if not isinstance(delivered_at, (int, float)) or isinstance(delivered_at, bool):
        delivered_at = now
    return delivered_at, bool(job.get('delivered_in_target') is True or within)
