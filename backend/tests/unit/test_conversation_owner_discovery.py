"""Public ownership uses Firestore even when Redis contains a stale hint."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import pytest
from fastapi import HTTPException
from google.cloud import firestore

from database import conversations, redis_db


def snapshot(uid='owner', **overrides):
    data = {'id': 'cid', 'visibility': 'shared', **overrides}
    doc = MagicMock()
    doc.exists = True
    doc.reference.path = f'users/{uid}/conversations/cid'
    doc.to_dict.return_value = data
    return doc


@pytest.fixture
def store(monkeypatch):
    client = MagicMock()
    doc = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    query = client.collection_group.return_value.where.return_value.select.return_value.limit.return_value
    query.stream.return_value = [snapshot()]
    doc.get.return_value = snapshot()
    monkeypatch.setattr(conversations, 'db', client)
    cache = fakeredis.FakeRedis()
    monkeypatch.setattr(redis_db, 'r', cache)
    return SimpleNamespace(client=client, doc=doc, query=query, cache=cache)


def test_discovery_by_stored_id_and_ttl_cache(store):
    assert redis_db.get_conversation_uid('cid') == 'owner'
    query = store.client.collection_group.return_value
    store.client.collection_group.assert_called_once_with('conversations')
    field_filter = query.where.call_args.kwargs['filter']
    assert (field_filter.field_path, field_filter.op_string, field_filter.value) == ('id', '==', 'cid')
    query.where.return_value.select.return_value.limit.assert_called_once_with(2)
    assert 86398 <= store.cache.ttl('memories-visibility:cid') <= 86400


def test_ambiguous_id_fails_closed(store):
    store.query.stream.return_value = [snapshot(), snapshot('other')]
    assert redis_db.get_conversation_uid('cid') == ''
    assert not store.cache.exists('memories-visibility:cid')


@pytest.mark.parametrize(
    'data', [{'visibility': 'private'}, {'deleted': True}, {'owner_uid': 'wrong'}, {'is_locked': True}]
)
def test_cache_never_overrides_firestore_state(store, data):
    store.cache.set('memories-visibility:cid', 'owner')
    store.doc.get.return_value = snapshot(**data)
    assert redis_db.get_conversation_uid('cid') == ''
    store.doc.get.assert_called_once()


@pytest.mark.parametrize('cached', [False, True])
def test_firestore_down_is_503_not_not_found(store, cached):
    if cached:
        store.cache.set('memories-visibility:cid', 'owner')
        store.doc.get.side_effect = RuntimeError('Firestore down')
    else:
        store.query.stream.side_effect = RuntimeError('Firestore down')
    with pytest.raises(HTTPException) as error:
        redis_db.get_conversation_uid('cid')
    assert error.value.status_code == 503


def test_redis_down_still_discovers(monkeypatch, store):
    import redis

    broken = MagicMock()
    broken.get.side_effect = redis.exceptions.ConnectionError('down')
    broken.set.side_effect = redis.exceptions.ConnectionError('down')
    monkeypatch.setattr(redis_db, 'r', broken)
    assert redis_db.get_conversation_uid('cid') == 'owner'


def test_missing_owner_is_unavailable(store):
    store.query.stream.return_value = []
    assert redis_db.get_conversation_uid('cid') == ''


def test_soft_deleted_bounded_chat_does_not_decode(store, monkeypatch):
    store.doc.get.return_value = snapshot(deleted=True, transcript_segments='secret')
    decode = MagicMock(side_effect=AssertionError('must not decode deleted data'))
    monkeypatch.setattr(conversations, '_decode_public_transcript_segments_bounded', decode)
    assert conversations.get_public_shared_conversation_bounded('owner', 'cid', firestore_client=store.client) is None
    assert 'deleted' in store.doc.get.call_args.kwargs['field_paths']
    decode.assert_not_called()


def test_share_visibility_writes_owner_atomically(store):
    conversations.set_conversation_visibility('owner', 'cid', 'public')
    store.doc.update.assert_called_once_with({'visibility': 'public', 'owner_uid': 'owner'})


def test_unshare_clears_owner_and_redis_membership(store):
    conversations.set_conversation_visibility('owner', 'cid', 'private')
    store.doc.update.assert_called_once_with({'visibility': 'private', 'owner_uid': firestore.DELETE_FIELD})
    store.cache.set('memories-visibility:cid', 'owner')
    store.cache.sadd('public-memories', 'cid')
    redis_db.remove_conversation_to_uid('cid')
    assert not store.cache.exists('memories-visibility:cid')
    assert not store.cache.sismember('public-memories', 'cid')


def test_email_publish_and_rollback_cas_include_owner(store):
    doc = snapshot(visibility='private')
    doc.update_time = 'read-version'
    store.doc.get.return_value = doc
    store.doc.update.return_value.update_time = 'write-version'
    assert conversations.publish_conversation_visibility_if_private('owner', 'cid') == (True, 'write-version')
    assert store.doc.update.call_args.args[0] == {'visibility': 'shared', 'owner_uid': 'owner'}
    store.client.write_option.assert_called_with(last_update_time='read-version')
    assert conversations.set_conversation_visibility_if_unchanged('owner', 'cid', 'private', 'write-version')
    assert store.doc.update.call_args.args[0] == {'visibility': 'private', 'owner_uid': firestore.DELETE_FIELD}
    store.client.write_option.assert_called_with(last_update_time='write-version')
