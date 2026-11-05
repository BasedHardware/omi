"""Episode-join variant F: recorded-time uncertain joins settle with full-transcript Jev behind a flag."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import episodes as config
from database import episode_timeline
from database import episodes as episodes_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import omi_flags
from utils.episodes import f_join, incremental, metrics, service
from utils.episodes.service import Collaborators, MomentInput

UID = 'uid-f-join'
T0 = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
FIRST = (
    'okay lunch at the noodle place works for both of us today. the table is booked for two people at noon. '
    'we can walk over now and grab a coffee on the way back to the office after we are done eating'
)
SECOND = (
    'hi this is the dentist office calling about your cleaning appointment tomorrow morning. '
    'please call us back to confirm the time or we will need to give the slot to another patient soon'
)


class FakeModel:
    def __init__(self):
        self.calls = []

    def __call__(self, uid, messages):
        import json

        self.calls.append(messages)
        return SimpleNamespace(
            content=json.dumps({'title': 'T', 'bullets': ['x']}),
            usage_metadata={'input_tokens': 10, 'output_tokens': 5},
        )


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'true')
    for name in (
        config.EPISODES_ENABLED_ENV,
        config.EPISODES_PERCENT_ENV,
        config.EPISODE_F_JOIN_ENABLED_ENV,
        config.EPISODE_HARD_CAP_ACROSS_CONVERSATIONS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '100')
    # No flag-store rule: the env bucket decides (the store path has its own test).
    monkeypatch.setattr(omi_flags, 'resolve', lambda key, uid: None)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    monkeypatch.setattr(service.client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setattr(service, 'get_user_name', lambda *_a, **_kw: None)
    monkeypatch.setattr(service.incremental, 'get_user_name', lambda *_a, **_kw: None)
    monkeypatch.setattr(service.episode_language, 'language_preference', lambda uid: 'en')
    service.client_gate.reset_for_tests()
    service.reset_for_tests()


@pytest.fixture
def store(monkeypatch):
    store = StrictFirestore()
    # Policy/storage seam as in test_episode_live_integrity; query ordering runs on the emulator.
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda uid, *a, **kw: [
            dict(v, id=k[-1]) for k, v in store.rows.items() if len(k) == 4 and k[:3] == ('users', uid, 'episodes')
        ],
    )
    # The photo-join read path is not part of this unit; serve the stored row as get_conversation would.
    monkeypatch.setattr(
        service.conversations_db,
        'get_conversation',
        lambda uid, cid, **kw: store.rows.get(('users', uid, 'conversations', cid)),
    )
    return store


def _segments(text, *, start=0.0):
    return [
        {'text': w, 'start': start + i * 5.0, 'end': start + (i + 1) * 5.0, 'is_user': i % 2 == 0}
        for i, w in enumerate(text.split('. '))
    ]


def _c(store, *, minutes, ask=None, model=None):
    return Collaborators(
        invoke=model or FakeModel(),
        ask=ask or (lambda *a, **k: None),
        tz_name='UTC',
        firestore_client=store,
        saved_tasks=lambda uid, cid: [],
        people_names=lambda uid, ids: {},
        now=lambda: T0 + timedelta(minutes=minutes),
    )


def _moment(cid, *, minutes, text, source='omi'):
    return MomentInput(
        conversation_id=cid,
        source=source,
        segments=_segments(text),
        started_at=T0 + timedelta(minutes=minutes),
        ended_at=T0 + timedelta(minutes=minutes + 1),
        trigger='pause',
    )


def _store_row(store, cid, text, *, minutes):
    store.rows[('users', UID, 'conversations', cid)] = {
        'id': cid,
        'source': 'omi',
        'started_at': T0 + timedelta(minutes=minutes),
        'finished_at': T0 + timedelta(minutes=minutes + 1),
        'transcript_segments': _segments(text),
    }


def _attach(store, cid, *, minutes, source='omi'):
    return service.attach_conversation(
        UID, cid, source, started_at=T0 + timedelta(minutes=minutes), collaborators=_c(store, minutes=minutes)
    )


def _first_episode(store):
    _store_row(store, 'c1', FIRST, minutes=0)
    assert _attach(store, 'c1', minutes=0) == 'opened'
    assert service.record_moment(UID, _moment('c1', minutes=0, text=FIRST), _c(store, minutes=1)) == 'applied'
    return episodes_db.get_current_episode(UID, firestore_client=store)


def test_uncertain_recorded_join_is_marked_for_f_and_moved_on_splits_it_off(store):
    first = _first_episode(store)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    joined = episodes_db.get_current_episode(UID, firestore_client=store)
    assert joined['id'] == first['id'] and joined['conversation_ids'] == ['c1', 'c2']
    assert joined['pending_boundary']['c2']['variant'] == 'f'

    asked = []

    def ask(state, questions, **kwargs):
        asked.append((state, kwargs))
        return SimpleNamespace(noul=lambda name: 0.05)

    assert service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=ask)) == (
        'applied'
    )
    state, kwargs = asked[0]
    assert kwargs['lane'] == 'episode_boundary_f' and kwargs['max_attempts'] == 1
    assert state.startswith('EPISODE so far (full transcript of its last conversation):\nYou: okay lunch')
    assert '\n\nNEW speech (full transcript):\nYou: hi this is the dentist' in state
    assert 'minutes_since_last_speech' not in state and 'voices_changed' not in state
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'moved_on'
    assert closed['conversation_ids'] == ['c1']
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['id'] != first['id'] and current['conversation_ids'] == ['c2']


def test_same_occasion_keeps_the_join_and_clears_the_marker(store):
    first = _first_episode(store)
    _attach(store, 'c2', minutes=12)
    keep = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=keep))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']
    assert episode['pending_boundary'] == {}


@pytest.mark.parametrize('answer', [None, TimeoutError('slow'), 1.7])
def test_no_answer_error_or_timeout_falls_back_to_todays_join(store, answer):
    first = _first_episode(store)
    _attach(store, 'c2', minutes=25, source='phone')  # past the 15 min fallback gap and a device change

    def ask(*_a, **_k):
        if isinstance(answer, Exception):
            raise answer
        return None if answer is None else SimpleNamespace(noul=lambda name: answer)

    service.record_moment(UID, _moment('c2', minutes=25, text=SECOND, source='phone'), _c(store, minutes=26, ask=ask))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_short_gaps_keep_todays_rules_without_a_model_call(store):
    _first_episode(store)
    _attach(store, 'c2', minutes=2.5)  # under two minutes after c1's last speech at minute one
    assert episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary'] == {}


@pytest.mark.parametrize('env', [{'EPISODE_F_JOIN_PERCENT': '0'}, {'EPISODE_F_JOIN_ENABLED': 'off'}])
def test_outside_the_cohort_or_killed_nothing_is_marked(store, monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _first_episode(store)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    assert episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary'] == {}


def test_kill_switch_after_marking_settles_as_todays_join_without_calling_jev(store, monkeypatch):
    first = _first_episode(store)
    _attach(store, 'c2', minutes=12)
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')

    def ask(*_a, **_k):
        raise AssertionError('killed F must not call Jev')

    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=ask))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']
    assert episode['pending_boundary'] == {}


def test_cohort_is_a_stable_bucket_and_invalid_percent_admits_nobody(monkeypatch):
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '25')
    admitted = [f'u{i}' for i in range(2000) if f_join.admitted(f'u{i}')]
    assert 400 < len(admitted) < 600
    assert admitted == [f'u{i}' for i in range(2000) if f_join.admitted(f'u{i}')]
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, 'lots')
    assert not any(f_join.admitted(f'u{i}') for i in range(200))
    monkeypatch.delenv(config.EPISODE_F_JOIN_PERCENT_ENV)
    assert not f_join.admitted('u1')


def test_flag_store_rule_is_the_ramp_and_the_env_kill_switch_overrides_it(monkeypatch):
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=5.0)
    monkeypatch.setattr(omi_flags, 'resolve', lambda key, uid: omi_flags.evaluate(rule, uid))
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '100')
    share = sum(f_join.admitted(f'u{i}') for i in range(4000)) / 4000
    assert 0.03 < share < 0.07
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=False, rollout_percentage=100.0)
    assert not any(f_join.admitted(f'u{i}') for i in range(200))
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=100.0)
    assert f_join.admitted('u1')
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    assert not f_join.admitted('u1')

    def broken(key, uid):
        raise RuntimeError('store')

    monkeypatch.delenv(config.EPISODE_F_JOIN_ENABLED_ENV)
    monkeypatch.setattr(omi_flags, 'resolve', broken)
    assert not f_join.admitted('u1')


def test_f_state_caps_each_side_and_marks_empty_speech():
    state = incremental.f_boundary_state('a' * 13_000 + 'END', 'START' + 'b' * 9_000)
    previous, new = state.split('\n\nNEW speech (full transcript):\n')
    assert previous.endswith('END') and len(previous.split(':\n', 1)[1]) == config.F_JOIN_PREVIOUS_CHARS
    assert new.startswith('START') and len(new) == config.F_JOIN_NEW_CHARS
    assert incremental.f_boundary_state('', '').count('(no speech captured)') == 2
    rendered = incremental.render_f_transcript(
        [
            {'text': 'later', 'start': 9, 'is_user': False, 'speaker': 'SPEAKER_01'},
            {'text': 'hi', 'start': 0, 'is_user': True},
            {'text': 'there', 'start': 1, 'is_user': True},
            {'text': ' ', 'start': 2, 'is_user': False},
        ]
    )
    assert rendered == 'You: hi there\nSPEAKER_01: later'


def test_closed_episode_size_is_recorded_by_arm(store):
    before = metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get()
    _first_episode(store)
    _attach(store, 'c2', minutes=12)
    move = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.0)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=move))
    assert metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get() == before + 1
