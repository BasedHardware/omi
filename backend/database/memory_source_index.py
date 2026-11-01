"""Per-owner historical source index: lets conversation retraction skip the legacy scan.

One content-free document per owner (``users/{uid}/memory_state/historical_source_index``)
holds short hashes of every conversation id that a live historical row references
(``conversation_id`` or a conversation evidence ``source_id``). Conversation
retraction checks it and skips the full dual-keyset scan of ``users/{uid}/memories``
when the donor is absent.

Every write that could add a reference, or move a live row in the scan's keyset
order, holds ``fence``: it bumps ``epoch`` and holds ``writers`` above zero for its
duration (``database/memories.py`` decorators, ``entities.reassign_fact_subject``).
An index is trusted only when ``indexed_epoch == epoch`` and no writer is in flight,
and is stored only under a last-update-time precondition from before its scan. A
writer that dies or fails to release leaves ``writers`` raised; that owner then keeps
the full scan (the pre-index behaviour) until an operator deletes the document,
because no clock can tell a lost release from a long write that is still moving rows.

``MEMORY_HISTORICAL_SOURCE_INDEX=off`` is the kill switch for readers and builders;
writers always bump so re-enabling never trusts a stale index.
"""

import hashlib
import logging
import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, ContextManager, Optional

from google.cloud import firestore
from prometheus_client import Counter

from database._client import get_firestore_client

try:
    from google.api_core.exceptions import AlreadyExists, FailedPrecondition  # type: ignore[reportAssignmentType]
except Exception:  # pragma: no cover - lightweight tests may stub only google.cloud

    class AlreadyExists(Exception):
        pass

    class FailedPrecondition(Exception):
        pass


logger = logging.getLogger(__name__)

ENV = 'MEMORY_HISTORICAL_SOURCE_INDEX'
DOC = 'historical_source_index'
MAX_KEYS = 40_000
_OFF_VALUES = frozenset({'off', 'false', '0', 'no', 'disabled'})

EVENTS = Counter(
    'omi_memory_historical_source_index_events_total',
    'Historical source index: retraction scans skipped or run, index builds, and writer bumps',
    ['event', 'outcome'],
)


def enabled() -> bool:
    return os.environ.get(ENV, '').strip().lower() not in _OFF_VALUES


def source_key(conversation_id: str) -> str:
    return hashlib.sha256(conversation_id.encode()).hexdigest()[:16]


def _db(firestore_client: Any) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _ref(database: Any, uid: str) -> Any:
    return database.collection('users').document(uid).collection('memory_state').document(DOC)


def bump(uid: str, firestore_client: Any, writers: int) -> None:
    _ref(_db(firestore_client), uid).set(
        {'epoch': firestore.Increment(1), 'writers': firestore.Increment(writers)},
        merge=True,
    )


@contextmanager
def fence(uid: str, firestore_client: Any = None) -> Iterator[None]:
    """Hold around a legacy-row write; no such writer may bypass it."""
    # A failed claim aborts the write, so no row can outlive a trusted index
    # that misses it. The release is retried; a lost release fails safe.
    try:
        bump(uid, firestore_client, 1)
    except Exception:
        EVENTS.labels(event='bump', outcome='failed').inc()
        raise
    try:
        yield
    finally:
        for attempt in range(2):
            try:
                bump(uid, firestore_client, -1)
                break
            except Exception:
                if attempt:
                    # ``writers`` stays raised: this owner's retractions scan.
                    EVENTS.labels(event='bump', outcome='release_failed').inc()
                    logger.exception('historical source index writer release failed uid=%s', uid)


class Snapshot:
    """One read of the index document, kept as the precondition for a rebuild."""

    def __init__(
        self, *, exists: bool, update_time: Any, epoch: Any, keys: Optional[frozenset[str]], writers: int = 0
    ) -> None:
        self.exists = exists
        self.update_time = update_time
        self.epoch = epoch
        self.keys = keys
        self.writers = writers

    def excludes(self, conversation_id: str) -> bool:
        """True only when a current index proves no live historical row names the id."""
        return self.keys is not None and source_key(conversation_id) not in self.keys


def read(uid: str, *, firestore_client: Any = None) -> Snapshot:
    snapshot = _ref(_db(firestore_client), uid).get()
    if not getattr(snapshot, 'exists', False):
        return Snapshot(exists=False, update_time=None, epoch=0, keys=None)
    raw: object = snapshot.to_dict()
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}  # type: ignore[reportUnknownVariableType]
    epoch = data.get('epoch', 0)
    raw_writers = data.get('writers', 0)
    # An unreadable counter counts as a writer in flight.
    writers = raw_writers if isinstance(raw_writers, int) and not isinstance(raw_writers, bool) else 1
    keys: Optional[frozenset[str]] = None
    encoded = data.get('keys')
    if isinstance(encoded, str) and data.get('indexed_epoch') == epoch and writers <= 0:
        keys = frozenset(key for key in encoded.split(',') if key)
    return Snapshot(exists=True, update_time=snapshot.update_time, epoch=epoch, keys=keys, writers=writers)


def store(uid: str, observed: Snapshot, conversation_ids: Iterable[str], *, firestore_client: Any = None) -> str:
    """Store the index for a scan that began after ``observed`` was read.

    Returns a bounded outcome. Any writer bump since ``observed`` fails the
    precondition, so the index never claims a scan that missed a later write.
    """
    keys = sorted({source_key(cid) for cid in conversation_ids})
    now = datetime.now(timezone.utc)
    if observed.writers > 0:
        # The scan may have run while that write was moving rows.
        outcome = 'writer_active'
    elif len(keys) > MAX_KEYS:
        outcome = 'too_large'
    else:
        database = _db(firestore_client)
        ref = _ref(database, uid)
        payload = {'keys': ','.join(keys), 'key_count': len(keys), 'built_at': now}
        try:
            if observed.exists:
                # A bump since ``observed`` moves update_time and fails this.
                ref.update(
                    {**payload, 'indexed_epoch': observed.epoch},
                    option=database.write_option(last_update_time=observed.update_time),
                )
            else:
                ref.create({**payload, 'epoch': 0, 'indexed_epoch': 0, 'writers': 0})
            outcome = 'stored'
        except (AlreadyExists, FailedPrecondition):
            outcome = 'raced'
        except Exception:
            logger.exception('historical source index store failed uid=%s', uid)
            outcome = 'failed'
    EVENTS.labels(event='build', outcome=outcome).inc()
    return outcome


def _conversation_sources(record: Any) -> Iterator[str]:
    """Every conversation id ``_names`` can match for this historical record."""
    if isinstance(record.memory.conversation_id, str):
        yield record.memory.conversation_id
    for evidence in record.memory.evidence:
        if evidence.source_type == "conversation" and isinstance(evidence.source_id, str):
            yield evidence.source_id


def _names(record: Any, conversation_id: str) -> bool:
    return record.memory.conversation_id == conversation_id or any(
        evidence.source_type == "conversation" and evidence.source_id == conversation_id
        for evidence in record.memory.evidence
    )


def retraction_historical_ids(
    uid: str,
    conversation_id: str,
    *,
    scan: Callable[[], Sequence[Any]],
    fresh_pages: Callable[[], ContextManager[Any]],
    firestore_client: Any = None,
) -> list[str]:
    """Live historical row ids that name ``conversation_id``.

    ``scan`` is the full live historical scan, which may replay the task memo.
    A scan that rebuilds the index runs inside ``fresh_pages`` so it describes
    rows read after the index's epoch read.
    """
    observed: Optional[Snapshot] = None
    outcome = 'scanned_disabled'
    if enabled():
        try:
            observed = read(uid, firestore_client=firestore_client)
        except Exception:
            logger.warning('historical source index read failed uid=%s', uid, exc_info=True)
            outcome = 'scanned_read_failed'
    if observed is not None and observed.excludes(conversation_id):
        EVENTS.labels(event='retraction_scan', outcome='skipped').inc()
        logger.info('event=memory_retraction_historical_scan outcome=skipped uid=%s', uid)
        return []
    if observed is None:
        records = scan()
    else:
        outcome = 'scanned_match' if observed.keys is not None else 'scanned_unindexed'
        with fresh_pages():
            records = scan()
        store(
            uid,
            observed,
            (source for record in records for source in _conversation_sources(record)),
            firestore_client=firestore_client,
        )
    EVENTS.labels(event='retraction_scan', outcome=outcome).inc()
    logger.info('event=memory_retraction_historical_scan outcome=%s uid=%s rows=%d', outcome, uid, len(records))
    return [record.memory.id for record in records if _names(record, conversation_id)]
