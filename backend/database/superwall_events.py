"""
Idempotency table for inbound Superwall webhooks.

Each webhook delivery carries a unique ``svix-id`` header. We persist that id
under ``superwall_events/{svix_id}`` the first time we process it; subsequent
deliveries of the same id short-circuit before any state mutation. This guards
against svix retries (which can fire repeatedly until a 2xx is returned) from
double-applying purchase / renewal / cancellation events.

Doc shape (small — kept cheap to write):
  superwall_events/{svix_id}
    received_at:  ISO8601 string
    event_type:   "initial_purchase" | "renewal" | "cancellation" | ...
    uid:          string (the omi user id we resolved the event to, if any)

Set a Firestore TTL policy on ``received_at`` (recommend 30 days) so the
collection doesn't grow unbounded — older events are not relevant to dedup
anyway because svix stops retrying long before that.
"""

from datetime import datetime, timezone
from typing import Optional

from database._client import db


def already_processed(svix_id: str) -> bool:
    """Return True if a webhook with this svix-id has already been recorded."""
    doc = db.collection('superwall_events').document(svix_id).get()
    return doc.exists


def record_processed(svix_id: str, event_type: str, uid: Optional[str]) -> None:
    """Persist that ``svix_id`` has been handled. Safe to call multiple times —
    the doc id is the svix-id, so a second write is idempotent.
    """
    db.collection('superwall_events').document(svix_id).set(
        {
            'received_at': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'uid': uid,
        }
    )
