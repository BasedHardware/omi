"""Dual-backend contract for the legal hold and the destructive-operation gate
(ADR-0044 facade + ADR-0002 store port).

`database/legal_holds.py` arrived with upstream in the +30 merge, as a NEW file — it merged cleanly and
only the coverage ratchet (ADR-0030 audit) noticed it had no dual-backend cover. It matters more than
its size suggests: `external_write_fence` in this module is what every owner-scoped object-store and
vector write now consults before mutating a provider, so if the two backends disagree about what this
module reads or writes, they disagree about whether a user's data can still be written while their
account is being deleted.

The at-risk shape is `transaction`, and it appears three times:

    acquire   reads BOTH the hold and the gate inside the transaction, then decides: take the gate,
              return silently (already ours), or refuse. The decision is computed from what was read.
    finish    reads the gate and refuses unless uid/kind/token still match — the ownership check that
              stops a late finisher from closing somebody else's gate.
    place     reads the gate and the account-deletion marker and refuses to place a hold that would
              overtake a deletion already running.

The gate row is also written with `transaction.set(gate_ref, {**gate, ...})` — a REPLACING write of a
document the transaction just read, which is precisely the translation a facade can get wrong.

What this suite does NOT hold, measured rather than assumed: it cannot prove the reads are inside the
transaction. That needs a concurrent write between read and commit, and the two backends deliberately
disagree there (Firestore locks its read set, Mongo snapshots — ADR-0070). A contract suite asserts the
intersection: same decisions, same stored shape, same exceptions, on both backends.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def account(bind_store):
    import database.legal_holds as legal_holds

    run = uuid.uuid4().hex[:8]
    uid = f'uid-{run}'

    yield {'uid': uid, 'store': bind_store, 'now': datetime.now(timezone.utc)}

    bind_store.delete(f'{legal_holds.LEGAL_HOLDS_COLLECTION}/{uid}')
    bind_store.delete(f'{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}')
    bind_store.delete(f'account_deletions/{uid}')


def _gate(account):
    import database.legal_holds as legal_holds

    stored = account['store'].get(f"{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{account['uid']}")
    return stored.data if stored is not None and stored.exists else None


def _hold(account):
    import database.legal_holds as legal_holds

    stored = account['store'].get(f"{legal_holds.LEGAL_HOLDS_COLLECTION}/{account['uid']}")
    return stored.data if stored is not None and stored.exists else None


def _acquire(account, *, kind='account_deletion', token='token-1', now=None):
    import database.legal_holds as legal_holds

    legal_holds.acquire_destructive_operation(
        account['uid'], kind=kind, token=token, firestore_client=_client(), now=now or account['now']
    )


# --- transaction: acquiring the gate ---------------------------------------------------------------


def test_acquiring_writes_a_running_gate_the_other_backend_would_write_identically(account):
    _acquire(account)

    gate = _gate(account)
    assert gate['uid'] == account['uid']
    assert gate['kind'] == 'account_deletion'
    assert gate['token'] == 'token-1'
    assert gate['state'] == 'running'
    assert gate['finished_at'] is None
    # A timestamp must survive the round trip as an AWARE datetime on both backends: `_validated_gate`
    # rejects a naive one as malformed, so a lossy translation would make every later call fail closed.
    assert isinstance(gate['started_at'], datetime)
    assert gate['started_at'].utcoffset() is not None


def test_reacquiring_the_same_operation_is_silent(account):
    """The same holder retrying (a crashed worker resuming) must not be refused: the transaction reads
    the gate, recognises uid+kind+token as its own, and returns."""
    _acquire(account)
    first = _gate(account)

    _acquire(account, now=account['now'] + timedelta(minutes=5))

    assert _gate(account)['started_at'] == first['started_at']


def test_a_second_operation_is_refused_while_the_first_is_live(account):
    import database.legal_holds as legal_holds

    _acquire(account, token='token-1')

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        _acquire(account, token='token-2')

    assert _gate(account)['token'] == 'token-1'


def test_an_abandoned_gate_is_taken_over_rather_than_blocking_forever(account):
    """A holder that crashed must not lock the account out permanently: past
    GATE_STALE_AFTER_SECONDS the gate is stale and the next operation takes it.

    Both backends must agree on this, because the alternative is an account nobody can ever delete.
    """
    import database.legal_holds as legal_holds

    _acquire(account, token='token-1')
    later = account['now'] + timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 1)

    _acquire(account, token='token-2', now=later)

    gate = _gate(account)
    assert gate['token'] == 'token-2'
    assert gate['state'] == 'running'


# --- transaction: finishing, and the ownership check -----------------------------------------------


def test_finishing_closes_the_gate_and_keeps_its_identity(account):
    import database.legal_holds as legal_holds

    _acquire(account)

    legal_holds.finish_destructive_operation(
        account['uid'],
        kind='account_deletion',
        token='token-1',
        outcome='completed',
        firestore_client=_client(),
        now=account['now'] + timedelta(minutes=1),
    )

    gate = _gate(account)
    assert gate['state'] == 'completed'
    assert gate['finished_at'] is not None
    # The write is `set({**gate, ...})`: a replacing write built from the read. Everything the gate
    # carried must still be there afterwards, or the next validation rejects it as malformed.
    assert gate['uid'] == account['uid'] and gate['kind'] == 'account_deletion' and gate['token'] == 'token-1'


def test_a_finisher_with_the_wrong_token_is_refused(account):
    import database.legal_holds as legal_holds

    _acquire(account, token='token-1')

    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds.finish_destructive_operation(
            account['uid'],
            kind='account_deletion',
            token='token-2',
            outcome='completed',
            firestore_client=_client(),
        )

    assert _gate(account)['state'] == 'running'


def test_finishing_twice_with_the_same_outcome_is_idempotent(account):
    import database.legal_holds as legal_holds

    _acquire(account)
    for _ in range(2):
        legal_holds.finish_destructive_operation(
            account['uid'],
            kind='account_deletion',
            token='token-1',
            outcome='failed',
            firestore_client=_client(),
        )

    assert _gate(account)['state'] == 'failed'


# --- transaction: placing a hold, and what the fence then refuses ----------------------------------


def test_placing_a_hold_merges_and_then_blocks_deletion(account):
    import database.legal_holds as legal_holds

    account['store'].set(f"{legal_holds.LEGAL_HOLDS_COLLECTION}/{account['uid']}", {'note': 'case-42'})

    legal_holds.place_legal_hold(account['uid'], issuer='admin', firestore_client=_client(), now=account['now'])

    hold = _hold(account)
    assert hold['active'] is True
    assert hold['issuer'] == 'admin'
    # merge=True: the field the case carried is not erased by the hold.
    assert hold['note'] == 'case-42'

    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds.assert_account_deletion_permitted(account['uid'], firestore_client=_client())


def test_a_hold_cannot_overtake_a_deletion_already_running(account):
    """The transaction reads the gate before writing the hold, and refuses if a destructive operation
    owns it. Without that read the hold would land mid-wipe and leave the account half-deleted."""
    import database.legal_holds as legal_holds

    _acquire(account)

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds.place_legal_hold(account['uid'], issuer='admin', firestore_client=_client(), now=account['now'])

    assert _hold(account) is None


def test_lifting_a_hold_is_allowed_even_while_an_operation_runs(account):
    """`active=False` skips the overtake check on purpose: lifting never conflicts with a wipe, and an
    unliftable hold would be its own outage.

    The running operation here is `external_data_write`, the one kind whose acquire does NOT consult
    the hold (it consults the account-deletion marker instead) — an ordinary provider write can be in
    flight under a hold, and that is exactly the state from which the hold must still be liftable.
    """
    import database.legal_holds as legal_holds

    legal_holds.place_legal_hold(account['uid'], issuer='admin', firestore_client=_client(), now=account['now'])
    _acquire(account, kind='external_data_write')

    legal_holds.place_legal_hold(
        account['uid'], issuer='admin', active=False, firestore_client=_client(), now=account['now']
    )

    assert _hold(account)['active'] is False
    legal_holds.assert_account_deletion_permitted(account['uid'], firestore_client=_client())


# --- the fence every provider write consults -------------------------------------------------------


def test_the_external_write_fence_refuses_while_a_destructive_operation_owns_the_gate(account):
    """This is the read path `owner_storage_write_gate` and the vector write decorator take before
    mutating a provider (utils/other/storage.py, database/vector_db.py). Both backends must refuse
    identically, or a self-host on Mongo would keep writing objects for an account being deleted.
    """
    import database.legal_holds as legal_holds

    with legal_holds.external_write_fence(account['uid'], firestore_client=_client()):
        pass  # no gate, no hold: the write proceeds

    _acquire(account)

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.external_write_fence(account['uid'], firestore_client=_client()):
            pass  # pragma: no cover


def test_the_fence_also_refuses_while_the_account_wipe_is_running(account):
    import database.legal_holds as legal_holds

    account['store'].set(f"account_deletions/{account['uid']}", {'wipe_status': 'running'})

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.external_write_fence(account['uid'], firestore_client=_client()):
            pass  # pragma: no cover
