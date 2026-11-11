"""Transactional owner-wide UTC-day refresh budget and durable recap repair debt."""

from datetime import datetime, timezone
from typing import Any

from utils.other.daily_summary_refresh import FIELD

# Identity, privacy, creation and delivery are independently owned.
CONTENT_FIELDS = frozenset(
    (
        'headline',
        'overview',
        'day_emoji',
        'stats',
        'highlights',
        'action_items',
        'unresolved_questions',
        'decisions_made',
        'knowledge_nuggets',
        'memories_learned',
        'locations',
        'read_contract_version',
        'action_items_coverage',
        'memories_learned_coverage',
        'tomorrow_focus',
        'overall_sentiment',
        'people_mentioned',
        'memorable_moments',
    )
)


def get_firestore_client():
    from database._client import get_firestore_client as get_client

    return get_client()


def _refs(uid, date, existing, client):
    user = client.collection('users').document(uid)
    return (
        user.collection('daily_summaries').document(existing['id']),
        user.collection('daily_summary_generation').document(date),
    )


def adopt(uid, date, existing, fingerprint, stale, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    recap, marker = _refs(uid, date, existing, client)

    from google.cloud import firestore

    @firestore.transactional
    def apply(tx: Any):
        snapshot = recap.get(transaction=tx)
        debt = marker.get(transaction=tx).to_dict() or {}
        current = snapshot.to_dict() or {}
        if not snapshot.exists or current.get(FIELD) != existing.get(FIELD):
            return None
        tx.update(recap, {FIELD: fingerprint})
        tx.set(marker, {**debt, 'late_refresh_required': stale, 'late_refresh_verify_pending': True})
        return {**current, FIELD: fingerprint}

    return apply(client.transaction())


def reserve(uid, date, *, firestore_client=None, now=None):
    """Reserve before every model attempt, including failures; never refund a spent attempt."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    user = client.collection('users').document(uid)
    counter = user.collection('daily_summary_refresh_budget').document(today)
    marker = user.collection('daily_summary_generation').document(date)

    from google.cloud import firestore

    @firestore.transactional
    def apply(tx: Any):
        budget = counter.get(transaction=tx).to_dict() or {}
        debt = marker.get(transaction=tx).to_dict() or {}
        count = budget.get('refresh_count', 0)
        tx.set(marker, {**debt, 'late_refresh_required': True, 'late_refresh_verify_pending': True})
        if count >= 2:
            return False
        tx.set(counter, {'refresh_count': count + 1})
        return True

    return apply(client.transaction())


def commit(uid, date, existing, payload, fingerprint, *, firestore_client=None):
    """CAS the recap writer, patch content, and retain a verification obligation.

    The producer re-reads the input window before calling this. Even an input
    arriving after that read cannot be blessed: the recap stores the *original*
    fingerprint and verify_pending remains durable for the next bounded scan.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    recap, marker = _refs(uid, date, existing, client)

    from google.cloud import firestore

    @firestore.transactional
    def apply(tx: Any):
        snapshot = recap.get(transaction=tx)
        debt = marker.get(transaction=tx).to_dict() or {}
        current = snapshot.to_dict() or {}
        if not snapshot.exists or current.get(FIELD) != existing.get(FIELD):
            return None
        patch = {key: value for key, value in payload.items() if key in CONTENT_FIELDS}
        patch.update({FIELD: fingerprint, 'late_refresh_silent': True})
        tx.update(recap, patch)
        tx.set(marker, {**debt, 'late_refresh_required': False, 'late_refresh_verify_pending': True})
        return {**current, **patch}

    return apply(client.transaction())
