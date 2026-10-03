"""Content-free audit sibling for each smart-merge absorb (``users/{uid}/smart_merge_audit/{donor_id}``).

Written by ``database/smart_merge.absorb_conversation`` inside the absorb
transaction, so it is created only when an absorb committed: one sibling per
donor, never on a rejected or already-absorbed replay. It sits outside every
conversation cascade, so deleting the survivor (which purges its donors) keeps
the record that a merge happened; only the account wipe removes it. The
``expire_at`` field is set for a future Firestore TTL policy, which is not
activated.

Content-free means a closed projection of ids, enums and numbers: no
transcript, title, overview, ledger summary, prompt state hash or uid. Every
identifier must be a bounded, slash-free token; source, model, question version
and mode must match server-known values. Identifiers remain user-scoped metadata,
not anonymized data. Invalid projections are skipped rather than written.

Failure semantics (the merge decision never depends on the audit):

- ``CONVERSATION_SMART_MERGE_AUDIT_ENABLED`` off: zero extra reads or writes.
- A durable account-deletion marker, live destructive-operation gate, or
  malformed authority: absorb without the sibling (``skipped_gate``). Both
  authority documents are read in the transaction. The durable marker keeps
  blocking after a failed/completed wipe or a stale gate.
- An authority RPC or audit staging error: roll back, then re-read and re-plan
  in a fresh transaction with no audit I/O (``skipped_error``). A failed read
  can leave its transaction unusable; never continue on that transaction.
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

from config.conversation_smart_merge import (
    ELIGIBLE_SOURCES,
    QUESTION_VERSION,
    SmartMergeMode,
    smart_merge_audit_enabled,
)
from config.jev_decisions import JEV_MODEL
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.legal_holds import (
    DestructiveOperationInProgress,
    LegalHoldAuthorityUnavailable,
    assert_no_destructive_operation_transaction,
)

AUDIT_COLLECTION = 'smart_merge_audit'
AUDIT_VERSION = 1
RETENTION_DAYS = 60

WRITTEN = 'written'
DISABLED = 'disabled'
SKIPPED_GATE = 'skipped_gate'
SKIPPED_INVALID = 'skipped_invalid'
SKIPPED_ERROR = 'skipped_error'

# Identifiers only; enums use exact server-known values, including the model's slash.
_TOKEN = re.compile(r'[A-Za-z0-9_.:\-]{1,128}')
_DECISION_FLOATS = ('p_same', 'threshold', 'gap_seconds', 'speech_gap_seconds')
_DECISION_ENUMS = {'model': JEV_MODEL, 'question_version': QUESTION_VERSION, 'mode': SmartMergeMode.MERGE.value}


class AuditUnavailable(RuntimeError):
    """Audit I/O failed; roll back before retrying the absorb without an audit."""


def audit_ref(client: Any, uid: str, donor_id: str) -> Any:
    return client.collection('users').document(uid).collection(AUDIT_COLLECTION).document(donor_id)


def gate_skip(transaction: Any, client: Any, uid: str) -> Optional[str]:
    """Read phase: ``None`` when the sibling may be staged, else the skip outcome.

    Two document reads when enabled, none when disabled. Must run before the
    transaction's first write.
    """
    if not smart_merge_audit_enabled():
        return DISABLED
    try:
        snapshot = client.collection('account_deletions').document(uid).get(transaction=transaction)
        payload = snapshot.to_dict() or {}
        status = normalize_account_deletion_status(
            marker_exists=snapshot.exists,
            raw_status=payload.get('wipe_status') if isinstance(payload, Mapping) else None,
        )
        if account_deletion_blocks_access(status):
            return SKIPPED_GATE
    except Exception as error:
        raise AuditUnavailable('account deletion audit fence read failed') from error
    try:
        assert_no_destructive_operation_transaction(transaction, client, uid=uid)
    except (DestructiveOperationInProgress, LegalHoldAuthorityUnavailable):
        # These are validation failures after a successful read, with no RPC failure.
        return SKIPPED_GATE
    except Exception as error:
        raise AuditUnavailable('destructive operation audit fence read failed') from error
    return None


def _token(value: Any) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value) or value in {'.', '..'}:
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
    if source not in ELIGIBLE_SOURCES:
        raise ValueError('audit source is not eligible')
    for name, expected in _DECISION_ENUMS.items():
        if decision.get(name) != expected:
            raise ValueError('audit decision enum is unsupported')
    record: dict[str, Any] = {
        'version': AUDIT_VERSION,
        'donor_id': _token(donor_id),
        'survivor_id': _token(survivor_id),
        'survivor_revision': revision,
        'ledger_position': len(fragments),
        'source': source,
        'merged_at': merged_at,
        'expire_at': merged_at + timedelta(days=RETENTION_DAYS),
        'stretch_count': stretch,
    }
    if 'flattened_ancestor_count' in marker:
        flattened = marker['flattened_ancestor_count']
        if isinstance(flattened, bool) or not isinstance(flattened, int) or not 0 <= flattened <= 11:
            raise ValueError('audit flattened_ancestor_count is out of bounds')
        record['flattened_ancestor_count'] = flattened
    record.update({name: _number(decision.get(name)) for name in _DECISION_FLOATS})
    record.update(_DECISION_ENUMS)
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
    """Validate before staging; an I/O failure must roll back the transaction."""
    try:
        record = audit_record(
            donor_id=donor_id,
            survivor_id=survivor_id,
            survivor_state=survivor_state,
            donor_update=donor_update,
            source=source,
        )
    except Exception:
        return SKIPPED_INVALID
    try:
        transaction.set(audit_ref(client, uid, donor_id), record)
    except Exception as error:
        raise AuditUnavailable('audit staging failed') from error
    return WRITTEN
