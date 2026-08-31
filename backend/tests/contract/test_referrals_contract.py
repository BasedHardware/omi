"""Dual-backend contract for the referral entitlement (ADR-0044 facade + ADR-0002 store port).

`database/referrals.py` arrived with upstream and grants a one-time 30-day Operator trial to a referred
account. It is money, and it is granted exactly once, so its single shape is the whole module:

    transaction   `claim_referral_trial` reads the user document INSIDE the transaction and computes the
                  patch from what it read. The read is what sees a claim that already happened: without
                  it, a connector or a user double-submitting the referral link is granted the trial
                  twice — and the second grant RESTARTS the trial window, because `claimed_at` and
                  `trial_ends_at` are recomputed from "now". Nobody is told; the account simply gets
                  paid features for longer than the programme allows.

                  The write is `merge=True` for the same reason it matters elsewhere: the patch names
                  only `subscription` and `referral`, so a replacing write would erase everything else
                  on the user document.

The module was found by the post-merge audit (ADR-0030), not by the merge conflicts — it is a NEW file
from upstream, so it merged cleanly and the coverage ratchet is what noticed it had no dual-backend
cover.

What this suite does NOT hold, measured rather than assumed: moving the read out of the transaction
(`user_ref.get()` instead of `user_ref.get(transaction=transaction)`) survives every test here, as it
does in every other suite. Catching it needs a genuine concurrent write between the read and the commit,
and the two backends deliberately disagree about what happens then (Firestore locks its read set, Mongo
snapshots and takes no read lock — ADR-0070). A contract suite asserts the intersection, so what is held
is that the decision is computed from what was READ, which the first mutation below proves.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def referral(bind_store):
    run = uuid.uuid4().hex[:8]
    referred, referrer = f'referred-{run}', f'referrer-{run}'

    yield {'referred': referred, 'referrer': referrer, 'run': run, 'store': bind_store}

    for uid in (referred, referrer):
        bind_store.delete(f'users/{uid}')


def _claim(referral, *, is_new_user=True, referred=None, referrer=None):
    import database.referrals as referrals_db

    # Upstream widened the return to `(claimed, reason)` so the router can emit why a claim was
    # refused. The contract these suites assert is the grant decision itself, identical on both
    # backends, so the reason rides alongside rather than replacing it.
    claimed, _reason = referrals_db.claim_referral_trial(
        referred or referral['referred'],
        referrer or referral['referrer'],
        is_new_user=is_new_user,
        firestore_client=_client(),
    )
    return claimed


def _user(referral, uid=None):
    stored = referral['store'].get(f"users/{uid or referral['referred']}")
    return stored.data if stored is not None and stored.exists else None


# --- transaction: the grant ------------------------------------------------------------------------


def test_a_new_referred_account_is_granted_the_trial(referral):
    assert _claim(referral) is True

    stored = _user(referral)
    assert stored['subscription']['plan'] == 'operator'
    assert stored['subscription']['status'] == 'active'
    assert stored['subscription']['cancel_at_period_end'] is True
    assert stored['referral']['referrer_uid'] == referral['referrer']


def test_the_grant_works_when_the_user_document_does_not_exist_yet(referral):
    """A referred account signing in for the first time may have no user document at all — the patch is
    computed against nothing, and the transaction creates it."""
    assert _user(referral) is None
    assert _claim(referral) is True
    assert _user(referral)['referral']['program'] == 'desktop_operator_month_v1'


def test_the_grant_preserves_everything_else_on_the_user_document(referral):
    """`merge=True`. The patch names only `subscription` and `referral`; a replacing write would take
    the rest of the account with it."""
    referral['store'].set(f"users/{referral['referred']}", {'time_zone': 'Europe/Rome', 'language': 'it'})

    assert _claim(referral) is True

    stored = _user(referral)
    assert stored['time_zone'] == 'Europe/Rome'
    assert stored['language'] == 'it'
    assert stored['referral']['referrer_uid'] == referral['referrer']


# --- transaction: granted exactly once ---------------------------------------------------------------


def test_a_second_claim_is_refused_and_does_not_restart_the_trial(referral):
    """What the in-transaction read is FOR, stated as the money it protects.

    A double-submitted referral link must not grant twice. Asserting "still one referral record" would
    not be enough — the record is keyed by nothing, so a second write overwrites it and looks identical.
    What actually changes is `claimed_at` / `trial_ends_at`, recomputed from "now": a second grant
    RESTARTS the 30 days. So the assertion is that the original timestamps survive.
    """
    assert _claim(referral) is True
    first = _user(referral)['referral']

    assert _claim(referral) is False

    second = _user(referral)['referral']
    assert second['claimed_at'] == first['claimed_at'], 'the second claim restarted the trial window'
    assert second['trial_ends_at'] == first['trial_ends_at']


def test_an_account_that_already_has_a_paid_plan_is_refused(referral):
    """The trial is for accounts that are not already paying; granting it would downgrade a real
    subscription to a cancelling 30-day one."""
    referral['store'].set(f"users/{referral['referred']}", {'subscription': {'plan': 'operator', 'status': 'active'}})

    assert _claim(referral) is False
    assert _user(referral).get('referral') is None


def test_an_account_that_is_not_new_is_refused(referral):
    """`is_new_user` is decided by the caller from the account's creation time; an established account
    claiming a referral link gets nothing."""
    assert _claim(referral, is_new_user=False) is False
    assert _user(referral) is None, 'a refusal must not create the user document either'


def test_referring_yourself_is_refused(referral):
    assert _claim(referral, referrer=referral['referred']) is False
    assert _user(referral) is None
