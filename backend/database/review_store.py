"""Owner-scoped proposal queue and transactional daily attention accounting.

Three answers per UTC day, including Not sure. Merely viewing a card costs
nothing. The offered source snapshot pins speaker metadata across cooldowns.
Uncertain answers suppress an evidence fingerprint, never an entire identity.
"""

import os
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import get_firestore_client
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database import review_queries
from models.review import ReviewItem, ReviewItemV2, ReviewAnswerReceipt
from models.review_context import enrich_spelling

DAILY_BUDGET = 3
_USER_REQUEST_OWNER: ContextVar[str | None] = ContextVar('review_user_request_owner', default=None)


class ReviewNotFound(ValueError):
    pass


class ReviewConflict(ValueError):
    pass


class ReviewStale(ReviewConflict):
    """The offered question no longer applies; retrying cannot repair it."""


def client():
    return get_firestore_client()


def user(uid: str):
    return client().collection('users').document(uid)


def safe_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(value: Any) -> str:
    return safe_id(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')))


@contextmanager
def user_request_authority(uid: str):
    """Only this authenticated owner's explicit mutation may bypass Review admission."""
    if not uid:
        raise ValueError('agent_invalid_owner')
    token = _USER_REQUEST_OWNER.set(uid)
    try:
        yield
    finally:
        _USER_REQUEST_OWNER.reset(token)


def is_user_request(uid):
    return _USER_REQUEST_OWNER.get() == uid


def require_enabled(uid: str | None = None) -> None:
    if uid is not None and _USER_REQUEST_OWNER.get() == uid:
        return
    if os.environ.get('REVIEW_SURFACE_MODE', 'off').strip().lower() != 'on':
        raise ReviewConflict('review_surface_disabled')


def enqueue_review_proposal(
    uid: str,
    item: ReviewItem | ReviewItemV2,
    *,
    evidence_version: str,
    source: dict | None = None,
    edit_key: str | None = None,
    dream_run_id: str | None = None,
    now: datetime | None = None,
) -> str:
    """Dream writer: same stable item_id + same evidence version is an idempotent enqueue.

    Identity, spelling and agent proposals share this queue. New evidence_version explicitly
    permits re-asking an uncertain answer. Resolved decisions remain terminal.
    """
    require_enabled(uid)
    item = enrich_spelling(item, source or {}, overwrite=True)
    is_agent = item.kind == 'agent_proposal'
    if item.kind not in {'same_person', 'spelling', 'agent_proposal'} or not evidence_version.strip():
        raise ValueError('Unsupported proposal kind or evidence version')
    if dream_run_id and item.kind not in {'spelling', 'same_person', 'agent_proposal'}:
        raise ValueError('Dream atomic question admission requires a question')
    if not item.item_id.startswith(f'{item.kind}:') or '/' in item.item_id:
        raise ValueError('item_id must be <kind>:<opaque source id>')
    ref = user(uid).collection('review_proposals').document(safe_id(item.item_id))

    if is_agent and (not source or not edit_key):
        raise ValueError('Agent proposals require a source snapshot and suppression key')
    day = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    budget_ref = user(uid).collection('review_attention').document(day)
    marker = user(uid).collection('review_do_not_redo').document(safe_id(edit_key)) if edit_key else None

    @firestore.transactional
    def enqueue(tx):
        from database.dream_effect_fence import assert_active

        assert_active(uid, tx)
        budget = (budget_ref.get(transaction=tx).to_dict() or {}) if is_agent or dream_run_id else {}
        current = decode_doc(uid, ref.get(transaction=tx).to_dict()) or {}
        if marker is not None and marker.get(transaction=tx).exists:
            return 'suppressed'
        if current.get('status') == 'resolved' or current.get('evidence_version') == evidence_version:
            return 'already_suggested'
        data = {}
        if dream_run_id:
            state = client().collection('dream_users').document(uid)
            data = state.get(transaction=tx).to_dict() or {}
            if (data.get('lease') or {}).get('run_id') != dream_run_id:
                raise ReviewConflict('dream_lease_lost')
            questions = data.get('questions', 0) if data.get('question_day') == day else 0
            if questions + budget.get('dream_suggestions', 0) >= DAILY_BUDGET or budget.get('used', 0) >= DAILY_BUDGET:
                return 'suggestion_cap'
            if not is_agent:
                tx.update(state, {'question_day': day, 'questions': questions + 1})
        if is_agent:
            from config.dream_agent import SUGGESTIONS_PER_DAY

            dream_state = (
                data
                if dream_run_id
                else client().collection('dream_users').document(uid).get(transaction=tx).to_dict() or {}
            )
            questions = dream_state.get('questions', 0) if dream_state.get('question_day') == day else 0
            if (
                budget.get('dream_suggestions', 0) + questions >= SUGGESTIONS_PER_DAY
                or budget.get('used', 0) >= DAILY_BUDGET
            ):
                return 'suggestion_cap'
            tx.set(budget_ref, {'dream_suggestions': budget.get('dream_suggestions', 0) + 1}, merge=True)
        record: dict[str, Any] = {
            'item': item.model_dump(mode='python'),
            'source': source or {},
            'created_at': item.created_at,
            'evidence_version': evidence_version,
            'status': 'pending',
        }
        if dream_run_id:
            record['dream_origin'] = True
        tx.set(ref, encode_doc(uid, record))

        return 'suggested'

    result = run_with_transaction_contention_retry(
        client().transaction, enqueue, operation_name='review_proposal_enqueue'
    )
    return result if is_agent or dream_run_id else item.item_id


def validate_records(uid: str, tx, expected_records: dict | None) -> None:
    """Fence the offered target/evidence snapshots in the edit's transaction."""
    from database.dream_effect_fence import assert_active

    assert_active(uid, tx)
    for path, expected in (expected_records or {}).items():
        collection, key = path.split('/', 1)
        current = user(uid).collection(collection).document(key).get(transaction=tx).to_dict()
        if current != expected:
            raise ReviewConflict('Dream proposal evidence changed during apply')


def dream_question_item_id(uid: str, kind: str, source_ref: str, quote: str) -> str:
    """Id ``dream_review_policy.ask`` writes for a spelling or same-person question."""
    body = json.dumps([uid, kind, source_ref, quote], ensure_ascii=False)
    return f'{kind}:{uuid5(NAMESPACE_URL, body)}'


def proposal_record_is_dream_origin(uid: str, record: dict | None) -> bool:
    """True for a Dream question, including rows written before ``dream_origin`` existed.

    Those rows still carry the id ``ask`` assigned. An ordinary question uses a
    different id and has no marker.
    """
    data = record or {}
    if data.get('dream_origin') is True:
        return True
    item = data.get('item')
    if not isinstance(item, dict) or item.get('kind') not in {'spelling', 'same_person'}:
        return False
    kind = item.get('kind')
    source_ref = item.get('source_ref')
    quote = item.get('quote')
    item_id = item.get('item_id')
    if not isinstance(kind, str) or not isinstance(source_ref, str) or not isinstance(quote, str):
        return False
    if not isinstance(item_id, str):
        return False
    return item_id == dream_question_item_id(uid, kind, source_ref, quote)


def proposal_is_dream_origin(uid: str, item_id: str) -> bool:
    """True when Dream enqueued this spelling or same-person question."""
    data = decode_doc(uid, user(uid).collection('review_proposals').document(safe_id(item_id)).get().to_dict()) or {}
    return proposal_record_is_dream_origin(uid, data)


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


def offer_item(uid: str, item: ReviewItem | ReviewItemV2, source: dict, version: str) -> bool:
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
        budget = budget_ref.get(transaction=tx).to_dict() or {}
        data = decode_doc(uid, ref.get(transaction=tx).to_dict())
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
        tx.set(budget_ref, {'used': used + 1}, merge=True)
        return data | {'day': day, 'retry': False}

    return run_with_transaction_contention_retry(client().transaction, begin, operation_name='review_answer_begin')


def finish_answer(
    uid: str, item_id: str, *, applied: bool, uncertain: bool, offered_version: str, stale: bool = False
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
        if (stale or item_id.startswith(('same_person:', 'spelling:', 'agent_proposal:'))) and not uncertain:
            proposal_ref = user(uid).collection('review_proposals').document(safe_id(item_id))
            proposal = decode_doc(uid, proposal_ref.get(transaction=tx).to_dict())

        budget_ref = user(uid).collection('review_attention').document(answer['day']) if stale else None
        budget = (budget_ref.get(transaction=tx).to_dict() or {}) if budget_ref is not None else {}

        tx.update(ref, {'state': 'uncertain' if uncertain else 'answered', 'applied': applied})
        if budget_ref is not None:
            tx.set(budget_ref, {'used': max(0, budget.get('used', 0) - 1)}, merge=True)
        # A producer may refresh the stable item id while this answer is
        # applying. Resolve only the exact evidence version the user saw.
        if proposal_ref is not None and proposal and proposal.get('evidence_version') == offered_version:
            tx.update(proposal_ref, {'status': 'resolved', **({'resolution': 'stale'} if stale else {})})

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
            tx.set(budget_ref, {'used': max(0, budget.get('used', 0) - 1)}, merge=True)

    release(client().transaction())


_CONTENT_FIELDS = {
    'item',
    'source',
    'change',
    'edits',
    'before',
    'memory_edit',
    'memory_hygiene',
    'summary',
    'transcript_overlay',
}


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
