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
import time
from typing import Any

from google.cloud import firestore

from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_projection import assignment_held_without_recovery
from database.batch_pipeline_shadow_hook import mirror_refresh
from utils.batch_pipeline.scheduler import owner_key
from config.batch_pipeline import projection_hold_recovery_enabled

logger = logging.getLogger(__name__)

# Held rows examined per maintenance pass; the scan wraps at its own pace.
RELEASE_PAGE = 128
RELEASE_TICK_SECONDS = 5.0
MAX_RELEASE_ATTEMPTS = 3


class ProjectionReleaseStore:
    """Operator-free reset of one held unit; every assignment fence still applies."""

    def __init__(self, store):
        self.store = store

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
            and not conversation.get('discarded')
            and conversation.get('status') == 'completed'
            and not conversation.get('uses_custom_stt')
            and conversation.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        )

    def release(self, segment_id: str, now: float) -> bool:
        """Reset one held unit to pending iff its record target was restored."""
        released_owner: list[str] = []

        @firestore.transactional
        def commit(transaction):
            job = self.store.ref('jobs', segment_id).get(transaction=transaction).to_dict() or {}
            entry = self.store.ref('results', segment_id).get(transaction=transaction).to_dict() or {}
            binding = normalized_binding(job['projection_binding']) if job.get('projection_binding') else None
            receipt = entry.get('projection') or {}
            attempts = entry.get('projection_release_attempts', int(entry.get('projection_redriven_at') is not None))
            if (
                binding is None
                or segment_id not in binding.segment_ids
                or job.get('owner_id') != binding.owner_id
                or entry.get('owner_key') != owner_key(binding.owner_id)
                or job.get('recovery_state') != 'held'
                or entry.get('projection_state') != 'quarantine_held'
                or receipt.get('state') != 'quarantined'
                or receipt.get('disposition') != 'ambiguous_generation'
                or (not projection_hold_recovery_enabled() and entry.get('projection_redriven_at') is not None)
                or type(attempts) is not int
                or not 0 <= attempts < MAX_RELEASE_ATTEMPTS
                or entry.get('projection_privacy_refusal')
                or not assignment_held_without_recovery(job, entry)
                or (
                    entry.get('projection_parts')
                    and not any(part.get('state') == 'quarantined' for part in entry['projection_parts'].values())
                )
            ):
                return False
            if not self._target_restorable(transaction, binding):
                return False
            reset: dict[str, Any] = {
                'projection_state': 'pending',
                'projection_redriven_at': now,
                'projection_release_attempts': attempts + 1,
                'projection': {},
                'projection_blocked_since': None,
                'projection_block_type': None,
            }
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
            transaction.update(self.store.ref('jobs', segment_id), {'recovery_state': None})
            released_owner.append(binding.owner_id)
            return True

        released = self.store.run(commit)
        if released:
            try:
                mirror_refresh(
                    self.store.store.namespace,
                    [
                        ('jobs', segment_id),
                        ('results', segment_id),
                        ('owners', owner_key(released_owner[0])),
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


def release_page(store, *, limit: int, after_id: str | None, now: float | None = None, deadline: float | None = None):
    """One bounded page of held rows; returns (counts, next_after)."""
    moment = now if now is not None else time.time()
    counts = {'released': 0, 'waiting': 0, 'error': 0, 'examined': 0}
    limit = max(1, min(limit, RELEASE_PAGE))
    try:
        page = held_page_ids(store.client, store.store.namespace, limit, after_id)
    except Exception as error:
        # A failed fetch must not lose the cursor the pass chain would keep.
        logger.warning(
            'event=batch_projection action=release_held action=fetch outcome=retry exception_type=%s',
            type(error).__name__,
        )
        return counts, after_id
    for segment_id in page:
        counts['examined'] += 1
        try:
            released = ProjectionReleaseStore(store).release(segment_id, moment)
            counts['released' if released else 'waiting'] += 1
        except Exception as error:
            counts['error'] += 1
            logger.warning(
                'event=batch_projection action=release_held outcome=retry exception_type=%s', type(error).__name__
            )
        if deadline is not None and time.monotonic() >= deadline:
            break
    processed = counts['examined']
    next_after = page[processed - 1] if processed and (processed < len(page) or len(page) >= limit) else None
    return counts, next_after
