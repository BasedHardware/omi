"""Capture groups: one event recorded by several capture surfaces (#3244).

A capture group records that conversations from different surfaces (desktop,
pendant, phone...) captured the same real-world event, proven by shared speech.
Grouping is metadata only: no transcript, summary, or derived effect changes,
and every member remains a complete conversation of its own.

Storage: every member document carries the same ``capture_group`` record
(``id``, ``primary_id``, ``revision``, ``members``). The group id is minted
independently of any member, so the primary (the longest window) can change
without changing the event's identity. ``capture_group_exclusions`` holds
conversation ids a person separated from this one; they never regroup.

This module is the only writer of both fields. Processing writes strip
``capture_group`` (see ``database.conversations``), so a stale in-memory
conversation cannot clobber membership.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from google.cloud import firestore

from ._client import get_firestore_client

logger = logging.getLogger(__name__)

CAPTURE_GROUP_FIELD = 'capture_group'
EXCLUSIONS_FIELD = 'capture_group_exclusions'
MAX_GROUP_MEMBERS = 12
_CONVERSATIONS = 'conversations'


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _source(row: Mapping[str, Any]) -> Optional[str]:
    source = row.get('source')
    return getattr(source, 'value', source)


def _member(conversation_id: str, row: Mapping[str, Any], evidence: Optional[dict] = None) -> dict:
    member = {
        'id': conversation_id,
        'source': _source(row),
        'started_at': _aware(row.get('started_at')),
        'finished_at': _aware(row.get('finished_at')),
    }
    if evidence:
        member['evidence'] = evidence
    return member


def _primary_rank(member: Mapping[str, Any]) -> tuple[float, str]:
    start, finish = member.get('started_at'), member.get('finished_at')
    duration = (finish - start).total_seconds() if start and finish else 0.0
    return (-duration, member['id'])


def _record(group_id: str, members: list[dict], revision: int) -> dict:
    ordered = sorted(members, key=lambda m: (m.get('started_at') or datetime.min.replace(tzinfo=timezone.utc), m['id']))
    return {
        'id': group_id,
        'primary_id': min(ordered, key=_primary_rank)['id'],
        'revision': revision,
        'members': ordered,
        'updated_at': datetime.now(timezone.utc),
    }


def _joinable(row: Optional[Mapping[str, Any]]) -> bool:
    return bool(row) and not row.get('deleted') and not row.get('discarded') and row.get('status') == 'completed'


def _excludes(row: Mapping[str, Any], other_ids: set[str]) -> bool:
    return bool(set(row.get(EXCLUSIONS_FIELD) or ()) & other_ids)


def join_capture_group(
    uid: str,
    first_id: str,
    second_id: str,
    evidence: dict,
    *,
    expected_windows: Optional[Mapping[str, tuple[Any, Any]]] = None,
    firestore_client=None,
) -> Optional[str]:
    """Put two content-confirmed captures in one group; return the group id.

    A new pair founds a group; a capture joins an existing group through one of
    its members. Two captures already in different groups are left alone:
    pairwise shared speech is not transitive event identity, so bridging two
    groups needs stronger evidence than one pair. Every member is re-read in
    the transaction, so a concurrent join, separation, discard, or deletion
    fences the write. ``expected_windows`` fences capture-window changes after
    discovery.
    """
    client = firestore_client or get_firestore_client()
    collection = client.collection('users').document(uid).collection(_CONVERSATIONS)

    @firestore.transactional
    def join(transaction) -> Optional[str]:
        rows = {cid: collection.document(cid).get(transaction=transaction).to_dict() for cid in (first_id, second_id)}
        if not all(_joinable(row) for row in rows.values()):
            return None
        for cid, window in (expected_windows or {}).items():
            row = rows.get(cid) or {}
            if (_aware(row.get('started_at')), _aware(row.get('finished_at'))) != tuple(_aware(v) for v in window):
                return None
        groups = {cid: (row.get(CAPTURE_GROUP_FIELD) or {}) for cid, row in rows.items()}
        group_ids = {g.get('id') for g in groups.values() if g.get('id')}
        if len(group_ids) > 1:
            return None
        if group_ids and all(g.get('id') for g in groups.values()):
            return group_ids.pop()  # already grouped together

        existing = next((g for g in groups.values() if g.get('id')), None)
        member_ids = [m['id'] for m in (existing or {}).get('members', []) if m.get('id') not in rows]
        for cid in member_ids:
            rows[cid] = collection.document(cid).get(transaction=transaction).to_dict()
        # Members deleted without cleanup drop out; members moved elsewhere fence the join.
        live = {cid: row for cid, row in rows.items() if row and not row.get('deleted')}
        if existing and any(
            (live[cid].get(CAPTURE_GROUP_FIELD) or {}).get('id') != existing['id'] for cid in member_ids if cid in live
        ):
            return None
        all_ids = set(live)
        if any(_excludes(row, all_ids - {cid}) for cid, row in live.items()):
            return None
        if len(live) > MAX_GROUP_MEMBERS:
            return None

        group_id = existing['id'] if existing else str(uuid.uuid4())
        prior = {m['id']: m for m in (existing or {}).get('members', [])}
        members = []
        for cid, row in live.items():
            if cid in prior:
                members.append(_member(cid, row, prior[cid].get('evidence')))
            else:
                partner = second_id if cid == first_id else first_id
                members.append(_member(cid, row, {**evidence, 'matched_conversation_id': partner}))
        record = _record(group_id, members, int((existing or {}).get('revision') or 0) + 1)
        for cid in live:
            transaction.update(collection.document(cid), {CAPTURE_GROUP_FIELD: record})
        return group_id

    return join(client.transaction())


def leave_capture_group(uid: str, conversation_id: str, *, sticky: bool, firestore_client=None) -> bool:
    """Remove one conversation from its group.

    ``sticky`` records the person's decision that this capture is a different
    event from every current member, so later finalizations never regroup them.
    A group left with one member dissolves. Returns whether anything changed.
    """
    client = firestore_client or get_firestore_client()
    collection = client.collection('users').document(uid).collection(_CONVERSATIONS)

    @firestore.transactional
    def leave(transaction) -> bool:
        row = collection.document(conversation_id).get(transaction=transaction).to_dict()
        group = (row or {}).get(CAPTURE_GROUP_FIELD) or {}
        if not row or not group.get('id'):
            return False
        others = [m['id'] for m in group.get('members', []) if m.get('id') and m['id'] != conversation_id]
        other_rows = {cid: collection.document(cid).get(transaction=transaction).to_dict() for cid in others}
        remaining = {
            cid: r
            for cid, r in other_rows.items()
            if r and not r.get('deleted') and (r.get(CAPTURE_GROUP_FIELD) or {}).get('id') == group['id']
        }
        own_update: dict[str, Any] = {CAPTURE_GROUP_FIELD: None}
        if sticky:
            own_update[EXCLUSIONS_FIELD] = sorted(set(row.get(EXCLUSIONS_FIELD) or ()) | set(others))
        transaction.update(collection.document(conversation_id), own_update)
        if len(remaining) < 2:
            for cid in remaining:
                transaction.update(collection.document(cid), {CAPTURE_GROUP_FIELD: None})
            return True
        prior = {m['id']: m for m in group.get('members', [])}
        record = _record(
            group['id'],
            [_member(cid, r, (prior.get(cid) or {}).get('evidence')) for cid, r in remaining.items()],
            int(group.get('revision') or 0) + 1,
        )
        for cid in remaining:
            transaction.update(collection.document(cid), {CAPTURE_GROUP_FIELD: record})
        return True

    return leave(client.transaction())
