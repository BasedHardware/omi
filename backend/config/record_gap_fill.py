"""Dark switch for filling a closed record's missing retained tail from the owner's WAL.

Both settings default to off. ``RECORD_GAP_FILL=on`` arms the path and
``RECORD_GAP_FILL_PERCENT`` (0-100, default 0) admits a stable uid cohort, so
the ramp is 1/10/50/100 with no code change. Rollback is the switch.
"""

import os

from config.policy.batch import cohort_bucket

# A record must have been finished (and its row unchanged) this long before a
# fill may run: the pusher's last flush and its close have long since landed.
CLOSED_MIN_SECONDS = 300
# One marker per (record, WAL) so retries during the drain's catch-up skip.
MARKER_SECONDS = 600
# Never write past the capture's own finish by more than this.
FINISH_SLACK_SECONDS = 1.0
# One request writes at most this much audio, in objects of at most PIECE_SECONDS.
MAX_FILL_SECONDS = 3600
PIECE_SECONDS = 300
# A fill holds the record_pending job's drain lease (``available_at``) while it
# writes, so drain admission cannot start mid-fill; it stops writing new pieces
# LEASE_MARGIN_SECONDS before the lease would lapse.
FILL_LEASE_SECONDS = 600
LEASE_MARGIN_SECONDS = 60


def gap_fill_enabled(uid: str) -> bool:
    if os.getenv('RECORD_GAP_FILL', 'off').strip().lower() != 'on':
        return False
    try:
        percent = float(os.getenv('RECORD_GAP_FILL_PERCENT', '0'))
    except ValueError:
        return False
    return bool(uid) and 0 < percent <= 100 and cohort_bucket(uid, 'record-gap-fill', bits=64) < percent


def retained_ack_enabled(uid: str) -> bool:
    """Option A: answer 200 once the server holds a byte-exact durable copy.

    ``RECORD_RETAINED_ACK=on`` plus ``RECORD_RETAINED_ACK_PERCENT`` (0-100,
    default 0). It runs only inside the gap-fill cohort, after its gates.
    """
    if os.getenv('RECORD_RETAINED_ACK', 'off').strip().lower() != 'on':
        return False
    try:
        percent = float(os.getenv('RECORD_RETAINED_ACK_PERCENT', '0'))
    except ValueError:
        return False
    return bool(uid) and 0 < percent <= 100 and cohort_bucket(uid, 'record-retained-ack', bits=64) < percent
