"""PL-042: task creation must never undo or misreport a committed obligation.

Run the same contract over the reference simulator, legacy Firestore emulator
and new Postgres outbox. Require the backends when claiming qualification:
``OMI_REQUIRE_STORE_BACKENDS=all``. All owners and payloads are synthetic.
"""

from __future__ import annotations

import pytest

from database.outbox import Claim, Outcome
from testing.store_fixtures import outbox_backend  # noqa: F401

pytestmark = pytest.mark.integration

T0 = 1000.0
LEASE = 120.0


class CommittedEnqueueReportedAsFailed(AssertionError):
    """Only the known post-commit task-create exception, after durability checks."""


@pytest.mark.parametrize('transactional', [False, True], ids=['own-transaction', 'caller-transaction'])
@pytest.mark.parametrize('delivery', ['push', 'pull'])
def test_pl042_committed_work_survives_task_create_failure(
    outbox_backend, transactional, delivery, request
):  # noqa: F811
    ob = outbox_backend
    ob.store_harness.seed_user('o')
    owner = ob.store_harness.uid('o')
    payload = ob.payload('retained')
    leaked_wake_error = False

    # Strict xfail matches only the known no-raise defect, not an assertion,
    # import/setup failure, or a regression in the recovery path below.
    if ob.name == 'emulator' and not transactional:
        request.node.add_marker(
            pytest.mark.xfail(
                strict=True,
                raises=CommittedEnqueueReportedAsFailed,
                reason='PL-042: https://github.com/BasedHardware/omi/issues/23559',
            )
        )

    def enqueue(tx=None):
        return ob.outbox.enqueue(
            ob.key(owner, 'retained'),
            owner,
            payload,
            T0,
            policy_id='admitted-policy',
            tx=tx,
            now=T0,
        )

    ob.fail_wakes[0] = True
    if transactional:
        queued = ob.run_tx(enqueue)
        assert ob.wakes == []  # caller owns the post-commit wake
        with pytest.raises(RuntimeError, match='^task create failed$'):
            ob.outbox.wake(queued.row_id, queued.wake_token)
    else:
        try:
            enqueue()
        except RuntimeError as exc:
            if str(exc) != 'task create failed':
                raise
            leaked_wake_error = True
    assert ob.wakes == []

    # Repair attempts during the outage remain errors, never false progress.
    for now in (T0 + 1, T0 + 2):
        counts = ob.outbox.sweep(now=now)
        assert (counts.rewoken, counts.errors, counts.discarded, counts.expired_leases) == (0, 1, 0, 0)
        assert ob.wakes == []

    ob.fail_wakes[0] = False
    if delivery == 'push':
        repaired = ob.outbox.sweep(now=T0 + 3)
        assert (repaired.rewoken, repaired.errors) == (1, 0)
        ((row_id, token, available_at),) = ob.wakes
        assert available_at == T0
        if transactional:
            assert (row_id, token) == (queued.row_id, queued.wake_token)
        settled = ob.outbox.sweep(now=T0 + 4)
        assert (settled.rewoken, settled.errors) == (0, 0)
        claim = ob.outbox.claim_key(row_id, token, LEASE, now=T0 + 5)
        assert isinstance(claim, Claim)
        assert ob.outbox.claim_key(row_id, token, LEASE, now=T0 + 6) is Outcome.BUSY
    else:
        # The queue is a wake mechanism: a pull worker can recover the durable
        # obligation even before any task create succeeds.
        (claim,) = ob.outbox.claim(2, LEASE, now=T0 + 3)
        assert ob.wakes == []

    assert (claim.owner_id, claim.policy_id, claim.attempt) == (owner, 'admitted-policy', 1)
    assert {key: claim.payload[key] for key in payload} == payload
    assert ob.outbox.claim(2, LEASE, now=T0 + 6) == []
    assert ob.outbox.ack(claim, 'done', now=T0 + 7)
    assert not ob.outbox.ack(claim, 'done', now=T0 + 8)
    assert ob.outbox.claim(2, LEASE, now=T0 + 9) == []
    settled = ob.outbox.sweep(now=T0 + 9)
    assert (settled.rewoken, settled.errors) == (0, 0)
    if delivery == 'push':
        assert ob.outbox.claim_key(row_id, token, LEASE, now=T0 + 10) is Outcome.STALE

    if leaked_wake_error:
        raise CommittedEnqueueReportedAsFailed('committed enqueue leaked the task-create failure')
