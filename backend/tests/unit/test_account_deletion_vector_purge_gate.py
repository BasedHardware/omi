"""Regression: the account-deletion vector purge must run against the REAL vector_db module.

Prod signature: `purge_derived_user_data` gated every vector purge on `vector_db.index is None`, a
module attribute the vector port removed (ADR-0033/WP4 replaced it with `is_vector_available()`).
Reading it raises AttributeError, which the surrounding `except` turns into a *required* failure for
all five purge operations, and a non-empty required-failure list makes `background_wipe_user_data`
refuse the Firestore wipe. Net effect: no user with any conversation, memory, action item or screen
row could ever complete account deletion — on any storage backend.

It shipped because the existing suite (tests/services/users/test_account_deletion.py) installs a
meta-path finder that replaces the whole `database` package with auto-MagicMock modules, so
`vector_db.index` exists in the test and nowhere else. These tests therefore import the real
`database.vector_db` on purpose: the point is to assert the contract the production module actually
has, not the one a mock grants it.

Two behaviours are pinned, because the removed guard existed for a good reason and a naive fix
would trade one broken deletion for another:
  * store NOT configured (the on-prem posture deploy/onprem/backend.env ships) -> nothing was ever
    written, so nothing to purge: the wipe must proceed;
  * store configured but failing -> must still block, because the ids needed to find those vectors
    are about to be deleted with the Firestore data.
"""

import pytest

import database.vector_db as vector_db
from services.users import account_deletion


@pytest.fixture(autouse=True)
def _one_row_per_surface(monkeypatch):
    """Make every purge branch reachable: each id-getter returns exactly one row."""
    monkeypatch.setattr(account_deletion, 'get_conversation_ids', lambda uid: ['conv-1'])
    monkeypatch.setattr(account_deletion, '_historical_memory_ids', lambda uid: ['mem-1'])
    monkeypatch.setattr(account_deletion, 'get_action_item_ids', lambda uid: ['ai-1'])
    monkeypatch.setattr(account_deletion, 'get_screen_activity_ids', lambda uid: ['screen-1'])
    # Surfaces that are not under test here.
    monkeypatch.setattr(account_deletion, 'delete_all_conversation_recordings', lambda uid: 0)
    monkeypatch.setattr(account_deletion, 'purge_canonical_derived_user_data', lambda uid: {'vector_ids': []})


def _no_vector_store(monkeypatch):
    """Env with no vector backend configured — is_vector_available() is False for real."""
    for var in ('VECTOR_STORE_BACKEND', 'PINECONE_API_KEY', 'PINECONE_INDEX_NAME', 'QDRANT_URL'):
        monkeypatch.delenv(var, raising=False)
    assert vector_db.is_vector_available() is False


def _configured_vector_store(monkeypatch):
    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'pinecone')
    monkeypatch.setenv('PINECONE_API_KEY', 'test-key')
    monkeypatch.setenv('PINECONE_INDEX_NAME', 'test-index')
    assert vector_db.is_vector_available() is True


def test_purge_completes_when_no_vector_store_is_configured(monkeypatch):
    """The whole point: a vector-less deployment must still be able to erase an account."""
    _no_vector_store(monkeypatch)

    result = account_deletion.purge_derived_user_data('uid-1')

    assert result['required_failures'] == [], (
        'a deployment with no vector store has no vectors to purge; blocking the wipe over it makes '
        f"account deletion impossible: {result['required_failures']}"
    )
    # Non-blocking, but never silent: an erasure that skipped a surface has to say so, once.
    skipped = [f['operation'] for f in result['best_effort_failures']]
    assert skipped == [account_deletion.VECTOR_PURGE_SKIPPED], skipped


def test_purge_does_not_consult_a_removed_module_attribute(monkeypatch):
    """Pins the exact defect: no failure may mention a missing attribute on the vector module."""
    _no_vector_store(monkeypatch)

    result = account_deletion.purge_derived_user_data('uid-1')

    offenders = [f for f in result['required_failures'] + result['best_effort_failures'] if 'attribute' in f['error']]
    assert offenders == [], f'purge read a symbol the vector port does not expose: {offenders}'


def test_a_configured_but_failing_store_still_blocks_the_wipe(monkeypatch):
    """The removed guard's real purpose survives: a reachable-but-broken store must not be skipped."""
    _configured_vector_store(monkeypatch)

    def _boom(*_a, **_k):
        raise RuntimeError('vector backend unreachable')

    for name in (
        'delete_conversation_vectors_batch',
        'delete_transcript_chunk_vectors_batch',
        'delete_memory_vectors_batch',
        'delete_action_item_vectors_batch',
        'delete_screen_activity_vectors',
    ):
        monkeypatch.setattr(account_deletion, name, _boom)

    result = account_deletion.purge_derived_user_data('uid-1')

    failed = {f['operation'] for f in result['required_failures']}
    assert failed == {
        'conversation_vectors',
        'transcript_chunk_vectors',
        'memory_vectors',
        'action_item_vectors',
        'screen_activity_vectors',
    }, failed


def test_a_configured_store_is_actually_asked_to_delete(monkeypatch):
    """A configured store must not be skipped by the new gate — the purge has to reach it."""
    _configured_vector_store(monkeypatch)
    called: list[str] = []

    monkeypatch.setattr(
        account_deletion, 'delete_conversation_vectors_batch', lambda uid, ids: called.append('conversations')
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_transcript_chunk_vectors_batch',
        lambda uid, ids, raise_on_failure=False: called.append('chunks') or 1,
    )
    monkeypatch.setattr(
        account_deletion, 'delete_memory_vectors_batch', lambda uid, ids: called.append('memories') or 1
    )
    monkeypatch.setattr(
        account_deletion, 'delete_action_item_vectors_batch', lambda uid, ids: called.append('action_items')
    )
    monkeypatch.setattr(
        account_deletion, 'delete_screen_activity_vectors', lambda uid, ids: called.append('screen') or 1
    )

    result = account_deletion.purge_derived_user_data('uid-1')

    assert called == ['conversations', 'chunks', 'memories', 'action_items', 'screen']
    assert result['required_failures'] == []
