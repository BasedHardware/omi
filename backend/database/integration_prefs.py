"""Per-user, per-integration preference flags.

Stores opt-in toggles like ``two_way_sync_enabled`` that gate writebacks to
third-party systems (Jira, Linear, etc.). Default is OFF — surprise writes
to a user's external account are a trust hazard, so the absence of a doc is
treated as ``two_way_sync_enabled = False``.

Firestore path: ``users/{uid}/integration_prefs/{integration_id}`` (one
singleton doc per integration). Keep this DB-level only — no upward imports.
"""

from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore

from ._client import db

_PREFS_COLLECTION = 'integration_prefs'


def _doc_ref(uid: str, integration_id: str) -> firestore.DocumentReference:
    return db.collection('users').document(uid).collection(_PREFS_COLLECTION).document(integration_id)


def get_integration_pref(uid: str, integration_id: str) -> Optional[dict]:
    """Return the prefs doc for ``integration_id`` or ``None`` if not set."""
    doc = _doc_ref(uid, integration_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data['integration_id'] = integration_id
    return data


def set_integration_pref(uid: str, integration_id: str, **updates) -> dict:
    """Merge ``updates`` into the prefs doc (creates if missing).

    Always stamps ``updated_at``. Returns the resulting doc.
    """
    if not updates:
        # No-op: still ensure we return current state without writing.
        existing = get_integration_pref(uid, integration_id)
        return existing or {'integration_id': integration_id}

    payload = dict(updates)
    payload['updated_at'] = datetime.now(timezone.utc)

    ref = _doc_ref(uid, integration_id)
    # set(merge=True) creates-or-updates; preserves any unspecified fields.
    ref.set(payload, merge=True)

    result = get_integration_pref(uid, integration_id) or {}
    return result


def is_two_way_sync_enabled(uid: str, integration_id: str) -> bool:
    """Convenience: return True only if the user has explicitly opted in.

    Missing doc / missing field both default to False — this is the hard
    product rule (writes never go out unless the user flipped the toggle).
    """
    pref = get_integration_pref(uid, integration_id)
    if not pref:
        return False
    return bool(pref.get('two_way_sync_enabled', False))
