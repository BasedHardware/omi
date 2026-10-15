"""Strict owner-scoped storage for existing manual-correction contract tests."""

from copy import deepcopy
import sys

from database import conversations, memory_ledger, review_store, review_transcript_changes, vector_db
from tests.support.dream_firestore import DreamFirestore


def install_store(monkeypatch, uid, conversation_id, snapshot, *, store=None, encode=True):
    database = store or DreamFirestore()
    monkeypatch.setitem(sys.modules, 'database.conversations', conversations)
    monkeypatch.setattr(sys.modules['database'], 'conversations', conversations)
    path = ('users', uid, 'conversations', conversation_id)
    database.rows[('users', uid)] = {}
    if snapshot is None:
        database.rows.pop(path, None)
    else:
        snapshot = {**deepcopy(snapshot), 'id': conversation_id}
        database.rows[path] = (
            conversations.encode_conversation_for_write(
                uid, snapshot, snapshot.get('data_protection_level', 'standard')
            )
            if encode
            else snapshot
        )
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(memory_ledger, 'transactional', lambda fn: fn)
    monkeypatch.setattr(conversations, 'db', database)
    monkeypatch.setattr(conversations.firestore, 'transactional', lambda fn: fn)
    # These transaction tests have no vector provider; projection/index tests
    # install their own index and verify the post-commit rebuild separately.
    monkeypatch.setattr(vector_db, 'index', None)
    return database


def target_updates(database, uid, conversation_id):
    path = ('users', uid, 'conversations', conversation_id)
    return [patch for tx in database.transactions for target, patch in tx.updates if target == path]


def read(database, uid, conversation_id):
    raw = database.rows.get(('users', uid, 'conversations', conversation_id))
    return conversations.prepare_conversation_for_read(raw, uid, firestore_client=database)
