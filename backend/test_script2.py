from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from models.boundary_evidence import BoundarySignal
from utils.episodes import boundary_store
from datetime import datetime, timezone, timedelta
import os
os.environ['EPISODE_BOUNDARIES_MODE_SHADOW_PERCENT'] = '100'
os.environ['EPISODE_BOUNDARIES_MODE'] = 'serve'
NOW = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
ACCOUNT = 'test-account'

def signal(**updates):
    return BoundarySignal(kind='calendar_event', external_id='event-test', started_at=NOW, **updates)

store = StrictFirestore()
boundary_store._shadow_windows.clear()

print("record1:", boundary_store.record(ACCOUNT, [signal()], firestore_client=store))
print("store rows:", store.rows)

closed = signal(ended_at=NOW + timedelta(minutes=20))
print("record3:", boundary_store.record(ACCOUNT, [closed], firestore_client=store))
print("store rows after closed:", store.rows)
