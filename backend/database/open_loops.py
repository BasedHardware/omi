"""Firestore open-loop store: per-user loops and daily surfaced cards.

Storage layout:

- ``users/{uid}/open_loops/{loop_id}`` — one document per loop. The whole loop
  dict (quotes from the owner's conversations) is stored as one derived JSON
  blob: zlib-compressed and AES-encrypted for **every** user, the enhanced
  protection shape from ``database/conversations.py`` applied unconditionally
  because the content is conversation-derived regardless of tier. The raw
  document is ``{id, data: <encrypted blob>, data_compressed: True}`` plus a
  plain ``status``/``last_activity_at`` mirror used only for bounded-read
  triage; nothing readable leaves the blob.
- ``users/{uid}/open_loop_cards/{date}`` — the per-local-day surfaced cards
  (state pending|done|remind|dropped). Its existence is also the daily pass's
  once-per-day marker; an empty cards list still marks the pass as run.
- ``users/{uid}/open_loop_claims/{date}`` — the spend guard: a tiny plain
  document claimed atomically (create-if-absent) **before** the pass's model
  call, so retried recap ticks, abandoned workers and the locked-retry path
  can never double-pay for one local day. ``state`` is ``claimed``/``ran``/
  ``failed``; ``attempts`` bounds a genuinely failed day to one retry.

The collection is read by streaming the subcollection and filtering in code
(no queries, no new indexes); expiry plus the store cap keep it small.
"""

from __future__ import annotations

import json
import logging
import zlib
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from ._client import get_firestore_client, run_transactional
from utils import encryption

logger = logging.getLogger(__name__)

OPEN_LOOPS_COLLECTION = 'open_loops'
OPEN_LOOP_CARDS_COLLECTION = 'open_loop_cards'
OPEN_LOOP_CLAIMS_COLLECTION = 'open_loop_claims'

# The writer's initial card state; the answer transaction's pending check.
CARD_STATE_PENDING = 'pending'

DATA_FIELD = 'data'
DATA_COMPRESSED_FIELD = 'data_compressed'

CLAIM_STATE_CLAIMED = 'claimed'
CLAIM_STATE_RAN = 'ran'
CLAIM_STATE_FAILED = 'failed'
# A claimed-but-unfinished pass (worker abandoned mid-call) may be taken over
# after this long — the recap tick runs every 15 minutes, so a stale claim
# self-heals on the following tick, never mid-flight.
CLAIM_STALE_SECONDS = 600
# One model call per day, plus exactly one retry for a day that genuinely failed.
MAX_PASS_ATTEMPTS = 2


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _protect(value: Any, uid: str) -> str:
    payload = zlib.compress(json.dumps(value, default=_json_default).encode('utf-8'))
    return encryption.encrypt(payload.hex(), uid)


def _reveal(raw: Any, uid: str) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        payload = encryption.decrypt(raw, uid)
        return json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
    raise ValueError(f'undecodable open-loop blob: {type(raw).__name__}')


def _collection(uid: str, name: str, firestore_client: Any):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid).collection(name)


def _loop_ref(uid: str, loop_id: str, *, firestore_client: Any = None):
    return _collection(uid, OPEN_LOOPS_COLLECTION, firestore_client).document(loop_id)


def upsert_loop(uid: str, loop: Dict[str, Any], *, firestore_client: Any = None) -> None:
    """Write one loop document (full overwrite; loops are small and self-contained)."""
    loop_id = str(loop['id'])
    _loop_ref(uid, loop_id, firestore_client=firestore_client).set(
        {
            'id': loop_id,
            # Plain triage mirrors: never conversation content, only status.
            'status': loop.get('status'),
            'last_activity_at': loop.get('last_activity_at'),
            DATA_FIELD: _protect(loop, uid),
            DATA_COMPRESSED_FIELD: True,
        }
    )


def delete_loops(uid: str, loop_ids: List[str], *, firestore_client: Any = None) -> None:
    for loop_id in loop_ids:
        _loop_ref(uid, str(loop_id), firestore_client=firestore_client).delete()


def get_loops(uid: str, *, firestore_client: Any = None) -> List[Dict[str, Any]]:
    """All stored loops, decoded. Undecodable documents are skipped, not fatal."""
    loops: List[Dict[str, Any]] = []
    for doc in _collection(uid, OPEN_LOOPS_COLLECTION, firestore_client).stream():
        raw = doc.to_dict() or {}
        if not raw.get(DATA_COMPRESSED_FIELD):
            continue
        try:
            value = _reveal(raw.get(DATA_FIELD), uid)
        except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
            logger.error('open_loop_store_undecodable uid=%s loop_id=%s', uid, doc.id)
            continue
        if isinstance(value, dict) and value.get('id'):
            loops.append(value)
    return loops


def get_cards_doc(uid: str, date_str: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """The raw cards document for one local day, or None when the pass has not run."""
    raw = _collection(uid, OPEN_LOOP_CARDS_COLLECTION, firestore_client).document(date_str).get().to_dict()
    return raw if raw else None


def get_cards(uid: str, date_str: str, *, firestore_client: Any = None) -> Optional[List[Dict[str, Any]]]:
    """The decoded cards for one local day; None when the pass has not run."""
    raw = get_cards_doc(uid, date_str, firestore_client=firestore_client)
    if raw is None:
        return None
    try:
        value = _reveal(raw.get(DATA_FIELD), uid)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
        logger.error('open_loop_cards_undecodable uid=%s date=%s', uid, date_str)
        return []
    return value if isinstance(value, list) else []


def set_cards(uid: str, date_str: str, cards: List[Dict[str, Any]], *, firestore_client: Any = None) -> None:
    """Store the day's surfaced cards (possibly empty) — also the pass-ran marker."""
    _collection(uid, OPEN_LOOP_CARDS_COLLECTION, firestore_client).document(date_str).set(
        {
            'date': date_str,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            DATA_FIELD: _protect(cards, uid),
            DATA_COMPRESSED_FIELD: True,
        }
    )


def cards_doc_ref(uid: str, date_str: str, *, firestore_client: Any = None):
    return _collection(uid, OPEN_LOOP_CARDS_COLLECTION, firestore_client).document(date_str)


@firestore.transactional
def _transition_card(
    transaction: Any,
    uid: str,
    ref: Any,
    date_str: str,
    card_id: str,
    state: str,
    answered_at: Optional[str],
    from_state: str = CARD_STATE_PENDING,
) -> Optional[Dict[str, Any]]:
    """Read-check-update of one card's state, serialized against every other answer.

    The whole cards document is one encrypted blob, so a field-level update of a
    single card is not possible; the transaction is what keeps two in-flight
    answers from each resurrecting the other's card as pending. Returns the
    answered card, or None when the day has no document, the card is missing or
    it is no longer pending (answered elsewhere — the caller's 409).
    """
    raw = ref.get(transaction=transaction).to_dict()
    if not raw:
        return None
    try:
        cards = _reveal(raw.get(DATA_FIELD), uid)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
        logger.error('open_loop_cards_undecodable uid=%s date=%s', uid, date_str)
        return None
    if not isinstance(cards, list):
        return None
    position = next((i for i, c in enumerate(cards) if isinstance(c, dict) and str(c.get('id')) == str(card_id)), None)
    if position is None or cards[position].get('state') != from_state:
        return None
    card = {**cards[position], 'state': state, 'answered_at': answered_at}
    cards[position] = card
    transaction.set(
        ref,
        {
            'date': date_str,
            'generated_at': raw.get('generated_at'),
            DATA_FIELD: _protect(cards, uid),
            DATA_COMPRESSED_FIELD: True,
        },
    )
    return card


def transition_card_state(
    uid: str,
    date_str: str,
    card_id: str,
    state: str,
    answered_at: Optional[str],
    *,
    from_state: str = CARD_STATE_PENDING,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Move one card of the day's document from ``from_state`` (pending) to ``state`` atomically.

    On contention (another answer committed since this transaction's read) the
    Firestore wrapper re-runs the body against the committed state, so the
    check-then-update can never overwrite a concurrent answer with a stale
    snapshot of the document.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return run_transactional(
        client,
        _transition_card,
        uid,
        cards_doc_ref(uid, date_str, firestore_client=client),
        date_str,
        card_id,
        state,
        answered_at,
        from_state,
    )


def _claim_ref(uid: str, date_str: str, firestore_client: Any):
    return _collection(uid, OPEN_LOOP_CLAIMS_COLLECTION, firestore_client).document(date_str)


def _parse_claim_moment(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def claim_daily_pass(uid: str, date_str: str, *, now: Optional[datetime] = None, firestore_client: Any = None) -> bool:
    """Atomically claim this user's pass for this local day, before the model call.

    ``create()`` is Firestore's compare-and-insert: exactly one of N concurrent
    callers wins the fresh claim, everyone else sees the existing claim and
    skips — the double-spend guard for retried ticks, abandoned workers and
    the recap's locked-retry path. A ``failed`` (or long-``claimed``) day may
    be re-claimed once, bounded by ``MAX_PASS_ATTEMPTS``; the retry path runs
    on a later 15-minute tick, never concurrently with a live claim.
    """
    moment = now or datetime.now(timezone.utc)
    ref = _claim_ref(uid, date_str, firestore_client)
    try:
        ref.create({'date': date_str, 'state': CLAIM_STATE_CLAIMED, 'attempts': 1, 'updated_at': moment.isoformat()})
        return True
    except Exception:
        pass  # AlreadyExists on the real client; verified by the read below
    raw = ref.get().to_dict()
    if not raw:
        # The create failed but no claim exists (transient): fail closed —
        # skip now, the next tick's create succeeds and spends once.
        return False
    state = raw.get('state')
    if state == CLAIM_STATE_RAN:
        return False
    attempts = 0
    try:
        attempts = int(raw.get('attempts') or 0)
    except (TypeError, ValueError):
        attempts = 0
    if state == CLAIM_STATE_CLAIMED:
        updated = _parse_claim_moment(raw.get('updated_at'))
        live = updated is not None and (moment - updated).total_seconds() < CLAIM_STALE_SECONDS
        if live:
            return False  # a worker still owns the day
    if attempts >= MAX_PASS_ATTEMPTS:
        return False
    ref.update({'state': CLAIM_STATE_CLAIMED, 'attempts': attempts + 1, 'updated_at': moment.isoformat()})
    return True


def mark_daily_pass_ran(uid: str, date_str: str, *, firestore_client: Any = None) -> None:
    """Settle the claim after the day's cards are stored (best-effort)."""
    try:
        _claim_ref(uid, date_str, firestore_client).update(
            {'state': CLAIM_STATE_RAN, 'updated_at': datetime.now(timezone.utc).isoformat()}
        )
    except Exception as error:
        logger.error('open_loop_claim_mark_ran_failed uid=%s date=%s error=%s', uid, date_str, error)


def mark_daily_pass_failed(uid: str, date_str: str, *, firestore_client: Any = None) -> None:
    """Release a failed claim so the day may retry once (best-effort)."""
    try:
        _claim_ref(uid, date_str, firestore_client).update(
            {'state': CLAIM_STATE_FAILED, 'updated_at': datetime.now(timezone.utc).isoformat()}
        )
    except Exception as error:
        logger.error('open_loop_claim_mark_failed_failed uid=%s date=%s error=%s', uid, date_str, error)
