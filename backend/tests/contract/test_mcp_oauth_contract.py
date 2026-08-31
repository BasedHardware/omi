"""Dual-backend contract for the MCP OAuth store (ADR-0044 facade + ADR-0002 store port).

`database/mcp_oauth.py` is the credential store behind the MCP server: it is what stands between an
authorization code that ChatGPT or Claude hands back and a live bearer token for somebody's memories,
conversations and action items. Every state change in it is one shape:

    transaction   five read-modify-write bodies run under `@firestore.transactional`
                  (`_ensure_oauth_memory_grant`, `create_grant_and_authorization_code_if_allowed`,
                  `consume_authorization_code`, `exchange_authorization_code_for_tokens`,
                  `rotate_refresh_token`). Each reads a credential document *inside* the transaction,
                  decides from what it read, and writes the decision back in the same fence.

                  The decision is always the same one: **this secret may be redeemed exactly once.**
                  An authorization code that mints a second access token is the classic OAuth
                  authorization-code replay — an attacker who observes a code in a redirect URL (a
                  browser history entry, a referrer header, a proxy log) exchanges it again and walks
                  away with a second, independently-lived bearer token for that account. The account
                  owner sees a normal, working connection; nothing in the product ever shows the
                  duplicate. The same fence protects refresh-token rotation, where a replay is the
                  signal that a token was stolen, and the module's answer is to revoke the entire
                  grant — a decision it can only make if it reliably sees that the token was already
                  used.

                  The other half of the fence is all-or-nothing. `exchange_authorization_code_for_tokens`
                  stages four writes (burn the code, mint the access token, mint the refresh token,
                  touch the grant). A write that escapes the fence produces two distinct user-visible
                  failures: if the code burn escapes, a token exchange that fails at the last step
                  leaves the user's connector permanently broken — the code is spent and no token was
                  returned, and the only recovery is re-consenting; if the token write escapes, a live
                  bearer token exists on the account that was never handed to anyone and that no UI
                  lists, so it cannot be revoked.

                  `create_grant_and_authorization_code_if_allowed` fences the same writes against the
                  account-deletion marker: a consent that half-lands while an account is being wiped
                  leaves a grant behind that survives the deletion.

What this suite holds, and what it does not
-------------------------------------------
It holds SINGLE USE and ALL-OR-NOTHING, both mutation-proven on both backends, by making a
transaction body fail *after* it has staged its writes and asserting nothing survived. Moving any one
of those writes out of the fence (`transaction.update(ref, …)` -> `ref.update(…)`) is caught.

It also holds that the code is read INSIDE the fence, which a serial replay test cannot show — a
plain `code_ref.get()` reads the same row and answers the same question. That needs an interleaving,
and there is one below: a competing redemption forced to land after this transaction's read. Both
backends refuse it, for different reasons (Firestore locks its read set; Mongo's read is the session's
first operation and so fixes the snapshot the later write conflicts with), and dropping
`transaction=transaction` makes BOTH mint a second token. ADR-0070's caveat still stands and is worth
keeping in mind when reading that test: Mongo's protection here comes from writing the same document
it read, not from a read lock, so it does not generalise to a transaction that only reads a row.

It does NOT hold the 500-writes/1MB-per-commit ceilings, nor anything about contention that needs two
real processes: everything here runs in one, by construction, so that the interleaving is exact.

Binding: the shared ``bind_store`` fixture in ``conftest.py``. This module was surveyed as having "no
injection point — monkeypatch `database.mcp_oauth.db`"; measured on the live rig, that is not needed.
`db` is `_client._LazyFirestoreClient`, which re-resolves `get_firestore_client()` on **every**
attribute access, and `bind_store` patches that accessor — so `mcp_oauth.db.collection(...)` already
returns the emulator's client on one leg and the neutral facade on the other. The fixture asserts
which one it got rather than trusting the chain.

Every test runs TWICE. These are TOP-LEVEL, cross-account collections shared with every other suite
on this rig, so nothing here queries them unfiltered and teardown deletes only rows carrying this
run's uid.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

RESOURCE = "https://api.omi.me/v1/mcp/sse"
REDIRECT_URI = "https://example.test/oauth/callback"
CLIENT_ID = "omi-mcp-public"
SCOPES = ["memories.read"]
VERIFIER = "contract-verifier-" + "x" * 40  # 43..128 chars of the PKCE alphabet

# The four top-level collections the module owns. Every document in them carries a `uid`, which is the
# only safe way to clean up a shared collection.
CREDENTIAL_COLLECTIONS = (
    "mcp_oauth_grants",
    "mcp_oauth_authorization_codes",
    "mcp_oauth_access_tokens",
    "mcp_oauth_refresh_tokens",
)


def _assert_bound(bind_store, when: str) -> None:
    """`mcp_oauth.db` must resolve to THIS leg's client, before and after the test body.

    Checked at both ends because a test can silently unbind it: pytest's ``monkeypatch`` fixture is one
    object shared with ``conftest``, so a ``monkeypatch.undo()`` inside a test body reverts the accessor
    patch too. On the mongo leg that sends the rest of the test to the FIRESTORE EMULATOR — which is
    running for the other leg, so nothing raises and the assertions just describe the wrong database
    (BACKLOG L1, measured here on the first draft of the atomicity test below). Hence no ``undo()``
    anywhere in this file: reversible patches are armed and disarmed with a flag instead.
    """
    expected = 'CollectionReference' if 'firestore' in type(bind_store).__module__ else '_CollRef'
    import database.mcp_oauth as oauth_db

    resolved = type(oauth_db.db.collection('mcp_oauth_grants')).__name__
    assert resolved == expected, f'{when}: db resolved to {resolved}, expected {expected} — binding lost'


@pytest.fixture
def oauth(bind_store):
    """One clean account with no prior grant, no deletion marker and no memory-grant state."""
    import database.mcp_oauth as oauth_db

    _assert_bound(bind_store, 'setup')

    run = uuid.uuid4().hex[:8]
    uid = f'mcpo-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store, 'db': oauth_db}

    _assert_bound(bind_store, 'teardown')
    for collection in CREDENTIAL_COLLECTIONS:
        for document in bind_store.query(collection, filters=[('uid', '==', uid)]):
            bind_store.delete(document.path)
    bind_store.delete(f'account_deletions/{uid}')
    bind_store.delete(f'users/{uid}/memory_control/app_key_memory_grants')


def _challenge() -> str:
    import database.mcp_oauth as oauth_db

    return oauth_db.pkce_s256(VERIFIER)


def _consent(oauth):
    """Run the real consent transaction; return (grant, raw_code)."""
    return oauth['db'].create_grant_and_authorization_code_if_allowed(
        oauth['uid'], CLIENT_ID, REDIRECT_URI, RESOURCE, SCOPES, _challenge()
    )


def _exchange(oauth, code, *, redirect_uri=REDIRECT_URI, verifier=VERIFIER):
    return oauth['db'].exchange_authorization_code_for_tokens(code, CLIENT_ID, redirect_uri, RESOURCE, verifier)


def _rows(oauth, collection: str) -> list:
    return oauth['store'].query(collection, filters=[('uid', '==', oauth['uid'])])


def _code_doc(oauth, code: str):
    path = f"mcp_oauth_authorization_codes/{oauth['db'].hash_secret(code)}"
    return oauth['store'].get(path)


def _grant_doc(oauth, grant_id: str):
    return oauth['store'].get(f'mcp_oauth_grants/{grant_id}')


# --- consent: the grant, the code and the memory grant land in one fence ------------------------------


def test_consent_writes_the_grant_the_code_and_the_memory_grant_together(oauth):
    """The happy path the whole suite measures against."""
    grant, code = _consent(oauth)

    assert grant['uid'] == oauth['uid'] and grant['status'] == 'active'
    assert _grant_doc(oauth, grant['id']).exists
    assert _code_doc(oauth, code).exists
    memory_grant = oauth['store'].get(f"users/{oauth['uid']}/memory_control/app_key_memory_grants")
    assert memory_grant.exists, 'the MCP consumer must be able to read memories it was granted'


def test_an_account_being_deleted_gets_no_grant_and_no_code(oauth):
    """The deletion marker is read INSIDE the same transaction that writes the consent, so admission and
    consent cannot interleave. A grant written past the marker outlives the wipe: the account is gone and
    a third-party connector still holds a credential pointed at it."""
    import database.mcp_oauth as oauth_db

    oauth['store'].set(f"account_deletions/{oauth['uid']}", {'uid': oauth['uid'], 'wipe_status': 'pending'})

    with pytest.raises(oauth_db.AccountDeletionAccessBlocked):
        _consent(oauth)

    assert _rows(oauth, 'mcp_oauth_grants') == []
    assert _rows(oauth, 'mcp_oauth_authorization_codes') == []
    assert not oauth['store'].get(f"users/{oauth['uid']}/memory_control/app_key_memory_grants").exists


def test_a_cancelled_deletion_does_not_block_consent(oauth):
    """The legacy-principal case: a marker in an access-restoring state must not lock the user out of
    connecting. Without this, the fence above would be indistinguishable from "any marker blocks"."""
    oauth['store'].set(f"account_deletions/{oauth['uid']}", {'uid': oauth['uid'], 'wipe_status': 'cancelled'})

    grant, code = _consent(oauth)

    assert _grant_doc(oauth, grant['id']).exists and _code_doc(oauth, code).exists


def test_a_consent_that_fails_midway_leaves_no_grant_behind(oauth, monkeypatch):
    """All-or-nothing, forced: the memory-grant step raises AFTER `transaction.set(grant_ref, …)` has been
    staged. If that write is not inside the fence, the account ends up carrying an active OAuth grant for
    a consent the user never completed and no authorization code was ever issued for."""
    import database.mcp_oauth as oauth_db

    def _boom(*_args, **_kwargs):
        raise RuntimeError('memory grant write failed')

    monkeypatch.setattr(oauth_db, '_create_oauth_memory_grant_if_absent', _boom)

    with pytest.raises(RuntimeError):
        _consent(oauth)

    assert _rows(oauth, 'mcp_oauth_grants') == [], 'a half-applied consent left a live grant'
    assert _rows(oauth, 'mcp_oauth_authorization_codes') == []


# --- the authorization code is single-use --------------------------------------------------------------


def test_an_authorization_code_mints_exactly_one_token_pair(oauth):
    """One code in, one access token and one refresh token out, the code marked spent and the grant
    touched — the four writes the fence has to keep together."""
    grant, code = _consent(oauth)

    tokens = _exchange(oauth, code)

    assert tokens is not None and tokens['token_type'] == 'Bearer'
    assert tokens['scope'] == 'memories.read'
    assert len(_rows(oauth, 'mcp_oauth_access_tokens')) == 1
    assert len(_rows(oauth, 'mcp_oauth_refresh_tokens')) == 1
    assert _code_doc(oauth, code).data['consumed_at'] is not None
    assert _grant_doc(oauth, grant['id']).data['last_used_at'] is not None


def test_a_replayed_authorization_code_mints_no_second_token(oauth):
    """The contract this module exists for. The second redemption must be refused and must leave the
    account with exactly the one bearer token the first redemption returned — a second one is a stolen
    code turned into a credential the owner cannot see, name, or revoke."""
    _grant, code = _consent(oauth)

    first = _exchange(oauth, code)
    replay = _exchange(oauth, code)

    assert first is not None
    assert replay is None, 'a spent authorization code was redeemed twice'
    assert len(_rows(oauth, 'mcp_oauth_access_tokens')) == 1, 'the replay minted a second access token'
    assert len(_rows(oauth, 'mcp_oauth_refresh_tokens')) == 1


def test_the_older_of_two_codes_still_works_after_the_newer_one_is_spent(oauth):
    """The fence is per code, not per account: consenting twice and spending the second code must not
    invalidate the first. Otherwise a user with two connectors open loses one of them."""
    _grant, first_code = _consent(oauth)
    _grant2, second_code = _consent(oauth)

    assert _exchange(oauth, second_code) is not None
    assert _exchange(oauth, first_code) is not None
    assert len(_rows(oauth, 'mcp_oauth_access_tokens')) == 2


def test_a_wrong_pkce_verifier_is_refused_without_burning_the_code(oauth):
    """PKCE is what stops an intercepted code from being redeemed by whoever intercepted it. The refusal
    must not consume the code either, or the attacker's failed attempt denies the legitimate client its
    one redemption."""
    _grant, code = _consent(oauth)

    assert _exchange(oauth, code, verifier='wrong-verifier-' + 'y' * 40) is None
    assert _rows(oauth, 'mcp_oauth_access_tokens') == []
    assert _code_doc(oauth, code).data['consumed_at'] is None

    assert _exchange(oauth, code) is not None, 'the legitimate client lost its redemption'


def test_a_mismatched_redirect_uri_is_refused_without_burning_the_code(oauth):
    """The other half of the code-injection defence: the code is bound to the redirect it was issued
    for."""
    _grant, code = _consent(oauth)

    assert _exchange(oauth, code, redirect_uri='https://evil.test/cb') is None
    assert _rows(oauth, 'mcp_oauth_access_tokens') == []

    assert _exchange(oauth, code) is not None


def test_an_expired_authorization_code_is_refused(oauth):
    """Codes are short-lived on purpose (10 minutes by default). The expiry is evaluated against what the
    transaction read, so a backend that hands back a stale or type-mangled `expires_at` would keep an
    ancient code redeemable forever."""
    _grant, code = _consent(oauth)
    path = f"mcp_oauth_authorization_codes/{oauth['db'].hash_secret(code)}"
    oauth['store'].set(path, {'expires_at': datetime.now(timezone.utc) - timedelta(minutes=1)}, merge=True)

    assert _exchange(oauth, code) is None
    assert _rows(oauth, 'mcp_oauth_access_tokens') == []


def test_a_revoked_grant_cannot_be_exchanged(oauth):
    """The grant is re-read inside the same transaction as the code. A user who disconnects the connector
    between consent and exchange must not have a token minted against the grant they just revoked."""
    grant, code = _consent(oauth)
    oauth['db'].revoke_grant(grant['id'])

    assert _exchange(oauth, code) is None
    assert _rows(oauth, 'mcp_oauth_access_tokens') == []


def test_a_failure_after_the_token_writes_leaves_the_code_redeemable(oauth, monkeypatch):
    """All-or-nothing on the exchange, forced: the response builder raises AFTER all four writes are
    staged. Nothing may survive — no orphan bearer token that no UI can list and no user can revoke, and
    above all the code must NOT be spent, because a user whose exchange failed at the last step and whose
    code was burned anyway has a permanently broken connector and no way back except re-consenting."""
    import database.mcp_oauth as oauth_db

    grant, code = _consent(oauth)
    untouched_last_used_at = _grant_doc(oauth, grant['id']).data['last_used_at']
    real_response = oauth_db._token_pair_response
    armed = {'fail': True}

    def _boom(*args, **kwargs):
        if armed['fail']:
            raise RuntimeError('response build failed')
        return real_response(*args, **kwargs)

    monkeypatch.setattr(oauth_db, '_token_pair_response', _boom)

    with pytest.raises(RuntimeError):
        _exchange(oauth, code)

    assert _rows(oauth, 'mcp_oauth_access_tokens') == [], 'an unreturned bearer token was left live'
    assert _rows(oauth, 'mcp_oauth_refresh_tokens') == []
    assert _code_doc(oauth, code).data['consumed_at'] is None, 'the code was burned by a failed exchange'
    assert (
        _grant_doc(oauth, grant['id']).data['last_used_at'] == untouched_last_used_at
    ), 'the fourth staged write, the grant touch, escaped the fence'

    armed['fail'] = False  # disarmed by flag, never by monkeypatch.undo() — see _assert_bound
    assert _exchange(oauth, code) is not None, 'the user could not retry'


def test_a_code_redeemed_concurrently_mints_nothing_for_the_second_redeemer(oauth, monkeypatch):
    """The replay the *fence* exists for, as opposed to the replay the `consumed_at` field catches.

    A serial replay is refused by re-reading a field. This one is not: the competing redemption lands
    AFTER this transaction has already read the code and seen it unspent. The interleaving is forced
    deterministically — `_now()` is called once inside the body, right after the code read, and the
    first call writes the competing `consumed_at` out of band — so there is no thread and no timing to
    be flaky about.

    Both deployed backends refuse, and this is the test that proves the read must be INSIDE the fence:

      Firestore  locks what the transaction read; the racing writer collides and the commit aborts.
      Mongo      takes no read lock, but the in-transaction read is the session's FIRST operation and
                 therefore establishes its snapshot; the later write to the same document is then a
                 write conflict and the transaction aborts.

    Measured: with `code_ref.get(transaction=transaction)` the caller gets `Aborted` and zero tokens
    exist. Replace it with a plain `code_ref.get()` and BOTH backends mint a token — on Mongo because
    the snapshot now starts after the racing write. So the assertion below is not "some error happened":
    it is that the second redeemer of a code walks away with nothing.
    """
    from google.api_core.exceptions import Aborted

    import database.mcp_oauth as oauth_db

    _grant, code = _consent(oauth)
    code_path = f"mcp_oauth_authorization_codes/{oauth_db.hash_secret(code)}"
    real_now = oauth_db._now
    raced = {'done': False}

    def _now_racing():
        if not raced['done']:
            raced['done'] = True
            oauth['store'].set(code_path, {'consumed_at': datetime.now(timezone.utc)}, merge=True)
        return real_now()

    monkeypatch.setattr(oauth_db, '_now', _now_racing)

    outcome = 'no exception'
    try:
        outcome = _exchange(oauth, code)
    except Aborted:
        outcome = None

    assert raced['done'], 'the race never fired — the interleaving hook did not run inside the body'
    assert outcome is None, 'the losing redeemer was handed a token pair'
    assert _rows(oauth, 'mcp_oauth_access_tokens') == [], 'a concurrently replayed code minted a token'
    assert _rows(oauth, 'mcp_oauth_refresh_tokens') == []


def test_a_grant_revoked_mid_exchange_still_mints_nothing(oauth, monkeypatch):
    """The second in-transaction read, fenced on its own.

    The previous test only exercises the CODE read: `code_ref.get(transaction=…)` can be de-fenced and
    the grant read still saves the exchange, so the two guards would look redundant. They are not — the
    grant is what a user revokes when they hit "disconnect", and the window this covers is a revocation
    that lands after the grant has been read and before the tokens are written. A token minted there is
    a live credential for a connector the user believes they just cut off.

    The interleaving is forced between the grant read and the token writes, by racing inside
    `_build_token_pair_writes` — the first thing the body does after reading the grant.

    ASYMMETRY, measured, and reported rather than smoothed over: de-fencing the grant read makes
    Firestore mint the token (no read lock is taken, so nothing collides) while Mongo still aborts —
    the code read earlier in the body already fixed the session snapshot, and the transaction writes
    the grant document too, so the racing revocation is a write conflict either way. So this test kills
    that mutation on one leg only. Under `STORAGE_BACKEND=mongo` the guard is genuinely load-bearing
    only for a grant the transaction reads WITHOUT writing, which this body does not do.
    """
    from google.api_core.exceptions import Aborted

    import database.mcp_oauth as oauth_db

    grant, code = _consent(oauth)
    real_build = oauth_db._build_token_pair_writes
    raced = {'done': False}

    def _build_racing(*args, **kwargs):
        if not raced['done']:
            raced['done'] = True
            oauth['store'].set(f"mcp_oauth_grants/{grant['id']}", {'status': 'revoked'}, merge=True)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(oauth_db, '_build_token_pair_writes', _build_racing)

    outcome = 'no exception'
    try:
        outcome = _exchange(oauth, code)
    except Aborted:
        outcome = None

    assert raced['done'], 'the race never fired — the interleaving hook did not run inside the body'
    assert outcome is None
    assert _rows(oauth, 'mcp_oauth_access_tokens') == [], 'a revoked grant still minted a bearer token'


def test_consume_authorization_code_is_single_use_too(oauth):
    """The second consumer of the same fence, used by the authorize leg. Same document, same guard: if
    only one of the two enforced it, whichever route skipped it would be the replay hole."""
    _grant, code = _consent(oauth)

    first = oauth['db'].consume_authorization_code(code, CLIENT_ID, REDIRECT_URI, RESOURCE, VERIFIER)
    second = oauth['db'].consume_authorization_code(code, CLIENT_ID, REDIRECT_URI, RESOURCE, VERIFIER)

    assert first is not None and first['uid'] == oauth['uid']
    assert second is None
    assert _exchange(oauth, code) is None, 'a consumed code must not still be exchangeable'


# --- refresh-token rotation: single-use, and a replay burns the grant -----------------------------------


def test_a_refresh_token_rotates_into_a_new_pair_exactly_once(oauth):
    """Rotation is the same read-modify-write fence: read the token, see it unused, mark it used and
    replaced, mint the successor."""
    _grant, code = _consent(oauth)
    tokens = _exchange(oauth, code)

    rotated = oauth['db'].rotate_refresh_token(tokens['refresh_token'], CLIENT_ID, RESOURCE)

    assert rotated is not None
    assert rotated['refresh_token'] != tokens['refresh_token']
    assert rotated['access_token'] != tokens['access_token']
    used = oauth['store'].get(f"mcp_oauth_refresh_tokens/{oauth['db'].hash_secret(tokens['refresh_token'])}").data
    assert used['used_at'] is not None and used['replaced_by'] is not None


def test_replaying_a_refresh_token_revokes_the_whole_grant(oauth):
    """A refresh token presented twice means one of the two holders is not the user. The module cannot
    tell which, so it revokes everything — and it can only reach that decision if the fence reliably
    reports that the token was already used. A rotation that silently succeeds instead hands an attacker
    an indefinitely renewable session."""
    grant, code = _consent(oauth)
    tokens = _exchange(oauth, code)
    rotated = oauth['db'].rotate_refresh_token(tokens['refresh_token'], CLIENT_ID, RESOURCE)

    replay = oauth['db'].rotate_refresh_token(tokens['refresh_token'], CLIENT_ID, RESOURCE)

    assert replay is None
    revoked_grant = _grant_doc(oauth, grant['id']).data
    assert revoked_grant['status'] == 'revoked' and revoked_grant['replay_detected'] is True
    assert oauth['db'].validate_access_token(rotated['access_token'], RESOURCE) is None
    assert oauth['db'].get_active_grant(grant['id']) is None


def test_a_replay_revokes_every_token_of_the_grant_not_only_the_replayed_one(oauth):
    """The sweep `revoke_grant` runs over both token collections. A token it misses is exactly the
    credential the attacker is holding."""
    grant, code = _consent(oauth)
    tokens = _exchange(oauth, code)
    oauth['db'].rotate_refresh_token(tokens['refresh_token'], CLIENT_ID, RESOURCE)
    oauth['db'].rotate_refresh_token(tokens['refresh_token'], CLIENT_ID, RESOURCE)

    for collection in ('mcp_oauth_access_tokens', 'mcp_oauth_refresh_tokens'):
        stored = _rows(oauth, collection)
        assert stored, f'precondition: {collection} has rows for this grant'
        assert all(row.data.get('revoked_at') is not None for row in stored), f'{collection} kept a live token'
    assert _grant_doc(oauth, grant['id']).data['status'] == 'revoked'


# --- the credential the whole fence protects ------------------------------------------------------------


def test_the_minted_access_token_authenticates_and_a_revoked_one_does_not(oauth):
    """End to end through the real chain: consent -> exchange -> validate. This is the read that every
    MCP request makes, so it is what makes "one token pair" a statement about access rather than about
    rows."""
    grant, code = _consent(oauth)
    tokens = _exchange(oauth, code)

    identity = oauth['db'].validate_access_token(tokens['access_token'], RESOURCE)

    assert identity == {
        'uid': oauth['uid'],
        'auth_type': 'oauth',
        'client_id': CLIENT_ID,
        'resource': RESOURCE,
        'scopes': SCOPES,
        'grant_id': grant['id'],
    }

    oauth['db'].revoke_user_grant(oauth['uid'], grant['id'])
    assert oauth['db'].validate_access_token(tokens['access_token'], RESOURCE) is None


def test_a_token_is_bound_to_the_resource_it_was_issued_for(oauth):
    """The audience check. A token minted for the MCP endpoint must not authenticate against another
    resource, or one connector's credential becomes a skeleton key for every plane."""
    _grant, code = _consent(oauth)
    tokens = _exchange(oauth, code)

    assert oauth['db'].validate_access_token(tokens['access_token'], 'https://other.test/v1/mcp/sse') is None


def test_deleting_the_account_credentials_leaves_no_code_and_no_token(oauth):
    """Account deletion's own sweep over these four collections. A leftover access token is a live
    credential for an account that no longer exists."""
    _grant, code = _consent(oauth)
    _exchange(oauth, code)
    _grant2, unused_code = _consent(oauth)

    oauth['db'].delete_user_oauth_credentials(oauth['uid'])

    for collection in CREDENTIAL_COLLECTIONS:
        assert _rows(oauth, collection) == [], f'{collection} kept a row for a deleted account'
    assert not _code_doc(oauth, unused_code).exists
