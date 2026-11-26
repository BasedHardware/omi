"""Compact Home acceptance against a disposable loopback Firestore emulator.

Exercise SDK encoding, atomic write augmentation and real transactions rather
than replacing the transaction runner. No cloud fallback or customer identity.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import home_feed
from database.conversation_payload import (
    PAYLOAD_CHUNKS,
    read_conversation_payload,
    stage_conversation_notes_patch,
    stage_conversation_payload,
)
from utils.conversation_payload import PAYLOAD_FIELD

pytestmark = pytest.mark.integration
AT = datetime(2026, 11, 15, 8, tzinfo=timezone.utc)


@pytest.fixture
def world():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('explicit loopback Firestore emulator required; no cloud fallback')
    client = firestore.Client(project='demo-home-feed', credentials=AnonymousCredentials())
    uid = 'home-feed-fixture-' + uuid4().hex
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'standard', 'private_cloud_sync_enabled': True})
    try:
        yield client, uid, user
    finally:
        # The owning mobile session destroys this synthetic emulator inventory.
        client.close()


def source(title, *, at=AT):
    return {
        'started_at': at,
        'created_at': AT,
        'finished_at': at + timedelta(minutes=2),
        'status': 'completed',
        'record_projection_revision': 'fixture-ready',
        'structured': {'title': title, 'overview': 'Synthetic saved notes'},
        'source': 'omi',
    }


def drain(client, uid):
    for step in range(60):
        result = home_feed.prepare(uid, firestore_client=client)
        assert result['processed'] <= home_feed.PREPARE_LIMIT
        if result['ready']:
            assert result['has_more'] is False
            return step + 1
    pytest.fail('bounded synthetic preparation did not converge')


def seed_group(user, count=2, *, composed=True):
    batch = user._client.batch()
    ids = [f'member-{i:03}' for i in range(count)]
    for i, cid in enumerate(ids):
        batch.set(user.collection('conversations').document(cid), source(f'Synthetic member {i}'))
        batch.set(user.collection('episode_links').document(cid), {'episode_id': 'episode'})
    batch.set(
        user.collection('episodes').document('episode'),
        {
            'started_at': AT,
            'status': 'closed',
            'conversation_ids': ids,
            **({'composed_at': AT} if composed else {}),
        },
    )
    batch.commit()
    return ids


def test_real_transactions_prepare_group_and_keyset_continuation(world):
    client, uid, user = world
    seed_group(user)
    for i in range(4):
        user.collection('conversations').document(f'old-{i}').set(
            source(f'Synthetic older {i}', at=AT - timedelta(days=i + 1))
        )
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed(uid, firestore_client=client)
    drain(client, uid)
    first = home_feed.feed(uid, limit=2, firestore_client=client)
    assert first['items'][0]['id'] == 'episode:episode'
    assert first['items'][0]['member_count'] == 2
    assert first['has_more'] is True
    seen = [card['id'] for card in first['items']]
    cursor = first['next_cursor']
    while cursor:
        page = home_feed.feed(uid, limit=2, cursor=cursor, firestore_client=client)
        seen.extend(card['id'] for card in page['items'])
        cursor = page['next_cursor']
    assert len(seen) == len(set(seen)) == 5
    assert not any(cid.startswith('conversation:member-') for cid in seen)


def test_acknowledged_remote_deletion_invalidates_and_removes_old_display(world):
    client, uid, user = world
    ids = seed_group(user)
    drain(client, uid)
    before = home_feed.feed(uid, firestore_client=client)
    assert before['items'][0]['member_count'] == 2
    user.collection('conversations').document(ids[0]).delete()
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed(uid, firestore_client=client)
    drain(client, uid)
    after = home_feed.feed(uid, firestore_client=client)
    assert after['generation'] != before['generation']
    assert after['items'][0]['member_count'] == 1
    assert 'Synthetic member 0' not in json.dumps(after, default=str)


def test_upload_custody_progress_keeps_prepared_cards_until_a_content_edit(world):
    client, uid, user = world
    ref = user.collection('conversations').document('recording')
    ref.set(source('Synthetic recording'))
    drain(client, uid)
    before = home_feed.feed(uid, firestore_client=client)
    version = ref.get().to_dict()['home_source_version']
    ref.update({'record_upload_sessions': {'live': True}})
    ref.update({'record_upload_sessions': {}, 'audio_files': []})
    assert ref.get().to_dict()['home_source_version'] == version
    assert home_feed.feed(uid, firestore_client=client) == before
    ref.update({'record_upload_sessions': {}, 'user_title': 'Synthetic renamed'})
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed(uid, firestore_client=client)


def test_hard_episode_delete_recovers_surviving_member_history(world):
    client, uid, user = world
    ids = seed_group(user)
    drain(client, uid)
    user.collection('episodes').document('episode').delete()
    drain(client, uid)
    page = home_feed.feed(uid, firestore_client=client)
    assert {card['id'] for card in page['items']} == {f'conversation:{cid}' for cid in ids}


def test_dense_episode_remains_grouped_across_bounded_preparation_chunks(world):
    client, uid, user = world
    seed_group(user, count=120)
    steps = drain(client, uid)
    assert steps > 1
    page = home_feed.feed(uid, firestore_client=client)
    assert len(page['items']) == 1
    assert page['items'][0]['id'] == 'episode:episode'
    assert page['items'][0]['member_count'] == 120


def test_ready_member_cards_replace_with_composed_owner_across_real_transactions(world, monkeypatch):
    client, uid, user = world
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'on')
    monkeypatch.setattr(home_feed, 'MEMBERS_PER_PREPARE', 1)
    ids = seed_group(user, composed=False)
    drain(client, uid)
    before = home_feed.feed(uid, firestore_client=client)
    assert {card['id'] for card in before['items']} == {f'conversation:{cid}' for cid in ids}
    user.collection('episodes').document('episode').update({'composed_at': AT})
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed(uid, firestore_client=client)
    assert home_feed.prepare(uid, firestore_client=client)['ready'] is False
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed(uid, firestore_client=client)
    drain(client, uid)
    after = home_feed.feed(uid, firestore_client=client)
    assert after['generation'] != before['generation']
    assert [(card['id'], card['member_count']) for card in after['items']] == [('episode:episode', 2)]


def seed_payload_notes(client, ref, title):
    prepared = source(title)
    prepared['structured']['sections'] = [{'title': 'Synthetic section', 'content': 'a' * 1_100_000}]
    prepared['structured']['action_items'] = [{'description': 'Synthetic task'}]

    @firestore.transactional
    def publish(tx):
        stage_conversation_payload(
            tx, ref.get(transaction=tx), prepared, spill_fields={'structured'}, allow_promotion=True
        )

    publish(client.transaction())
    parent = ref.get().to_dict()
    assert PAYLOAD_FIELD in parent and 'structured' not in parent


def test_prepare_hydrates_chunked_notes_for_episodes_and_dirty_updates(world, monkeypatch):
    client, uid, user = world
    monkeypatch.delenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES', raising=False)
    ref = user.collection('conversations').document('member')
    seed_payload_notes(client, ref, 'Initial title')
    member_link = user.collection('episode_links').document(ref.id)
    member_link.set({'episode_id': 'episode'}, merge=True)
    user.collection('episodes').document('episode').set(
        {'started_at': AT, 'status': 'closed', 'conversation_ids': [ref.id], 'composed_at': AT}
    )
    drain(client, uid)

    @firestore.transactional
    def rename(tx):
        snapshot = ref.get(transaction=tx)
        row = read_conversation_payload(client, tx, snapshot)
        stage_conversation_notes_patch(tx, snapshot, row, {'structured.title': 'Updated title'})

    for title in ('Initial title', 'Updated title'):
        [episode] = home_feed.feed(uid, firestore_client=client)['items']
        assert episode['kind'] == 'episode'
        assert episode['title'] == title and episode['preview'] == 'Synthetic saved notes'
        assert episode['has_tasks'] is True
        [member] = home_feed.feed(uid, episodes_admitted=False, firestore_client=client)['items']
        assert member['title'] == title
        assert member['has_tasks'] is True
        if title == 'Initial title':
            rename(client.transaction())
            with pytest.raises(home_feed.PreparationRequired):
                home_feed.feed(uid, firestore_client=client)
            drain(client, uid)


@pytest.mark.parametrize('tight_document_budget', [False, True])
def test_prepare_defers_payloads_under_budget_and_skips_locked_chunks(world, monkeypatch, tight_document_budget):
    client, uid, user = world
    if tight_document_budget:
        monkeypatch.setattr(home_feed, 'MAX_PREPARE_READS', 68)
    coll = user.collection('conversations')
    for index in range(5):
        seed_payload_notes(client, coll.document(f'row-{index}'), f'Synthetic title {index}')
    locked = coll.document('locked')
    seed_payload_notes(client, locked, 'Locked content')
    locked.update({'is_locked': True, 'v3_derived': True})
    # Missing chunks would fail validation if preparation read this locked row.
    for chunk in locked.collection(PAYLOAD_CHUNKS).list_documents():
        chunk.delete()

    first = home_feed.prepare(uid, firestore_client=client)
    assert first['ready'] is False
    assert user.collection('episode_links').document('row-4').get().to_dict()['home_dirty'] is True
    drain(client, uid)
    cards = home_feed.feed(uid, firestore_client=client)['items']
    assert {item['title'] for item in cards if not item['is_locked']} == {
        f'Synthetic title {index}' for index in range(5)
    }
    [locked_card] = [item for item in cards if item['is_locked']]
    assert locked_card['title'] == locked_card['preview'] == ''


def test_prepare_leaves_corrupt_visible_payload_unprepared(world):
    client, uid, user = world
    ref = user.collection('conversations').document('corrupt')
    seed_payload_notes(client, ref, 'Synthetic title')
    next(ref.collection(PAYLOAD_CHUNKS).list_documents()).delete()
    with pytest.raises(home_feed.PreparationRequired, match='home_feed_payload_unavailable'):
        home_feed.prepare(uid, firestore_client=client)
    assert ref.get().to_dict().get('home_prepared') is not True
    assert user.collection('episode_links').document(ref.id).get().to_dict()['home_dirty'] is True
