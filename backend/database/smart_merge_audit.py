"""Content-free audit sibling for each smart-merge absorb (``users/{uid}/smart_merge_audit/{donor_id}``).

Written by ``database/smart_merge.absorb_conversation`` inside the absorb
transaction, so it exists exactly when an absorb committed: one sibling per
donor, never on a rejected or already-absorbed replay. It sits outside every
conversation cascade, so deleting the survivor (which purges its donors) keeps
the record that a merge happened; only the account wipe removes it. The
``expire_at`` field is set for a future Firestore TTL policy, which is not
activated.

Content-free means a closed projection of ids, enums and numbers: no
transcript, title, overview, ledger summary, prompt state hash or uid. Every
string must match ``_TOKEN``; a value that does not is a build error and the
audit is skipped rather than written.

Failure semantics (the merge decision never depends on the audit):

- ``CONVERSATION_SMART_MERGE_AUDIT_ENABLED`` off: zero extra reads or writes.
- A live destructive-operation gate (account wipe, memory deletion), a
  malformed gate, or an unreadable gate document: the absorb commits without
  the sibling (``skipped_gate``). The gate is read in the same transaction, so
  a wipe that starts before commit conflicts with it and the retry skips.
- A projection that fails validation: the absorb commits without the sibling
  (``skipped_invalid``).
- A commit failure aborts the whole transaction atomically, audit included,
  exactly like any other absorb commit failure.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from config.conversation_smart_merge import smart_merge_audit_enabled
from database.legal_holds import assert_no_destructive_operation_transaction

AUDIT_COLLECTION = 'smart_merge_audit'
AUDIT_VERSION = 1
RETENTION_DAYS = 60

WRITTEN = 'written'
DISABLED = 'disabled'
SKIPPED_GATE = 'skipped_gate'
SKIPPED_INVALID = 'skipped_invalid'

# Ids, enum values and the model name only: no spaces, so prose cannot pass.
_TOKEN = re.compile(r'^[A-Za-z0-9_.:/\-]{1,128}$')
_DECISION_FLOATS = ('p_same', 'threshold', 'gap_seconds', 'speech_gap_seconds')
_DECISION_TOKENS = ('model', 'question_version', 'mode')


def audit_ref(client: Any, uid: str, donor_id: str) -> Any:
    return client.collection('users').document(uid).collection(AUDIT_COLLECTION).document(donor_id)


def gate_skip(transaction: Any, client: Any, uid: str) -> Optional[str]:
    """Read phase: ``None`` when the sibling may be staged, else the skip outcome.

    One document read when enabled, none when disabled. Must run before the
    transaction's first write.
    """
    if not smart_merge_audit_enabled():
        return DISABLED
    try:
        assert_no_destructive_operation_transaction(transaction, client, uid=uid)
    except Exception:
        # A live or malformed gate, or an unreadable one: never create the sibling.
        return SKIPPED_GATE
    return None


def _token(value: Any) -> str:
    if not isinstance(value, str) or not _TOKEN.match(value):
        raise ValueError('audit value is not a bounded token')
    return value


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('audit value is not a finite number')
    return float(value)


def audit_record(
    *, donor_id: str, survivor_id: str, survivor_state: Mapping[str, Any], donor_update: Mapping[str, Any], source: Any
) -> dict[str, Any]:
    """Closed projection of the committed absorb; raises ``ValueError`` on anything unexpected."""
    marker = donor_update['smart_merge']
    decision = donor_update.get('smart_merge_decision') or {}
    merged_at = marker['merged_at']
    if not isinstance(merged_at, datetime) or merged_at.tzinfo is None:
        raise ValueError('audit merged_at is not an aware datetime')
    revision, fragments = marker['survivor_revision'], survivor_state.get('fragments')
    if isinstance(revision, bool) or not isinstance(revision, int) or not isinstance(fragments, list):
        raise ValueError('audit ledger is malformed')
    stretch = decision.get('stretch_count')
    if isinstance(stretch, bool) or not isinstance(stretch, int):
        raise ValueError('audit stretch_count is malformed')
    record: dict[str, Any] = {
        'version': AUDIT_VERSION,
        'donor_id': _token(donor_id),
        'survivor_id': _token(survivor_id),
        'survivor_revision': revision,
        'ledger_position': len(fragments),
        'source': _token(source),
        'merged_at': merged_at,
        'expire_at': merged_at + timedelta(days=RETENTION_DAYS),
        'stretch_count': stretch,
    }
    record.update({name: _number(decision.get(name)) for name in _DECISION_FLOATS})
    record.update({name: _token(decision.get(name)) for name in _DECISION_TOKENS})
    return record


def stage_audit(
    transaction: Any,
    client: Any,
    uid: str,
    *,
    donor_id: str,
    survivor_id: str,
    survivor_state: Mapping[str, Any],
    donor_update: Mapping[str, Any],
    source: Any,
) -> str:
    """Write phase: stage the sibling in ``transaction``; never raises."""
    try:
        record = audit_record(
            donor_id=donor_id,
            survivor_id=survivor_id,
            survivor_state=survivor_state,
            donor_update=donor_update,
            source=source,
        )
        transaction.set(audit_ref(client, uid, donor_id), record)
    except Exception:
        return SKIPPED_INVALID
    return WRITTEN
