"""CAS keyset checkpoint for bounded enrichment watchdog passes."""

import math
from typing import Any

from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound
from google.cloud import firestore


def begin(client: Any, collection: str) -> tuple[Any, dict[str, Any] | None]:
    snapshot = client.collection('sync_reprocess_scan').document('cursor').get()
    value = snapshot.to_dict() or {}
    due, document_id = value.get('due_at'), value.get('document_id')
    cursor = None
    if (
        isinstance(due, (int, float))
        and not isinstance(due, bool)
        and math.isfinite(due)
        and isinstance(document_id, str)
        and len(document_id) == 64
        and '/' not in document_id
    ):
        cursor = {'due_at': due, '__name__': client.collection(collection).document(document_id)}
    return snapshot, cursor


def finish(previous: Any, last: Any, exhausted: bool) -> None:
    if last is None and not exhausted:
        return
    value = (
        {'due_at': None, 'document_id': None}
        if exhausted
        else {
            'due_at': last.to_dict()['due_at'],
            'document_id': last.id,
        }
    )
    try:
        if previous.exists:
            previous.reference.update(value, option=firestore.LastUpdateOption(previous.update_time))
        else:
            previous.reference.create(value)
    except (AlreadyExists, FailedPrecondition, NotFound):
        # Another replica advanced the shared pass. Per-row CAS still owns all
        # wake repairs; a lost cursor race may repeat reads, never skip custody.
        pass
