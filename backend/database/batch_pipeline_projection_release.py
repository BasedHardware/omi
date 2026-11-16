"""Restore redrive: a held record unit re-enters projection when its target returns.

The quarantined receipt is replay-fenced by design, so nothing automatic will
ever re-assign a held unit. This module is the deliberate reset: it verifies the
record-target conflict is really gone (the target conversation is restored, not
merely undiscarded-but-unfinalized) and returns the row to the ordinary pending
state for the next assignment pass. Audio is never touched, and the reset marks
the row ``projection_redriven_at`` so the re-assignment cannot drag the owner
watermark backward onto already-terminal rows.

The reset writes falsy tombstones (empty receipt map, ``None`` stamps) rather
than field deletes: every consumer reads these fields through truthiness, and
tombstones keep the strict Firestore test fixture's sentinel contract intact.
"""

import logging
import math
import time
from typing import Any, TypeGuard

from google.cloud import firestore

from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_projection_finish import projection_finish_state_fields
from database.batch_pipeline_projection import assignment_held_without_recovery, OPERATOR_INTENTS
from database.batch_pipeline_shadow_hook import mirror_refresh
from utils.batch_pipeline.scheduler import owner_key
from config.batch_pipeline import (
    projection_hold_recovery_enabled,
    batch_held_dead_letter_enabled,
    HELD_DEAD_LETTER_SECONDS,
    projection_ghost_settle_enabled,
    projection_ghost_settle_cohort,
    projection_restorable_cap_expiry_enabled,
)
from utils.conversations.fragment_visibility import is_automatic_discard

logger = logging.getLogger(__name__)

# Held rows examined per maintenance pass; the scan wraps at its own pace.
RELEASE_PAGE = 128
RELEASE_TICK_SECONDS = 5.0
MAX_RELEASE_ATTEMPTS = 3
GHOST_SETTLE_MAX_PER_PASS = 16
GHOST_SETTLE_MIN_AGE_SECONDS = 86400
GHOST_SKIP_CLASSES = (
    'hint_changed',
    'receipt_not_ready',
    'part_quarantined',
    'target_not_restorable',
    'privacy',
    'binding',
    'job_held',
    'job_not_committed',
    'invalid_age',
    'young',
    'count_only',
    'cap',
    'expiry_scan',
)
GHOST_AGE_BUCKETS = ('1d', '7d', '30d_plus')


def release_counts() -> dict[str, int]:
    return {
        'released': 0,
        'waiting': 0,
        'error': 0,
        'examined': 0,
        'expired': 0,
        'ghost_settled': 0,
        'ghost_classified': 0,
        **{f'ghost_skipped_{name}': 0 for name in GHOST_SKIP_CLASSES},
        **{f'ghost_age_{name}': 0 for name in GHOST_AGE_BUCKETS},
    }


def ghost_age_bucket(entry, now: float) -> str | None:
    """Committed-age bucket for ghost telemetry; shared by every ghost return path."""
    committed_at = entry.get('committed_at')
    age = now - committed_at if finite_timestamp(now) and finite_timestamp(committed_at) else -1
    return '30d_plus' if age >= 30 * 86400 else '7d' if age >= 7 * 86400 else '1d' if age >= 86400 else None


def ghost_class(entry, job, binding, segment_id: str, now: float) -> str:
    """Classify transaction-fresh hints; eligibility still requires the target fence before settling."""
    if entry.get('projection_state') != 'quarantine_held':
        return 'hint_changed'
    if (entry.get('projection') or {}).get('state') != 'ready':
        return 'receipt_not_ready'
    if any(part.get('state') == 'quarantined' for part in (entry.get('projection_parts') or {}).values()):
        return 'part_quarantined'
    if (
        entry.get('projection_privacy_refusal')
        or (entry.get('projection') or {}).get('privacy_reason') == 'conversation_deleted'
        or any(
            part.get('privacy_reason') == 'conversation_deleted'
            for part in (entry.get('projection_parts') or {}).values()
        )
    ):
        return 'privacy'
    if (
        binding is None
        or not binding.owner_id
        or segment_id not in binding.segment_ids
        or job.get('owner_id') != binding.owner_id
        or entry.get('owner_key') != owner_key(binding.owner_id)
        or entry.get('segment_id') != segment_id
    ):
        return 'binding'
    if job.get('recovery_state') == 'held':
        return 'job_held'
    if job.get('state') != 'committed':
        return 'job_not_committed'
    committed_at = entry.get('committed_at')
    if not finite_timestamp(committed_at) or not finite_timestamp(now):
        return 'invalid_age'
    if now - committed_at < GHOST_SETTLE_MIN_AGE_SECONDS:
        return 'young'
    return 'eligible'


class ProjectionReleaseStore:
    """Operator-free reset of one held unit; every assignment fence still applies."""

    def __init__(self, store, *, ghost_budget: int = GHOST_SETTLE_MAX_PER_PASS):
        self.store = store
        self.expired = False
        self.ghost_budget = max(0, min(ghost_budget, GHOST_SETTLE_MAX_PER_PASS))
        self.ghost_settled = False
        self.ghost_skip: str | None = None
        self.ghost_age: str | None = None

    def _target_restorable(self, transaction, binding) -> bool:
        """Mirror ``replace_record``'s own raises: anything still raising there
        has not actually been restored, and releasing into it would only
        re-hold the unit on the next assignment."""
        target = binding.target_conversation_id
        if not target or (not binding.record_origin and not projection_hold_recovery_enabled()):
            return False
        conversation = (
            self.store.client.collection('users')
            .document(binding.owner_id)
            .collection('conversations')
            .document(target)
            .get(transaction=transaction)
            .to_dict()
            or {}
        )
        return bool(
            conversation
            and (
                not binding.record_origin or conversation.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'}
            )
            and not conversation.get('deleted')
            # A record's batch text supersedes the pipeline's own discard (replace_record).
            and (not conversation.get('discarded') or (binding.record_origin and is_automatic_discard(conversation)))
            and conversation.get('status') == 'completed'
            and not conversation.get('uses_custom_stt')
            and conversation.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        )

    def _expire_assignment(self, transaction, segment_id, entry, now, expired, attempts):
        # Persisted multipart suffixes and privacy holds never expire. Missing
        # anchors get a full window; malformed anchors never authorize expiry.
        if (
            expired
            or entry.get('projection_state') != 'quarantine_held'
            or not batch_held_dead_letter_enabled()
            or not finite_timestamp(now)
        ):
            return None
        deadline = entry.get('held_deadline_at')
        if deadline is None:
            transaction.update(
                self.store.ref('results', segment_id),
                {
                    'held_deadline_at': now + HELD_DEAD_LETTER_SECONDS,
                },
            )
            return 'stamped'
        if not finite_timestamp(deadline) or deadline > now:
            return None
        expiry = {'held_expired_reason': 'held_expired', 'held_expired_at': now}
        if attempts >= MAX_RELEASE_ATTEMPTS:
            expiry.update(held_expired_release_attempts=attempts, projection_release_attempts=0)
        transaction.update(self.store.ref('results', segment_id), expiry)
        return 'expired'

    def release(
        self,
        segment_id: str,
        now: float,
        *,
        dead_before: float | None = None,
        operator: bool = False,
        expected_job=None,
        expected_entry=None,
    ) -> bool:
        """Reset one held unit to pending iff its record target was restored."""
        released_owner: list[str] = []

        @firestore.transactional
        def commit(transaction):
            job = self.store.ref('jobs', segment_id).get(transaction=transaction).to_dict() or {}
            entry = self.store.ref('results', segment_id).get(transaction=transaction).to_dict() or {}
            from utils.batch_pipeline.input_retention import input_expiring

            terminal_input = input_expiring(job)
            if (
                (terminal_input and (not operator or job.get('input_expiring_leg') != 'assignment'))
                or (expected_job is not None and job != expected_job)
                or (expected_entry is not None and entry != expected_entry)
            ):
                return False
            # Re-read the stamp inside each transaction: the other scan leg
            # may already have expired this row and reset its attempt count.
            if (
                dead_before is None
                and not (terminal_input and operator)
                and entry.get('held_expired_at') is not None
                and projection_restorable_cap_expiry_enabled()
            ):
                return False
            binding = normalized_binding(job['projection_binding']) if job.get('projection_binding') else None
            receipt = entry.get('projection') or {}
            # Multipart summaries can remain ambiguous holds after a privacy
            # refusal. Fence every receipt before either expiry path or release.
            if projection_restorable_cap_expiry_enabled() and (
                entry.get('projection_privacy_refusal')
                or receipt.get('privacy_reason')
                or any(part.get('privacy_reason') for part in (entry.get('projection_parts') or {}).values())
            ):
                # Report the refusal with the same ghost classification and age
                # bucket as the gate-failure branch below, so privacy refusals
                # keep counting in ghost_classified and ghost_skipped_*. The tuple
                # is read-only: released, expired and ghost_settled stay false.
                return (ghost_class(entry, job, binding, segment_id, now), ghost_age_bucket(entry, now))
            held_receipt = next(
                (
                    part
                    for part in (
                        [receipt, *(entry.get('projection_parts') or {}).values()]
                        if projection_hold_recovery_enabled()
                        else [receipt]
                    )
                    if part.get('state') == 'quarantined' and part.get('disposition') == 'ambiguous_generation'
                ),
                None,
            )
            expired = entry.get('held_expired_reason') == 'held_expired' and finite_timestamp(
                entry.get('held_expired_at')
            )
            attempts = entry.get('projection_release_attempts', int(entry.get('projection_redriven_at') is not None))
            if (
                binding is None
                or segment_id not in binding.segment_ids
                or job.get('owner_id') != binding.owner_id
                or entry.get('owner_key') != owner_key(binding.owner_id)
                or job.get('recovery_state') != 'held'
                or entry.get('projection_state') not in {'quarantine_held', 'persisted'}
                or (entry.get('projection_state') == 'persisted' and not projection_hold_recovery_enabled())
                or held_receipt is None
                or (not projection_hold_recovery_enabled() and entry.get('projection_redriven_at') is not None)
                or type(attempts) is not int
                or attempts < 0
                or (attempts >= MAX_RELEASE_ATTEMPTS and not batch_held_dead_letter_enabled())
                or entry.get('projection_privacy_refusal')
                or not assignment_held_without_recovery(job, {**entry, 'projection': held_receipt})
                or (
                    entry.get('projection_parts')
                    and not any(part.get('state') == 'quarantined' for part in entry['projection_parts'].values())
                )
            ):
                # Sibling to the real-held gate: a completed receipt with a
                # legacy held hint owes discovery, not expiry or reassignment.
                classification = ghost_class(entry, job, binding, segment_id, now)
                bucket = ghost_age_bucket(entry, now)
                if classification == 'eligible':
                    if dead_before is not None:
                        classification = 'expiry_scan'
                    elif not projection_ghost_settle_enabled():
                        classification = 'count_only'
                    elif not self.ghost_budget:
                        classification = 'cap'
                    elif not self._target_restorable(transaction, binding):
                        classification = 'target_not_restorable'
                    else:
                        cohort, invalid_cohort = projection_ghost_settle_cohort()
                        transaction.update(
                            self.store.ref('results', segment_id),
                            {
                                'projection_state': 'ready',
                                'ghost_settled_cohort': cohort,
                                **projection_finish_state_fields('ready', now),
                            },
                        )
                        return ('ghost_settled', bucket, invalid_cohort)
                    return (classification, bucket)
                # Ready receipts blocked only by recovery/age fences still owe
                # discovery; never stamp or expire them while repair waits.
                # A committed assignment hold can lack the original receipt
                # shape. Retain it with the SAME expiry markers, never release
                # through a failed identity/privacy/operator fence.
                if (
                    classification not in {'privacy', 'job_held', 'young', 'invalid_age'}
                    and binding is not None
                    and segment_id in binding.segment_ids
                    and job.get('owner_id') == binding.owner_id
                    and entry.get('owner_key') == owner_key(binding.owner_id)
                    and entry.get('segment_id') == segment_id
                    and job.get('state') == 'committed'
                    and job.get('recovery_state') == 'held'
                    and not entry.get('projection_privacy_refusal')
                    and not any(
                        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
                        for key in OPERATOR_INTENTS
                    )
                    and type(attempts) is int
                    and attempts >= 0
                    and dead_before is None
                ):
                    outcome = self._expire_assignment(transaction, segment_id, entry, now, expired, attempts)
                    if outcome == 'expired':
                        return outcome
                    if outcome == 'stamped':
                        return False
                return (classification, bucket)
            if dead_before is not None:
                expired_at = entry.get('held_expired_at')
                if not expired or not finite_timestamp(expired_at) or expired_at >= dead_before:
                    return False
            restorable = self._target_restorable(transaction, binding)
            if not restorable:
                if self._expire_assignment(transaction, segment_id, entry, now, expired, attempts) == 'expired':
                    return 'expired'
                return False
            if attempts >= MAX_RELEASE_ATTEMPTS:
                if projection_restorable_cap_expiry_enabled():
                    # Use the same deadline/one-time CAS as unrestorable holds;
                    # any release must wait for a later pass after the reset.
                    return self._expire_assignment(transaction, segment_id, entry, now, expired, attempts)
                return False
            reset: dict[str, Any] = {
                'projection_state': 'pending',
                **projection_finish_state_fields('pending', now),
                'projection_redriven_at': now,
                'projection_release_attempts': attempts + 1,
                'projection': {},
                'projection_blocked_since': None,
                'projection_block_type': None,
            }
            if 'held_deadline_at' in entry and (expired or batch_held_dead_letter_enabled()):
                reset['held_deadline_at'] = None
            if expired:
                reset.update(held_expired_at=None, held_expired_reason=None)
            if entry.get('lineage_quarantine_version') == 1:
                # Old-binaries fence for the held receipt; the receipt is gone.
                reset['protocol_version'] = 1
                reset['lineage_quarantine_version'] = 0
            if projection_hold_recovery_enabled():
                # Old binaries cannot rebuild a summary around preserved
                # multipart suffixes or enforce the new lifecycle fence.
                reset.update(protocol_version=2, projection_release_version=1)
            if entry.get('projection_parts'):
                # Keep proven assignments and their outstanding follow-ups;
                # only held parts may re-enter assignment, in ordinary order.
                reset['projection_parts'] = {
                    index: part
                    for index, part in entry['projection_parts'].items()
                    if part.get('state') != 'quarantined'
                }
            transaction.update(self.store.ref('results', segment_id), reset)
            transaction.update(
                self.store.ref('jobs', segment_id),
                {
                    'recovery_state': None,
                    **({'state': 'committed', 'dead_letter_reason': None} if terminal_input else {}),
                },
            )
            released_owner.append(binding.owner_id)
            return True

        outcome = self.store.run(commit)
        # Publish telemetry only from the committed attempt, never inside the
        # retryable callback. release() keeps its existing real-release bool.
        self.ghost_settled = isinstance(outcome, tuple) and outcome[0] == 'ghost_settled'
        self.ghost_skip = outcome[0] if isinstance(outcome, tuple) and not self.ghost_settled else None
        self.ghost_age = outcome[1] if isinstance(outcome, tuple) else None
        if self.ghost_settled and outcome[2]:
            logger.warning('event=batch_projection_ghost_cohort outcome=invalid_fallback count=1')
        self.expired = outcome == 'expired'
        released = outcome is True
        if released or self.expired or self.ghost_settled:
            try:
                mirror_refresh(
                    self.store.store.namespace,
                    [
                        *([('jobs', segment_id)] if not self.ghost_settled else []),
                        ('results', segment_id),
                        *([('owners', owner_key(released_owner[0]))] if released else []),
                    ],
                )
            except Exception:
                logger.warning('event=jobstore_shadow op=refresh outcome=hook_error site=projection_release')
        return released


def held_page_ids(client: Any, namespace: str, limit: int, after_id: str | None) -> list[str]:
    collection = client.collection(f'{namespace}_results')
    query = (
        collection.where('projection_state', '==', 'quarantine_held')
        .order_by('__name__')
        .limit(max(1, min(limit, RELEASE_PAGE)))
    )
    if after_id is not None:
        query = query.start_after({'__name__': collection.document(after_id)})
    return [document.id for document in query.stream()]


def assignment_held_page_ids(client: Any, namespace: str, limit: int, after_id: str | None) -> list[str]:
    collection = client.collection(f'{namespace}_jobs')
    query = (
        collection.where('state', '==', 'committed')
        .where('recovery_state', '==', 'held')
        .order_by('__name__')
        .limit(max(1, min(limit, RELEASE_PAGE)))
    )
    if after_id is not None:
        query = query.start_after({'__name__': collection.document(after_id)})
    return [document.id for document in query.stream()]


# Instances restart far more often than one scan wraps. Persist the cursor so a
# new instance resumes where the last pass stopped instead of at page one. The
# doc carries no scheduler field, so control-shard queries never select it.
RELEASE_CURSOR_KEY = 'projection_release_cursor'
ASSIGNMENT_RELEASE_CURSOR_KEY = 'projection_assignment_release_cursor'


def load_release_cursor(store, *, key=RELEASE_CURSOR_KEY) -> dict:
    try:
        row = store.ref('control', key).get().to_dict() or {}
    except Exception as error:
        logger.warning(
            'event=batch_projection action=release_held action=cursor_load outcome=retry exception_type=%s',
            type(error).__name__,
        )
        return {'after_id': None}
    after = row.get('after_id')
    return {**row, 'after_id': after if isinstance(after, str) and after else None}


def save_release_cursor(store, after_id: str | None, now: float, *, key=RELEASE_CURSOR_KEY, **extra) -> None:
    @firestore.transactional
    def put(transaction):
        transaction.set(store.ref('control', key), {'after_id': after_id, 'updated_at': now, **extra})

    try:
        store.run(put)
    except Exception as error:
        # Advisory: a lost write only repeats rows the next instance re-checks.
        logger.warning(
            'event=batch_projection action=release_held action=cursor_save outcome=retry exception_type=%s',
            type(error).__name__,
        )


def release_page_settled(
    store,
    *,
    limit: int,
    after_id: str | None,
    now: float | None = None,
    deadline: float | None = None,
    assignment_held: bool = False,
    ghost_budget: int = GHOST_SETTLE_MAX_PER_PASS,
):
    """Return (counts, next_after, settled segment ids)."""
    moment = now if now is not None else time.time()
    counts = release_counts()
    settled = []
    limit = max(1, min(limit, RELEASE_PAGE))
    try:
        page = (
            assignment_held_page_ids(store.client, store.store.namespace, limit, after_id)
            if assignment_held
            else held_page_ids(store.client, store.store.namespace, limit, after_id)
        )
    except Exception as error:
        # A failed fetch must not lose the cursor the pass chain would keep.
        logger.warning(
            'event=batch_projection action=release_held action=fetch outcome=retry exception_type=%s',
            type(error).__name__,
        )
        return counts, after_id, settled
    for segment_id in page:
        counts['examined'] += 1
        try:
            release_store = ProjectionReleaseStore(store, ghost_budget=ghost_budget - counts['ghost_settled'])
            released = release_store.release(segment_id, moment)
            counts[
                (
                    'ghost_settled'
                    if release_store.ghost_settled
                    else 'expired' if release_store.expired else 'released' if released else 'waiting'
                )
            ] += 1
            if release_store.ghost_settled:
                settled.append(segment_id)
            if release_store.ghost_settled or release_store.ghost_skip:
                counts['ghost_classified'] += 1
            if release_store.ghost_skip:
                counts[f'ghost_skipped_{release_store.ghost_skip}'] += 1
            if release_store.ghost_age:
                counts[f'ghost_age_{release_store.ghost_age}'] += 1
        except Exception as error:
            counts['error'] += 1
            logger.warning(
                'event=batch_projection action=release_held outcome=retry exception_type=%s', type(error).__name__
            )
        if deadline is not None and time.monotonic() >= deadline:
            break
    processed = counts['examined']
    next_after = page[processed - 1] if processed and (processed < len(page) or len(page) >= limit) else None
    return counts, next_after, settled


def release_page(*args, **kwargs):
    counts, next_after, _ = release_page_settled(*args, **kwargs)
    return counts, next_after


def release_scan_pass_settled(store, *, limit: int, after_id: str | None, now: float, deadline: float | None = None):
    """Two durable discovery cursors share the existing row and time budgets."""
    start = after_id if after_id is not None else load_release_cursor(store)['after_id']
    limit = max(1, min(limit, RELEASE_PAGE))
    enabled = projection_hold_recovery_enabled()
    assignment = load_release_cursor(store, key=ASSIGNMENT_RELEASE_CURSOR_KEY) if enabled else {}
    assignment_first = assignment.get('next_first', False) is True
    legs = [True, False] if assignment_first else [False, True] if enabled else [False]
    counts = release_counts()
    settled = []
    next_after = start
    for index, is_assignment in enumerate(legs):
        first_limit = max(1, limit // 2)
        page_limit = (first_limit if index == 0 else limit - first_limit) if enabled else limit
        if page_limit <= 0 or (deadline is not None and time.monotonic() >= deadline):
            break
        # Reserve time for the other leg as well as rows. Alternating the first
        # leg durably also covers a single-row budget or one slow transaction.
        page_deadline = deadline
        if index == 0 and enabled and deadline is not None:
            page_deadline = time.monotonic() + max(0, deadline - time.monotonic()) / 2
        cursor = assignment.get('after_id') if is_assignment else start
        page_counts, after, page_settled = release_page_settled(
            store,
            limit=page_limit,
            after_id=cursor,
            now=now,
            deadline=page_deadline,
            assignment_held=is_assignment,
            ghost_budget=GHOST_SETTLE_MAX_PER_PASS - counts['ghost_settled'],
        )
        settled.extend(page_settled)
        for key, value in page_counts.items():
            counts[key] += value
        if is_assignment:
            assignment['after_id'] = after
        else:
            next_after = after
            if page_counts['examined'] or after != start:
                save_release_cursor(store, after, now)
    if enabled:
        save_release_cursor(
            store,
            assignment.get('after_id'),
            now,
            key=ASSIGNMENT_RELEASE_CURSOR_KEY,
            next_first=not assignment_first,
        )
    return counts, next_after, settled


def release_scan_pass(*args, **kwargs):
    counts, next_after, _ = release_scan_pass_settled(*args, **kwargs)
    return counts, next_after


def finite_timestamp(value: Any) -> TypeGuard[int | float]:
    return type(value) in (int, float) and math.isfinite(value)


def expired_page_ids(client, namespace, limit, after_id):
    collection = client.collection(f'{namespace}_results')
    query = (
        collection.where('projection_state', '==', 'quarantine_held')
        .where('held_expired_reason', '==', 'held_expired')
        .order_by('__name__')
    )
    if after_id is not None:
        query = query.start_after({'__name__': collection.document(after_id)})
    return [doc.id for doc in query.limit(max(1, min(limit, RELEASE_PAGE))).stream()]
