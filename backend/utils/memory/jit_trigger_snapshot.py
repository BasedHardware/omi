"""Authoritative, exhaustive trigger-watchlist snapshot for desktop clients."""

# LIFECYCLE: permanent

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_data_plane_firestore_client
from database.memory_collections import MemoryCollections
from models.jit_proactivity import is_jit_trigger_paid_authority
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryKind
from utils.memory.jit_trigger_contract import (
    CompiledTrigger,
    DEFAULT_TRIGGER_RUNTIME_POLICY,
    TriggerAction,
    TriggerRuntimePolicy,
    compile_memory_item_trigger,
)
from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason,
    V3TrustedAccountGenerationReadError,
    read_memory_v3_trusted_account_generation,
)

MAX_AUTHORITATIVE_TRIGGERS = 500


@dataclass(frozen=True)
class AuthoritativeTriggerRow:
    memory_id: str
    item_revision: int
    updated_at: datetime
    trigger_condition: dict[str, Any]
    action: TriggerAction
    wakeup_budget_per_day: int
    snoozed_until: datetime | None = None


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
    policy: TriggerRuntimePolicy = DEFAULT_TRIGGER_RUNTIME_POLICY
    # The reservation store owns the budget window using the profile's IANA
    # timezone.  Returning the same authority lets clients pace their local
    # mirror under that window instead of silently using the host timezone.
    budget_day: str | None = None
    budget_timezone: str | None = None


@dataclass(frozen=True)
class AuthoritativeTriggerComponents:
    """Validated paid-work projection for one trigger row."""

    compiled: CompiledTrigger
    wakeup_budget_per_day: int
    snoozed_until: datetime | None


def _authoritative_trigger_components(
    item: MemoryItem,
    at: datetime,
) -> AuthoritativeTriggerComponents:
    """Validate one trigger and return its exact paid-work projection."""
    if not is_jit_trigger_paid_authority(item, at=at):
        raise ValueError('trigger is not paid-work authority')
    compiled = compile_memory_item_trigger(item)
    if compiled.condition.embedding is not None:
        embedding_policy = DEFAULT_TRIGGER_RUNTIME_POLICY.embedding
        if (
            not embedding_policy.enabled
            or compiled.condition.embedding.model_id != embedding_policy.model_id
            or compiled.condition.embedding.model_version != embedding_policy.model_version
            or compiled.condition.embedding.language != embedding_policy.language
        ):
            raise ValueError('embedding trigger is not locally attested')
    if compiled.condition.action is None:
        raise ValueError('trigger action is missing')
    raw_budget = item.arguments.get('wakeup_budget_per_day')
    if (
        type(raw_budget) is not int
        or raw_budget != DEFAULT_TRIGGER_RUNTIME_POLICY.planned_notifications_per_trigger_per_day
    ):
        raise ValueError('trigger wakeup budget is invalid')

    feedback = item.arguments.get('jit_trigger_feedback', {})
    if not isinstance(feedback, dict):
        raise ValueError('trigger feedback state is malformed')
    raw_snoozed_until = feedback.get('snoozed_until')
    snoozed_until: datetime | None = None
    if raw_snoozed_until is not None:
        if isinstance(raw_snoozed_until, datetime):
            snoozed_until = raw_snoozed_until
        else:
            snoozed_until = datetime.fromisoformat(str(raw_snoozed_until))
        if snoozed_until.tzinfo is None or snoozed_until.utcoffset() is None:
            raise ValueError('trigger snooze must be timezone-aware')
    return AuthoritativeTriggerComponents(
        compiled=compiled,
        wakeup_budget_per_day=int(raw_budget),
        snoozed_until=snoozed_until,
    )


def is_authoritative_trigger_for_paid_work(item: MemoryItem, at: datetime) -> bool:
    """Use the exact snapshot compiler, snooze, and policy as the paid transaction gate."""

    try:
        components = _authoritative_trigger_components(item, at)
    except Exception:
        return False
    return components.snoozed_until is None or at >= components.snoozed_until


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
        'policy': DEFAULT_TRIGGER_RUNTIME_POLICY.model_dump(mode='json'),
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
                'snoozed_until': row.snoozed_until.isoformat() if row.snoozed_until else None,
            }
            for ordinal, row in enumerate(ordered_rows)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _empty_watchlist_revision(uid: str, account_generation: int) -> str:
    """Deterministic revision for a watchlist proven empty by head absence."""
    encoded = f'empty-watchlist:{uid}:{account_generation}'.encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _budget_authority(uid: str, at: datetime, client: Any) -> tuple[str, str] | None:
    """Read the content-free profile timezone used by JIT reservations.

    Some old or synthetic users have no timezone yet.  Keep the snapshot
    readable for compatibility; the client will use its legacy fallback and
    the paid reservation remains the final authority.  A malformed timezone is
    never projected as a plausible value.
    """

    try:
        snapshot = client.document(f'users/{uid}').get()
        payload = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        timezone_name = payload.get('time_zone') if isinstance(payload, dict) else None
        if not isinstance(timezone_name, str):
            return None
        timezone_name = timezone_name.strip()
        if not timezone_name:
            return None
        zone = ZoneInfo(timezone_name)
        return at.astimezone(zone).date().isoformat(), timezone_name
    except Exception:
        return None


def read_authoritative_trigger_snapshot(
    uid: str,
    *,
    firestore_client: Any = None,
) -> AuthoritativeTriggerSnapshot:
    """Read one owner/generation-fenced snapshot or return an explicit incomplete receipt.

    Absence is authoritative only after the query is exhausted.  Any malformed,
    mixed-generation, oversized, or actionless active row makes the whole
    snapshot incomplete so ambient work cannot outrank an unseen planned action.
    A state head proven absent (the owner has no memory-v3 generation at all)
    yields a complete, empty watchlist with a deterministic revision; unproven
    absence (read failure, malformed head) stays incomplete.
    """

    client = firestore_client or get_data_plane_firestore_client()
    head = read_memory_v3_trusted_account_generation(uid=uid, db_client=client)
    try:
        account_generation = head.require_account_generation()
    except V3TrustedAccountGenerationReadError as exc:
        if exc.reason is not V3AccountGenerationFailureReason.MISSING_STATE_HEAD:
            return AuthoritativeTriggerSnapshot(uid, 0, '', 0, '', False, (), 'generation_unavailable')
        # A proven-absent state head means the owner never initialized memory
        # v3, so the exhaustive watchlist is provably empty.  Fence the absence
        # exactly like a row scan: certify complete only if the head is still
        # absent on a trailing re-read, so a head created mid-flight cannot be
        # certified away as an empty generation.
        trailing = read_memory_v3_trusted_account_generation(uid=uid, db_client=client)
        if trailing.read_error_reason is not V3AccountGenerationFailureReason.MISSING_STATE_HEAD:
            return AuthoritativeTriggerSnapshot(uid, 0, '', 0, '', False, (), 'generation_unavailable')
        budget_authority = _budget_authority(uid, datetime.now(timezone.utc), client)
        return AuthoritativeTriggerSnapshot(
            owner_id=uid,
            account_generation=0,
            head_commit_id='',
            commit_sequence=0,
            snapshot_revision=_empty_watchlist_revision(uid, 0),
            complete=True,
            rows=(),
            budget_day=budget_authority[0] if budget_authority else None,
            budget_timezone=budget_authority[1] if budget_authority else None,
        )
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
    authority_time = datetime.now(timezone.utc)
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
            components = _authoritative_trigger_components(item, authority_time)
            action = components.compiled.condition.action
            assert action is not None
            rows.append(
                AuthoritativeTriggerRow(
                    memory_id=item.memory_id,
                    item_revision=item.item_revision,
                    updated_at=item.updated_at,
                    trigger_condition=components.compiled.as_condition(),
                    action=action,
                    wakeup_budget_per_day=components.wakeup_budget_per_day,
                    snoozed_until=components.snoozed_until,
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
    # Keep the projected day tied to the same instant as the fenced snapshot.
    # A second clock read here could straddle a profile-local midnight.
    budget_authority = _budget_authority(uid, authority_time, client)
    return AuthoritativeTriggerSnapshot(
        owner_id=uid,
        account_generation=account_generation,
        head_commit_id=head_commit_id,
        commit_sequence=commit_sequence,
        snapshot_revision=revision,
        complete=True,
        rows=tuple(rows),
        budget_day=budget_authority[0] if budget_authority else None,
        budget_timezone=budget_authority[1] if budget_authority else None,
    )


__all__ = [
    'AuthoritativeTriggerComponents',
    'AuthoritativeTriggerRow',
    'AuthoritativeTriggerSnapshot',
    'MAX_AUTHORITATIVE_TRIGGERS',
    'is_authoritative_trigger_for_paid_work',
    'read_authoritative_trigger_snapshot',
]
