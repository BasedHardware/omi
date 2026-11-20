"""Revisioned scheduling metadata on the canonical result log.

Only the projection state machine decides whether an effect landed. These
fields claim and schedule delivery of that existing work.
"""

from dataclasses import dataclass
import math
import uuid
from typing import Any

from config.batch_pipeline import projection_followup_backoff_seconds, projection_outbox_enabled
from database.batch_pipeline_projection_followup_clock import DUE_FIELD as FOLLOWUP_DUE_FIELD
from database.batch_pipeline_projection_followup_clock import STATES as FOLLOWUP_STATES

KIND_FIELD = 'projection_outbox_kind'
DUE_FIELD = 'projection_outbox_due_at'
TOKEN_FIELD = 'projection_outbox_token'
REASON_FIELD = 'projection_outbox_reason'
KIND = 'project_conversation_v1'
PATCH_FIELDS = frozenset({DUE_FIELD, TOKEN_FIELD, REASON_FIELD})
RUNNABLE = frozenset({'pending', 'persisted', 'ready'})
CLAIM_SECONDS = 180.0
RETRY_DELAYS = {
    'predecessor': 10.0,
    'claim_busy': 10.0,
    'contention': 10.0,
    'incomplete': 60.0,
    'blocked': 60.0,
    'retry': 60.0,
}


@dataclass(frozen=True)
class Obligation:
    segment_id: str
    revision: int


@dataclass(frozen=True)
class DueObligation:
    key: Obligation
    due_at: float


def due_obligation(segment_id: str, row: dict[str, Any]) -> DueObligation | None:
    due, revision = row.get(DUE_FIELD), row.get('log_sequence')
    if (
        row.get(KIND_FIELD) == KIND
        and type(revision) is int
        and revision > 0
        and isinstance(due, (int, float))
        and not isinstance(due, bool)
        and math.isfinite(due)
    ):
        return DueObligation(Obligation(segment_id, revision), due)
    return None


def holds_claim(row: dict, key: Obligation, token: str, now: float) -> bool:
    due = due_obligation(key.segment_id, row)
    return due is not None and due.key == key and row.get(TOKEN_FIELD) == token and due.due_at > now


def covered(segment_id: str, row: dict) -> bool:
    return (
        row.get('projection_state') in RUNNABLE
        and row.get(REASON_FIELD) != 'legacy'
        and due_obligation(segment_id, row) is not None
    )


def metadata(due, token, reason) -> dict:
    return {DUE_FIELD: due, TOKEN_FIELD: token, REASON_FIELD: reason}


def arm(row: dict, now: float) -> dict:
    # Even with the switch off, invalidate any existing claim if an
    # authoritative writer changes the work underneath it. No new debt is
    # created by an off writer. Legacy discovery still sees every such row.
    if projection_outbox_enabled() and type(row.get('log_sequence')) is int and row['log_sequence'] > 0:
        return {KIND_FIELD: KIND, **metadata(now, None, None)}
    return metadata(None, None, 'legacy') if row.get(KIND_FIELD) == KIND else {}


def validate_batch_patch(table: str, fields: dict[str, Any]) -> None:
    # A result metadata patch can never replace a document, manufacture a
    # receipt, or publish after a privacy fence. It only updates a live row.
    if (table == 'conversations' and set(fields) == {'record_lane_owner'}) or (
        table == 'results' and set(fields) == set(PATCH_FIELDS)
    ):
        return
    raise ValueError('only the conversation route owner or projection scheduling fields may be patched')


def disposition(row: dict) -> str | None:
    state = row.get('projection_state')
    if state in RUNNABLE:
        return None
    if state == 'quarantine_held':
        return 'held'  # The existing hold owner can rearm it; never mark it delivered.
    return state if state in {'completed', 'erased'} else 'legacy'


def followup_due_at(row: dict, now: float) -> float:
    due = row.get(FOLLOWUP_DUE_FIELD) if row.get('projection_state') in FOLLOWUP_STATES else None
    if isinstance(due, (int, float)) and not isinstance(due, bool) and math.isfinite(due):
        return max(now, due)
    return now


def claim(store, key: Obligation, clock) -> str | None:
    token = uuid.uuid4().hex

    def take(tx):
        row = tx.get('results', key.segment_id)
        due = due_obligation(key.segment_id, row)
        now = clock()
        if due is None or due.key != key or due.due_at > now or row.get(REASON_FIELD) == 'legacy':
            return None
        reason = disposition(row)
        if reason is not None:
            tx.patch('results', key.segment_id, metadata(None, None, reason))
            return None
        followup_due = followup_due_at(row, now)
        if followup_due > now:
            tx.patch('results', key.segment_id, metadata(followup_due, None, 'followup_due'))
            return None
        tx.patch('results', key.segment_id, metadata(now + CLAIM_SECONDS, token, 'claimed'))
        return token

    return store.run(take) if projection_outbox_enabled() else None


def settle(store, key: Obligation, token: str, clock, outcome: str) -> str | None:
    def finish(tx):
        row = tx.get('results', key.segment_id)
        now = clock()
        if not holds_claim(row, key, token, now):
            return None
        reason = disposition(row)
        if reason is not None:
            tx.patch('results', key.segment_id, metadata(None, None, reason))
            return reason
        reason = outcome if outcome in RETRY_DELAYS else 'incomplete'
        delay = RETRY_DELAYS[reason]
        if row.get('projection_state') in FOLLOWUP_STATES and reason in {'incomplete', 'blocked', 'retry'}:
            delay = projection_followup_backoff_seconds() or delay
        tx.patch('results', key.segment_id, metadata(max(now + delay, followup_due_at(row, now)), None, reason))
        return reason

    return store.run(finish)
