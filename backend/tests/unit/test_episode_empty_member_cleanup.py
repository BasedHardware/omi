"""The existing empty-live transaction detaches metadata without deleting audio."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from database import recording_sessions
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

ROOT = ('users', 'owner')
CONV = (*ROOT, 'conversations', 'empty')
EPISODE = (*ROOT, 'episodes', 'episode')
LINK = (*ROOT, 'episode_links', 'empty')
FENCE = (*ROOT, 'episode_links', 'recorded_timeline')
SESSION = (*ROOT, 'recording_sessions', 'session')


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', 'true')
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    store = StrictFirestore(
        {
            CONV: {
                'status': 'in_progress',
                'episode_id': 'episode',
                'transcript_segments': [],
                'data_protection_level': 'standard',
            },
            EPISODE: {
                'status': 'closed',
                'close_reason': 'gap',
                'started_at': now,
                'closed_at': now,
                'state_version': 3,
                'conversation_ids': ['speech', 'empty'],
                'recovered_conversation_ids': ['empty'],
                'recorded_members': {'speech': {}, 'empty': {}},
                'member_activity': {'speech': now, 'empty': now},
                'primary_conversation_id': 'empty',
                'recorded_partition': {'state_version': 3},
                'content': 'opaque encrypted content',
            },
            LINK: {'episode_id': 'episode'},
            FENCE: {'version': 7, 'other': 'retained'},
            SESSION: {
                'uid': 'owner',
                'recording_session_id': 'session',
                'conversation_id': 'empty',
                'lifecycle_phase': 'in_progress',
                'lifecycle_sequence': 2,
            },
        }
    )
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a, **kw: None)
    return store


def delete(db):
    return recording_sessions.tombstone_and_delete_empty_conversation('owner', 'empty', 'session', firestore_client=db)


def test_detach_and_existing_session_tombstone_share_one_transaction(db):
    assert delete(db)
    assert CONV not in db.rows and LINK not in db.rows
    assert db.rows[SESSION]['lifecycle_phase'] == 'discarded'
    assert db.rows[SESSION]['lifecycle_sequence'] == 3
    episode = db.rows[EPISODE]
    assert episode['conversation_ids'] == ['speech']
    assert episode['recovered_conversation_ids'] == []
    assert set(episode['recorded_members']) == set(episode['member_activity']) == {'speech'}
    assert episode['primary_conversation_id'] == 'speech'
    assert episode['state_version'] == 4 and episode['recorded_partition'] is None
    assert episode['home_needs_prepare'] is True
    assert episode['content'] == 'opaque encrypted content'
    assert episode['status'] == 'closed' and episode['close_reason'] == 'gap'
    assert db.rows[FENCE] == {'version': 8, 'other': 'retained'}
    assert len(db.transactions) == 1  # StrictFirestore also rejects every read-after-write.


@pytest.mark.parametrize(
    'content',
    [
        {'has_content': True},
        {'photos': [{}]},
        {'audio_files': [{'path': 'existing-audio'}]},
        {'transcript_segments': [{'text': 'Real speech', 'start': 0, 'end': 1}]},
        {'record_lane_owner': 'batch_live_v1', 'server_batch_audio_received': True},
    ],
)
def test_audio_or_content_prevents_all_cleanup_mutations(db, content):
    db.rows[CONV].update(content)
    before = deepcopy(db.rows)
    assert not delete(db)
    assert db.rows == before


def test_cleanup_off_restores_prior_transaction(db, monkeypatch):
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', 'false')
    original = deepcopy(db.rows[EPISODE])
    assert delete(db)
    assert db.rows[EPISODE] == original
    assert LINK in db.rows and CONV not in db.rows


def test_reverse_link_is_removed_if_episode_is_already_absent(db):
    db.rows.pop(EPISODE)
    assert delete(db)
    assert LINK not in db.rows and CONV not in db.rows
    assert db.rows[FENCE]['version'] == 7


def test_stale_conversation_owner_and_current_link_are_both_detached(db):
    second = (*ROOT, 'episodes', 'new-owner')
    db.rows[second] = {**deepcopy(db.rows[EPISODE]), 'conversation_ids': ['empty', 'other']}
    db.rows[LINK]['episode_id'] = 'new-owner'
    assert delete(db)
    assert 'empty' not in db.rows[EPISODE]['conversation_ids']
    assert 'empty' not in db.rows[second]['conversation_ids']


def test_cleanup_defaults_off_and_only_true_opts_in(monkeypatch):
    from config.episode_composition import empty_member_cleanup_enabled

    monkeypatch.delenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', raising=False)
    assert not empty_member_cleanup_enabled()
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', 'invalid')
    assert not empty_member_cleanup_enabled()
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', 'true')
    assert empty_member_cleanup_enabled()


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_registered_audio_protection_is_independent_of_detach_switch(db, monkeypatch, enabled):
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', enabled)
    db.rows[CONV]['server_batch_audio_start'] = 123
    before = deepcopy(db.rows)
    assert not delete(db)
    assert db.rows == before
