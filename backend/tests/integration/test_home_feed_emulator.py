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
