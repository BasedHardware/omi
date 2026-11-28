"""Forced first-week attempt at close (SCA-4806).

The one part of the first-week guarantee that overrides a deliberate cost
policy. In the last ``FIRST_WEEK_CLOSE_RESERVE_HOURS`` of a stored window, a
conversation whose summary obligation is refused or parked for a **capacity**
reason is revived exactly once and admitted from the reserved first-week lane,
under its own per-tick admission limit. Everything else stays ``no_attempt``:
privacy, user-chosen local-only, on-device processing, lifecycle, manual edits,
empty-output exhaustion, short clips and batch/Go-owned generation. An open,
queued or leased row is never touched: that row is already in a lane, and
forcing it would pay twice for the same summary.

Why this is its own module, not a flag branch inside the close-out: the
close-out counts outcomes and must stay a pure read-write of the outcome stamp;
this path writes the outbox custody row. Keeping them separate keeps the
counter auditable when the forced path is off.

The flag ships **off**. Off is the rollback: the close-out keeps counting
``no_attempt`` and no row is revived.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Any, Callable, Mapping

from google.cloud import firestore

from config.summary_guarantee import (
    first_week_close_reserve_seconds,
    first_week_forced_admission_limit,
    first_week_forced_close_enabled,
    first_week_open,
)
from database._client import get_firestore_client
from models.finalization_owner import python_owns_finalization
from utils.conversations.summary_delivery import (
    EMPTY_BLOCKED_REASONS,
    projection_owns_finalization,
)
from utils.enrichment import age_gate, outbox

logger = logging.getLogger(__name__)

FORCED_AT_FIELD = 'first_week_forced_at'
FORCED_POLICY_FIELD = 'first_week_forced_policy'
FORCED_POLICY_ID = 'first_week_forced_close.v1'
OUTCOME_FIELD = 'first_week_outcome'
RESERVE_PAGE_LIMIT = 25

CONVERSATION_FIELDS = (
    'deleted',
    'discarded',
    'status',
    'data_protection_level',
    'processing_state',
    'processing_deferred',
    'terminal_no_derived_effects',
    'deferred',
    'client_processing',
    'user_title',
    'user_overview',
    'summary_blocked_reason',
    'summary_empty_failures',
    'summary_completed_at',
    'summary_output_present',
    'first_week_summary',
    'first_week_outcome',
    'finalization_engine',
    'finalization_owner_epoch',
    'finalization_status',
    'finalization_job_id',
    'finalization_revision',
    'record_lane_owner',
    'record_projection_revision',
    'summary_projection_finalization',
)


def _client_processing(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, Mapping):
        return any(item is not None for item in value.values())
    return True


def _budget_waiting(row: Mapping[str, Any]) -> bool:
    """The stored writer marker, not the flattened ``local_only`` refusal.

    ``_store_budget_waiting`` stamps both fields and clears ``deferred``. A row
    that also carries a user-choice marker is refused before this check.
    """
    return bool(row.get('processing_deferred')) and bool(row.get('terminal_no_derived_effects'))


def never_force(conversation: Mapping[str, Any], *, now: float) -> str | None:
    """Why this conversation may not be forced at all, or ``None`` when it may.

    Precedence mirrors ``summary_delivery._refusal``. Privacy, the user-chosen
    local-only family, lifecycle, manual edits, empty-output exhaustion, short
    clips and batch/Go-owned generation are terminal here: they stay
    ``no_attempt`` and are counted, never retried.
    """
    if conversation.get('first_week_outcome') is not None:
        return 'already_closed'
    if not first_week_open(conversation, now=now):
        return 'window_closed'
    if conversation.get('deleted') or conversation.get('discarded'):
        return 'lifecycle'
    if conversation.get('status') not in (None, 'completed') and not conversation.get('deferred'):
        return 'lifecycle'
    if conversation.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        return 'privacy'
    if conversation.get('processing_state') == 'local_pending':
        return 'local_only'
    if _client_processing(conversation.get('client_processing')):
        return 'local_only'
    if conversation.get('user_title') is not None or conversation.get('user_overview') is not None:
        return 'manual'
    if conversation.get('summary_blocked_reason') in EMPTY_BLOCKED_REASONS:
        return 'attempt_failed'
    if isinstance(conversation.get('summary_empty_failures'), (int, float)) and not isinstance(
        conversation.get('summary_empty_failures'), bool
    ):
        if conversation['summary_empty_failures'] > 0:
            return 'attempt_failed'
    if conversation.get('summary_blocked_reason') == 'content_below_floor':
        return 'content_below_floor'
    if not python_owns_finalization(conversation):
        return 'generation_owned'
    if conversation.get('finalization_status') == 'blocked_byok':
        return 'generation_owned'
    if conversation.get('finalization_job_id') and not projection_owns_finalization(dict(conversation)):
        return 'generation_owned'
    if conversation.get('summary_completed_at') or conversation.get('summary_output_present'):
        return 'already_summarized'
    # Desktop capture deferral is out of scope by ruling: the capture may not be
    # available yet, and the census found no such first-week row.
    if conversation.get('deferred'):
        return 'deferred_out_of_scope'
    return None


def _parked(row: Mapping[str, Any]) -> bool:
    """Exactly the one-way 72 h park this pass exists to reverse."""
    return age_gate.parked(row)


def custody_refusal(conversation: Mapping[str, Any], row: Mapping[str, Any] | None, *, now: float) -> str | None:
    """Why this obligation may not be revived, or ``None`` when it may.

    A parked row is always out of any lane, so a capacity park may be revived.
    An **open** row is only revived when the conversation carries the stored
    budget refusal: that row is being refused at every delivery, not generating.
    An open row with no such marker is the late-delivery class PR1 owns, and
    forcing it would pay twice for the same summary. A leased row is in flight
    and is never touched.
    """
    if row is None:
        return 'no_obligation_row'
    if row.get(FORCED_AT_FIELD) is not None:
        return 'already_forced'
    if float(row.get('lease_until') or 0) > now:
        return 'leased'
    if not isinstance(row.get('task_token'), str) or not row['task_token']:
        return 'unfenced'
    if row.get('summary_blocked_reason') or row.get('summary_seen'):
        return 'blocked'
    if row.get('dormant') is True:
        # Dormant for a custody reason (merge/sync hold, ownership park) is not
        # a capacity park; reviving it would break custody.
        return None if _parked(row) else 'custody_hold'
    if not _budget_waiting(conversation):
        return 'row_open'
    return None


def _split_path(path: str) -> tuple[str, str] | None:
    parts = path.split('/')
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations':
        return None
    if not parts[1] or not parts[3]:
        return None
    return parts[1], parts[3]


def force_one(
    conversation_ref: Any,
    *,
    now: float,
    client: Any,
    wake: Callable[[dict[str, Any]], None] = outbox.wake_row,
) -> tuple[str, dict[str, Any] | None]:
    """Revive one parked capacity row inside the window, exactly once.

    Returns ``(disposition, pending_row)``. The transaction re-reads both the
    conversation and the outbox row, so a summary that lands, a lease that is
    taken, or a window that closes between the scan and the write all win.
    """
    identity = _split_path(getattr(conversation_ref, 'path', ''))
    if identity is None:
        return 'invalid_identity', None
    uid, conversation_id = identity
    row_id = outbox.key(uid, conversation_id)
    row_ref = client.collection(outbox.COLLECTION).document(row_id)
    decision: list[tuple[str, dict[str, Any] | None]] = []

    @firestore.transactional
    def commit(transaction: Any) -> None:
        decision.clear()
        snapshot = conversation_ref.get(transaction=transaction, field_paths=list(CONVERSATION_FIELDS))
        if not snapshot.exists:
            decision.append(('conversation_missing', None))
            return
        conversation = snapshot.to_dict() or {}
        row_snapshot = row_ref.get(transaction=transaction)
        row = row_snapshot.to_dict() if row_snapshot.exists else None
        if row is None:
            decision.append(('no_obligation_row', None))
            return
        if row.get(FORCED_AT_FIELD) is not None:
            decision.append(('already_forced', None))
            return
        if row.get('uid') != uid or row.get('conversation_id') != conversation_id:
            decision.append(('identity_changed', None))
            return
        for reason in (never_force(conversation, now=now), custody_refusal(conversation, row, now=now)):
            if reason:
                decision.append((reason, None))
                return
        pending = dict(row)
        pending.pop('deferred_since', None)
        pending.update(
            document_id=row_id,
            age_gate_parked=False,
            deferred_reason=None,
            dormant=False,
            due_at=now,
            task_due_at=now,
            task_token=uuid.uuid4().hex,
            lease_until=0,
            owner=None,
            wake_check_after=0,
            first_week_summary=conversation.get('first_week_summary'),
            dispatch=outbox.dispatch_binding(first_week=True) or row.get('dispatch'),
        )
        pending[FORCED_AT_FIELD] = now
        pending[FORCED_POLICY_FIELD] = FORCED_POLICY_ID
        if not outbox.valid_dispatch_binding(pending.get('dispatch')):
            decision.append(('unbound', None))
            return
        transaction.set(row_ref, pending)
        decision.append(('forced', pending))

    commit(client.transaction())
    disposition, pending = decision[0] if decision else ('unknown', None)
    if disposition != 'forced' or pending is None:
        return disposition, None
    try:
        wake(pending)
    except Exception:
        # The row keeps due_at=now and a valid binding, so the normal sweep
        # re-wakes it; no obligation is lost.
        logger.warning('event=first_week_forced_close outcome=wake_error')
        return 'wake_error', pending
    logger.info('event=first_week_forced_close outcome=forced')
    return 'forced', pending


CURSOR_DOCUMENT = 'maintenance/first_week_forced_close_v1'


def _cursor(value: Any) -> dict[str, Any] | None:
    """A usable stored bookmark, or None when the document is absent/malformed."""
    if not isinstance(value, Mapping):
        return None
    end, path = value.get('window_end'), value.get('path')
    if isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end):
        return None
    parts = path.split('/') if isinstance(path, str) else []
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations' or not parts[1] or not parts[3]:
        return None
    return {'window_end': float(end), 'path': path}


def _snapshot_cursor(snapshot: Any) -> dict[str, Any] | None:
    row = snapshot.to_dict() or {}
    stamp = row.get('first_week_summary')
    end = stamp.get('window_end_at') if isinstance(stamp, Mapping) else None
    path = getattr(getattr(snapshot, 'reference', None), 'path', None)
    return _cursor({'window_end': end, 'path': path})


def _read_cursor(client: Any) -> dict[str, Any] | None:
    """Read the rotation bookmark; a read failure restarts from the earliest window."""
    try:
        snapshot = client.document(CURSOR_DOCUMENT).get()
        return _cursor((snapshot.to_dict() or {}).get('after'))
    except Exception as error:
        logger.warning(
            'event=first_week_forced_close outcome=cursor_read_error exception_type=%s', type(error).__name__
        )
        return None


def _write_cursor(client: Any, after: dict[str, Any] | None, *, now: float) -> None:
    """Persist the rotation bookmark; a lost write repeats a page, never skips one."""
    try:
        client.document(CURSOR_DOCUMENT).set({'after': after, 'updated_at': now}, merge=True)
    except Exception as error:
        logger.warning(
            'event=first_week_forced_close outcome=cursor_write_error exception_type=%s', type(error).__name__
        )


def tick(
    *,
    now: float | None = None,
    client: Any | None = None,
    limit: int | None = None,
    wake: Callable[[dict[str, Any]], None] = outbox.wake_row,
) -> dict[str, int]:
    """Force at most the per-tick admissions from one rotating reserve page.

    The page is a keyset rotation, not a fixed prefix: the bookmark advances past
    every examined row and wraps to the earliest window when the page is
    exhausted. An already-forced, non-forceable, leased or already-counted row is
    therefore examined once per rotation and cannot pin the page, so a forceable
    row behind it is still reached before its window closes.
    """
    counts = {'examined': 0, 'forced': 0, 'skipped': 0, 'errors': 0, 'disabled': 0}
    if not first_week_forced_close_enabled():
        counts['disabled'] = 1
        return counts
    reserve = first_week_close_reserve_seconds()
    if reserve <= 0:
        counts['disabled'] = 1
        return counts
    from database.first_week_queries import approaching_first_week_conversations

    bound = client or get_firestore_client()
    current = time.time() if now is None else now
    admission = first_week_forced_admission_limit()
    page_limit = max(admission, min(RESERVE_PAGE_LIMIT, limit or RESERVE_PAGE_LIMIT))

    def page_after(after: dict[str, Any] | None) -> list[Any]:
        return approaching_first_week_conversations(
            now=current, until=current + reserve, limit=page_limit, after=after, firestore_client=bound
        )

    cursor = _read_cursor(bound)
    try:
        page = page_after(cursor)
        if not page and cursor is not None:
            # The rotation reached the end: wrap to the earliest remaining window.
            page = page_after(None)
    except Exception as error:
        counts['errors'] += 1
        logger.warning('event=first_week_forced_close outcome=query_error exception_type=%s', type(error).__name__)
        return counts
    counts['examined'] = len(page)
    last = None
    for snapshot in page:
        if counts['forced'] >= admission:
            break
        last = snapshot
        try:
            disposition, _pending = force_one(snapshot.reference, now=current, client=bound, wake=wake)
        except Exception as error:
            counts['errors'] += 1
            logger.warning('event=first_week_forced_close outcome=error exception_type=%s', type(error).__name__)
            continue
        if disposition == 'forced':
            counts['forced'] += 1
        elif disposition == 'wake_error':
            counts['forced'] += 1
            counts['errors'] += 1
        else:
            counts['skipped'] += 1
    # A full page resumes after its last row; a short or absent page starts the
    # next rotation at the earliest window.
    _write_cursor(bound, _snapshot_cursor(last) if last is not None and len(page) >= page_limit else None, now=current)
    return counts
