"""Dual-backend contract for the exactly-once conversation mutation (ADR-0044 facade + ADR-0002 port).

`database/conversation_mutations.py` arrived with upstream in the +1002 merge and the coverage ratchet
found it: a NEW file merges cleanly, so nothing else would have. Its one at-risk shape is `transaction`,
and it is the whole module — a user's edit and the RECEIPT proving it happened share one commit:

    the receipt is read first, inside the transaction. A retry of the same `client_mutation_id` returns
    the stored response instead of applying the edit again; the same id with a DIFFERENT payload is a
    conflict rather than a silent overwrite. Without that read a flaky client renames a conversation
    twice, or worse, a reused id returns somebody else's answer.

    the conversation is read in the same transaction and its `update_time` is the revision the caller
    must have based its edit on. A mismatch is written as a conflict RECEIPT rather than raised, so the
    retry gets the same verdict instead of racing again.

Both backends must agree on all of it, including the shapes a facade has to translate: `transaction
.create` on a document that must not already exist, `transaction.update` with DOTTED keys
(`structured.title`), and the document `update_time` a revision is derived from.

What this suite does NOT hold, measured rather than assumed: it cannot prove the reads are inside the
transaction. That needs a concurrent writer, and the two backends deliberately disagree about read
locks (ADR-0070). A contract suite asserts the intersection.

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
def conversation(bind_store):
    run = uuid.uuid4().hex[:8]
    uid, conversation_id = f'uid-{run}', f'conv-{run}'
    path = f'users/{uid}/conversations/{conversation_id}'
    bind_store.set(path, {'id': conversation_id, 'structured': {'title': 'before'}, 'user_title': 'before'})

    yield {'uid': uid, 'conversation_id': conversation_id, 'path': path, 'store': bind_store}

    for document in bind_store.query(f'{path}/mutation_receipts'):
        bind_store.delete(f'{path}/mutation_receipts/{document.id}')
    bind_store.delete(path)
    bind_store.delete(f'users/{uid}')


def _revision(conversation):
    """The conversation's current revision, as the caller would have read it."""
    import database.conversation_mutations as mutations

    stored = _client().document(conversation['path']).get()
    return mutations._normalized_revision(getattr(stored, 'update_time', None))


def _apply(conversation, *, mutation_id, operation=None, base_revision=None):
    import database.conversation_mutations as mutations

    return mutations.apply_conversation_sync_mutation(
        conversation['uid'],
        conversation['conversation_id'],
        client_mutation_id=mutation_id,
        base_revision=base_revision if base_revision is not None else _revision(conversation),
        operation=operation if operation is not None else {'type': 'set_title', 'title': 'after'},
        firestore_client=_client(),
    )


def _stored(conversation):
    stored = conversation['store'].get(conversation['path'])
    return stored.data if stored is not None and stored.exists else None


# --- transaction: the edit and its receipt commit together ---------------------------------------


def test_a_mutation_applies_and_leaves_a_receipt(conversation):
    result = _apply(conversation, mutation_id='m-1')

    assert result['status'] == 'ok'
    assert result['conversation_id'] == conversation['conversation_id']

    stored = _stored(conversation)
    assert stored['user_title'] == 'after'
    # A DOTTED update key: the patch names `structured.title`, so the sibling keys of that map survive.
    assert stored['structured']['title'] == 'after'

    receipts = list(conversation['store'].query(f"{conversation['path']}/mutation_receipts"))
    assert len(receipts) == 1
    assert receipts[0].data['client_mutation_id'] == 'm-1'


def test_replaying_the_same_mutation_returns_the_stored_response_and_edits_nothing(conversation):
    """The idempotency the module exists for: a retried edit must not apply twice.

    The in-transaction read of the receipt is what sees the first attempt; both backends must return
    the stored response, and neither may write a second receipt.
    """
    # The SAME base_revision as the first attempt: the receipt's fingerprint hashes
    # (base_revision, operation), so a genuine retry replays the identical request. Reading a fresh
    # revision here would be a DIFFERENT request wearing the same id — which the next test covers.
    base = _revision(conversation)
    first = _apply(conversation, mutation_id='m-1', base_revision=base)

    second = _apply(conversation, mutation_id='m-1', base_revision=base)

    assert second['status'] == 'ok'
    assert second['client_mutation_id'] == first['client_mutation_id']
    assert len(list(conversation['store'].query(f"{conversation['path']}/mutation_receipts"))) == 1
    assert _stored(conversation)['user_title'] == 'after'


def test_reusing_a_mutation_id_with_a_different_payload_is_a_conflict(conversation):
    """Not an overwrite: the caller would otherwise receive an answer computed for another edit."""
    import database.conversation_mutations as mutations

    base = _revision(conversation)
    _apply(conversation, mutation_id='m-1', base_revision=base, operation={'type': 'set_title', 'title': 'after'})

    with pytest.raises(mutations.ConversationMutationConflictError) as raised:
        _apply(
            conversation,
            mutation_id='m-1',
            base_revision=base,
            operation={'type': 'set_title', 'title': 'different'},
        )

    assert raised.value.response['code'] == 'mutation_id_reused'
    assert _stored(conversation)['user_title'] == 'after'


def test_an_edit_against_a_stale_revision_is_refused_and_recorded(conversation):
    """A conflict is WRITTEN as a receipt, not just raised: the retry must get the same verdict rather
    than race again. Both backends have to store and replay it identically."""
    import database.conversation_mutations as mutations

    stale = _revision(conversation) - timedelta(seconds=30)

    with pytest.raises(mutations.ConversationMutationConflictError) as raised:
        _apply(conversation, mutation_id='m-1', base_revision=stale)

    assert raised.value.response['code'] == 'base_revision_mismatch'
    assert _stored(conversation)['user_title'] == 'before', 'a refused edit must not land'

    # Replayed: the stored conflict comes back, not a fresh evaluation.
    with pytest.raises(mutations.ConversationMutationConflictError) as replayed:
        _apply(conversation, mutation_id='m-1', base_revision=stale)
    assert replayed.value.response['code'] == 'base_revision_mismatch'


def test_a_locked_conversation_refuses_the_edit(conversation):
    import database.conversation_mutations as mutations

    conversation['store'].set(conversation['path'], {'is_locked': True}, merge=True)

    with pytest.raises(mutations.ConversationMutationLockedError):
        _apply(conversation, mutation_id='m-1')

    assert _stored(conversation)['user_title'] == 'before'


def test_a_missing_conversation_is_not_found_not_a_crash(conversation):
    import database.conversation_mutations as mutations

    base = _revision(conversation)
    conversation['store'].delete(conversation['path'])

    with pytest.raises(mutations.ConversationMutationNotFoundError):
        _apply(conversation, mutation_id='m-1', base_revision=base)


def test_a_no_op_edit_still_answers_ok_and_still_leaves_one_receipt(conversation):
    """Setting the title it already has changes nothing, and must not look like a failure — the client
    retried for a reason and needs the same answer either way."""
    result = _apply(conversation, mutation_id='m-1', operation={'type': 'set_title', 'title': 'before'})

    assert result['status'] == 'ok'
    assert _stored(conversation)['user_title'] == 'before'
    assert len(list(conversation['store'].query(f"{conversation['path']}/mutation_receipts"))) == 1
