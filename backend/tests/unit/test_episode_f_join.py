"""Episode-join variant F: recorded-time uncertain joins settle with full-transcript Jev behind a flag."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import episodes as config
from database import episode_timeline
from database import episodes as episodes_db
from database.episodes import EpisodeConflict
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import omi_flags
from utils.conversations.recorded_time import conversation_span
from utils.episodes import f_join, incremental, metrics, policy, service
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
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: omi_flags.EMPTY)
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
        'status': 'in_progress',
        'discarded': False,
        'is_locked': False,
        'data_protection_level': 'standard',
        'visibility': 'private',
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
    _store_row(store, 'c2', SECOND, minutes=12)
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
    _store_row(store, 'c2', SECOND, minutes=12)
    _attach(store, 'c2', minutes=12)
    move = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.0)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=move))
    assert metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get() == before + 1


def test_a_typo_in_the_kill_switch_turns_f_off(monkeypatch):
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'disabled')
    assert not config.f_join_enabled()
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'true')
    assert config.f_join_enabled()
    monkeypatch.delenv(config.EPISODE_F_JOIN_ENABLED_ENV)
    assert config.f_join_enabled()


def test_a_moment_too_short_to_commit_never_calls_jev_or_splits(store):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)

    def ask(*_a, **_k):
        raise AssertionError('a short moment must not ask Jev')

    short = 'yes sure'
    assert service.record_moment(UID, _moment('c2', minutes=12, text=short), _c(store, minutes=13, ask=ask)) == (
        'skipped_short'
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c2']
    assert episode['pending_boundary']['c2']['variant'] == 'f'


def test_the_predecessor_is_the_one_recorded_at_the_join_not_a_later_member(store):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)
    marker = episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary']['c2']
    assert marker['previous'] == 'c1'
    # A later member attaching before c2's first moment must not become c2's predecessor.
    episode = {'conversation_ids': ['c1', 'c2', 'c3'], 'member_activity': {'c1': T0, 'c3': T0 + timedelta(minutes=14)}}
    _store_row(store, 'c3', SECOND, minutes=14)
    rendered = f_join.previous_transcript(UID, episode, 'c2', marker, _c(store, minutes=13))
    assert 'okay lunch' in rendered and 'dentist' not in rendered


def test_the_arm_is_the_one_live_when_the_episode_opened(store, monkeypatch):
    _first_episode(store)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['f_join_arm'] == 'f'
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    before = metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get()
    f_join.record_closed_size({**episode, 'closed_at': T0 + timedelta(minutes=5), 'conversation_ids': ['c1']})
    assert metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get() == before + 1
    f_join.record_closed_size({'conversation_ids': ['c1']})


def test_a_later_member_keeps_the_candidate_without_a_question_so_no_overlapping_split(store):
    first = _first_episode(store)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    assert _attach(store, 'c3', minutes=14) == 'joined'
    asked = []
    service.record_moment(
        UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=15, ask=lambda *a, **k: asked.append(a))
    )
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2', 'c3']
    assert 'c2' not in episode['pending_boundary']


def test_a_member_that_attaches_while_jev_answers_keeps_the_join(store):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    attached = []

    def ask(*_a, **_k):
        # c3 attaches after the candidate's own check but before the model answers: the split must not go.
        attached.append(_attach(store, 'c3', minutes=14))
        return SimpleNamespace(noul=lambda name: 0.05)

    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=15, ask=ask))
    assert attached == ['joined']
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2', 'c3']
    assert 'c2' not in episode['pending_boundary']


def test_a_member_attaching_between_the_split_plan_and_its_close_is_kept_not_erased(store, monkeypatch):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    real_close = service.episodes_db.close_episode
    raced = []

    def racing_close(*args, **kwargs):
        if not raced:
            raced.append(True)
            # c3 attaches after the split was planned from c1 and c2, before the close transaction runs.
            assert _attach(store, 'c3', minutes=14) == 'joined'
        return real_close(*args, **kwargs)

    monkeypatch.setattr(service.episodes_db, 'close_episode', racing_close)
    ask = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=ask))
    assert raced == [True]
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2', 'c3']
    assert 'c2' not in episode['pending_boundary']
    assert episodes_db.get_episode(UID, first['id'], firestore_client=store)['status'] == 'live'


@pytest.mark.parametrize('error', [EpisodeConflict('lost the compare-and-swap'), RuntimeError('storage down')])
def test_a_failed_f_marker_records_the_shared_fallback_and_keeps_todays_join(monkeypatch, error):
    fallbacks = []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    def fail(*_a, **_k):
        raise error

    monkeypatch.setattr(f_join.episodes_db, 'commit_moment', fail)
    live = {'id': 'e1', 'status': 'live', 'state_version': 1, 'conversation_ids': ['c1']}
    decision = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    f_join.mark_pending(UID, live, live, 'c2', decision, {}, firestore_client=None)
    assert [item['component'] for item in fallbacks] == ['episode_f_join']


def _sync_attach(store, cid, text, *, minutes, ask=None):
    _store_row(store, cid, text, minutes=minutes)
    row = store.rows[('users', UID, 'conversations', cid)]
    return service.attach_synced_intake(UID, cid, row, collaborators=_c(store, minutes=minutes + 1, ask=ask))


def test_a_synced_join_the_model_calls_moved_on_opens_its_own_occasion(store):
    first = _first_episode(store)
    asked = []

    def ask(state, questions, **kwargs):
        asked.append(state)
        return SimpleNamespace(noul=lambda name: 0.05)

    _sync_attach(store, 'c2', SECOND, minutes=12, ask=ask)
    assert asked and '\n\nNEW speech (full transcript):\nYou: hi this is the dentist' in asked[0]
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'moved_on'
    assert closed['conversation_ids'] == ['c1']
    # A sync conversation with no live owner forms its own closed occasion, as it does without F.
    own = episodes_db.get_episode_for_conversation(UID, 'c2', firestore_client=store)
    assert own['id'] != first['id'] and own['conversation_ids'] == ['c2']
    assert own['status'] == 'closed'


def test_a_synced_join_the_model_calls_same_occasion_stays_one_episode(store):
    first = _first_episode(store)
    keep = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=keep)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize('answer,opens_own', [(0.05, True), (0.9, False)], ids=['moved_on', 'same_occasion'])
def test_a_sync_attach_retried_after_lost_cas_asks_jev_once(store, monkeypatch, answer, opens_own):
    # sync_attach re-runs the whole attach after a lost CAS; each run used to ask Jev again (up to three times).
    # Every attempt also keeps the first answer's placement: a moved-on candidate opens its own occasion each time.
    _first_episode(store)
    real_attach_recorded = service.attach_recorded
    attempts = []

    def lose_two_cas(uid, conversation_id, row, started, finished, c, **kwargs):
        attempts.append(kwargs.get('new_occasion', False))
        if len(attempts) <= 2:
            raise EpisodeConflict('lost cas')
        return real_attach_recorded(uid, conversation_id, row, started, finished, c, **kwargs)

    monkeypatch.setattr(service, 'attach_recorded', lose_two_cas)
    asked = []

    def ask(state, questions, **kwargs):
        asked.append(state)
        return SimpleNamespace(noul=lambda name: answer)

    _sync_attach(store, 'c2', SECOND, minutes=12, ask=ask)
    assert attempts == [opens_own] * 3, 'the lost CAS must be retried twice, each with the first answer'
    assert len(asked) == 1, 'a retry must reuse the first answer, never ask Jev again'


def test_a_synced_candidate_locked_after_intake_never_reaches_jev(store):
    # The intake snapshot was taken before the conversation was locked; the worker must ask the stored document.
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    snapshot = dict(row)
    row['is_locked'] = True
    span = conversation_span(snapshot)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', snapshot, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked == [], 'a conversation locked after intake must never be sent to Jev'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_an_unexpected_failure_closing_the_owner_keeps_todays_join(store, monkeypatch):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)

    def close_fails(*args, **kwargs):
        raise RuntimeError('close failed')

    monkeypatch.setattr(service, '_close', close_fails)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked, 'F decided moved-on, so the close is the step that failed'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize('case', ['killed', 'outside_cohort', 'short_speech', 'short_gap', 'member_later'])
def test_a_synced_join_that_f_does_not_decide_keeps_todays_join_without_a_question(store, monkeypatch, case):
    first = _first_episode(store)
    text, minutes = SECOND, 12
    if case == 'killed':
        monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    elif case == 'outside_cohort':
        monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '0')
    elif case == 'short_speech':
        text = 'please call us back to confirm'
    elif case == 'short_gap':
        minutes = 2.5
    elif case == 'member_later':
        _attach(store, 'c3', minutes=12.5)
    asked = []
    _sync_attach(
        store,
        'c2',
        text,
        minutes=minutes,
        ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda name: 0.05),
    )
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and 'c2' in episode['conversation_ids']


def test_a_failing_synced_f_decision_keeps_todays_join_and_reports_the_fallback(store, monkeypatch):
    first = _first_episode(store)
    fallbacks = []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    def boom(*_a, **_k):
        raise RuntimeError('storage down')

    monkeypatch.setattr(f_join, 'settle', boom)
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']
    assert [item['component'] for item in fallbacks] == ['episode_f_join']


def test_a_split_refused_by_the_member_guard_keeps_the_join(store, monkeypatch):
    first = _first_episode(store)

    def refuse(*_a, **_k):
        raise EpisodeConflict('split_member_recorded_later')

    monkeypatch.setattr(service, '_close', refuse)
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_a_conversation_already_placed_is_never_asked_about_again(store, monkeypatch):
    first = _first_episode(store)
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9))
    assert episodes_db.get_episode_for_conversation(UID, 'c2', firestore_client=store)['id'] == first['id']
    ambiguous = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    monkeypatch.setattr(f_join, 'uncertain', lambda *a, **k: ambiguous)
    monkeypatch.setattr(f_join, 'settle', lambda *a, **k: pytest.fail('a placed conversation was asked about again'))
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)
    service._attach_recorded_synced(UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


EXCLUDED_CLASSES = [
    ('locked', {'is_locked': True}),
    ('discarded', {'discarded': True}),
    ('deleted', {'deleted': True}),
    ('deferred', {'deferred': True}),
    ('processing_deferred', {'processing_deferred': True}),
    ('local_pending', {'processing_state': 'local_pending'}),
    ('client_processing', {'client_processing': True}),
    ('local_only', {'summary_blocked_reason': 'local_only'}),
    ('held', {f_join.HOLD_FIELD: {'held': True}}),
    ('another_owner', {'owner_uid': 'someone-else'}),
    ('failed_status', {'status': 'failed'}),
    ('unknown_protection', {'data_protection_level': 'none'}),
]


@pytest.mark.parametrize('name, change', EXCLUDED_CLASSES, ids=[n for n, _ in EXCLUDED_CLASSES])
def test_a_synced_candidate_that_may_not_feed_the_llm_is_never_sent_to_jev(store, name, change):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    row.update(change)
    span = conversation_span(row)
    asked = []
    c = _c(store, minutes=13, ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05))
    try:
        service._attach_recorded_synced(UID, 'c2', row, span.recorded_start, span.recorded_end, c)
    except EpisodeConflict as error:
        # Placement itself refuses a hidden conversation, after F has already declined to ask.
        assert str(error) == 'conversation_hidden' and name in {'discarded', 'deleted'}
        assert asked == []
        return
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and 'c2' in episode['conversation_ids']


@pytest.mark.parametrize('name, change', EXCLUDED_CLASSES, ids=[n for n, _ in EXCLUDED_CLASSES])
def test_settle_reads_the_candidate_and_never_asks_about_an_excluded_one(store, name, change):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    store.rows[('users', UID, 'conversations', 'c2')].update(change)
    asked = []
    c = _c(store, minutes=13, ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05))
    pending = {'gap_seconds': 720.0, 'source_changed': False, 'previous': 'c1'}
    decision = f_join.settle(UID, first, 'c2', pending, [], c, started_at=T0 + timedelta(minutes=12))
    assert decision.action == policy.CONTINUE and asked == []


def test_settle_without_the_candidate_document_fails_closed_and_never_asks(store):
    first = _first_episode(store)
    asked = []
    c = _c(store, minutes=13, ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05))
    pending = {'gap_seconds': 720.0, 'source_changed': False, 'previous': 'c1'}
    decision = f_join.settle(UID, first, 'c2', pending, [], c, started_at=T0 + timedelta(minutes=12))
    assert decision.action == policy.CONTINUE and asked == []


def test_candidate_head_keeps_the_spec_head_and_names_only_its_first_voices():
    segments = [
        {'text': 'x' * 5000, 'start': 0.0, 'person_id': 'a'},
        {'text': 'y' * 5000, 'start': 10.0, 'person_id': 'b'},
        {'text': 'z', 'start': 20.0, 'person_id': 'c'},
    ]
    head = f_join.candidate_head(segments)
    assert [len(s['text']) for s in head] == [5000, config.F_JOIN_NEW_CHARS - 5001]
    voices = [{'text': 'hi', 'start': float(i), 'person_id': f'p{i}'} for i in range(20)]
    named = f_join.candidate_head(voices)
    assert sum(1 for s in named if s.get('person_id')) == config.F_JOIN_PEOPLE_READ_LIMIT
    assert [s.get('person_id') for s in named[: config.F_JOIN_PEOPLE_READ_LIMIT]] == [
        f'p{i}' for i in range(config.F_JOIN_PEOPLE_READ_LIMIT)
    ]


def test_a_long_synced_candidate_names_at_most_the_people_read_limit(store):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    row['transcript_segments'] = [
        {'text': 'word ' * 60, 'start': 720.0 + i * 60.0, 'end': 750.0 + i * 60.0, 'person_id': f'p{i}'}
        for i in range(40)
    ]
    span = conversation_span(row)
    lookups, asked = [], []
    c = _c(store, minutes=13, ask=lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.9))
    c.people_names = lambda uid, ids: lookups.append(list(ids)) or {}
    service._attach_recorded_synced(UID, 'c2', row, span.recorded_start, span.recorded_end, c)
    assert asked, 'the candidate must reach Jev for the cap to matter'
    assert lookups and all(len(ids) <= config.F_JOIN_PEOPLE_READ_LIMIT for ids in lookups)
    assert sorted(lookups[-1]) == sorted(f'p{i}' for i in range(config.F_JOIN_PEOPLE_READ_LIMIT))
    new_speech = asked[0].split('NEW speech (full transcript):\n', 1)[1]
    assert len(new_speech) <= config.F_JOIN_NEW_CHARS
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and 'c2' in episode['conversation_ids']
