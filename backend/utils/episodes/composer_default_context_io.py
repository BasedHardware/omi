"""Bounded Firestore reads for deterministic episode background, composer only.

Every reference starts at users/{uid}; no external calendar API or model call.
Single-field range/equality queries use existing automatic indexes.
"""

from __future__ import annotations

import json
import re
import zlib
from datetime import timedelta
from typing import Any, Mapping, Sequence

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from utils import encryption
from utils.episodes.composer_default_context import ReadBudget, bounds, live, person_ids, safe_id, text, utc
from utils.manual_speaker_assignments import apply_manual_assignments
from utils.observability.fallback import record_fallback as record_fallback
from utils.open_loops.store import OPEN_STATUSES


def _root(uid: str, firestore_client: Any = None) -> Any:
    if not safe_id(uid):
        raise ValueError('invalid context owner')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid)


def _query(query: Any, limit: int, budget: ReadBudget) -> list[dict[str, Any]]:
    timeout = budget.reserve(limit)
    docs = list(query.limit(limit).stream(timeout=timeout, retry=None))
    budget.refund(limit, len(docs))
    return [{**(doc.to_dict() or {}), 'id': doc.id} for doc in docs]


def _get(ref: Any, budget: ReadBudget) -> dict[str, Any]:
    doc = ref.get(timeout=budget.reserve(1), retry=None)
    budget.check()
    return {**(doc.to_dict() or {}), 'id': doc.id} if doc.exists else {}


def _json(value: Any, uid: str, compressed: bool = False) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, (str, bytes)):
        return None
    payload = encryption.decrypt(value, uid) if isinstance(value, str) else value
    if compressed:
        payload = zlib.decompress(bytes.fromhex(payload) if isinstance(payload, str) else payload).decode('utf-8')
    return json.loads(payload)


def people(uid: str, ids: Sequence[str], budget: ReadBudget, *, firestore_client: Any = None) -> list[dict]:
    root = _root(uid, firestore_client)
    result = []
    for pid in sorted({safe_id(pid) for pid in ids} - {''})[:6]:
        row = _get(root.collection('people').document(pid), budget)
        if not row or not live(row) or row.get('is_dismissed'):
            continue
        facts = []
        for fact in row.get('facts') or []:
            if isinstance(fact, Mapping):
                if live(fact):
                    facts.append(text(fact.get('content') or fact.get('text'), 180))
            elif isinstance(fact, str):
                facts.append(text(fact, 180))
        result.append(
            {
                'source': f'stored about this person: people/{pid}',
                'person_id': pid,
                'name': text(row.get('name'), 120),
                'aliases': [text(alias, 80) for alias in (row.get('aliases') or [])[:5]],
                'relationship': text(row.get('relationship') or row.get('role') or row.get('subtitle'), 180),
                'description': text(row.get('description'), 300),
                'facts': [fact for fact in facts if fact][:3],
            }
        )
    return result


def calendar(
    uid: str, members: Sequence[Mapping[str, Any]], budget: ReadBudget, *, firestore_client: Any = None
) -> list[dict]:
    start, end = bounds(members)
    if not start or not end or end <= start:
        return []
    # One range + matching order uses the automatic start_time index. A fixed
    # candidate window avoids a new two-range composite and unbounded history.
    query = (
        _root(uid, firestore_client)
        .collection('meetings')
        .where(filter=FieldFilter('start_time', '>=', start - timedelta(days=1)))
        .where(filter=FieldFilter('start_time', '<', end))
        .order_by('start_time', direction='DESCENDING')
    )
    candidates = []
    for row in _query(query, 8, budget):
        a, b = utc(row.get('start_time')), utc(row.get('end_time'))
        if live(row) and a and b and b > start and a < end:
            overlap = (min(end, b) - max(start, a)).total_seconds()
            candidates.append((-overlap, str(row['id']), row, a, b))
    if not candidates:
        return []
    _, _, row, a, b = min(candidates, key=lambda item: item[:2])
    return [
        {
            'source': f'calendar entry: meetings/{row["id"]}',
            'title': text(row.get('title'), 200),
            'attendees': [text(item, 140) for item in (row.get('participants') or row.get('attendees') or [])[:12]],
            'description_or_agenda': text(row.get('description') or row.get('agenda'), 500),
            'start': a.isoformat(),
            'end': b.isoformat(),
        }
    ]


def prior(
    uid: str,
    members: Sequence[Mapping[str, Any]],
    ids: Sequence[str],
    budget: ReadBudget,
    *,
    firestore_client: Any = None,
) -> list[dict]:
    start, _ = bounds(members)
    if not start or not ids:
        return []
    query = (
        _root(uid, firestore_client)
        .collection('conversations')
        .where(filter=FieldFilter('started_at', '<', start))
        .order_by('started_at', direction='DESCENDING')
        .select(
            [
                'started_at',
                'finished_at',
                'structured.title',
                'structured.overview',
                'manual_speaker_assignments',
                'manual_speaker_assignments_compressed',
                'deleted',
                'is_deleted',
                'deleted_at',
                'discarded',
                'status',
                'episode_id',
            ]
        )
    )
    result = []
    excluded = {row.get('id') for row in members}
    for row in _query(query, 12, budget):
        if not live(row) or row.get('discarded') or row['id'] in excluded:
            continue
        # The durable identity receipt is a compact assignment projection.
        # Do not fetch/decode transcript text or a GCS pointer for matching.
        receipt = _json(
            row.get('manual_speaker_assignments'), uid, bool(row.get('manual_speaker_assignments_compressed'))
        )
        segments = []
        if isinstance(receipt, Mapping):
            for group in ('speakers', 'segments', 'voices'):
                for key, decision in (receipt.get(group) or {}).items():
                    if not isinstance(decision, Mapping):
                        continue
                    seed = {
                        'id': key,
                        'speaker_id': decision.get('speaker_id', -1),
                        'speaker_id_scope': decision.get('speaker_id_scope'),
                    }
                    if group == 'speakers':
                        try:
                            seed['speaker_id'] = int(key)
                        except ValueError:
                            continue
                    elif group == 'voices':
                        scope, label = json.loads(key)
                        seed.update(speaker_id_scope=scope, speaker=label)
                    segments.append(seed)
            segments = apply_manual_assignments(segments, dict(receipt))
        shared = sorted(set(person_ids([{'transcript_segments': segments}])) & set(ids))
        if not shared:
            continue
        at = utc(row.get('started_at'))
        structured = row.get('structured') or {}
        result.append(
            {
                'source': f'from the conversation on {at.date() if at else "unknown"}: conversations/{row["id"]}',
                'conversation_id': row['id'],
                'shared_person_ids': shared,
                'date': at.isoformat() if at else '',
                'title': text(structured.get('title'), 180),
                'existing_summary': text(structured.get('overview'), 700),
            }
        )
        if len(result) == 2:
            break
    return result


def actions(
    uid: str,
    ids: Sequence[str],
    people_rows: Sequence[Mapping[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
    budget: ReadBudget,
    *,
    member_ids: Sequence[str] = (),
    firestore_client: Any = None,
) -> list[dict]:
    if not ids and not prior_rows and not member_ids:
        return []
    root = _root(uid, firestore_client)
    control = _get(root.collection('task_intelligence_control').document('state'), budget)
    generation = control.get('account_generation', 0)
    prior_ids = [safe_id(row.get('conversation_id')) for row in prior_rows]
    conversation_ids = list(dict.fromkeys(pid for pid in [*member_ids, *prior_ids] if safe_id(pid)))
    names = {
        text(value).casefold()
        for row in people_rows
        for value in [row.get('name'), *(row.get('aliases') or [])]
        if value
    }
    result = []

    def related(row):
        references = set(row.get('source_conversation_ids') or []) | {row.get('conversation_id')}
        bound_people = set(row.get('person_ids') or []) | {row.get('person_id'), row.get('assignee_person_id')}
        description = (text(row.get('description') or row.get('what'), 1500) + ' ' + text(row.get('who'))).casefold()
        return bool(
            set(conversation_ids) & references
            or set(ids) & bound_people
            or any(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', description) for name in names)
        )

    # Relation first, then the small candidate cap. IN + same-field order
    # uses that field's automatic single-field index, never a composite.
    candidates = {}
    batches = [conversation_ids[i : i + 30] for i in range(0, min(len(conversation_ids), 90), 30)]
    for index, batch in enumerate(batches):
        limit = 8 // len(batches) + (index < 8 % len(batches))
        query = (
            root.collection('action_items')
            .where(filter=FieldFilter('conversation_id', 'in', batch))
            .order_by('conversation_id', direction='DESCENDING')
        )
        for row in _query(query, limit, budget):
            candidates.setdefault(row['id'], row)
    if ids:
        query = (
            root.collection('action_items')
            .where(filter=FieldFilter('person_id', 'in', list(ids)[:6]))
            .order_by('person_id', direction='DESCENDING')
        )
        for row in _query(query, 3, budget):
            candidates.setdefault(row['id'], row)
        # Name-only legacy tasks have no indexed person field. A tiny recent
        # window supplies best-effort name matches after exact linked queries.
        for row in _query(root.collection('action_items').order_by('created_at', direction='DESCENDING'), 2, budget):
            candidates.setdefault(row['id'], row)
    for row in candidates.values():
        if (
            live(row)
            and row.get('completed') is False
            and row.get('account_generation', 0) == generation
            and row.get('status') not in {'completed', 'cancelled', 'done'}
            and related(row)
        ):
            result.append(
                {
                    'source': f'stored open action: action_items/{row["id"]}',
                    'description': text(row.get('description'), 240),
                    'due': text(row.get('due_at'), 60),
                }
            )
    for raw in _query(
        root.collection('open_loops')
        .where(filter=FieldFilter('status', 'in', sorted(OPEN_STATUSES)))
        .order_by('status', direction='ASCENDING'),
        8,
        budget,
    ):
        row = _json(raw.get('data'), uid, bool(raw.get('data_compressed')))
        if isinstance(row, Mapping) and live(raw) and live(row) and row.get('status') in OPEN_STATUSES and related(row):
            result.append(
                {
                    'source': f'stored open loop: open_loops/{raw["id"]}',
                    'description': text(row.get('what'), 240),
                    'who': text(row.get('who'), 100),
                    'due': text(row.get('by_when'), 60),
                }
            )
    return result[:6]
