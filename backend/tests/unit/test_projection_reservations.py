"""Atomic Firestore ownership for scheduled projection generation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from database import projections
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
PROJECTION_ID = '00000000-0000-0000-0000-000000000001'
RESERVATION_PATH = (
    'users',
    'owner-a',
    projections.PROJECTION_RESERVATIONS_COLLECTION,
    PROJECTION_ID,
)
PROJECTION_PATH = ('users', 'owner-a', projections.PROJECTIONS_COLLECTION, PROJECTION_ID)


class _ContendedTransaction(StrictFirestoreTransaction):
    """Serialize fixture callbacks so two threads model Firestore transaction retries."""

    def _begin(self, retry_id: bytes | None = None) -> None:
        self.lock.acquire()
        super()._begin(retry_id)

    def _commit(self) -> None:
        try:
            super()._commit()
        finally:
            self.lock.release()

    def _rollback(self) -> None:
        try:
            super()._rollback()
        finally:
            self.lock.release()


class _ContendedFirestore(StrictFirestore):
    def transaction(self) -> StrictFirestoreTransaction:
        transaction = _ContendedTransaction(self, allow_reads_after_writes=self._allow_reads_after_writes)
        self.transactions.append(transaction)
        return transaction


def _reserve(client: StrictFirestore, attempt_token: str, *, now: datetime = NOW) -> bool:
    return projections.reserve_projection_generation(
        'owner-a',
        PROJECTION_ID,
        '2026-07-29',
        attempt_token,
        now=now,
        expires_at=now + timedelta(minutes=15),
        firestore_client=client,
    )


def test_overlapping_attempts_have_exactly_one_firestore_owner():
    client = _ContendedFirestore()
    start = Barrier(3)

    def claim(attempt_token: str) -> bool:
        start.wait()
        return _reserve(client, attempt_token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(claim, '00000000-0000-0000-0000-0000000000a1')
        second = executor.submit(claim, '00000000-0000-0000-0000-0000000000b2')
        start.wait()
        results = [first.result(), second.result()]

    assert sorted(results) == [False, True]
    assert client.rows[RESERVATION_PATH]['attempt_token'] in {
        '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000b2',
    }
    assert len(client.transactions) == 2


def test_expired_reservation_can_be_reclaimed_by_a_new_attempt():
    client = StrictFirestore()
    assert _reserve(client, '00000000-0000-0000-0000-0000000000a1') is True

    replacement_now = NOW + timedelta(minutes=16)
    assert _reserve(client, '00000000-0000-0000-0000-0000000000b2', now=replacement_now) is True
    assert client.rows[RESERVATION_PATH]['attempt_token'] == '00000000-0000-0000-0000-0000000000b2'


def test_only_the_current_unexpired_attempt_can_finalize():
    client = StrictFirestore()
    current_attempt = '00000000-0000-0000-0000-0000000000a1'
    assert _reserve(client, current_attempt) is True
    projection = {
        'id': PROJECTION_ID,
        'image_path': f'owner-a/{PROJECTION_ID}/{current_attempt}.png',
    }

    assert (
        projections.finalize_projection_generation(
            'owner-a',
            projection,
            '00000000-0000-0000-0000-0000000000b2',
            now=NOW + timedelta(minutes=1),
            firestore_client=client,
        )
        is False
    )
    assert PROJECTION_PATH not in client.rows

    assert (
        projections.finalize_projection_generation(
            'owner-a',
            projection,
            current_attempt,
            now=NOW + timedelta(minutes=1),
            firestore_client=client,
        )
        is True
    )
    assert client.rows[PROJECTION_PATH] == projection
    assert client.rows[RESERVATION_PATH]['status'] == 'finalized'

    assert (
        projections.finalize_projection_generation(
            'owner-a',
            projection,
            current_attempt,
            now=NOW + timedelta(minutes=2),
            firestore_client=client,
        )
        is False
    )
