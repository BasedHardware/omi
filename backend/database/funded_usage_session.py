"""Finite legacy processing allowance: closed-hour totals plus current-hour reads."""

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Iterator
import time

from google.cloud.firestore_v1 import FieldFilter
from database._client import get_customer_firestore_client
from database.usage_units_session import UsageUnitsSession


class LegacyUsageSession:
    def __init__(self):
        self.state = {}
        self._firestore_client = None

    def read(self, uid: str, launch: datetime, *, firestore_client: Any = None) -> dict:
        state = self.state
        now = datetime.now(timezone.utc)
        if now < launch:
            return {}
        key = (uid, now.strftime('%Y-%m'), launch.isoformat(), client_identity(firestore_client))
        hour = now.strftime('%Y-%m-%d-%H')
        client = firestore_client if firestore_client is not None else get_customer_firestore_client()
        collection = client.collection('users').document(uid).collection('hourly_usage')
        names = ('transcription_seconds', 'speech_seconds', 'words_transcribed', 'insights_gained', 'memories_created')
        if state.get('key') != key or time.monotonic() - state.get('full_at', 0) >= 900:
            kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
            rows = read_month(uid, now, launch, **kwargs)
            closed = {name: sum(row.get(name, 0) for identity, row in rows if identity != hour) for name in names}
            current = next((row for identity, row in rows if identity == hour), {})
            full_at = time.monotonic()
        else:
            closed = dict(state['closed'])
            if state['hour'] != hour:
                previous = collection.document(state['hour']).get().to_dict() or {}
                for name in closed:
                    closed[name] += previous.get(name, 0)
            current = collection.document(hour).get().to_dict() or {}
            full_at = state['full_at']
        state.update(key=key, hour=hour, closed=closed, full_at=full_at)
        self._firestore_client = firestore_client
        return {name: total + current.get(name, 0) for name, total in closed.items()}


def read_month(uid: str, now: datetime, launch: datetime, *, firestore_client: Any = None):
    client = firestore_client if firestore_client is not None else get_customer_firestore_client()
    collection = client.collection('users').document(uid).collection('hourly_usage')
    return [
        (snap.id, snap.to_dict() or {})
        for snap in collection.where(filter=FieldFilter('year', '==', now.year))
        .where(filter=FieldFilter('month', '==', now.month))
        .where(filter=FieldFilter('id', '>=', launch.strftime('%Y-%m-%d-00')))
        .stream()
    ]


def client_identity(firestore_client: Any = None) -> int | None:
    """Identity, not equality/hashability: injected stores must never share totals."""
    return None if firestore_client is None else id(firestore_client)


@dataclass
class BudgetSession:
    # Retain the explicit client while cached, so its id cannot be recycled.
    firestore_client: Any = None
    lock: Any = field(default_factory=threading.RLock)
    units: UsageUnitsSession = field(default_factory=UsageUnitsSession)
    legacy: LegacyUsageSession = field(default_factory=LegacyUsageSession)


MAX_BUDGET_SESSIONS = 1024
_sessions: OrderedDict[tuple[str, int | None], BudgetSession] = OrderedDict()
_sessions_lock = threading.Lock()


@contextmanager
def budget_session(uid: str, *, firestore_client: Any = None) -> Iterator[BudgetSession]:
    """Borrow one serialized UID/client session; keep at most 1024 cached entries.

    Sessions retain reduced closed-bucket totals, with a 900-second full refresh
    owned by the underlying readers. Eviction never invalidates an active
    borrow; a later borrow of an evicted key simply starts cold.
    """
    key = (uid, client_identity(firestore_client))
    with _sessions_lock:
        entry = _sessions.pop(key, None)
        if entry is None:
            entry = BudgetSession(firestore_client=firestore_client)
        _sessions[key] = entry
        while len(_sessions) > MAX_BUDGET_SESSIONS:
            _sessions.popitem(last=False)
    with entry.lock:
        yield entry
