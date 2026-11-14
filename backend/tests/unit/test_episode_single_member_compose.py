"""One-conversation episodes are built from that conversation's notes, with no model call."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config import episodes as config
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.episodes import composer, service

UID = 'single-member-uid'
T0 = datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)


def _segments():
    return [
        {'id': 's0', 'start': 0, 'end': 20, 'text': 'We planned the launch.', 'is_user': True, 'speaker': 'SPEAKER_01'},
        {
            'id': 's1',
            'start': 20,
            'end': 40,
            'text': 'Arjan owns the rollout.',
            'is_user': False,
            'speaker': 'SPEAKER_02',
        },
        {
            'id': 's2',
            'start': 40,
            'end': 60,
            'text': 'Then we talked about pricing.',
            'is_user': True,
            'speaker': 'SPEAKER_01',
        },
        {
            'id': 's3',
            'start': 60,
            'end': 90,
            'text': 'Pricing stays at ten dollars.',
            'is_user': False,
            'speaker': 'SPEAKER_02',
        },
    ]


def _row(**over):
    row = {
        'id': 'c1',
        'status': 'completed',
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=2),
        'recorded_start': T0,
        'recorded_end': T0 + timedelta(minutes=2),
        'structured': {
            'title': 'Launch plan and pricing',
            'gist': 'Launch plan settled; Arjan owns rollout',
            'overview': '## Launch\n\n- We planned the launch.\n\n## Pricing\n\n- Pricing stays at ten dollars.',
            'emoji': '🚀',
            'sections': [
                {
                    'heading': 'Launch',
                    'body_markdown': '- We planned the launch.\n  - Arjan owns the rollout.',
                    'source_segment_ids': ['s0', 's1'],
                },
                {
                    'heading': 'Pricing',
                    'body_markdown': '- Pricing stays at ten dollars.',
                    'source_segment_ids': ['s2', 's3'],
                },
            ],
            'action_items': [
                {'description': 'Ship the launch', 'completed': False},
                {'description': 'Already done', 'completed': True},
            ],
            'participants': [{'name': 'Arjan'}],
        },
        'transcript_segments': _segments(),
    }
    row.update(over)
    return row


class Store:
    def __init__(self, episode, rows):
        self.episode = dict(episode)
        self.rows = {row['id']: row for row in rows}
        self.writes = []

    def get_episode(self, uid, episode_id, firestore_client=None):
        return dict(self.episode)

    def update_episode(self, uid, episode_id, *, expected_version, updates, firestore_client=None, **_):
        assert expected_version == self.episode['state_version']
        self.writes.append(dict(updates))
        self.episode.update(updates)
        self.episode['state_version'] += 1
        return self.episode

    def get_conversation(self, uid, cid, firestore_client=None, **_):
        row = self.rows.get(cid)
        return dict(row) if row else None


def _episode(**over):
    base = {
        'id': 'ep1',
        'status': 'closed',
        'started_at': T0,
        'closed_at': T0 + timedelta(minutes=5),
        'conversation_ids': ['c1'],
        'discarded_conversation_ids': [],
        'state_version': 3,
        'title': 'old',
        'bullets': ['David: Yeah.'],
        'moments': [],
    }
    base.update(over)
    return base


@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSER_THRIFT_ENV, raising=False)
    monkeypatch.setattr(composer, '_deferred', {})
    monkeypatch.setattr(composer, '_foreground', set())
    monkeypatch.setattr(composer, '_recent', {})
    monkeypatch.setattr(composer, '_inflight', set())
    monkeypatch.setattr(composer, '_rerun', set())
    s = Store(_episode(), [_row()])
    monkeypatch.setattr(composer.episodes_db, 'get_episode', s.get_episode)
    monkeypatch.setattr(composer.episodes_db, 'update_episode', s.update_episode)
    monkeypatch.setattr(composer.conversations_db, 'get_conversation', s.get_conversation)
    return s


def _c(invoke=None, calls=None):
    def default(uid, messages):
        if calls is not None:
            calls.append(messages)
        raise AssertionError('the single-member shortcut must not call the composer model')

    return service.Collaborators(
        tz_name='Asia/Bangkok',
        owner_name=lambda uid: 'David',
        people_names=lambda uid, ids: {},
        extras={'compose_invoke': invoke or default},
    )


def test_one_member_episode_is_built_from_notes_without_a_model_call(store):
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    written = store.writes[-1]
    assert written['title'] == 'Launch plan and pricing'
    assert written['lede'] == 'Launch plan settled; Arjan owns rollout'
    assert written['bullets'] == ['Launch plan settled; Arjan owns rollout']
    assert written['emoji'] == '🚀'
    assert written['follow_ups'] == ['Ship the launch']
    assert written['people'] == ['Arjan']
    assert written['summary_needs_regeneration'] is False
    assert written['composed_fingerprint'] and written['composed_notes']
    assert written['compose_failures'] == 0 and 'compose_lease' not in written
    # No paid call, so no composer usage is recorded.
    assert 'usage' not in written

    launch, pricing = written['moments']
    assert [moment['heading'] for moment in written['moments']] == ['Launch', 'Pricing']
    assert launch['conversation_id'] == 'c1'
    assert launch['points'] == [
        {'text': 'We planned the launch.', 'details': ['Arjan owns the rollout.']},
    ]
    assert pricing['points'] == [{'text': 'Pricing stays at ten dollars.', 'details': []}]
    # Chapter times come from the sections' cited segments, on the conversation's own clock.
    assert launch['started_at'] == T0 and launch['ended_at'] == T0 + timedelta(seconds=40)
    assert (launch['start_offset'], launch['end_offset']) == (0.0, 40.0)
    assert pricing['started_at'] == T0 + timedelta(seconds=40)
    assert pricing['ended_at'] == T0 + timedelta(seconds=90)
    assert written['member_activity'] == {'c1': T0 + timedelta(minutes=2)}


def test_the_shortcut_is_idempotent_and_never_recomposes(store):
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'unchanged'
    assert composer.needs_compose(store.episode) is False


def test_kill_switch_restores_the_paid_composer(store, monkeypatch):
    monkeypatch.setenv(config.EPISODE_COMPOSER_THRIFT_ENV, 'false')
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert len(calls) == 1
    assert store.writes[-1]['title'] == 'Composed title'


def test_two_members_still_use_the_composer(store):
    store.episode['conversation_ids'] = ['c1', 'c2']
    store.rows['c2'] = _row(id='c2', started_at=T0 + timedelta(minutes=3))
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert len(calls) == 1


def test_a_member_without_notes_falls_through_to_the_composer(store):
    store.rows['c1']['structured'] = {}
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert len(calls) == 1


def test_sections_without_citations_partition_the_conversation(store):
    sections = store.rows['c1']['structured']['sections']
    sections[0]['source_segment_ids'] = []
    sections[1]['source_segment_ids'] = []
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    launch, pricing = store.writes[-1]['moments']
    # No citations: the sections split the conversation once, in order, with no overlap.
    assert (launch['start_offset'], launch['end_offset']) == (0.0, 45.0)
    assert (pricing['start_offset'], pricing['end_offset']) == (45.0, 90.0)


def test_no_sections_uses_the_overview_as_the_lede(store):
    structured = store.rows['c1']['structured']
    structured['sections'] = []
    structured['gist'] = ''
    structured['overview'] = 'David and Arjan settled the launch plan and the price.'
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    written = store.writes[-1]
    assert written['lede'] == 'David and Arjan settled the launch plan and the price.'
    assert written['moments'] == []


def test_a_second_member_arrival_recomposes_with_the_model(store):
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    store.episode['conversation_ids'] = ['c1', 'c2']
    store.rows['c2'] = _row(id='c2', started_at=T0 + timedelta(minutes=3))
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert len(calls) == 1


def _reply():
    from types import SimpleNamespace
    import json

    data = {
        'title': 'Composed title',
        'emoji': '🛠️',
        'lede': 'A composed lede.',
        'chapters': [
            {
                'start': '14:00:00',
                'end': '14:01:00',
                'title': 'Launch',
                'points': [{'text': 'We planned the launch.', 'details': []}],
            }
        ],
        'follow_ups': [],
        'people': [],
    }
    return SimpleNamespace(content=json.dumps(data), usage_metadata={'input_tokens': 100, 'output_tokens': 20})


@pytest.mark.parametrize(
    'change', ['sections', 'gist', 'participants', 'emoji', 'action_status', 'span', 'segment_end', 'segment_id']
)
def test_shortcut_fingerprint_covers_every_read_field(store, change):
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    old = store.episode['composed_fingerprint']
    row = store.rows['c1']
    structured = row['structured']
    if change == 'sections':
        structured['sections'][0]['body_markdown'] = '- A corrected launch decision.'
    elif change == 'gist':
        structured['gist'] = 'A corrected gist'
    elif change == 'participants':
        structured['participants'][0]['name'] = 'David'
    elif change == 'emoji':
        structured['emoji'] = '🛠️'
    elif change == 'action_status':
        structured['action_items'][0]['completed'] = True
    elif change == 'span':
        row['recorded_end'] += timedelta(minutes=1)
        row['finished_at'] += timedelta(minutes=1)
    elif change == 'segment_end':
        row['transcript_segments'][1]['end'] += 1
    else:
        row['transcript_segments'][0]['id'] = 'replacement-id'
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    assert store.episode['composed_fingerprint'] != old


def test_title_only_notes_use_paid_composer_and_later_body_refreshes(store):
    store.rows['c1']['structured'] = {'title': 'Title alone'}
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert store.episode['lede'] and len(calls) == 1
    store.rows['c1']['structured']['gist'] = 'Now a readable summary'
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    assert store.episode['lede'] == 'Now a readable summary'


def test_member_final_gist_only_change_refreshes_the_shortcut(store, monkeypatch):
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    store.rows['c1']['structured']['gist'] = 'A later corrected gist'
    monkeypatch.setattr(composer.episodes_db, 'get_episode_for_conversation', lambda *a, **k: store.episode)
    monkeypatch.setattr(composer._executor, 'submit', lambda fn: fn())
    composer.schedule_for_conversation(UID, 'c1', collaborators=_c(), row=store.rows['c1'])
    assert store.episode['lede'] == 'A later corrected gist'


def test_an_old_title_only_empty_compose_is_repaired_without_input_change(store):
    store.rows['c1']['structured'] = {'title': 'Title alone'}
    store.episode.update(
        composed_fingerprint=composer.fingerprint(list(store.rows.values())),
        composed_notes=composer.notes_hash(store.episode),
    )
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert store.episode['lede'] and len(calls) == 1


def test_refused_member_activity_retries_only_the_window_field(store, monkeypatch):
    real_write = store.update_episode
    attempts = []

    def write(*args, **kwargs):
        attempts.append(kwargs['updates'])
        if 'member_activity' in kwargs['updates']:
            raise composer.episodes_db.EpisodeConflict('member_window_refused')
        return real_write(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', write)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed_single'
    assert len(attempts) == 4
    assert all('member_activity' in update for update in attempts[:3])
    assert 'member_activity' not in attempts[-1]
    assert store.episode['lede'] and store.episode['moments']


@pytest.fixture
def transactional_store(monkeypatch):
    """Exercise the real episode CAS with strict read-before-write semantics."""
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSER_THRIFT_ENV, raising=False)
    episode_path = ('users', UID, 'episodes', 'ep1')
    member_path = ('users', UID, 'conversations', 'c1')
    end = T0 + timedelta(minutes=2)
    db = StrictFirestore(
        {
            episode_path: composer.episodes_db.seal(UID, _episode(last_activity_at=end, member_activity={'c1': end})),
            member_path: _row(),
        }
    )
    revisions = {member_path: T0}
    original_get = StrictFirestoreDocument.get
    member_reads = []

    def get(ref, transaction=None, **kwargs):
        snapshot = original_get(ref, transaction=transaction, **kwargs)
        snapshot.update_time = revisions.get(ref.path)
        if ref.path == member_path:
            member_reads.append(transaction)
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)

    def read_member(uid, cid, *, firestore_client=None):
        # Keep canonical snapshot metadata, while omitting unrelated photo and
        # Home projection reads from this persistence-boundary test.
        ref = db.collection('users').document(uid).collection('conversations').document(cid)
        return composer.conversations_db.document_data_with_revision(ref.get())

    monkeypatch.setattr(composer.conversations_db, 'get_conversation', read_member)
    c = _c()
    c.firestore_client = db
    return SimpleNamespace(
        db=db, c=c, revisions=revisions, episode_path=episode_path, member_path=member_path, reads=member_reads
    )


def test_single_member_normal_write_validates_member_in_the_episode_transaction(transactional_store):
    s = transactional_store
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'composed_single'
    episode = composer.episodes_db.get_episode(UID, 'ep1', firestore_client=s.db)
    assert episode['title'] == 'Launch plan and pricing'
    assert episode['state_version'] == 4
    assert episode['composed_fingerprint'] == composer.fingerprint([_row()])
    assert s.reads[0] is None
    assert s.reads[-1] is s.db.transactions[-1]
    assert s.db.transactions[-1].sets[0][0] == s.episode_path


@pytest.mark.parametrize('change', ['notes', 'transcript', 'timing', 'hidden', 'deleted'])
def test_single_member_refuses_changed_member_snapshot(transactional_store, monkeypatch, change):
    s = transactional_store
    original_update = composer.episodes_db.update_episode
    attempts = []

    def update(*args, **kwargs):
        attempts.append(kwargs)
        row = s.db.rows[s.member_path]
        if change == 'notes':
            row['structured']['gist'] = 'Newer finalized notes'
        elif change == 'transcript':
            row['transcript_segments'][0]['text'] = 'Corrected speech'
        elif change == 'timing':
            row['recorded_end'] += timedelta(seconds=10)
        elif change == 'hidden':
            row['discarded'] = True
        else:
            del s.db.rows[s.member_path]
        s.revisions[s.member_path] += timedelta(seconds=1)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    assert len(attempts) == 1  # no stale retry or window-only fallback
    assert not any(tx.sets for tx in s.db.transactions)
    assert 'composed_fingerprint' not in s.db.rows[s.episode_path]
    if change == 'notes':
        monkeypatch.setattr(composer.episodes_db, 'update_episode', original_update)
        assert composer.compose(UID, 'ep1', collaborators=s.c) == 'composed_single'
        assert composer.episodes_db.get_episode(UID, 'ep1', firestore_client=s.db)['lede'] == 'Newer finalized notes'


@pytest.mark.parametrize('member_changed', [False, True])
def test_newer_replica_notes_survive_a_stale_single_member_write(transactional_store, monkeypatch, member_changed):
    s = transactional_store
    original_update = composer.episodes_db.update_episode
    attempts = []

    def update(*args, **kwargs):
        attempts.append(kwargs)
        row = s.db.rows[s.member_path]
        if member_changed:
            row['structured']['gist'] = 'Newer replica notes'
            s.revisions[s.member_path] += timedelta(seconds=1)
        # Another replica finishes its compose after our snapshot and before
        # our CAS. Its notes and fingerprint must both survive.
        winner = {**composer.single_member_updates(row), 'composed_fingerprint': composer.fingerprint([row])}
        winner['lede'] = 'Newer replica notes'
        original_update(UID, 'ep1', expected_version=3, updates=winner, firestore_client=s.db)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    episode = composer.episodes_db.get_episode(UID, 'ep1', firestore_client=s.db)
    assert episode['lede'] == 'Newer replica notes'
    assert episode['composed_fingerprint'] == composer.fingerprint([s.db.rows[s.member_path]])
    assert episode['state_version'] == 4
    assert len(attempts) == 1


def test_stale_empty_compose_cannot_clear_newly_finalized_notes(transactional_store, monkeypatch):
    s = transactional_store
    s.db.rows[s.member_path]['transcript_segments'] = []
    original_update = composer.episodes_db.update_episode

    def update(*args, **kwargs):
        s.db.rows[s.member_path] = _row()
        s.revisions[s.member_path] += timedelta(seconds=1)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    episode = composer.episodes_db.get_episode(UID, 'ep1', firestore_client=s.db)
    assert episode['title'] == 'old' and episode['bullets'] == ['David: Yeah.']
    assert episode.get('composed_fingerprint') is None


@pytest.mark.parametrize('missing', [False, True])
def test_unchanged_empty_snapshot_can_still_be_cleared(transactional_store, missing):
    s = transactional_store
    if missing:
        del s.db.rows[s.member_path]
    else:
        s.db.rows[s.member_path]['transcript_segments'] = []
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'empty'
    episode = composer.episodes_db.get_episode(UID, 'ep1', firestore_client=s.db)
    assert episode['title'] == '' and episode['bullets'] == []
    assert episode['composed_fingerprint']


def test_missing_member_arrival_refuses_stale_empty_write(transactional_store, monkeypatch):
    s = transactional_store
    del s.db.rows[s.member_path]
    original_update = composer.episodes_db.update_episode

    def update(*args, **kwargs):
        s.db.rows[s.member_path] = _row()
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    assert not any(tx.sets for tx in s.db.transactions)


def test_window_only_fallback_retains_member_freshness_guard(transactional_store, monkeypatch):
    s = transactional_store
    original_update = composer.episodes_db.update_episode
    attempts = []

    def update(*args, **kwargs):
        attempts.append(kwargs)
        if 'member_activity' in kwargs['updates']:
            s.db.rows[s.member_path]['structured']['gist'] = 'A newer gist during window refusal'
            s.revisions[s.member_path] += timedelta(seconds=1)
            raise composer.episodes_db.EpisodeConflict('member_window_refused')
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    assert len(attempts) == 4  # existing bounded window retries, then one fenced fallback
    assert not any(tx.sets for tx in s.db.transactions)
