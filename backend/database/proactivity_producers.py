"""Bounded producer history/outcome lookups on the existing item authority."""

from datetime import timedelta
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from config.proactivity_v2 import ProactivityDenied, utc_now
from database import proactivity as ledger


def mentor_history_query(client: Any, uid: str) -> Any:
    return (
        ledger.user_ref(client, uid)
        .collection(ledger.ITEMS)
        .where(filter=FieldFilter('producer', '==', 'conversation_mentor_v2'))
        .where(filter=FieldFilter('state', '==', 'ready'))
        .where(filter=FieldFilter('delivered', '==', True))
        .order_by('delivered_at', direction='DESCENDING')
        .limit(5)
    )


def recent_mentor_query(client: Any, uid: str, since: Any) -> Any:
    return (
        ledger.user_ref(client, uid)
        .collection(ledger.ITEMS)
        .where(filter=FieldFilter('producer', '==', 'conversation_mentor_v2'))
        .where(filter=FieldFilter('state', '==', 'ready'))
        .where(filter=FieldFilter('created_at', '>=', since))
        .order_by('created_at', direction='DESCENDING')
        .limit(180)
    )


def task_items_query(client: Any, uid: str, task_id: str) -> Any:
    # At most 27 eligible evaluations across three UTC days, even with due edits.
    return (
        ledger.user_ref(client, uid)
        .collection(ledger.ITEMS)
        .where(filter=FieldFilter('source_id', '==', task_id))
        .where(filter=FieldFilter('producer', '==', 'commitment_followup'))
        .where(filter=FieldFilter('state', '==', 'ready'))
        .where(filter=FieldFilter('created_at', '>=', utc_now() - timedelta(hours=48)))
        .order_by('created_at', direction='DESCENDING')
        .limit(27)
    )


def delivered_mentor_items(uid: str, *, firestore_client: Any = None) -> list[dict]:
    client = ledger.client_or_default(firestore_client)
    return [
        item
        for snapshot in mentor_history_query(client, uid).stream()
        if (item := snapshot.to_dict()) and item.get('state') == 'ready' and ledger.source_visible(client, uid, item)
    ]


def record_mentor_reply(uid: str, *, firestore_client: Any = None) -> None:
    """Map replies only to persisted mentor messages or independently exposed items."""
    client = ledger.client_or_default(firestore_client)
    now = utc_now()
    for snapshot in recent_mentor_query(client, uid, now - timedelta(hours=48)).stream():
        item = snapshot.to_dict()
        if not item or item.get('state') != 'ready':
            continue
        anchor = item.get('delivered_at') or (
            item.get('mentor_chat_persisted_at') if item.get('mentor_chat_message_id') else None
        )
        if anchor is not None and anchor <= now <= anchor + timedelta(hours=24):
            try:
                ledger.record_server_outcome(item['item_id'], 'replied', uid=uid, firestore_client=client, now=now)
            except ProactivityDenied:
                continue


def record_task_completion(uid: str, task_id: str, *, firestore_client: Any = None) -> None:
    client = ledger.client_or_default(firestore_client)
    now = utc_now()
    for snapshot in task_items_query(client, uid, task_id).stream():
        item = snapshot.to_dict()
        if not item or item.get('producer') != 'commitment_followup' or item.get('state') != 'ready':
            continue
        # Retain even an independently completed task; the spine refuses value credit without exposure.
        try:
            ledger.record_server_outcome(item['item_id'], 'accepted', uid=uid, firestore_client=client, now=now)
        except ProactivityDenied:
            continue
