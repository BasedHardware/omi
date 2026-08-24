"""Authoritative, exhaustive trigger-watchlist snapshot for desktop clients."""

# LIFECYCLE: permanent

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.memory_collections import MemoryCollections
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryKind, MemorySubjectScope
from utils.memory.jit_trigger_contract import TriggerAction, compile_memory_item_trigger
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

MAX_AUTHORITATIVE_TRIGGERS = 500


@dataclass(frozen=True)
class AuthoritativeTriggerRow:
    memory_id: str
    item_revision: int
    updated_at: datetime
    trigger_condition: dict[str, Any]
    action: TriggerAction
    wakeup_budget_per_day: int | None


@dataclass(frozen=True)
class AuthoritativeTriggerSnapshot:
    owner_id: str
    account_generation: int
    head_commit_id: str
    commit_sequence: int
    snapshot_revision: str
    complete: bool
    rows: tuple[AuthoritativeTriggerRow, ...]
    failure_reason: str | None = None


def _revision(
    uid: str,
    account_generation: int,
    head_commit_id: str,
    commit_sequence: int,
    items: list[MemoryItem],
    rows: list[AuthoritativeTriggerRow],
) -> str:
    ordered_rows = sorted(rows, key=lambda candidate: candidate.memory_id)
    payload = {
        'uid': uid,
        'account_generation': account_generation,
        'head_commit_id': head_commit_id,
        'commit_sequence': commit_sequence,
        'items': [
            {
                'id': item.memory_id,
                'revision': item.item_revision,
                'status': item.status.value,
                'updated_at': item.updated_at.isoformat(),
                'superseded_by': item.superseded_by,
                'valid_to': item.valid_to.isoformat() if item.valid_to else None,
            }
            for item in sorted(items, key=lambda candidate: candidate.memory_id)
        ],
        'active_rows': [
            {
                'ordinal': ordinal,
                'memory_id': row.memory_id,
                'item_revision': row.item_revision,
                'updated_at': row.updated_at.isoformat(),
                'trigger_condition': row.trigger_condition,
                'action': {'type': row.action.type, 'prompt': row.action.prompt},
                'wakeup_budget_per_day': row.wakeup_budget_per_day,
            }
            for ordinal, row in enumerate(ordered_rows)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def read_authoritative_trigger_snapshot(
    uid: str,
    *,
    firestore_client: Any = None,
) -> AuthoritativeTriggerSnapshot:
    """Read one owner/generation-fenced snapshot or return an explicit incomplete receipt.

    Absence is authoritative only after the query is exhausted.  Any malformed,
    mixed-generation, oversized, or actionless active row makes the whole
    snapshot incomplete so ambient work cannot outrank an unseen planned action.
    """

    client = firestore_client or get_firestore_client()
    head = read_memory_v3_trusted_account_generation(uid=uid, db_client=client)
    try:
        account_generation = head.require_account_generation()
    except Exception:
        return AuthoritativeTriggerSnapshot(uid, 0, '', 0, '', False, (), 'generation_unavailable')
    head_commit_id = head.head_commit_id or ''
    commit_sequence = head.commit_sequence if head.commit_sequence is not None else 0
    collection = client.collection(MemoryCollections(uid=uid).memory_items)
    try:
        snapshots = list(
            collection.where(filter=FieldFilter('kind', '==', MemoryKind.trigger.value))
            .limit(MAX_AUTHORITATIVE_TRIGGERS + 1)
            .stream()
        )
    except Exception:
        return AuthoritativeTriggerSnapshot(
            uid, account_generation, head_commit_id, commit_sequence, '', False, (), 'query_failed'
        )
    if len(snapshots) > MAX_AUTHORITATIVE_TRIGGERS:
        return AuthoritativeTriggerSnapshot(
            uid, account_generation, head_commit_id, commit_sequence, '', False, (), 'trigger_limit_exceeded'
        )

    items: list[MemoryItem] = []
    rows: list[AuthoritativeTriggerRow] = []
    try:
        for snapshot in snapshots:
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                raise ValueError('malformed row')
            item = MemoryItem.model_validate(payload)
            if item.uid != uid or item.memory_id != snapshot.id or item.account_generation != account_generation:
                raise ValueError('identity or generation mismatch')
            items.append(item)
            is_open = item.status == MemoryItemStatus.active and item.valid_to is None and item.superseded_by is None
            if not is_open:
                continue
            if (
                item.ledger_schema_version != 'knowledge_ledger.v1'
                or item.subject_scope != MemorySubjectScope.primary_user
                or not item.intent_backed
            ):
                raise ValueError('active trigger is not intent authoritative')
            compiled = compile_memory_item_trigger(item)
            action = compiled.condition.action
            if action is None:
                raise ValueError('active trigger has no action')
            raw_budget = item.arguments.get('wakeup_budget_per_day')
            budget = raw_budget if type(raw_budget) is int and raw_budget > 0 else None
            rows.append(
                AuthoritativeTriggerRow(
                    memory_id=item.memory_id,
                    item_revision=item.item_revision,
                    updated_at=item.updated_at,
                    trigger_condition=compiled.as_condition(),
                    action=action,
                    wakeup_budget_per_day=budget,
                )
            )
    except Exception:
        return AuthoritativeTriggerSnapshot(
            uid, account_generation, head_commit_id, commit_sequence, '', False, (), 'row_invalid'
        )

    # Firestore has no transaction spanning this compound query and the
    # separately stored ledger head. Re-read the trusted head after exhausting
    # and validating every row; any mutation during the read makes the receipt
    # explicitly incomplete instead of certifying a torn projection.
    trailing_head = read_memory_v3_trusted_account_generation(uid=uid, db_client=client)
    try:
        trailing_identity = (
            trailing_head.require_account_generation(),
            trailing_head.head_commit_id or '',
            trailing_head.commit_sequence if trailing_head.commit_sequence is not None else 0,
        )
    except Exception:
        trailing_identity = None
    if trailing_identity != (account_generation, head_commit_id, commit_sequence):
        return AuthoritativeTriggerSnapshot(
            uid, account_generation, head_commit_id, commit_sequence, '', False, (), 'authority_changed'
        )

    revision = _revision(uid, account_generation, head_commit_id, commit_sequence, items, rows)
    rows.sort(key=lambda row: row.memory_id)
    return AuthoritativeTriggerSnapshot(
        owner_id=uid,
        account_generation=account_generation,
        head_commit_id=head_commit_id,
        commit_sequence=commit_sequence,
        snapshot_revision=revision,
        complete=True,
        rows=tuple(rows),
    )


__all__ = [
    'AuthoritativeTriggerRow',
    'AuthoritativeTriggerSnapshot',
    'MAX_AUTHORITATIVE_TRIGGERS',
    'read_authoritative_trigger_snapshot',
]
