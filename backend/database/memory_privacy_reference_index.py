"""Storage-only reverse references for owner-local privacy history.

Readers stay exhaustive unless explicitly enabled. Historical coverage, retirement
of old writers, stable key generation and index readiness must be proved before
cutover; the historical backfill is intentionally a separate PR.
"""

import hashlib
import hmac
import json
import os
from typing import Any

from google.cloud.firestore import ArrayUnion

PRIVACY_REFERENCE_TOKENS = 'privacy_reference_tokens'
PRIVACY_HISTORY_COLLECTIONS = (
    'memory_operations',
    'memory_commits',
    'memory_outbox',
    'memory_ledger_reopens',
    'jit_trigger_feedback',
    'jit_proactivity_events',
    'jit_proactivity_daily_budgets',
    'memory_source_replacements',
)
PRIVACY_REFERENCE_QUERY_CHUNK_SIZE = 30


def privacy_reference_index_enabled() -> bool:
    return os.getenv('MEMORY_PRIVACY_REFERENCE_INDEX', 'off').strip().lower() == 'on'


def privacy_reference_tokens(uid: str, values: set[str]) -> list[str]:
    secret = (os.getenv('ENCRYPTION_SECRET') or '').encode('utf-8')
    if len(secret) < 32:
        # Off must preserve existing writes in environments without a key. Such
        # rows are incomplete and cannot qualify for the later coverage fence.
        if privacy_reference_index_enabled():
            raise RuntimeError('privacy reference index secret is unavailable')
        return []
    return sorted(
        hmac.new(
            secret,
            json.dumps(['memory-privacy-reference.v1', uid, value], ensure_ascii=True, separators=(',', ':')).encode(),
            hashlib.sha256,
        ).hexdigest()
        for value in values
    )


def privacy_history_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep reference metadata out of predicates and returned logical commits."""
    return {key: value for key, value in payload.items() if key != PRIVACY_REFERENCE_TOKENS}


def with_privacy_reference_tokens(uid: str, payload: dict[str, Any], *, budget: bool = False) -> dict[str, Any]:
    logical = privacy_history_payload(payload)
    leaves: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            leaves.add(value)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(logical)
    planned = logical.get('planned_by_trigger')
    if budget and isinstance(planned, dict):
        leaves.update(key for key in planned if isinstance(key, str))
    return {**logical, PRIVACY_REFERENCE_TOKENS: privacy_reference_tokens(uid, leaves)}


def privacy_reference_patch(uid: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Atomically add updated leaves without losing concurrent references.

    Old tokens are harmless candidates: readers always recheck the payload.
    Full replacements recompute the exact set. No extra document read is needed.
    """
    tokens = with_privacy_reference_tokens(uid, patch)[PRIVACY_REFERENCE_TOKENS]
    return {**patch, PRIVACY_REFERENCE_TOKENS: ArrayUnion(tokens)} if tokens else dict(patch)
