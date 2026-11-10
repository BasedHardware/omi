"""Notes-first closed-episode compose: member notes by default, bounded transcript excerpts on demand."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config import episodes as config
from utils.episodes import composer, metrics, service

UID = 'notes-first-uid'
T0 = datetime(2026, 10, 30, 7, 56, tzinfo=timezone.utc)  # 14:56 in Asia/Bangkok


def _row(cid, start, minutes, *, title='T', overview='O', sections=None, lines=None):
    lines = lines if lines is not None else [(0, 'We planned the launch.'), (60 * minutes - 30, 'Done.')]
    return {
        'id': cid,
        'status': 'completed',
        'started_at': start,
        'finished_at': start + timedelta(minutes=minutes),
        'recorded_start': start,
        'recorded_end': start + timedelta(minutes=minutes),
        'structured': {
            'title': title,
            'overview': overview,
            'sections': sections or [],
            'action_items': [{'description': 'Ship it'}],
        },
        'transcript_segments': [
            {'start': s, 'end': s + 5, 'text': t, 'is_user': i % 2 == 0, 'speaker': 'SPEAKER_01'}
            for i, (s, t) in enumerate(lines)
        ],
    }


class Store:
    def __init__(self, episode, rows):
        self.episode = dict(episode)
        self.rows = {r['id']: r for r in rows}
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
        'closed_at': T0 + timedelta(hours=3, minutes=10),
        'conversation_ids': ['c1', 'c2'],
        'discarded_conversation_ids': [],
        'state_version': 5,
        'title': 'old',
        'bullets': ['David: Yeah.'],
        'moments': [],
        'usage': {'calls': 132},
    }
    base.update(over)
    return base


def _reply(**over):
    data = {
        'title': 'Omi app bugs and labeling tool',
        'emoji': '🛠️',
        'lede': 'David found two app regressions and explained the labeling tool.',
        'chapters': [
            {
                'start': '15:00:00',
                'end': '15:04:30',
                'title': 'App regressions',
                'points': [{'text': 'Ending an episode no longer shows the processing row.', 'details': []}],
            }
        ],
        'people': ['Arjan'],
        'follow_ups': ['Fix the processing row'],
    }
    data.update(over)
    return SimpleNamespace(content=json.dumps(data), usage_metadata={'input_tokens': 8000, 'output_tokens': 500})


def _tool_reply(recording=1, start='14:56:00', end='15:00:00', call_id='call-1'):
    return SimpleNamespace(
        content='',
        tool_calls=[
            {
                'name': 'get_transcript_excerpt',
                'args': {'recording': recording, 'start': start, 'end': end},
                'id': call_id,
            }
        ],
        usage_metadata={'input_tokens': 1000, 'output_tokens': 20},
    )


@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSER_NOTES_FIRST_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSER_NOTES_FIRST_PERCENT_ENV, raising=False)
    monkeypatch.setattr(composer, '_deferred', {})
    monkeypatch.setattr(composer, '_foreground', set())
    monkeypatch.setattr(composer, '_recent', {})
    monkeypatch.setattr(composer, '_inflight', set())
    monkeypatch.setattr(composer, '_rerun', set())
    rows = [_row('c1', T0, 180), _row('c2', T0 + timedelta(minutes=181), 8)]
    s = Store(_episode(), rows)
    monkeypatch.setattr(composer.episodes_db, 'get_episode', s.get_episode)
    monkeypatch.setattr(composer.episodes_db, 'update_episode', s.update_episode)
    monkeypatch.setattr(composer.conversations_db, 'get_conversation', s.get_conversation)
    return s


def _c(invoke=None, calls=None):
    def default(uid, messages, *, tools=None):
        if calls is not None:
            calls.append((messages, tools))
        return _reply()

    return service.Collaborators(
        tz_name='Asia/Bangkok',
        owner_name=lambda uid: 'David',
        people_names=lambda uid, ids: {},
        extras={'compose_invoke': invoke or default},
    )


def _enable(monkeypatch, percent='100'):
    monkeypatch.setenv(config.EPISODE_COMPOSER_NOTES_FIRST_ENV, 'on')
    monkeypatch.setenv(config.EPISODE_COMPOSER_NOTES_FIRST_PERCENT_ENV, percent)


def test_off_by_default_keeps_the_full_transcript(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    human = calls[0][0][1][1]
    assert 'Transcript:\n[14:56:00] David: We planned the launch.' in human
    assert 'Transcript: not included' not in human


def test_on_sends_notes_and_no_raw_transcript(store, monkeypatch):
    _enable(monkeypatch)
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    messages, tools = calls[0]
    human = messages[1][1]
    assert 'Title: T' in human and 'Overview: O' in human
    assert 'Action items: ["Ship it"]' in human
    assert 'Transcript: not included' in human
    assert 'We planned the launch.' not in human
    assert tools and tools[0]['function']['name'] == 'get_transcript_excerpt'


def test_a_member_without_notes_still_gets_its_transcript(store, monkeypatch):
    _enable(monkeypatch)
    store.rows['c2']['structured'] = {'title': '', 'overview': '', 'sections': [], 'action_items': []}
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    human = calls[0][0][1][1]
    assert 'Recording 2' in human and 'Transcript:\n[17:57:00] David: We planned the launch.' in human


def test_sections_are_rendered_into_the_notes_block(store, monkeypatch):
    _enable(monkeypatch)
    store.rows['c1']['structured']['sections'] = [
        {'heading': 'Launch', 'body_markdown': 'Ship on Friday.'},
        {'heading': '', 'body_markdown': 'Body only.'},
    ]
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    human = calls[0][0][1][1]
    assert '## Launch\nShip on Friday.' in human and 'Body only.' in human


def test_tool_call_fetches_a_bounded_excerpt_and_sums_usage(store, monkeypatch):
    _enable(monkeypatch)
    replies = [_tool_reply(), _reply()]
    seen = []

    def invoke(uid, messages, *, tools=None):
        seen.append((list(messages), tools))
        return replies.pop(0)

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    # Both turns offer the tool; the second turn carries the first turn's tool result.
    assert seen[0][1] and seen[1][1]
    tool_messages = [m for m in seen[1][0] if getattr(m, 'type', '') == 'tool']
    assert tool_messages and 'We planned the launch.' in tool_messages[0].content
    written = store.writes[-1]
    assert written['usage']['composer_input_tokens'] == 9000
    assert written['usage']['composer_tool_calls'] == 1


def test_the_last_turn_is_sent_without_tools(store, monkeypatch):
    _enable(monkeypatch)
    # Every turn asks for another excerpt; the last turn must be tool-free and its content parsed.
    replies = [_tool_reply(call_id='a'), _tool_reply(call_id='b'), _tool_reply(call_id='c'), _tool_reply(call_id='d')]
    calls = []

    def invoke(uid, messages, *, tools=None):
        calls.append(tools)
        return replies.pop(0) if replies else _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert len(calls) == config.COMPOSER_NOTES_FIRST_MAX_TURNS
    assert calls[-1] is None


def test_excerpt_bounds_chars_time_and_calls():
    row = _row('c1', T0, 180, lines=[(i * 60, f'line {i} ' + 'x' * 200) for i in range(180)])
    tz = ZoneInfo('Asia/Bangkok')
    text, spent = composer._excerpt(
        [row], 'David', tz, {'recording': 1, 'start': '14:56:00', 'end': '17:56:00'}, remaining_chars=10_000
    )
    assert spent <= config.COMPOSER_EXCERPT_MAX_CHARS
    assert len(text) <= config.COMPOSER_EXCERPT_MAX_CHARS
    # A range wider than the per-call window is clamped, not rejected.
    assert 'line 0' in text and 'line 179' not in text


def test_excerpt_rejects_an_unknown_recording_and_exhausted_budget():
    row = _row('c1', T0, 10)
    tz = ZoneInfo('Asia/Bangkok')
    assert composer._excerpt(
        [row], 'David', tz, {'recording': 9, 'start': '14:56', 'end': '15:00'}, remaining_chars=100
    )[0].startswith('error:')
    assert composer._excerpt([row], 'David', tz, {'recording': 1, 'start': '14:56', 'end': '15:00'}, remaining_chars=0)[
        0
    ].startswith('error:')


def test_cohort_percent_zero_keeps_the_full_path(store, monkeypatch):
    _enable(monkeypatch, percent='0')
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert 'Transcript:\n[14:56:00]' in calls[0][0][1][1]


def test_unknown_flag_value_stays_off(store, monkeypatch):
    monkeypatch.setenv(config.EPISODE_COMPOSER_NOTES_FIRST_ENV, 'maybe')
    monkeypatch.setenv(config.EPISODE_COMPOSER_NOTES_FIRST_PERCENT_ENV, '100')
    assert config.composer_notes_first_enabled(UID) is False


def test_operator_script_renders_a_stable_text_view():
    from scripts import episode_composer_notes_first_diff as diff

    text = diff._render(
        {
            'title': 'T',
            'lede': 'L',
            'follow_ups': ['F'],
            'moments': [
                {
                    'started_at': T0,
                    'ended_at': T0 + timedelta(minutes=1),
                    'heading': 'H',
                    'points': [{'text': 'P', 'details': ['D']}],
                }
            ],
        }
    )
    assert text.splitlines() == [
        'TITLE: T',
        'LEDE: L',
        'FOLLOW-UPS:',
        '  - F',
        f'CHAPTER {T0} - {T0 + timedelta(minutes=1)}: H',
        '  * P',
        '      - D',
    ]


def test_compose_tokens_are_recorded_by_mode():
    before = metrics.EPISODE_COMPOSE_INPUT_TOKENS_TOTAL.labels(mode='notes_first')._value.get()
    calls = metrics.EPISODE_COMPOSE_TOOL_CALLS.labels(mode='notes_first')._sum.get()
    metrics.record_compose_tokens('notes_first', 1234, 2)
    assert metrics.EPISODE_COMPOSE_INPUT_TOKENS_TOTAL.labels(mode='notes_first')._value.get() == before + 1234
    assert metrics.EPISODE_COMPOSE_TOOL_CALLS.labels(mode='notes_first')._sum.get() == calls + 2
    assert metrics.EPISODE_COMPOSE_INPUT_TOKENS_TOTAL._labelnames == ('mode',)
    assert metrics.EPISODE_COMPOSE_TOOL_CALLS._labelnames == ('mode',)
