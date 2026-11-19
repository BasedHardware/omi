"""The deletion barrier retries the same receipt and counts unresolved generations."""

from datetime import datetime, timedelta, timezone
import errno
import pytest

from database import go_queue_erase as receipts
from services.users import go_queue_erase as erase


def test_readback_counts_overdue_and_late_generations():
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    armed = now - timedelta(hours=1)
    ack = armed + timedelta(minutes=5)
    assert receipts.summarize(
        now,
        [
            {receipts.ARMED_AT: armed, receipts.RECEIPT_AT: ack, receipts.WIPE_AT: ack + timedelta(seconds=1)},
            {receipts.ARMED_AT: armed},
            {receipts.ARMED_AT: armed, receipts.RECEIPT_AT: now},
            {receipts.ARMED_AT: armed, receipts.RECEIPT_AT: ack, receipts.WIPE_AT: armed},
            {receipts.ARMED_AT: armed, receipts.RECEIPT_AT: ack},
            {receipts.ARMED_AT: armed, receipts.RECEIPT_AT: ack, receipts.ORDER_UNKNOWN: True},
            {receipts.ARMED_AT: now},
        ],
    ) == {'met': 2, 'eligible': 6, 'overdue_pending': 1}


@pytest.mark.parametrize(
    ('error', 'enabled', 'expected', 'failure'),
    [
        (None, False, ['arm', 'workerd', 'receipt', 'wipe'], None),
        (erase.EraseUnavailable, False, ['arm', 'workerd', 'verify', 'recovery'], erase.EraseUnavailable),
        (erase.EraseUnavailable, True, ['arm', 'workerd', 'verify', 'recovery', 'receipt', 'wipe'], None),
        (erase.EraseRejected, True, ['arm', 'workerd'], erase.EraseRejected),
    ],
)
def test_only_committed_erase_unlocks_wipe(monkeypatch, error, enabled, expected, failure):
    observed = []

    def record(uid, job_id, claim, step, path=None, *, expires=None):
        assert (uid, job_id, claim) == ('tenant', 'job', receipts.claim_fingerprint('token'))
        observed.append(step)
        return {receipts.CLAIM_EXPIRES_AT: datetime.now(timezone.utc) + timedelta(seconds=10)}

    def worker(uid, job_id, claim):
        observed.append('workerd')
        if error:
            raise error()

    def recovery(uid, expires):
        observed.append('recovery')
        return enabled

    monkeypatch.setattr(receipts, 'record', record)
    monkeypatch.setattr(erase, '_erase_at_worker', worker)
    monkeypatch.setattr(erase, '_erase_at_postgres', recovery)
    if failure:
        with pytest.raises(failure):
            erase.require_committed_erase(
                'tenant', 'job', 'token', lambda: datetime.now(timezone.utc), lambda _inflight: None
            )
    else:
        erase.require_committed_erase(
            'tenant', 'job', 'token', lambda: datetime.now(timezone.utc), lambda _inflight: None
        )
    assert observed == expected


def test_older_receipt_is_reused_under_new_claim(monkeypatch):
    observed = []

    def record(uid, job_id, claim, step, *, expires=None):
        assert claim == receipts.claim_fingerprint('new-token')
        observed.append(step)
        return {receipts.RECEIPT_AT: datetime.now(timezone.utc)}

    monkeypatch.setattr(receipts, 'record', record)
    erase.require_committed_erase(
        'tenant', 'job', 'new-token', lambda: datetime.now(timezone.utc), lambda _inflight: None
    )
    assert observed == ['arm', 'wipe']


@pytest.mark.parametrize(
    ('failure', 'during_tls', 'expected'),
    [
        (ConnectionRefusedError(errno.ECONNREFUSED, 'refused'), False, erase.EraseUnavailable),
        (PermissionError(errno.EACCES, 'forbidden'), False, erase.EraseRejected),
        (erase.ssl.SSLCertVerificationError('bad certificate'), True, erase.EraseRejected),
        (TimeoutError(), True, erase.EraseRejected),
    ],
)
def test_worker_transport_distinguishes_tcp_availability_from_tls_trust(monkeypatch, failure, during_tls, expected):
    from unittest.mock import MagicMock

    monkeypatch.setenv('GO_QUEUE_ERASE_URL', 'https://worker.example/internal/v1/tenant-erase')
    monkeypatch.setenv('GO_QUEUE_ERASE_AUDIENCE', 'worker')
    monkeypatch.setattr(erase, '_oidc_token', lambda _: 'token')
    connect = MagicMock(side_effect=None if during_tls else failure)
    monkeypatch.setattr(erase.socket, 'create_connection', connect)
    context = MagicMock()
    context.wrap_socket.side_effect = failure
    monkeypatch.setattr(erase.ssl, 'create_default_context', lambda: context)

    with pytest.raises(expected):
        erase._erase_at_worker('tenant', 'job', 'claim')


def test_recovery_is_off_without_a_database_binding(monkeypatch):
    monkeypatch.delenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', raising=False)
    assert erase._erase_at_postgres('tenant', datetime.now(timezone.utc)) is False


@pytest.mark.asyncio
async def test_recovery_closes_connection_before_cancelling_stalled_sql(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import psycopg

    connection = MagicMock()
    connection.set_isolation_level = AsyncMock()
    connection.close = AsyncMock()
    connection.commit = AsyncMock()
    started = asyncio.Event()

    async def stall(*args):
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            connection.close.assert_awaited_once()
            raise

    connection.execute = stall
    monkeypatch.setattr(psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection))
    with pytest.raises(erase.EraseUnavailable):
        await erase._recover_erase('test-only', 'queue', 'tenant', datetime.now(timezone.utc) + timedelta(seconds=1))

    assert started.is_set()
    connection.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_never_issues_commit_after_expiry(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import psycopg

    connection = MagicMock()
    connection.set_isolation_level = AsyncMock()
    connection.close = AsyncMock()
    connection.commit = AsyncMock()
    loop = asyncio.get_running_loop()
    start = loop.time()

    async def finish_after_deadline(*args):
        monkeypatch.setattr(loop, 'time', lambda: start + 15)

    connection.execute = finish_after_deadline
    monkeypatch.setattr(psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection))

    try:
        with pytest.raises(erase.EraseUnavailable):
            await erase._recover_erase(
                'test-only', 'queue', 'tenant', datetime.now(timezone.utc) + timedelta(seconds=10)
            )
    finally:
        monkeypatch.undo()

    connection.commit.assert_not_awaited()
    connection.close.assert_awaited_once()
