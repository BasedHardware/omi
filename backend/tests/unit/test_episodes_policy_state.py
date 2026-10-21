"""Pure episode rules: kill switch and cohort, compact state, boundaries, reconciliation."""

from datetime import datetime, timedelta, timezone

import pytest

from config import episodes as config
from utils.episodes import policy
from utils.episodes.state import InvalidUpdate, apply_update, parse_update, render_state

T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- kill switch and cohort


@pytest.mark.parametrize(
    'raw,expected',
    [(None, True), ('', True), ('true', True), ('on', True), ('off', False), ('of', False), ('false', False)],
)
def test_kill_switch_defaults_on_and_a_typo_turns_it_off(monkeypatch, raw, expected):
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    if raw is None:
        monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    else:
        monkeypatch.setenv(config.EPISODES_ENABLED_ENV, raw)
    assert config.episodes_enabled() is expected
    assert config.episodes_enabled_for('uid-1') is expected


def test_ramp_cohort_admits_allowlist_and_bucket(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.setenv(config.EPISODES_PERCENT_ENV, '0')
    monkeypatch.setenv(config.EPISODES_UID_ALLOWLIST_ENV, 'david, other')
    assert config.episodes_enabled_for('david') is True
    assert config.episodes_enabled_for('someone-else') is False
    monkeypatch.setenv(config.EPISODES_PERCENT_ENV, '100')
    assert config.episodes_enabled_for('someone-else') is True
    monkeypatch.setenv(config.EPISODES_PERCENT_ENV, 'not-a-number')
    assert config.episodes_enabled_for('someone-else') is False
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert config.episodes_enabled_for('david') is False
    assert config.episodes_enabled_for('') is False


def test_unset_percent_admits_everyone_by_default(monkeypatch):
    # Client gating (utils/episodes/client_gate.py) makes admission free, so the code default is 100.
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_UID_ALLOWLIST_ENV, raising=False)
    assert all(config.episodes_enabled_for(f'user-{i}') for i in range(2000))


def test_five_percent_cohort_is_stable_and_near_five_percent(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.setenv(config.EPISODES_PERCENT_ENV, '5')
    admitted = [config.episodes_enabled_for(f'user-{i}') for i in range(4000)]
    assert 0.03 < sum(admitted) / len(admitted) < 0.07
    assert admitted == [config.episodes_enabled_for(f'user-{i}') for i in range(4000)]


# --------------------------------------------------------------------------- state


def test_parse_update_bounds_and_validates_the_model_answer():
    raw = 'Sure! {"title": "  Lunch and git support for agents with a very long trailing title that keeps going on and on and on ", "moment_heading": "Lunch plans", "bullets": ["Lunch at 12:30", "lunch at 12:30", "", 3, "Git worktrees per agent"], "people": ["Huong"], "items": [{"text": "Book lunch table", "kind": "reminder", "explicit": true, "due": "2026-10-20T12:30:00"}, {"id": "p-unknown", "text": "Invented edit"}, {"id": "p1", "text": "Call Minh tomorrow"}, {"text": ""}], "drop_ids": ["p2", "p-unknown"]}'
    update = parse_update(raw, known_item_ids=['p1', 'p2'])
    assert len(update.title) <= config.MAX_TOPIC_CHARS
    assert update.bullets == ['Lunch at 12:30', 'Git worktrees per agent']
    assert update.drop_ids == {'p2'}
    assert update.edits['p1']['text'] == 'Call Minh tomorrow'
    assert [item['text'] for item in update.new_items] == ['Book lunch table']
    assert update.new_items[0]['kind'] == 'reminder' and update.new_items[0]['explicit'] is True
    assert update.new_items[0]['due_at'] == datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('raw', ['', 'no json here', '[1, 2]', '{"title": '])
def test_parse_update_rejects_non_objects(raw):
    with pytest.raises(InvalidUpdate):
        parse_update(raw, known_item_ids=[])


def test_render_state_lists_only_open_items_and_stays_inside_the_budget():
    episode = {
        'title': 'Coding at the café',
        'bullets': ['x' * 190] * 40,
        'people': ['Huong'],
        'open_questions': [],
        'provisional_items': [
            {'id': 'p1', 'text': 'Book a table', 'kind': 'task', 'status': 'provisional'},
            {'id': 'p2', 'text': 'Old', 'kind': 'task', 'status': 'kept'},
        ],
    }
    rendered = render_state(episode)
    assert len(rendered) <= config.MAX_STATE_CHARS
    assert '"p1"' in rendered and '"p2"' not in rendered
    assert render_state(None) == '{}'


def test_apply_update_drops_edits_dedupes_and_keeps_ids_stable():
    episode = {
        'title': 'Old topic',
        'bullets': ['A'],
        'people': ['Huong'],
        'provisional_items': [
            {'id': 'p1', 'text': 'Book a table', 'kind': 'task', 'status': 'provisional'},
            {'id': 'p2', 'text': 'Email Nik', 'kind': 'task', 'status': 'provisional'},
            {'id': 'p3', 'text': 'Done earlier', 'kind': 'task', 'status': 'kept'},
        ],
    }
    update = parse_update(
        '{"title": "Lunch and pricing", "bullets": ["B"], "people": ["Minh"], '
        '"items": [{"id": "p1", "text": "Book a table for 12:30"}, {"text": "email nik"}, {"text": "Draft pricing"}], '
        '"drop_ids": ["p2", "p3"]}',
        known_item_ids=['p1', 'p2'],
    )
    changed = apply_update(episode, update, conversation_id='c1', segment_offset=42.0, now=T0)
    items = {item['id']: item for item in changed['provisional_items']}
    assert items['p1']['text'] == 'Book a table for 12:30' and items['p1']['status'] == 'provisional'
    assert items['p2']['status'] == 'dropped'
    assert items['p3']['status'] == 'kept'
    new = [item for item in changed['provisional_items'] if item['id'] not in {'p1', 'p2', 'p3'}]
    # "email nik" duplicates the dropped p2 by text and is not re-added.
    assert [item['text'] for item in new] == ['Draft pricing']
    assert new[0]['conversation_id'] == 'c1' and new[0]['segment_offset'] == 42.0
    assert changed['title'] == 'Lunch and pricing' and changed['bullets'] == ['B']
    assert changed['people'] == ['Minh', 'Huong']


# --------------------------------------------------------------------------- boundaries


def _episode(**overrides):
    base = {
        'id': 'e1',
        'status': 'live',
        'started_at': T0,
        'last_activity_at': T0 + timedelta(minutes=10),
        'conversation_ids': ['c1'],
        'sources': ['omi'],
        'moments': [{'id': 'm1'}],
        'calendar_identity': None,
    }
    base.update(overrides)
    return base


def _moment(conversation_id='c2', *, start_minutes=11.0, end_minutes=12.0, source='omi', calendar=None):
    return policy.MomentFacts(
        conversation_id=conversation_id,
        source=source,
        started_at=T0 + timedelta(minutes=start_minutes),
        ended_at=T0 + timedelta(minutes=end_minutes),
        calendar_identity=calendar,
    )


def test_boundary_rules():
    assert policy.boundary(None, _moment()).action == 'new'
    assert policy.boundary(_episode(status='closed'), _moment()).action == 'new'
    assert policy.boundary(_episode(), _moment('c1', start_minutes=10.5)).action == 'continue'
    # Under the live split itself: the same occasion.
    assert policy.boundary(_episode(), _moment(start_minutes=11)).action == 'continue'
    # The ambiguous middle asks Jev.
    ask = policy.boundary(_episode(), _moment(start_minutes=20))
    assert ask.action == 'ask' and ask.gap_seconds == 600
    # A device change always asks, even right after the last speech.
    changed = policy.boundary(_episode(), _moment(start_minutes=10.5, source='phone'))
    assert changed.action == 'ask' and changed.source_changed
    # Overlap is another device of the same stretch.
    parallel = policy.boundary(_episode(), _moment(start_minutes=9, source='desktop'))
    assert parallel.action == 'continue' and parallel.parallel
    assert policy.boundary(_episode(), _moment(start_minutes=41)).reason == 'gap'
    assert policy.boundary(_episode(calendar_identity='evt-a'), _moment(calendar='evt-b')).reason == 'calendar_boundary'
    assert policy.boundary(_episode(), _moment(start_minutes=170, end_minutes=181)).reason == 'hard_cap'
    full = _episode(moments=[{'id': str(i)} for i in range(config.MAX_MOMENTS)])
    assert policy.boundary(full, _moment()).reason == 'hard_cap'


def test_resolve_ask_with_and_without_jev():
    ask = policy.Boundary('ask', gap_seconds=600)
    assert policy.resolve_ask(ask, 0.9).action == 'continue'
    assert policy.resolve_ask(ask, 0.05).reason == 'moved_on'
    assert policy.resolve_ask(ask, None).action == 'continue'
    assert policy.resolve_ask(policy.Boundary('ask', gap_seconds=1000), None).reason == 'gap'
    device = policy.Boundary('ask', gap_seconds=60, source_changed=True)
    assert policy.resolve_ask(device, None).reason == 'source_change'
    assert policy.resolve_ask(device, 0.1).reason == 'source_change'
    assert policy.resolve_ask(device, 0.8).action == 'continue'


def test_idle_close_due():
    assert policy.idle_close_due(_episode(), T0 + timedelta(minutes=41)) is True
    assert policy.idle_close_due(_episode(), T0 + timedelta(minutes=20)) is False
    assert policy.idle_close_due(_episode(status='closed'), T0 + timedelta(days=1)) is False


def test_speaker_keys():
    keys = policy.speaker_keys([{'is_user': True}, {'person_id': 'p9'}, {'speaker_id': 2}, {'speaker_id': 2}])
    assert keys == frozenset({'owner', 'person:p9', 'speaker:2'})


def test_match_saved_tasks_is_one_to_one_and_threshold_bound():
    items = [
        {'id': 'p1', 'text': 'Book lunch table for 12:30'},
        {'id': 'p2', 'text': 'Send the design candidates to David'},
        {'id': 'p3', 'text': 'Water the plants'},
    ]
    saved = [
        {'id': 't1', 'description': 'Book a lunch table'},
        {'id': 't2', 'description': 'Send design candidates to David'},
        {'id': 't3', 'description': 'Renew passport'},
    ]
    assert policy.match_saved_tasks(items, saved) == {'p1': 't1', 'p2': 't2', 'p3': None}
    assert policy.match_saved_tasks(items[:1], []) == {'p1': None}
