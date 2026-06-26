"""Deterministic Firestore document id helpers.

Keep natural-key seed construction in one low-dependency module so database
callers do not hand-roll subtly different id formats.
"""

import hashlib
import uuid


def document_id_from_seed(seed: str) -> str:
    """Return a stable UUIDv4-shaped document id for a natural-key seed."""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


def system_folder_doc_id(uid: str, category_mapping: str) -> str:
    """Stable id for a user's built-in system folder category."""
    return document_id_from_seed(f"user:{uid}:system_folder:{category_mapping}")


def calendar_meeting_doc_id(uid: str, calendar_source: str, calendar_event_id: str) -> str:
    """Stable id for a meeting from an external calendar provider.

    The current API exposes `calendar_source` and `calendar_event_id` as the
    available provider uniqueness dimensions. If provider account/calendar ids
    are added later, extend this helper rather than adding call-site seed logic.
    """
    return document_id_from_seed(f"user:{uid}:calendar_meeting:{calendar_source}:{calendar_event_id}")
