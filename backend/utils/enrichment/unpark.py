"""Bounded, digest-approved operator unpark for historical enrichment debt."""

from collections import Counter
import hashlib
import json
import math
import re
import time
from typing import Any
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from config import enrichment as enrichment_config
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from utils.enrichment import age_gate, outbox

OPERATION = 'enrichment-age-gate-unpark-v1'
ROW_ID = re.compile(r'[0-9a-f]{64}')


def _digest(body: dict) -> str:
    encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _cursor(after: object) -> dict | None:
    if after is None:
        return None
    if not isinstance(after, dict) or set(after) != {'deferred_since', 'path'}:
        raise ValueError('invalid unpark cursor')
    parked_at = after['deferred_since']
    if isinstance(parked_at, bool) or not isinstance(parked_at, (int, float)) or not math.isfinite(parked_at):
        raise ValueError('invalid unpark cursor')
    parts = after['path'].split('/') if isinstance(after['path'], str) else []
    if len(parts) != 2 or parts[0] != outbox.COLLECTION or not ROW_ID.fullmatch(parts[1]):
        raise ValueError('invalid unpark cursor')
    return {'deferred_since': parked_at, 'path': after['path']}


def discover(client: Any, *, limit: int = 128, after: dict | None = None) -> tuple[list[str], dict | None]:
    """Return one keys-only, newest-first page and its private resumption cursor."""
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('discovery limit must be 1..128')
    after = _cursor(after)
    collection = client.collection(outbox.COLLECTION)
    query = (
        collection.where(filter=FieldFilter('age_gate_parked', '==', True))
        .order_by('deferred_since', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .select(['deferred_since'])
        .limit(limit)
    )
    if after is not None:
        query = query.start_after(
            {'deferred_since': after['deferred_since'], '__name__': client.document(after['path'])}
        )
    snapshots = list(query.stream())
    ids = []
    for snapshot in snapshots:
        if not ROW_ID.fullmatch(snapshot.id):
            raise ValueError('invalid discovered outbox id')
        ids.append(snapshot.id)
    if not snapshots:
        return [], None
    last = snapshots[-1]
    parked_at = (last.to_dict() or {}).get('deferred_since')
    return ids, _cursor({'deferred_since': parked_at, 'path': last.reference.path})


def _too_old(row: dict, created_at: object, *, now: float, max_age_seconds: float) -> bool:
    if max_age_seconds == 0:
        return False
    cutoff = now - max_age_seconds
    return any(
        value is not None and value < cutoff
        for value in (age_gate.timestamp(row.get('first_pending_at')), age_gate.timestamp(created_at))
    )


def _refusal(row: dict, *, now: float) -> str | None:
    if (
        row.get('age_gate_parked') is not True
        or row.get('deferred_reason') != age_gate.REASON
        or not row.get('dormant')
    ):
        return 'not_parked'
    if not isinstance(row.get('task_token'), str) or not row['task_token']:
        return 'not_parked'
    if row.get('lease_until', 0) > now:
        return 'leased'
    if row.get('held_reason') or row.get('summary_blocked_reason') or row.get('summary_seen'):
        return 'blocked'
    if not outbox.valid_effects_binding(row):
        return 'unbound'
    return None


def prepare(
    client: Any,
    document_id: str,
    *,
    now: float,
    max_age_seconds: float,
    apply: bool,
    expected_token: str | None = None,
) -> tuple[str, dict | None]:
    """Recheck identity, exact token, age and privacy in the write transaction."""
    if not ROW_ID.fullmatch(document_id):
        raise ValueError('invalid outbox scope')
    ref = client.collection(outbox.COLLECTION).document(document_id)

    @firestore.transactional
    def commit(transaction):
        old = ref.get(transaction=transaction).to_dict() or {}
        uid, cid = old.get('uid'), old.get('conversation_id')
        if (
            not isinstance(uid, str)
            or not uid
            or not isinstance(cid, str)
            or not cid
            or outbox.key(uid, cid) != document_id
            or old.get('document_id', document_id) != document_id
        ):
            return 'identity_changed', None
        if expected_token is not None and old.get('task_token') != expected_token:
            return 'state_changed', None
        reason = _refusal(old, now=now)
        if reason:
            return reason, None
        conversation_ref = client.collection('users').document(uid).collection('conversations').document(cid)
        conversation = conversation_ref.get(transaction=transaction).to_dict() or {}
        if _too_old(old, conversation.get('created_at'), now=now, max_age_seconds=max_age_seconds):
            return 'outside_age_window', None
        try:
            assert_batch_write_allowed(client, transaction, uid, conversation_ids=[cid])
        except BatchPrivacyBlocked:
            return 'privacy_refused', None
        if not apply:
            return 'eligible', {'document_id': document_id, 'task_token': old['task_token']}
        pending = dict(old)
        pending.pop('deferred_since', None)
        pending.update(
            age_gate_parked=False,
            deferred_reason=None,
            dormant=False,
            due_at=now,
            task_due_at=now,
            task_token=uuid.uuid4().hex,
            lease_until=0,
            owner=None,
            wake_check_after=0,
        )
        transaction.set(ref, pending)
        return 'prepared', pending

    return commit(client.transaction())


def plan_unpark(client: Any, document_ids: list[str], *, now: float, max_age_seconds: float) -> dict:
    if len(document_ids) > 128 or len(set(document_ids)) != len(document_ids):
        raise ValueError('bounded unique discovery page required')
    if max_age_seconds < 0 or not math.isfinite(max_age_seconds):
        raise ValueError('invalid age window')
    entries = []
    for document_id in document_ids:
        try:
            disposition, entry = prepare(client, document_id, now=now, max_age_seconds=max_age_seconds, apply=False)
            entries.append(entry if disposition == 'eligible' else {'document_id': document_id})
            entries[-1]['disposition'] = disposition
        except Exception:
            entries.append({'document_id': document_id, 'disposition': 'read_error'})
    # ``now`` is deliberately absent from the approved body: the digest must be
    # reproducible by a later apply of the same page. Each eligible entry carries
    # the exact ``task_token`` the write transaction re-checks, so approving the
    # plan still pins the row state that justified it.
    body = {
        'operation': OPERATION,
        'entries': entries,
        'max_age_seconds': max_age_seconds,
    }
    return {**body, 'plan_sha256': _digest(body)}


def summary(plan: dict) -> dict:
    return {
        'operation': OPERATION,
        'plan_sha256': plan['plan_sha256'],
        'count': len(plan['entries']),
        'dispositions': dict(sorted(Counter(entry['disposition'] for entry in plan['entries']).items())),
    }


def apply_unpark(
    client: Any, plan: dict, approved_digest: str, *, pace_seconds: float = 1.0, wake=outbox.wake_row
) -> dict:
    if not enrichment_config.age_gate_unpark_enabled():
        raise ValueError('age-gate unpark is disabled')
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if approved_digest != plan.get('plan_sha256') or _digest(body) != approved_digest:
        raise ValueError('fresh dry-run plan approval required')
    if plan.get('operation') != OPERATION:
        raise ValueError('plan target changed')
    if plan.get('max_age_seconds') != age_gate.max_age_seconds():
        raise ValueError('age window changed after planning')
    if not 0 <= pace_seconds <= 60:
        raise ValueError('pace must be 0..60 seconds')
    outcomes = Counter()
    eligible_positions = [index for index, entry in enumerate(plan['entries']) if entry['disposition'] == 'eligible']
    for position, entry in enumerate(plan['entries']):
        if entry['disposition'] != 'eligible':
            outcomes[entry['disposition']] += 1
            continue
        try:
            status, pending = prepare(
                client,
                entry['document_id'],
                now=time.time(),
                max_age_seconds=plan['max_age_seconds'],
                apply=True,
                expected_token=entry['task_token'],
            )
        except Exception:
            outcomes['write_error'] += 1
        else:
            if pending is None:
                outcomes[status] += 1
            else:
                try:
                    wake(pending)  # Failure leaves durable due debt for the normal sweep.
                except Exception:
                    outcomes['enqueue_error'] += 1
                else:
                    outcomes['unparked'] += 1
        if position != eligible_positions[-1] and pace_seconds:
            time.sleep(pace_seconds)
    return dict(sorted(outcomes.items()))
