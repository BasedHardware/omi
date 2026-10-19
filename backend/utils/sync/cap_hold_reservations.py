"""Funded-capacity reservations for cap-held audio handed to batch (lane 6; Subscription ruling 10-19).

Legacy recovery debits the ladder budget synchronously when it transcribes a held piece. A hold handed to
batch admission is debited only when projection commits its usage, so the backlog worker would otherwise
check the next candidate against stale capacity. Each hand-off therefore reserves the hold's units (the
worker's own ``_candidate`` units) until the batch outcome is known:

- projected: projection committed ``transcription_seconds`` atomically with the content ledger, so the
  reservation is dropped. The usage is already visible before the reservation goes, so the two briefly
  both count (conservative, never over-admits); there is never a moment where neither counts;
- failed (every unit terminally quarantined) or abandoned (no intake): released, nothing was debited;
- still pending after ``STALE_SECONDS``: kept and still counted (slow is not lost; a lost job reads as
  abandoned), marked stale once with an error log and ``outcome=stale`` so it is alerted on.

Only reservations made in the current funded period reduce capacity: a previous month's reservation never
shrinks the new month. One document per owner holds a small map; the backlog job lease serializes its
writers, and every write is a read-modify-write transaction.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Callable

from google.cloud import firestore
from prometheus_client import Counter

from database._client import get_data_plane_firestore_client as get_firestore_client
from database.batch_pipeline_store import FirestoreStore
from database.legal_holds import external_write_fence
from utils.sync.stage import current_stage

COLLECTION = 'stt_cap_hold_reservations'
DOCUMENT = 'current'
STALE_SECONDS = 6 * 3600  # alert threshold only; a pending reservation is never released by age
PRUNE_SECONDS = 7 * 24 * 3600  # other-period entries no longer count; drop them after a week
MAX_OPEN = 200  # far above a backlog page; a bound, not a quota
OUTCOMES = ('projected', 'failed', 'abandoned', 'pruned', 'stale')

logger = logging.getLogger(__name__)
CAP_HOLD_RESERVATIONS_RELEASED = Counter(
    'omi_cap_hold_reservations_released_total',
    'Cap-hold funded-capacity reservation events by outcome: projected/failed/abandoned/pruned release one; '
    'stale marks one still pending past STALE_SECONDS (kept and counted; should stay at zero).',
    ['outcome'],
)


def _bounded_outcome(outcome: str) -> str:
    """Label value for CAP_HOLD_RESERVATIONS_RELEASED: a member of OUTCOMES, else 'unknown'."""
    return outcome if outcome in OUTCOMES else 'unknown'


StatusReader = Callable[[str, str], str]  # (uid, batch_job_id) -> 'projected' | 'failed' | 'abandoned' | 'pending'


def _ref(uid: str, client: Any) -> Any:
    return client.collection('users').document(uid).collection(COLLECTION).document(DOCUMENT)


def _entries(data: Any) -> dict[str, dict[str, Any]]:
    entries = (data or {}).get('entries') if isinstance(data, dict) else None
    return dict(entries) if isinstance(entries, dict) else {}


def _valid_units(units: object) -> float:
    if isinstance(units, bool) or not isinstance(units, (int, float)) or not math.isfinite(units) or units < 0:
        raise ValueError('reservation units must be a finite non-negative number')
    return float(units)


def reserve(
    uid: str,
    hold_id: str,
    *,
    units: float,
    period: str,
    batch_job_id: str,
    now: float | None = None,
    firestore_client: Any = None,
) -> None:
    """Idempotent per hold: a retried hand-off keeps the first reservation (and its age clock)."""
    units = _valid_units(units)
    client = firestore_client or get_firestore_client()
    ref = _ref(uid, client)
    stamp = time.time() if now is None else now

    @firestore.transactional
    def commit(transaction: Any) -> None:
        snapshot = ref.get(transaction=transaction)
        entries = _entries(snapshot.to_dict() if snapshot.exists else None)
        if hold_id in entries:
            return
        if len(entries) >= MAX_OPEN:
            raise ValueError('cap-hold reservation bound exceeded')
        entries[hold_id] = {'units': units, 'period': period, 'batch_job_id': batch_job_id, 'reserved_at': stamp}
        transaction.set(ref, {'entries': entries})

    with external_write_fence(uid, firestore_client=client):
        commit(client.transaction())


def open_units(
    uid: str,
    period: str,
    *,
    status_reader: StatusReader,
    now: float | None = None,
    firestore_client: Any = None,
) -> float:
    """Units still reserved in ``period`` after settling every reservation whose batch outcome is known.

    Only a terminal batch outcome releases a reservation. A job still pending past ``STALE_SECONDS`` is
    slow, not lost (lost jobs read as 'abandoned'), so it keeps counting; it is marked stale once, with an
    error log and ``outcome=stale``. Entries from another period stop counting immediately and are pruned
    after ``PRUNE_SECONDS``.
    """
    client = firestore_client or get_firestore_client()
    ref = _ref(uid, client)
    snapshot = ref.get()
    entries = _entries(snapshot.to_dict() if snapshot.exists else None)
    if not entries:
        return 0.0
    stamp = time.time() if now is None else now
    settled: dict[str, str] = {}
    stale: list[str] = []
    for hold_id, entry in entries.items():
        age = stamp - float(entry.get('reserved_at') or 0)
        if entry.get('period') != period and age >= PRUNE_SECONDS:
            settled[hold_id] = 'pruned'
            continue
        outcome = status_reader(uid, str(entry.get('batch_job_id') or ''))
        if outcome in ('projected', 'failed', 'abandoned'):
            settled[hold_id] = outcome
        elif age >= STALE_SECONDS and not entry.get('stale_at'):
            stale.append(hold_id)
    if settled or stale:
        _settle(uid, settled, stale, stamp, client)
    return sum(
        float(entry.get('units') or 0)
        for hold_id, entry in entries.items()
        if hold_id not in settled and entry.get('period') == period
    )


def _settle(uid: str, settled: dict[str, str], stale: list[str], stamp: float, client: Any) -> None:
    ref = _ref(uid, client)

    @firestore.transactional
    def commit(transaction: Any) -> None:
        snapshot = ref.get(transaction=transaction)
        entries = _entries(snapshot.to_dict() if snapshot.exists else None)
        for hold_id in settled:
            entries.pop(hold_id, None)
        for hold_id in stale:
            if hold_id in entries:
                entries[hold_id] = {**entries[hold_id], 'stale_at': stamp}
        transaction.set(ref, {'entries': entries})

    with external_write_fence(uid, firestore_client=client):
        commit(client.transaction())
    for outcome in settled.values():
        CAP_HOLD_RESERVATIONS_RELEASED.labels(outcome=_bounded_outcome(outcome)).inc()
    for _ in stale:
        # Alertable: still reserved and still counted; the batch job has not reached a terminal state.
        CAP_HOLD_RESERVATIONS_RELEASED.labels(outcome='stale').inc()
        logger.error('event=cap_hold_reservation outcome=stale stale_seconds=%d', STALE_SECONDS)


def batch_status(uid: str, batch_job_id: str) -> str:
    """Read-only batch outcome for a handed-off hold. Unreadable state is 'pending' (keeps the reservation)."""
    if not batch_job_id:
        return 'abandoned'
    store = FirestoreStore(f'batch_pipeline_{current_stage()}')

    def read(tx: Any) -> str:
        intake = tx.get('intakes', batch_job_id)
        if not intake or intake.get('owner_id') != uid:
            return 'abandoned'
        ledger = tx.get('content', f"{uid}/{intake['content_id']}") or {}
        if ledger.get('usage_committed_at') is not None or ledger.get('status') == 'completed':
            return 'projected'
        jobs = [tx.get('jobs', segment) or {} for segment in intake.get('segment_ids') or []]
        if jobs and all(
            job.get('state') == 'quarantined' and job.get('recovery_state') not in {'held', 'prepared', 'running'}
            for job in jobs
        ):
            return 'failed'
        return 'pending'

    try:
        return store.run(read)
    except Exception as error:
        logger.warning('event=cap_hold_reservation outcome=status_unavailable exception_type=%s', type(error).__name__)
        return 'pending'
