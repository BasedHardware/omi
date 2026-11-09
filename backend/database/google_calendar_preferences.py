"""Read preferences, scoped to the Omi owner and verified Google primary calendar.

Kept on the user document so disconnect/reconnect retains preferences, while
account deletion removes them with the user. Tokens never live here.
"""

from typing import Any
from utils.google_calendar_identity import account_key

FIELD = 'google_calendar_read_selections'


def get_selections(uid: str, *, firestore_client: Any = None) -> dict:
    from database._client import get_firestore_client

    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = client.collection('users').document(uid).get(field_paths=[FIELD])
    data = (snapshot.to_dict() or {}).get(FIELD, {}) if snapshot.exists else {}
    if not isinstance(data, dict):
        raise ValueError('invalid_calendar_preferences')
    return data


def save_selection(uid: str, primary_calendar_id: str, ids: list[str], *, firestore_client: Any = None) -> None:
    from database._client import get_firestore_client

    client = firestore_client if firestore_client is not None else get_firestore_client()
    # One nested-field update preserves other accounts and cannot resurrect a
    # user document removed by account deletion while the provider call waited.
    client.collection('users').document(uid).update({f'{FIELD}.{account_key(primary_calendar_id)}': ids})
