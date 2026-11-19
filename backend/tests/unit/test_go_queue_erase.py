"""The deletion barrier retries the same receipt and counts unresolved generations."""

from datetime import datetime, timedelta, timezone
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
            {receipts.ARMED_AT: now},
        ],
    ) == {'met': 2, 'eligible': 5, 'overdue_pending': 1}


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

    def record(uid, job_id, claim, step, path=None):
        assert (uid, job_id, claim) == ('tenant', 'job', receipts.claim_fingerprint('token'))
        observed.append(step)
        return {}

    def worker(uid, job_id, claim):
        observed.append('workerd')
        if error:
            raise error()

    def recovery(uid):
        observed.append('recovery')
        return enabled

    monkeypatch.setattr(receipts, 'record', record)
    monkeypatch.setattr(erase, '_erase_at_worker', worker)
    monkeypatch.setattr(erase, '_erase_at_postgres', recovery)
    if failure:
        with pytest.raises(failure):
            erase.require_committed_erase('tenant', 'job', 'token', lambda: None, lambda _inflight: None)
    else:
        erase.require_committed_erase('tenant', 'job', 'token', lambda: None, lambda _inflight: None)
    assert observed == expected


def test_older_receipt_is_reused_under_new_claim(monkeypatch):
    observed = []

    def record(uid, job_id, claim, step):
        assert claim == receipts.claim_fingerprint('new-token')
        observed.append(step)
        return {receipts.RECEIPT_AT: datetime.now(timezone.utc)}

    monkeypatch.setattr(receipts, 'record', record)
    erase.require_committed_erase('tenant', 'job', 'new-token', lambda: None, lambda _inflight: None)
    assert observed == ['arm', 'wipe']


def test_workerd_certificate_failure_cannot_authorize_recovery():
    import ssl

    import httpx

    error = httpx.ConnectError('connection rejected')
    error.__cause__ = ssl.SSLCertVerificationError('bad certificate')
    assert not erase._is_network_unavailable(error)
    assert erase._is_network_unavailable(httpx.ConnectTimeout('timeout'))


def test_recovery_is_off_without_a_database_binding(monkeypatch):
    monkeypatch.delenv('GO_QUEUE_ERASE_RECOVERY_DATABASE_URL', raising=False)
    assert erase._erase_at_postgres('tenant') is False
