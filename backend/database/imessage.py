"""iMessage DB layer: durable per-message processed-ledger + deterministic ids.

The ledger stores one claim document per ingested message at
``users/{uid}/integrations/imessage/processed_messages/{key}`` where
``key = document_id_from_seed(f"{chat_guid}:{message_guid}")``.

Claiming uses Firestore ``doc.create()`` which raises ``AlreadyExists`` if the
document already exists. That makes each claim an atomic compare-and-set: only
one concurrent writer can win, which both closes the concurrent-ingest race and
replaces the old fragile bounded ``processed_guids`` array (which silently
dropped the oldest GUIDs past a cap and re-ingested them).

This module is database-layer only (Firestore access + deterministic ids). All
orchestration that runs the conversation pipeline lives in
``utils/imessage_connector.py`` — database modules must not import ``utils/``.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Set

from google.api_core.exceptions import AlreadyExists, Conflict

from database._client import get_firestore_client

logger = logging.getLogger(__name__)

INTEGRATION_KEY = 'imessage'
PROCESSED_MESSAGES_SUBCOLLECTION = 'processed_messages'
# Firestore get_all() accepts up to 300 document refs per call; stay well under.
_GET_ALL_BATCH = 250

# Note: the pure ledger-key / conversation-id derivation (document_id_from_seed)
# lives in utils/imessage_connector.py, not here. Keeping this module to actual
# Firestore I/O means callers pass precomputed keys and the async blocker scanner
# doesn't flag those pure, non-blocking calls as database access.


def _processed_messages_ref(uid: str, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    return (
        client.collection('users')
        .document(uid)
        .collection('integrations')
        .document(INTEGRATION_KEY)
        .collection(PROCESSED_MESSAGES_SUBCOLLECTION)
    )


def filter_claimed_keys(uid: str, keys: List[str], *, firestore_client=None) -> Set[str]:
    """Return the subset of ``keys`` already present in the ledger.

    Best-effort dedup optimization run before ingest so already-processed
    messages are not re-summarized. Uses batched ``get_all`` reads to avoid one
    round-trip per key. Correctness (the concurrent-ingest race) still rests on
    the atomic ``claim_message`` create, not on this read.
    """
    if not keys:
        return set()
    client = firestore_client or get_firestore_client()
    coll = _processed_messages_ref(uid, firestore_client=client)
    # Preserve order while de-duplicating so batches are stable.
    unique = list(dict.fromkeys(keys))
    claimed: Set[str] = set()
    for i in range(0, len(unique), _GET_ALL_BATCH):
        batch = unique[i : i + _GET_ALL_BATCH]
        refs = [coll.document(k) for k in batch]
        for snap in client.get_all(refs):
            if snap.exists:
                claimed.add(snap.id)
    return claimed


def claim_message(
    uid: str,
    key: str,
    chat_guid: Optional[str] = None,
    message_guid: Optional[str] = None,
    *,
    firestore_client=None,
) -> bool:
    """Atomically claim a message BEFORE it is durably persisted (insert-first).

    Returns True if this call won the claim (wrote the ledger doc), False if it
    was already claimed (``AlreadyExists``) — meaning another concurrent ingest
    already owns this message and it is safe to skip.

    Claiming first serializes concurrent ingests so the same message can never be
    turned into two conversations / duplicate segments. The caller then persists
    the message's conversation synchronously; if that durable write fails it must
    call ``release_message`` so the message is retried on the next sync (never
    permanently dropped). Best-effort LLM enrichment runs later and its failure
    must NOT release the claim — the raw content is already durable.
    """
    coll = _processed_messages_ref(uid, firestore_client=firestore_client)
    payload = {'claimed_at': datetime.now(timezone.utc)}
    if chat_guid is not None:
        payload['chat_guid'] = chat_guid
    if message_guid is not None:
        payload['message_guid'] = message_guid
    try:
        coll.document(key).create(payload)
        return True
    except (AlreadyExists, Conflict):
        return False


def release_message(uid: str, key: str, *, firestore_client=None) -> None:
    """Delete a claim so its message is retried on the next sync.

    Called only when the synchronous durable persist of a claimed message's
    conversation fails, so a transient Firestore error can never strand a claimed
    message that was never actually stored.
    """
    coll = _processed_messages_ref(uid, firestore_client=firestore_client)
    try:
        coll.document(key).delete()
    except Exception as e:
        logger.warning(f'imessage: failed to release claim key={key} uid={uid}: {e}')
