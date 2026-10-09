"""Owner-scoped proposal queue and transactional daily attention accounting.

Three answers per UTC day, including Not sure. Merely viewing a card costs
nothing. The offered source snapshot pins speaker metadata across cooldowns.
Uncertain answers suppress an evidence fingerprint, never an entire identity.
"""

import os
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import get_firestore_client
from database import review_queries
from models.review import ReviewItem, ReviewAnswerReceipt

DAILY_BUDGET = 3


class ReviewNotFound(ValueError):
    pass


class ReviewConflict(ValueError):
    pass


def client():
    return get_firestore_client()


def user(uid: str):
    return client().collection('users').document(uid)


def safe_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(value: Any) -> str:
    return safe_id(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')))


def require_enabled() -> None:
    if os.environ.get('REVIEW_SURFACE_MODE', 'off').strip().lower() != 'on':
        raise ReviewConflict('review_surface_disabled')


def enqueue_review_proposal(uid: str, item: ReviewItem, *, evidence_version: str) -> str:
    """Dream writer: same stable item_id + same evidence version is an idempotent enqueue.

    Only same_person and spelling are owned here. New evidence_version explicitly
    permits re-asking an uncertain answer. Resolved decisions remain terminal.
    """
    require_enabled()
    if item.kind not in {'same_person', 'spelling'} or not evidence_version.strip():
        raise ValueError('Proposal requires same_person/spelling and an evidence version')
    if not item.item_id.startswith(f'{item.kind}:') or '/' in item.item_id:
        raise ValueError('item_id must be <kind>:<opaque source id>')
    ref = user(uid).collection('review_proposals').document(safe_id(item.item_id))

    @firestore.transactional
    def enqueue(tx):
        current = decode_doc(uid, ref.get(transaction=tx).to_dict()) or {}
        if current.get('status') == 'resolved' or current.get('evidence_version') == evidence_version:
            return
        tx.set(
            ref,
            encode_doc(
                uid,
                {
                    'item': item.model_dump(mode='python'),
                    'created_at': item.created_at,
                    'evidence_version': evidence_version,
                    'status': 'pending',
                },
            ),
        )

    enqueue(client().transaction())
    return item.item_id


def list_proposals(uid: str) -> list[dict]:
    query = review_queries.PROPOSALS.build(
        user(uid).collection('review_proposals'), {'status': 'pending'}, field_filter_factory=FieldFilter
    )
    return [
        require_doc(uid, s.to_dict()) for s in query.order_by('created_at', direction='DESCENDING').limit(100).stream()
    ]


def remaining_today(uid: str, now: datetime | None = None) -> int:
    day = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    data = user(uid).collection('review_attention').document(day).get().to_dict() or {}
    return max(0, DAILY_BUDGET - int(data.get('used', 0)))


def offer_item(uid: str, item: ReviewItem, source: dict, version: str) -> bool:
    """Atomically publish a version, preserving unanswered/terminal receipts."""
    ref = user(uid).collection('review_answers').document(safe_id(item.item_id))

    @firestore.transactional
    def offer(tx):
        data = decode_doc(uid, ref.get(transaction=tx).to_dict()) or {}
        if data.get('state') == 'applying':
            return False
        if data.get('state') in {'answered', 'uncertain'} and data.get('version') == version:
            return False
        tx.set(
            ref,
            encode_doc(
                uid, {'item': item.model_dump(mode='python'), 'source': source, 'version': version, 'state': 'offered'}
            ),
        )
        return True

    return offer(client().transaction())


def begin_answer(uid: str, item_id: str, answer_hash: str, now: datetime | None = None) -> dict:
    """Reserve one of three daily slots before invoking a shared resolution path.

    An interrupted application remains fenced (409), rather than risking a
    duplicate edit. A terminal identical request is an exact retry no-op.
    """
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(timezone.utc).date().isoformat()
    ref = user(uid).collection('review_answers').document(safe_id(item_id))
    budget_ref = user(uid).collection('review_attention').document(day)

    @firestore.transactional
    def begin(tx):
        data = decode_doc(uid, ref.get(transaction=tx).to_dict())
        budget = budget_ref.get(transaction=tx).to_dict() or {}
        if not data:
            raise ReviewNotFound('Review item was not offered')
        if data['state'] in {'answered', 'uncertain'}:
            if data.get('answer_hash') != answer_hash:
                raise ReviewConflict('Review item already answered')
            return data | {'retry': True}
        if data['state'] == 'applying':
            raise ReviewConflict('Review answer is in progress; refresh before retrying')
        used = budget.get('used', 0)
        if used >= DAILY_BUDGET:
            raise ReviewConflict('Daily attention budget exhausted')
        tx.update(ref, {'state': 'applying', 'answer_hash': answer_hash, 'day': day})
        tx.set(budget_ref, {'used': used + 1})
        return data | {'day': day, 'retry': False}

    return begin(client().transaction())


def finish_answer(
    uid: str, item_id: str, *, applied: bool, uncertain: bool, offered_version: str
) -> ReviewAnswerReceipt:
    ref = user(uid).collection('review_answers').document(safe_id(item_id))

    @firestore.transactional
    def finish(tx):
        answer = decode_doc(uid, ref.get(transaction=tx).to_dict())
        if answer is None:
            raise ReviewNotFound('Review answer reservation not found')
        if answer.get('state') != 'applying' or answer.get('version') != offered_version:
            raise ReviewConflict('Review answer reservation changed')

        proposal_ref = None
        proposal = None
        if item_id.startswith(('same_person:', 'spelling:')) and not uncertain:
            proposal_ref = user(uid).collection('review_proposals').document(safe_id(item_id))
            proposal = decode_doc(uid, proposal_ref.get(transaction=tx).to_dict())

        tx.update(ref, {'state': 'uncertain' if uncertain else 'answered', 'applied': applied})
        # A producer may refresh the stable item id while this answer is
        # applying. Resolve only the exact evidence version the user saw.
        if proposal_ref is not None and proposal and proposal.get('evidence_version') == offered_version:
            tx.update(proposal_ref, {'status': 'resolved'})

    finish(client().transaction())
    return ReviewAnswerReceipt(item_id=item_id, applied=applied, remaining_today=remaining_today(uid))


def release_failed_answer(uid: str, item_id: str) -> None:
    """Release only a known failure before application; uncertain outcomes stay fenced."""
    ref = user(uid).collection('review_answers').document(safe_id(item_id))

    @firestore.transactional
    def release(tx):
        data = decode_doc(uid, ref.get(transaction=tx).to_dict())
        if data is None:
            return
        budget_ref = user(uid).collection('review_attention').document(data['day'])
        budget = budget_ref.get(transaction=tx).to_dict() or {}
        if data.get('state') == 'applying':
            tx.update(ref, {'state': 'offered'})
            tx.set(budget_ref, {'used': max(0, budget.get('used', 0) - 1)})

    release(client().transaction())


_CONTENT_FIELDS = {'item', 'source', 'change', 'edits', 'before', 'memory_edit', 'summary'}


def _json_default(value):
    if isinstance(value, datetime):
        return {'__review_datetime__': value.isoformat()}
    raise TypeError(type(value).__name__)


def _json_hook(value):
    if set(value) == {'__review_datetime__'}:
        return datetime.fromisoformat(value['__review_datetime__'])
    return value


def encode_doc(uid: str, data: dict) -> dict:
    from utils.encryption import encrypt

    return {
        key: (
            {'review_encrypted_v1': encrypt(json.dumps(value, default=_json_default), uid)}
            if key in _CONTENT_FIELDS
            else value
        )
        for key, value in data.items()
    }


def decode_doc(uid: str, data: dict | None) -> dict | None:
    from utils.encryption import decrypt

    if data is None:
        return None
    return {
        key: (
            json.loads(decrypt(value['review_encrypted_v1'], uid), object_hook=_json_hook)
            if key in _CONTENT_FIELDS and isinstance(value, dict) and 'review_encrypted_v1' in value
            else value
        )
        for key, value in data.items()
    }


def require_doc(uid: str, data: dict | None) -> dict:
    decoded = decode_doc(uid, data)
    if decoded is None:
        raise ReviewNotFound('Review document not found')
    return decoded
