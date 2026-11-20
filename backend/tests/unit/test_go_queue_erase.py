"""The deletion barrier retries the same receipt and counts unresolved generations."""

from datetime import datetime, timedelta, timezone
import errno
import pytest

from database import go_queue_erase as receipts
from services.users import go_queue_erase as erase

QUEUE_ID = 'a' * 64


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

    def record(uid, job_id, claim, step, path=None, *, expires=None, queue_id=None):
        assert (uid, job_id, claim) == ('tenant', 'job', receipts.claim_fingerprint('token'))
        if step == 'receipt':
            assert queue_id == (QUEUE_ID if path == 'postgres' else None)
        observed.append(step)
        return {receipts.CLAIM_EXPIRES_AT: datetime.now(timezone.utc) + timedelta(seconds=10)}

    def worker(uid, job_id, claim):
        observed.append('workerd')
        if error:
            raise error()

    def recovery(uid, expires):
        observed.append('recovery')
        return QUEUE_ID if enabled else None

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
        (TimeoutError(), True, erase.EraseUnavailable),
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

    if during_tls:
        assert context.minimum_version is erase.ssl.TLSVersion.TLSv1_2


@pytest.mark.parametrize('interruption', ['disconnect', 'incomplete_read', 'short_content_length', 'tls_eof'])
def test_interrupted_acknowledgement_uses_database_recovery(monkeypatch, interruption):
    from unittest.mock import MagicMock

    monkeypatch.setenv('GO_QUEUE_ERASE_URL', 'https://worker.example/internal/v1/tenant-erase')
    monkeypatch.setenv('GO_QUEUE_ERASE_AUDIENCE', 'worker')
    monkeypatch.setattr(erase, '_oidc_token', lambda _: 'token')
    monkeypatch.setattr(erase.socket, 'create_connection', MagicMock())
    monkeypatch.setattr(erase.ssl, 'create_default_context', MagicMock())
    connection = MagicMock()
    monkeypatch.setattr(erase.http.client, 'HTTPSConnection', lambda *_args: connection)
    response = connection.getresponse.return_value.__enter__.return_value
    response.status = 200
    response.length = None
    if interruption == 'disconnect':
        connection.getresponse.side_effect = erase.http.client.RemoteDisconnected()
    elif interruption == 'tls_eof':
        connection.getresponse.side_effect = erase.ssl.SSLEOFError()
    elif interruption == 'incomplete_read':
        response.read.side_effect = erase.http.client.IncompleteRead(b'{', 20)
    else:
        response.read.return_value = b'{'
        response.length = 20

    expires = datetime.now(timezone.utc) + timedelta(seconds=25)
    record = MagicMock(return_value={receipts.CLAIM_EXPIRES_AT: expires})
    monkeypatch.setattr(receipts, 'record', record)
    recover = MagicMock(return_value=QUEUE_ID)
    monkeypatch.setattr(erase, '_erase_at_postgres', recover)

    erase.require_committed_erase('tenant', 'job', 'token', lambda: expires, lambda _: None)

    connection.request.assert_called_once()
    recover.assert_called_once_with('tenant', expires)
    assert [call.args[3] for call in record.call_args_list] == ['arm', 'verify', 'receipt', 'wipe']
    assert record.call_args_list[2].kwargs == {'queue_id': QUEUE_ID}


@pytest.mark.parametrize('status', [401, 409])
def test_interrupted_rejection_headers_cannot_authorize_recovery(monkeypatch, status):
    from unittest.mock import MagicMock

    monkeypatch.setenv('GO_QUEUE_ERASE_URL', 'https://worker.example/internal/v1/tenant-erase')
    monkeypatch.setenv('GO_QUEUE_ERASE_AUDIENCE', 'worker')
    monkeypatch.setattr(erase, '_oidc_token', lambda _: 'token')
    monkeypatch.setattr(erase.socket, 'create_connection', MagicMock())
    tls = MagicMock()
    monkeypatch.setattr(erase.ssl, 'create_default_context', lambda: tls)
    wire = tls.wrap_socket.return_value.makefile.return_value
    wire.readline.side_effect = [f'HTTP/1.1 {status} Rejected\r\n'.encode(), TimeoutError()]
    monkeypatch.setattr(receipts, 'record', MagicMock(return_value={}))
    recover = MagicMock()
    monkeypatch.setattr(erase, '_erase_at_postgres', recover)

    with pytest.raises(erase.EraseRejected, match='request rejected'):
        erase.require_committed_erase('tenant', 'job', 'token', lambda: datetime.now(timezone.utc), lambda _: None)

    recover.assert_not_called()


def test_tls_context_setup_timeout_cannot_authorize_recovery(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setenv('GO_QUEUE_ERASE_URL', 'https://worker.example/internal/v1/tenant-erase')
    monkeypatch.setenv('GO_QUEUE_ERASE_AUDIENCE', 'worker')
    monkeypatch.setattr(erase, '_oidc_token', lambda _: 'token')
    monkeypatch.setattr(erase.socket, 'create_connection', MagicMock())
    monkeypatch.setattr(erase.ssl, 'create_default_context', MagicMock(side_effect=TimeoutError()))
    monkeypatch.setattr(receipts, 'record', MagicMock(return_value={}))
    recover = MagicMock()
    monkeypatch.setattr(erase, '_erase_at_postgres', recover)

    with pytest.raises(erase.EraseRejected, match='TLS context setup failed'):
        erase.require_committed_erase('tenant', 'job', 'token', lambda: datetime.now(timezone.utc), lambda _: None)
    recover.assert_not_called()


@pytest.mark.parametrize('missing', ['DATABASE_URL', 'QUEUE_ID'])
def test_recovery_is_off_without_a_verified_database_binding(monkeypatch, missing):
    monkeypatch.setenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', 'configured')
    monkeypatch.setenv('GO_QUEUE_ERASE_RECOVERY_QUEUE_ID', QUEUE_ID)
    monkeypatch.delenv(f'GO_QUEUE_ERASE_RECOVERY_{missing}')
    assert erase._erase_at_postgres('tenant', datetime.now(timezone.utc)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('proof', [None, ('b' * 64, False)])
async def test_recovery_never_commits_against_an_unverified_queue(monkeypatch, proof):
    from unittest.mock import AsyncMock

    import psycopg

    connection = AsyncMock()
    connection.execute.return_value.fetchone.return_value = proof
    monkeypatch.setattr(psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection))

    with pytest.raises(erase.EraseRejected, match='does not match the intended queue'):
        await erase._recover_erase(
            'test-only', 'queue', 'tenant', datetime.now(timezone.utc) + timedelta(seconds=10), QUEUE_ID
        )

    connection.commit.assert_not_awaited()
    connection.close.assert_awaited_once()


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
        await erase._recover_erase(
            'test-only', 'queue', 'tenant', datetime.now(timezone.utc) + timedelta(seconds=1), QUEUE_ID
        )

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
        cursor = AsyncMock()
        cursor.fetchone.return_value = (QUEUE_ID, True)
        return cursor

    connection.execute = finish_after_deadline
    monkeypatch.setattr(psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection))

    try:
        with pytest.raises(erase.EraseUnavailable):
            await erase._recover_erase(
                'test-only', 'queue', 'tenant', datetime.now(timezone.utc) + timedelta(seconds=10), QUEUE_ID
            )
    finally:
        monkeypatch.undo()

    connection.commit.assert_not_awaited()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_does_not_extend_grant_when_clock_sampling_is_interrupted(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    import psycopg

    loop = asyncio.get_running_loop()
    started = loop.time()
    wall_clock = datetime.now(timezone.utc)
    clock_samples = iter((started, started + 15))

    class PausedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return wall_clock

    connect = AsyncMock()
    with monkeypatch.context() as patch:
        patch.setattr(loop, 'time', lambda: next(clock_samples))
        patch.setattr(erase, 'datetime', PausedClock)
        patch.setattr(psycopg.AsyncConnection, 'connect', connect)
        with pytest.raises(erase.EraseUnavailable, match='grant expired'):
            await erase._recover_erase('test-only', 'queue', 'tenant', wall_clock + timedelta(seconds=10), QUEUE_ID)
    connect.assert_not_awaited()


@pytest.mark.parametrize(
    ('armed', 'receipt_recorded', 'default_minutes', 'expected_minutes'),
    [(False, False, 45, 45), (True, False, 45, 4), (True, True, 45, 45), (True, False, 2, 2)],
)
def test_running_stale_window(armed, receipt_recorded, default_minutes, expected_minutes):
    now = datetime.now(timezone.utc)
    marker = {receipts.ARMED_AT: now if armed else None, receipts.RECEIPT_AT: now if receipt_recorded else None}
    assert receipts.running_stale_window(marker, timedelta(minutes=default_minutes)) == timedelta(
        minutes=expected_minutes
    )


def test_unreadable_success_headers_allow_recovery(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setenv('GO_QUEUE_ERASE_URL', 'https://worker.example/internal/v1/tenant-erase')
    monkeypatch.setenv('GO_QUEUE_ERASE_AUDIENCE', 'worker')
    monkeypatch.setattr(erase, '_oidc_token', lambda _: 'token')
    monkeypatch.setattr(erase.socket, 'create_connection', MagicMock())
    tls = MagicMock()
    monkeypatch.setattr(erase.ssl, 'create_default_context', lambda: tls)
    wire = tls.wrap_socket.return_value.makefile.return_value
    wire.readline.side_effect = [b'HTTP/1.1 200 OK\r\n', erase.http.client.LineTooLong('header')]
    expires = datetime.now(timezone.utc) + timedelta(seconds=20)
    monkeypatch.setattr(receipts, 'record', MagicMock(return_value={receipts.CLAIM_EXPIRES_AT: expires}))
    recover = MagicMock(return_value=QUEUE_ID)
    monkeypatch.setattr(erase, '_erase_at_postgres', recover)

    erase.require_committed_erase('tenant', 'job', 'token', lambda: expires, lambda _: None)

    recover.assert_called_once_with('tenant', expires)


def test_recovery_refuses_unresolved_dns_before_starting_event_loop(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', 'host=slow.invalid dbname=queue')
    monkeypatch.setenv('GO_QUEUE_ERASE_RECOVERY_SCHEMA', 'queue')
    monkeypatch.setenv('GO_QUEUE_ERASE_RECOVERY_QUEUE_ID', QUEUE_ID)
    resolver = MagicMock(side_effect=AssertionError('DNS may outlive the recovery grant'))
    start_loop = MagicMock()
    monkeypatch.setattr(erase.socket, 'getaddrinfo', resolver)
    monkeypatch.setattr(erase.asyncio, 'run', start_loop)

    with pytest.raises(erase.EraseRejected, match='numeric hostaddr'):
        erase._erase_at_postgres('tenant', datetime.now(timezone.utc) + timedelta(seconds=1))

    resolver.assert_not_called()
    start_loop.assert_not_called()
