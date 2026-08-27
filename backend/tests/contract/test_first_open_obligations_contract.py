"""Dual-backend contract for the first-open obligation lease (ADR-0044 facade + ADR-0002 store port).

`database/first_open_obligations.py` arrived with upstream in the +30 merge as a NEW file, so it merged
cleanly and only the coverage ratchet (ADR-0030 audit) noticed it had no dual-backend cover. It is a
lease: exactly one worker may run the first-open effects for a conversation, and the effects must not
run twice. Two at-risk shapes:

    transaction   every entry point reads the conversation document AND the account authority (the
                  user doc, the account-deletion marker, the memory control state) inside one
                  transaction, then decides from what it read. The generation match is the important
                  part: work claimed under an older account generation must not commit, or a wipe
                  followed by a re-signup gets the previous account's folder assignment.

    aggregation   `commit_first_open_folder_count` runs a COUNT query over the user's conversations
                  filtered by folder and `discarded=False`, and writes the number onto the folder.
                  Aggregations are the shape a facade most easily gets wrong (Firestore returns a
                  nested result rows structure; Mongo counts), and the number is user-visible.

What this suite does NOT hold, measured rather than assumed: it cannot prove the reads are inside the
transaction — that needs concurrency, and the two backends deliberately disagree about read locks
(ADR-0070). It also does not assert lease expiry under a real clock; `claim_first_open_work` takes
`now`, so the expiry path is driven explicitly. A contract suite asserts the intersection: same
decisions, same stored shape, same count.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def work(bind_store):
    run = uuid.uuid4().hex[:8]
    uid, conversation_id, folder_id = f'uid-{run}', f'conv-{run}', f'folder-{run}'
    client = _client()

    client.document(f'users/{uid}').set({'time_zone': 'UTC'})
    client.document(f'users/{uid}/memory_state/apply_control').set(
        {
            'schema_version': 'memory_control_state.v1',
            'uid': uid,
            'head_commit_id': 'head-1',
            'account_generation': 1,
            'source_generation': 1,
        }
    )
    client.document(f'users/{uid}/conversations/{conversation_id}').set(
        {'id': conversation_id, 'folder_id': folder_id, 'discarded': False}
    )
    client.document(f'users/{uid}/folders/{folder_id}').set({'id': folder_id, 'conversation_count': 0})

    context = {'uid': uid, 'conversation_id': conversation_id, 'folder_id': folder_id, 'store': bind_store}

    yield context

    for path in bind_store.query(f'users/{uid}/conversations'):
        bind_store.delete(f'users/{uid}/conversations/{path.id}')
    bind_store.delete(f'users/{uid}/folders/{folder_id}')
    bind_store.delete(f'users/{uid}/memory_state/apply_control')
    bind_store.delete(f'account_deletions/{uid}')
    bind_store.delete(f'users/{uid}')


def _state(work):
    stored = work['store'].get(f"users/{work['uid']}/conversations/{work['conversation_id']}")
    if stored is None or not stored.exists:
        return None
    return stored.data.get('jit_first_open')


def _initialize(work):
    import database.first_open_obligations as first_open

    return first_open.initialize_first_open_work(work['uid'], work['conversation_id'], firestore_client=_client())


def _claim(work, *, now=NOW, lease_seconds=300):
    import database.first_open_obligations as first_open

    return first_open.claim_first_open_work(
        work['uid'], work['conversation_id'], lease_seconds=lease_seconds, now=now, firestore_client=_client()
    )


# --- transaction: initialising and claiming the lease ----------------------------------------------


def test_initialising_stamps_the_account_generation_it_read(work):
    assert _initialize(work) is True

    state = _state(work)
    assert state['state'] == 'pending'
    assert state['attempt'] == 0
    assert state['account_generation'] == 1
    assert state['source_generation'] == 1
    assert set(state['effects']) == {'folder_assignment', 'app_fanout'}
    assert all(effect['state'] == 'pending' for effect in state['effects'].values())


def test_initialising_twice_is_idempotent_and_does_not_reset_the_lease(work):
    """Re-initialising an existing obligation must report the generation match rather than rewriting
    it: a rewrite would drop an in-flight lease and let a second worker start the same effects."""
    _initialize(work)
    token = _claim(work)
    assert token is not None

    assert _initialize(work) is True

    state = _state(work)
    assert state['state'] == 'in_flight'
    assert state['lease_token'] == token


def test_claiming_takes_the_lease_and_a_second_claim_is_refused_while_it_lives(work):
    _initialize(work)

    token = _claim(work)

    assert token is not None
    state = _state(work)
    assert state['state'] == 'in_flight'
    assert state['attempt'] == 1
    assert state['lease_token'] == token

    assert _claim(work, now=NOW + timedelta(seconds=60)) is None
    assert _state(work)['lease_token'] == token


def test_an_expired_lease_is_reclaimed_with_a_new_token_and_a_bumped_attempt(work):
    """A worker that died must not block the conversation forever — but the new holder gets a NEW
    token, so a late write from the dead one is refused by the ownership check."""
    _initialize(work)
    first = _claim(work, lease_seconds=30)

    second = _claim(work, now=NOW + timedelta(seconds=31), lease_seconds=30)

    assert second is not None and second != first
    state = _state(work)
    assert state['attempt'] == 2
    assert state['lease_token'] == second


def test_a_stale_token_authorizes_nothing(work):
    import database.first_open_obligations as first_open

    _initialize(work)
    stale = _claim(work, lease_seconds=30)
    _claim(work, now=NOW + timedelta(seconds=31), lease_seconds=30)

    assert (
        first_open.first_open_effect_is_authorized(
            work['uid'], work['conversation_id'], stale, 'folder_assignment', firestore_client=_client()
        )
        is False
    )
    assert (
        first_open.commit_first_open_conversation_patch(
            work['uid'],
            work['conversation_id'],
            stale,
            'folder_assignment',
            {'title': 'stale'},
            firestore_client=_client(),
        )
        is False
    )
    stored = work['store'].get(f"users/{work['uid']}/conversations/{work['conversation_id']}")
    assert 'title' not in stored.data


def test_work_claimed_under_an_older_generation_stops_authorizing(work):
    """The generation is the account's identity across a wipe-and-resignup. Work claimed before it
    changed must go dead rather than commit onto the new account's conversation."""
    import database.first_open_obligations as first_open

    _initialize(work)
    token = _claim(work)

    _client().document(f"users/{work['uid']}/memory_state/apply_control").set(
        {
            'schema_version': 'memory_control_state.v1',
            'uid': work['uid'],
            'head_commit_id': 'head-2',
            'account_generation': 2,
            'source_generation': 1,
        }
    )

    assert (
        first_open.first_open_effect_is_authorized(
            work['uid'], work['conversation_id'], token, 'folder_assignment', firestore_client=_client()
        )
        is False
    )


def test_nothing_is_authorized_while_the_account_is_being_deleted(work):
    import database.first_open_obligations as first_open

    _initialize(work)
    token = _claim(work)
    work['store'].set(f"account_deletions/{work['uid']}", {'wipe_status': 'running'})

    assert (
        first_open.first_open_effect_is_authorized(
            work['uid'], work['conversation_id'], token, 'folder_assignment', firestore_client=_client()
        )
        is False
    )


def test_completing_both_effects_closes_the_obligation(work):
    import database.first_open_obligations as first_open

    _initialize(work)
    token = _claim(work)

    assert first_open.complete_first_open_effect(
        work['uid'], work['conversation_id'], token, 'folder_assignment', firestore_client=_client()
    )
    # One effect done: finishing leaves the obligation pending, so the next pass picks it up again.
    assert first_open.finish_first_open_work(
        work['uid'], work['conversation_id'], token, succeeded=True, firestore_client=_client()
    )
    assert _state(work)['state'] == 'pending'
    assert 'lease_token' not in _state(work)

    token = _claim(work, now=NOW + timedelta(seconds=1))
    assert first_open.complete_first_open_effect(
        work['uid'], work['conversation_id'], token, 'app_fanout', firestore_client=_client()
    )
    assert first_open.finish_first_open_work(
        work['uid'], work['conversation_id'], token, succeeded=True, firestore_client=_client()
    )

    assert _state(work)['state'] == 'complete'
    assert _claim(work, now=NOW + timedelta(seconds=2)) is None


# --- aggregation: the folder count both backends must compute identically --------------------------


def test_the_folder_count_is_the_number_of_undiscarded_conversations(work):
    """A COUNT query with two filters, written onto the folder. The number is user-visible, and it is
    the shape a facade most easily gets wrong: Firestore returns nested aggregation result rows,
    Mongo counts documents.
    """
    import database.first_open_obligations as first_open

    client = _client()
    base = f"users/{work['uid']}/conversations"
    # Two more in the folder, one of them discarded, plus one in a different folder.
    client.document(f'{base}/other-1').set({'id': 'other-1', 'folder_id': work['folder_id'], 'discarded': False})
    client.document(f'{base}/other-2').set({'id': 'other-2', 'folder_id': work['folder_id'], 'discarded': True})
    client.document(f'{base}/other-3').set({'id': 'other-3', 'folder_id': 'somewhere-else', 'discarded': False})

    _initialize(work)
    token = _claim(work)

    assert first_open.commit_first_open_folder_count(
        work['uid'], work['conversation_id'], token, work['folder_id'], firestore_client=_client()
    )

    folder = work['store'].get(f"users/{work['uid']}/folders/{work['folder_id']}")
    # The seeded conversation plus other-1: discarded and out-of-folder are excluded.
    assert folder.data['conversation_count'] == 2


def test_the_folder_count_is_not_written_without_a_live_lease(work):
    """The aggregation runs before the transaction, but the WRITE is gated on the same authority as
    every other effect — a count computed by a worker whose lease died must not land."""
    import database.first_open_obligations as first_open

    _initialize(work)

    assert (
        first_open.commit_first_open_folder_count(
            work['uid'], work['conversation_id'], 'never-issued', work['folder_id'], firestore_client=_client()
        )
        is False
    )
    assert work['store'].get(f"users/{work['uid']}/folders/{work['folder_id']}").data['conversation_count'] == 0
