"""Owner cancellation of a legacy (pre-batch) upload whose audio sits in cap holds.

Before batch, an over-allowance sync upload stored its audio as encrypted
``stt_cap_holds`` rows and acknowledged the upload with its legacy job id. The
content ledger row (``dispatch_protocol='stt_cap_hold_v1'``, ``status='held'``)
names that job and every hold, and the paid-only recovery path later
transcribes the holds. ``DELETE /v2/sync-local-files/{job_id}`` with a legacy
handle reaches this module through ``owner_cancel.cancel_owner_upload``.

Same two phases as the batch path:

1. **Fence**: one transaction over the ledger row, every hold it names and the
   held-audio summary. Nothing is written unless every hold is detached from
   recovery: ``held`` or ``retained`` with no live lease. A hold that recovery
   has claimed, completed or handed to batch answers ``in_progress`` and is
   left untouched. Fenced holds become ``owner_cancelled`` (never claimed,
   listed, redriven or summed), the summary drops their seconds, and the ledger
   becomes ``owner_cancelled``.
2. **Erase**: idempotent and retryable. Each fenced hold's audio and metadata
   objects and its row, then the upload's unlinked private-cloud originals.

A recovery that already transcribed the content answers ``already_processed``.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, Protocol

from database.sync_ledger import (
    LEDGER_RETENTION_DAYS,
    is_valid_completed_sync_content_result,
    sync_content_reference,
)
from database.sync_cap_holds import PROTOCOL as HOLD_PROTOCOL
from utils.batch_pipeline.cap_hold_admission import held_content_id
from utils.batch_pipeline.owner_cancel import CancelResult, Outcome, conversation_ids
from utils.sync import cap_hold
from utils.sync.stage import collection_name

logger = logging.getLogger(__name__)

LEDGER_STATUS = 'owner_cancelled'
FENCED_HOLD_STATE = cap_hold.OWNER_CANCELLED_STATE
# Detached from recovery once no lease is live: waiting on credits, or terminal-retained audio.
DETACHED_HOLD_STATES = frozenset({'held', 'retained'})
# Audio already gone: a v4 tombstone. A missing row is gone too.
ERASED_HOLD_STATES = frozenset({'purged'})


class LegacyStore(Protocol):
    def find_content(self, uid: str, job_id: str) -> str | None:
        """The one ledger row this owner's legacy job names, or None. The fence re-proves it."""

    def run(self, fn: Callable[[Any], Any]) -> Any:
        """Run ``fn(tx)`` atomically; ``tx.get(kind, uid, key)`` / ``tx.put(kind, uid, key, row)``."""


class LegacyEraser(Protocol):
    def erase_hold(self, uid: str, hold_id: str) -> None:
        """Erase one fenced hold's objects and row; a no-op when absent. Raises on failure."""

    def erase_archives(self, uid: str, job_id: str, paths: tuple[str, ...]) -> None:
        """Erase the upload's unlinked private-cloud originals. Raises on failure."""


def is_legacy_handle(job_id: str) -> bool:
    return 0 < len(job_id) <= 128 and '/' not in job_id and not job_id.startswith('bp_')


def is_owner_cancelled_hold(row: dict) -> bool:
    return row.get('state') == FENCED_HOLD_STATE and row.get('owner_cancelled_at') is not None


def _detached(row: dict, now: float) -> bool:
    return row.get('state') in DETACHED_HOLD_STATES and float(row.get('lease_until') or 0) <= now


def _fence(tx: Any, uid: str, job_id: str, content_id: str, now: float) -> tuple[CancelResult, tuple[str, ...]]:
    ledger = tx.get('ledger', uid, content_id)
    if not ledger or ledger.get('job_id') != job_id:
        return CancelResult(Outcome.NOT_FOUND), ()
    hold_ids = tuple(sorted({h for h in ledger.get('cap_hold_ids') or () if isinstance(h, str) and h}))
    if ledger.get('status') == LEDGER_STATUS:
        erased = ledger.get('owner_cancel_erased_at') is not None
        paths = tuple(ledger.get('raw_capture_paths') or ()) if not erased else ()
        return (
            CancelResult(Outcome.CANCELLED, erasure='complete' if erased else 'pending', archive_paths=paths),
            hold_ids,
        )
    if ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(ledger.get('result')):
        return CancelResult(Outcome.ALREADY_PROCESSED, conversation_ids(ledger.get('result'))), ()
    if ledger.get('dispatch_protocol') != HOLD_PROTOCOL or ledger.get('status') != 'held':
        return CancelResult(Outcome.NOT_CANCELLABLE), ()
    # Every read precedes every write (Firestore transaction rule).
    holds = {hold_id: tx.get('hold', uid, hold_id) for hold_id in hold_ids}
    summary = tx.get('summary', uid, 'current')
    fenced: dict[str, dict] = {}
    for hold_id, row in holds.items():
        if not row or row.get('state') in ERASED_HOLD_STATES or is_owner_cancelled_hold(row):
            continue
        if not _detached(row, now):
            return CancelResult(Outcome.IN_PROGRESS), ()
        fenced[hold_id] = row
    if not fenced:
        processed_ids = set()
        processed = False
        for hold_id in hold_ids:
            handoff = tx.get('ledger', uid, held_content_id(uid, hold_id))
            if handoff.get('status') == 'completed' and is_valid_completed_sync_content_result(handoff.get('result')):
                processed = True
                processed_ids.update(conversation_ids(handoff.get('result')))
        if processed:
            return CancelResult(Outcome.ALREADY_PROCESSED, tuple(sorted(processed_ids))), ()
        return CancelResult(Outcome.NOT_CANCELLABLE), ()
    delta_seconds, delta_count = 0.0, 0
    for hold_id, row in fenced.items():
        remaining = cap_hold.remaining_seconds(row)
        delta_seconds -= remaining
        delta_count -= int(remaining > 0)
        tx.put(
            'hold',
            uid,
            hold_id,
            {
                **row,
                'state': FENCED_HOLD_STATE,
                'failed_reconciliation': False,
                'lease_until': 0,
                'lease_token': '',
                'next_attempt_at': cap_hold.RETAINED_NEXT_ATTEMPT_AT,
                'owner_cancelled_at': now,
                'owner_cancelled_from': row.get('state'),
            },
        )
    # A summary mid-rebuild (not version 2) recounts rows, and fenced rows count zero.
    if (delta_seconds or delta_count) and summary.get('version') == 2:
        tx.put('summary', uid, 'current', cap_hold.summary_after(summary, delta_seconds, delta_count))
    updated = datetime.fromtimestamp(now, timezone.utc)
    ledger.pop('expires_at', None)
    tx.put(
        'ledger',
        uid,
        content_id,
        {
            **ledger,
            'status': LEDGER_STATUS,
            'pending_cap_hold_ids': [],
            'owner_cancelled_at': now,
            'updated_at': updated,
        },
    )
    paths = tuple(ledger.get('raw_capture_paths') or ())
    return CancelResult(Outcome.CANCELLED, erasure='pending', archive_paths=paths), hold_ids


def _mark_erased(tx: Any, uid: str, job_id: str, content_id: str, now: float) -> None:
    ledger = tx.get('ledger', uid, content_id)
    if ledger.get('job_id') != job_id or ledger.get('status') != LEDGER_STATUS:
        raise RuntimeError('legacy owner cancellation fence missing')
    if ledger.get('owner_cancel_erased_at') is not None:
        return
    expires = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS)
    ledger.pop('raw_capture_paths', None)
    tx.put('ledger', uid, content_id, {**ledger, 'owner_cancel_erased_at': now, 'expires_at': expires})


def cancel_legacy_upload(
    uid: str, job_id: str, *, store: LegacyStore, eraser: LegacyEraser, now: float
) -> CancelResult:
    content_id = store.find_content(uid, job_id)
    if content_id is None:
        return CancelResult(Outcome.NOT_FOUND)
    result, hold_ids = store.run(lambda tx: _fence(tx, uid, job_id, content_id, now))
    if result.outcome is not Outcome.CANCELLED or result.erasure == 'complete':
        logger.info('event=sync_owner_cancel lane=legacy outcome=%s erasure=%s', result.outcome.value, result.erasure)
        return result
    try:
        for hold_id in hold_ids:
            eraser.erase_hold(uid, hold_id)
        eraser.erase_archives(uid, job_id, result.archive_paths)
        store.run(lambda tx: _mark_erased(tx, uid, job_id, content_id, now))
    except Exception as error:  # The fence holds; the owner's next call resumes erasure.
        logger.warning(
            'event=sync_owner_cancel lane=legacy outcome=cancelled erasure=pending exception_type=%s',
            type(error).__name__,
        )
        return CancelResult(Outcome.CANCELLED, erasure='pending')
    logger.info('event=sync_owner_cancel lane=legacy outcome=cancelled erasure=complete holds=%d', len(hold_ids))
    return CancelResult(Outcome.CANCELLED, erasure='complete')


# --- production adapters ------------------------------------------------------


class _FirestoreTx:
    def __init__(self, client: Any, transaction: Any):
        self.client = client
        self.transaction = transaction

    def _reference(self, kind: str, uid: str, key: str) -> Any:
        if kind == 'ledger':
            return sync_content_reference(self.client, uid, key)
        user = self.client.collection('users').document(uid)
        if kind == 'hold':
            return user.collection(cap_hold.COLLECTION).document(key)
        if kind == 'summary':
            return user.collection(cap_hold.SUMMARY_COLLECTION).document(key)
        raise ValueError(f'unknown legacy cancel row kind: {kind}')

    def get(self, kind: str, uid: str, key: str) -> dict:
        snapshot = self._reference(kind, uid, key).get(transaction=self.transaction)
        return (snapshot.to_dict() or {}) if snapshot.exists else {}

    def put(self, kind: str, uid: str, key: str, row: dict) -> None:
        self.transaction.set(self._reference(kind, uid, key), row)


def find_legacy_content(uid: str, job_id: str, client: Any = None) -> str | None:
    """The owner's one ledger row naming this legacy job (the legacy status read's query)."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    client = client if client is not None else cap_hold.get_firestore_client()
    candidates = list(
        client.collection('users')
        .document(uid)
        .collection(collection_name('sync_content_ledger'))
        .where(filter=FieldFilter('job_id', '==', job_id))
        .select(())
        .limit(2)
        .stream()
    )
    return candidates[0].id if len(candidates) == 1 else None


class FirestoreLegacyStore:
    """Holds and their ledger rows share one client so a single transaction fences both."""

    def __init__(self, client: Any = None):
        self._client = client

    @property
    def client(self) -> Any:
        return self._client if self._client is not None else cap_hold.get_firestore_client()

    def find_content(self, uid: str, job_id: str) -> str | None:
        return find_legacy_content(uid, job_id, client=self.client)

    def run(self, fn: Callable[[Any], Any]) -> Any:
        from google.cloud import firestore

        client = self.client

        @firestore.transactional
        def commit(transaction: Any) -> Any:
            return fn(_FirestoreTx(client, transaction))

        return commit(client.transaction())


class HoldNotFenced(RuntimeError):
    """The hold changed after the cancel; nothing is erased."""


class FirestoreLegacyEraser:
    """Cap-hold half of ``owner_cancel_erase.FirestoreEraser``."""

    def erase_hold(self, uid: str, hold_id: str) -> None:
        from utils.sync import cap_hold_erasure

        snapshot = cap_hold.holds(uid).document(hold_id).get()
        if not snapshot.exists:
            return
        row = snapshot.to_dict() or {}
        if row.get('state') in ERASED_HOLD_STATES:
            return
        if not is_owner_cancelled_hold(row):
            raise HoldNotFenced('hold is not fenced by owner cancellation')
        # Nothing reopens an owner_cancelled hold: claim, listing and redrive all exclude it.
        cap_hold_erasure.erase(uid, snapshot, row)
