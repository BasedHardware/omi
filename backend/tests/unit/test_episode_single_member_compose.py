"""One-conversation episodes are built from that conversation's notes, with no model call."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config import episodes as config
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
    monkeypatch.delenv(config.EPISODE_SINGLE_MEMBER_COMPOSE_ENV, raising=False)
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
    monkeypatch.setenv(config.EPISODE_SINGLE_MEMBER_COMPOSE_ENV, 'false')
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
