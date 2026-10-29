from utils.episodes.boundary_store import record, windows
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from models.boundary_evidence import BoundarySignal
from datetime import datetime, timedelta, timezone
import os

os.environ['EPISODE_BOUNDARIES_MODE_SHADOW_PERCENT'] = '100'
os.environ['EPISODE_BOUNDARIES_MODE'] = 'serve'
NOW = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
ACCOUNT = 'test-account'

def signal(**updates):
    return BoundarySignal(kind='calendar_event', external_id='event-test', started_at=NOW, **updates)

store = StrictFirestore()
print("1.", record(ACCOUNT, [signal()], firestore_client=store))
print("2.", record(ACCOUNT, [signal()], firestore_client=store))
closed = signal(ended_at=NOW + timedelta(minutes=20))
print("3.", record(ACCOUNT, [closed], firestore_client=store))
print("4.", record(ACCOUNT, [signal()], firestore_client=store))
print(windows(ACCOUNT, firestore_client=store))
