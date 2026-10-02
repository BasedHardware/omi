"""Non-evicting capture interval index. Metadata only; no transcript or ciphertext.

Day documents are read and written in the same transaction as conversations.
The recent document remains a migration hint and cross-version serialization fence.
"""

from collections.abc import ValuesView
from datetime import timedelta, timezone
from typing import TYPE_CHECKING

from utils.conversation_continuity import DEFAULT_GAP_SECONDS

if TYPE_CHECKING:
    from google.cloud.firestore_v1 import transaction as firestore_transaction
    from google.cloud.firestore_v1.document import DocumentReference


def days_for(row: dict, *, padding: bool = False) -> list[str]:
    delta = timedelta(seconds=DEFAULT_GAP_SECONDS if padding else 0)
    start = (row['started_at'] - delta).astimezone(timezone.utc).date()
    end = (row['finished_at'] + delta).astimezone(timezone.utc).date()
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


class AssignmentIndex:
    def __init__(self, transaction: 'firestore_transaction.Transaction', user_ref: 'DocumentReference') -> None:
        self.transaction = transaction
        self.collection = user_ref.collection('sync_assignment')
        self.recent_ref = self.collection.document('recent')
        self.recent = (self.recent_ref.get(transaction=transaction).to_dict() or {}).get('entries', [])
        self.buckets: dict[str, list[dict]] = {}

    def read(self, interval: dict) -> ValuesView[dict]:
        for day in days_for(interval, padding=True):
            if day not in self.buckets:
                raw = self.collection.document(day).get(transaction=self.transaction).to_dict() or {}
                self.buckets[day] = raw.get('entries', [])
        return {row['id']: row for rows in [self.recent, *self.buckets.values()] for row in rows}.values()

    def write(self, result: dict, replaced: set[str]) -> None:
        keys = ('id', 'started_at', 'finished_at', 'source', 'client_device_id', 'is_locked')
        entry = {key: result.get(key) for key in keys}
        occupied = set(days_for(result))
        for day, rows in self.buckets.items():
            rows = [row for row in rows if row['id'] not in replaced]
            if day in occupied:
                rows.append(entry)
            self.transaction.set(self.collection.document(day), {'entries': sorted(rows, key=lambda row: row['id'])})
        recent = [row for row in self.recent if row['id'] not in replaced] + [entry]
        self.transaction.set(self.recent_ref, {'entries': recent[-128:]})
