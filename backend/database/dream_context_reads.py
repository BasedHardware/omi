"""Bounded nearest temporal neighbours on existing owner-scoped collections."""

from datetime import datetime, timezone
from google.cloud.firestore_v1 import FieldFilter
from database._client import get_firestore_client
from database.screen_activity import normalize_screen_activity_timestamp
from database.task_intelligence_control import get_task_workflow_control


def temporal_neighbours(uid, collection, start, anchor, end, *, firestore_client=None):
    if collection not in {'conversations', 'screen_activity'}:
        raise ValueError('dream_temporal_collection')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    screen = collection == 'screen_activity'
    field = 'timestamp' if screen else 'created_at'
    source = database.collection('users').document(uid).collection(collection)
    generation = get_task_workflow_control(uid, firestore_client=database).account_generation if screen else None
    rows = {}
    for lower, upper, direction in ((start, anchor, 'DESCENDING'), (anchor, end, 'ASCENDING')):
        bounds = (
            (normalize_screen_activity_timestamp(lower), normalize_screen_activity_timestamp(upper))
            if screen
            else (lower, upper)
        )
        query = (
            source.where(filter=FieldFilter(field, '>=', bounds[0]))
            .where(filter=FieldFilter(field, '<=', bounds[1]))
            .order_by(field, direction=direction)
        )
        if not screen:
            query = query.select(['created_at'])
        for snapshot in query.limit(4).stream(timeout=3):
            row = dict(snapshot.to_dict() or {}, id=snapshot.id)
            if screen and (row.get('captureEligible') is not True or row.get('accountGeneration', 0) != generation):
                continue
            value = row.get(field)
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    continue
            if isinstance(value, datetime):
                value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
                rows[snapshot.id] = (abs((value - anchor).total_seconds()), row)
    return [row for _, row in sorted(rows.values(), key=lambda item: (item[0], item[1]['id']))[:4]]


def subject_memory_refs(uid, subject, *, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    source = database.collection('users').document(uid).collection('memory_items')
    query = source.where(filter=FieldFilter('subject_entity_id', '==', subject)).select(['id']).limit(4)
    return ['memory_items/' + snapshot.id for snapshot in query.stream(timeout=3)]
