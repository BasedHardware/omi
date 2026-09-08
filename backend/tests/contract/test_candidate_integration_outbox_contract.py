"""Dual-backend contract for the candidate-integration outbox (ADR-0044 facade + ADR-0002 port).

`database/candidate_integration_outbox.py` arrived with upstream in the +1002 merge and the coverage
ratchet found it: a NEW file merges cleanly, so nothing else would have. It is a lease over a durable
side effect — "deliver this accepted task to the user's integration" — and its at-risk shape is
`transaction`, used twice:

    claim      reads the outbox row AND the account's workflow-control document in one transaction,
               then decides. The generation check is the point: a side effect claimed for an account
               generation that has since changed must be SUPPRESSED, not delivered — otherwise a task
               accepted before a wipe-and-resignup is pushed into the new account's integration.
    complete   reads the row and refuses unless the lease token still matches, so a worker whose lease
               expired cannot mark somebody else's claim done. A failure is retried with backoff until
               the policy's attempt budget runs out, then it becomes a dead letter.

Both backends must agree on all of it: the same decisions from the same reads, the same stored status
transitions, and the same attempt accounting.

What this suite does NOT hold, measured rather than assumed: it cannot prove the reads are inside the
transaction. That needs a concurrent claimer, and the two backends deliberately disagree about read
locks (ADR-0070). A contract suite asserts the intersection.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def outbox(bind_store):
    from database.candidates import TASK_INTELLIGENCE_CONTROL_COLLECTION, TASK_INTELLIGENCE_CONTROL_DOCUMENT

    run = uuid.uuid4().hex[:8]
    uid, candidate_id = f'uid-{run}', f'cand-{run}'
    row = f'users/{uid}/candidate_integration_outbox/{candidate_id}'
    control = f'users/{uid}/{TASK_INTELLIGENCE_CONTROL_COLLECTION}/{TASK_INTELLIGENCE_CONTROL_DOCUMENT}'

    bind_store.set(control, {'workflow_mode': 'off', 'account_generation': 1})
    bind_store.set(row, {'status': 'pending', 'account_generation': 1, 'attempt_count': 0})

    yield {'uid': uid, 'candidate_id': candidate_id, 'row': row, 'control': control, 'store': bind_store}

    bind_store.delete(row)
    bind_store.delete(control)
    bind_store.delete(f'users/{uid}')


def _stored(outbox):
    stored = outbox['store'].get(outbox['row'])
    return stored.data if stored is not None and stored.exists else None


def _claim(outbox, *, generation=1, now=NOW, lease_seconds=300):
    import database.candidate_integration_outbox as db_outbox

    return db_outbox.claim_candidate_integration_dispatch(
        outbox['uid'], outbox['candidate_id'], account_generation=generation, now=now, lease_seconds=lease_seconds
    )


def _complete(outbox, *, token, succeeded, generation=1, now=NOW, error_text=None):
    import database.candidate_integration_outbox as db_outbox

    return db_outbox.complete_candidate_integration_dispatch(
        outbox['uid'],
        outbox['candidate_id'],
        account_generation=generation,
        lease_token=token,
        succeeded=succeeded,
        now=now,
        error_text=error_text,
    )


# --- transaction: claiming -----------------------------------------------------------------------


def test_claiming_takes_the_lease_and_counts_the_attempt(outbox):
    token = _claim(outbox)

    assert token
    stored = _stored(outbox)
    assert stored['status'] == 'processing'
    assert stored['attempt_count'] == 1
    assert stored['lease_token'] == token
    assert stored['claimed_at'] == NOW


def test_a_second_claim_is_refused_while_the_lease_lives(outbox):
    first = _claim(outbox, lease_seconds=300)

    assert _claim(outbox, now=NOW + timedelta(seconds=60), lease_seconds=300) is None
    assert _stored(outbox)['lease_token'] == first


def test_an_expired_lease_is_reclaimed_with_a_new_token(outbox):
    """A worker that died must not park the side effect forever — but the new holder gets a NEW token,
    so a late completion from the dead one is refused by the ownership check below."""
    first = _claim(outbox, lease_seconds=30)

    second = _claim(outbox, now=NOW + timedelta(seconds=31), lease_seconds=30)

    assert second and second != first
    stored = _stored(outbox)
    assert stored['attempt_count'] == 2
    assert stored['lease_token'] == second


def test_a_stale_account_generation_suppresses_the_side_effect(outbox):
    """The reason the control document is read in the same transaction: a task accepted before a
    wipe-and-resignup must never be delivered into the new account's integration."""
    outbox['store'].set(outbox['control'], {'workflow_mode': 'off', 'account_generation': 2})

    assert _claim(outbox, generation=1) is None

    stored = _stored(outbox)
    assert stored['status'] == 'suppressed'
    assert stored['resolution_reason'] == 'account_generation_mismatch'


def test_a_terminal_row_is_not_claimable(outbox):
    for terminal in ('completed', 'suppressed', 'dead_letter'):
        outbox['store'].set(outbox['row'], {'status': terminal, 'account_generation': 1}, merge=True)
        assert _claim(outbox) is None, terminal


def test_claiming_a_row_that_does_not_exist_is_none_not_an_error(outbox):
    outbox['store'].delete(outbox['row'])

    assert _claim(outbox) is None


# --- transaction: completing, and the lease ownership check ---------------------------------------


def test_completing_closes_the_row_and_releases_the_lease(outbox):
    token = _claim(outbox)

    assert _complete(outbox, token=token, succeeded=True) is True

    stored = _stored(outbox)
    assert stored['status'] == 'completed'
    assert stored['lease_token'] is None
    assert stored['dead_letter_reason'] is None


def test_a_completer_with_the_wrong_token_is_refused(outbox):
    _claim(outbox)

    assert _complete(outbox, token='not-the-lease', succeeded=True) is False
    assert _stored(outbox)['status'] == 'processing'


def test_a_failure_is_retried_until_the_attempt_budget_runs_out(outbox):
    """CANDIDATE_INTEGRATION_POLICY allows 5 attempts. Up to then a failure goes back to `failed` and
    stays claimable; the last one becomes a dead letter with its reason recorded."""
    import database.candidate_integration_outbox as db_outbox

    budget = db_outbox.CANDIDATE_INTEGRATION_POLICY.max_attempts
    for attempt in range(1, budget + 1):
        token = _claim(outbox, now=NOW + timedelta(hours=attempt))
        assert token, f'attempt {attempt} could not be claimed'
        assert _complete(outbox, token=token, succeeded=False, now=NOW + timedelta(hours=attempt), error_text='boom')
        stored = _stored(outbox)
        assert stored['attempt_count'] == attempt
        expected = 'dead_letter' if attempt == budget else 'failed'
        assert stored['status'] == expected, f'attempt {attempt} of {budget}'

    assert _stored(outbox)['dead_letter_reason']
